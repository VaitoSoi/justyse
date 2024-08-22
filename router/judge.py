import asyncio
import json
import logging
import threading

from fastapi import APIRouter, HTTPException, status, WebSocket, WebSocketDisconnect, Depends

import db
import judge
import utils


thread_manager: utils.ThreadingManager
judge_manger: judge.JudgeManager
loop: utils.Thread
heartbeat: utils.Thread
queue_manager: db.queue_manager
logger: logging.Logger = logging.getLogger("justyse.router.judge")
logger.propagate = False
logger.addHandler(utils.console_handler("Judge router"))


def start(thread_manager_: utils.ThreadingManager):
    global loop, heartbeat, queue_manager, thread_manager, judge_manger
    thread_manager = thread_manager_
    queue_manager = db.queue_manager

    logger.info("Starting judge services...")

    judge_manger = judge.JudgeManager(thread_manager)
    judge_manger.from_json()

    loop = thread_manager.create_thread("judge_manager.loop",
                                        judge_manger.loop,
                                        daemon=False,
                                        event=judge_manger.stop)
    logger.info("Loop is started")

    heartbeat = thread_manager.create_thread("judge_manager.heartbeat",
                                             judge_manger.heartbeat,
                                             daemon=False,
                                             event=judge_manger.stop)
    logger.info("Heartbeat is started")

    logger.info("Services are started.")


def stop(*args):
    logger.info("Killing services...")

    judge_manger.stop.set()

    thread_manager.close_thread("judge_manager.recv.*", True)
    logger.info("Recv is stopped")

    thread_manager.close_threads("judge_manager.ping.*", True)
    logger.info("Ping is stopped")

    thread_manager.close_thread("judge_manager.loop", True)
    logger.info("Loop is stopped")

    thread_manager.close_thread("judge_manager.heartbeat", True)
    logger.info("Heartbeat is stopped")

    thread_manager.close_timers("judge_manager.timers.*", True)
    logger.info("Timers are stopped")

    thread_manager.close_threads("judge_manager.judge:*", True)
    logger.info("Judge threads are stopped")

    if queue_manager:
        queue_manager.stop()

    logger.info("Services are killed. Shutting down...")


judge_router = APIRouter(prefix="/judge", tags=["judge"])

"""
Judge
"""


# POST
@judge_router.post("/{id}",
                   summary="Add submission to judge queue",
                   status_code=status.HTTP_201_CREATED,
                   dependencies=[Depends(utils.has_permission("submission:judge"))],
                   responses={
                       201: {
                           "description": "Submission added to judge queue",
                           "content": {
                               "application/json": {
                                   "example": {
                                       "id": "submission_id:judge_id"
                                   }
                               }
                           }
                       },
                       404: {
                           "description": "Submission not found",
                           "content": {
                               "application/json": {
                                   "examples": {
                                       "Submission not found": {
                                           "summary": "Submission not found",
                                           "value": {
                                               "message": "Submission not found"
                                           }
                                       },
                                       "Problem not found": {
                                           "summary": "Problem not found",
                                           "value": {
                                               "message": "Problem not found"
                                           }
                                       }
                                   }
                               }
                           }
                       },
                       503: {"description": "Redis not connected",
                             "content": {"application/json": {"example": {"message": "Redis not connected"}}}},
                       500: {
                           "description": "Internal server error",
                           "content": {
                               "application/json": {
                                   "examples": {
                                       "Out of judge id": {
                                           "sumary": "Out of judge id",
                                           "value": {
                                               "message": "Out of judge id"
                                           }
                                       },
                                       **utils.InternalServerErrorResponse_
                                   }
                               }
                           }
                       }
                   })
async def submission_judge(id: str):
    if queue_manager is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"message": "Redis not connected"})

    submission: db.DBSubmissions = None
    problem: db.DBProblems = None

    try:
        submission = db.get_submission(id)
    except db.exception.SubmissionNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "Submission not found"})
    except Exception as error:
        logger.error(f'get submission {id} raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)

    try:
        problem = db.get_problem(submission["problem"])
    except db.exception.ProblemNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "Problem not found"})
    except Exception as error:
        logger.error(f'get problem from submission {id} raise error')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)

    # judge_id = str(uuid.uuid4()).split('-')[0]
    check = 0
    judge_id = utils.rand_uuid(1)
    while queue_manager.check(f"judge::{submission.id}:{judge_id}"):
        judge_id = utils.rand_uuid(1)
        check += 1
        if check > 1000000:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"message": "Out of judge id"}
            )
    queue_id = f"{submission.id}:{judge_id}"

    judge_manger.add_submission(submission.id, queue_manager.create(f"judge::{queue_id}"), threading.Event())
    return queue_id


