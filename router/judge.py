import asyncio
import json
import logging
import threading

import redis
from fastapi import APIRouter, Response, status, WebSocket, WebSocketDisconnect

import db
import judge
import utils

# import uuid

logger = logging.getLogger("uvicorn.error")
judge_manger = judge.JudgeManager()
loop: threading.Thread = threading.Thread(target=judge_manger.loop)
heartbeat: threading.Thread = threading.Thread(target=judge_manger.heartbeat)
redis_client: redis.Redis = None
queue_manager: db.queue.QueueManager = None


async def start(*args):
    global loop, heartbeat, redis_client, queue_manager

    logger.info("Starting services...")

    if utils.config.store_place.startswith("sql:"):
        db.sql.create_all()
        logger.info("Created SQLModel Tables")

    redis_client = redis.Redis.from_url(utils.config.redis_server)
    try:
        redis_client.ping() # noqa
    except redis.exceptions.ConnectionError as error:
        logger.error(f"Failed to connect to Redis: {utils.config.redis_server}")
        raise error from error
    queue_manager = db.queue.QueueManager(redis_client)
    logger.info(f"Connected to Redis: {utils.config.redis_server}")

    judge_manger.connects(utils.config.judge_server)

    loop.start()
    logger.info("Loop is started")

    heartbeat.start()
    logger.info("Heartbeat is started")

    logger.info("Services are started.")


async def stop(*args):
    logger.info("Killing services...")

    judge_manger.stop.set()

    judge_manger.stop_recv()
    logger.info("Recv is stopped")

    loop.join()
    logger.info("Loop is stopped")

    heartbeat.join()
    logger.info("Heartbeat is stopped")

    judge_manger.join_thread()
    logger.info("Threads are stopped")

    redis_client.save() # noqa
    logger.info("Saved Redis data")

    redis_client.close()
    logger.info("Closed Redis connection")

    logger.info("Services are killed. Shutting down...")


judge_router = APIRouter(prefix="/judge", tags=["judge"])


# POST
@judge_router.post("/{id}")
async def submission_judge(id: str, response: Response):
    submission: db.DBSubmissions = None
    problem: db.DBProblems = None

    try:
        submission = db.get_submission(id)
    except db.exception.SubmissionNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "submission not found D:"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'judge {id} raise {error}')
        return error

    try:
        problem = db.get_problem(submission["problem"])
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found D:"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'judge {id} raise {error}')
        return error

    # judge_id = str(uuid.uuid4()).split('-')[0]
    judge_id = utils.rand_uuid(1)
    while queue_manager.check(f"judge::{submission.id}:{judge_id}"):
        judge_id = utils.rand_uuid(1)
    queue_id = f"{submission.id}:{judge_id}"

    judge_manger.add_submission(submission.id, queue_manager.create(f"judge::{queue_id}"), asyncio.Event())
    return queue_id


# WS
@judge_router.websocket("/{id}")
async def submission_judge_ws(id: str, ws: WebSocket):
    await ws.accept()

    submission_id, judge_id = id.split(':')

    if not submission_id or not judge_id:
        return await ws.close(status.WS_1013_TRY_AGAIN_LATER, "invalid id")

    if queue_manager.check(f"judge::{id}", True):
        msg_queue = queue_manager.get(f"judge::{id}")

    else:
        return await ws.close(status.WS_1013_TRY_AGAIN_LATER, "can find judge queue")

    for msg in msg_queue.get_all():
        msg = utils.padding(msg, 2)
        await ws.send_json({
            "status": msg[0],
            "data": msg[1] if len(msg) == 2 else None
        })

    if msg_queue.closed:
        return await ws.close(status.WS_1000_NORMAL_CLOSURE, "eof cache")

    judge_abort = judge_manger._judge_abort.get(submission_id, None)
    if judge_abort is None:
        return await ws.close(status.WS_1013_TRY_AGAIN_LATER, "judge not started")

    async def wait_for_abort():
        while True:
            try:
                msg = await ws.receive_text()
                if msg == 'abort':
                    judge_abort.set()
                    break
                await asyncio.sleep(1)

            except (WebSocketDisconnect, asyncio.CancelledError):
                break

    abort_task = asyncio.create_task(wait_for_abort())

    @msg_queue.on('put', asyncio.get_running_loop())
    async def broadcast_msg(msg: str):
        if not loop.is_alive():
            return await ws.close(status.WS_1011_INTERNAL_ERROR, "judge loop is aborted")

        msg = json.loads(msg)
        if msg[0] == 'error':
            return await ws.close(status.WS_1011_INTERNAL_ERROR, msg[1])

        elif msg[0] == 'abort':
            return await ws.close(status.WS_1000_NORMAL_CLOSURE, 'aborted')

        elif msg[0] == 'done':
            msg_queue.close()

            abort_task.cancel()
            return await ws.close(status.WS_1000_NORMAL_CLOSURE, 'done')

        else:
            return await ws.send_json({
                "status": msg[0],
                "data": msg[1] if len(msg) == 2 else None
            })

    await abort_task

    # @msg_queue.on('close')
    # async def close_ws():
    #     await ws.close(1000, "judge closed")