# WS
@judge_router.websocket("/{id}")
async def submission_judge_ws(id: str, ws: WebSocket):
    await ws.accept()

    if queue_manager is None:
        return await ws.close(status.WS_1011_INTERNAL_ERROR, "redis not connected")

    submission_id, judge_id = id.split(':')

    if not submission_id or not judge_id:
        return await ws.close(status.WS_1008_POLICY_VIOLATION, "invalid id")

    queue_id = f"judge::{submission_id}:{judge_id}"
    if queue_manager.check(queue_id):
        msg_queue = queue_manager.get(queue_id)
    elif queue_manager.check_cache(queue_id):
        msg_queue = queue_manager.get_cache(queue_id)
    else:
        return await ws.close(status.WS_1008_POLICY_VIOLATION, "can find judge queue")

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
        return await ws.close(status.WS_1008_POLICY_VIOLATION, "judge not started")

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


"""
Server
"""

server_router = APIRouter(prefix="/server", tags=["server"])


# GET
@server_router.get("s/",
                   summary="Get all servers",
                   response_model=list[dict[str, str]],
                   dependencies=[Depends(utils.has_permission("judge_server:view"))])
def judge_servers():
    return [{"id": connection._id, "name": connection.name, "status": connection.status()}
            for _, connection in judge_manger._connections.items()]


# POST
@server_router.post("/",
                    summary="Add server",
                    dependencies=[Depends(utils.has_permission("judge_server:add"))],
                    responses={
                        409: {"description": "Server already exists",
                              "content": {"application/json": {"example": "Server already exists"}}}
                    })
async def server_add(server: judge.data.Server):
    if server.id in judge_manger._connections:
        return "server already exists", status.HTTP_409_CONFLICT

    judge_manger.add_server(server)
    return "added"


@server_router.post("/{id}/pause",
                    summary="Pause server",
                    dependencies=[Depends(utils.has_permission("judge_server:edit"))],
                    responses={
                        404: {"description": "Server not found",
                              "content": {"application/json": {"example": "Server not found"}}}
                    })
async def server_pause(id: str):
    if id not in judge_manger._connections:
        return "server not found", status.HTTP_404_NOT_FOUND

    judge_manger.pause(id)
    return "paused"


@server_router.post("/{id}/resume",
                    summary="Resume server",
                    dependencies=[Depends(utils.has_permission("judge_server:edit"))],
                    responses={
                        404: {"description": "Server not found",
                              "content": {"application/json": {"example": "Server not found"}}}
                    })
async def server_resume(id: str):
    if id not in judge_manger._connections:
        return "server not found", status.HTTP_404_NOT_FOUND

    judge_manger.resume(id)
    return "resumed"


@server_router.post("/{id}/disconnect",
                    summary="Disconnect server",
                    dependencies=[Depends(utils.has_permission("judge_server:edit"))],
                    responses={
                        404: {"description": "Server not found",
                              "content": {"application/json": {"example": "Server not found"}}}
                    })
async def server_disconnect(id: str):
    if id not in judge_manger._connections:
        return "server not found", status.HTTP_404_NOT_FOUND

    judge_manger.disconnect(id)
    return "disconnected"


@server_router.post("/{id}/reconnect",
                    summary="Reconnect server",
                    dependencies=[Depends(utils.has_permission("judge_server:edit"))],
                    responses={
                        404: {"description": "Server not found",
                              "content": {"application/json": {"example": "Server not found"}}}
                    })
async def server_reconnect(id: str):
    if id not in judge_manger._connections:
        return "server not found", status.HTTP_404_NOT_FOUND

    judge_manger.reconnect(id)
    return "reconnected"


# DELETE
@server_router.delete("/{id}",
                      summary="Delete server",
                      dependencies=[Depends(utils.has_permission("judge_server:delete"))],
                      responses={
                          404: {"description": "Server not found",
                                "content": {"application/json": {"example": "Server not found"}}}
                      })
async def server_delete(id: str):
    if id not in judge_manger._connections:
        return "server not found", status.HTTP_404_NOT_FOUND

    judge_manger.remove_server(id)
    return "removed"
