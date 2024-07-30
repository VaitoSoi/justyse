import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager

import fastapi
import redis
import uvicorn
from fastapi import FastAPI, Response, status, UploadFile, WebSocket
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

import db
import declare
import utils
from judge import JudgeManager

"""
Init
"""
judge = JudgeManager()
loop = threading.Thread(target=judge.loop, daemon=True)
heartbeat = threading.Thread(target=judge.heartbeat, daemon=True)
logger: logging.Logger
redis_client: redis.Redis
queue_manager: db.queue.QueueManager


@asynccontextmanager
async def lifespan(app: FastAPI):
    global logger, redis_client, queue_manager
    logger = logging.getLogger("uvicorn.error")

    logger.info("Starting services...")

    if utils.config.store_place.startswith("sql"):
        db.sql.create_all()
        logger.info("SQLModel Tables is created")

    redis_client = redis.Redis.from_url(utils.config.redis_server)
    queue_manager = db.queue.QueueManager(redis_client)
    logger.info("Redis is connected")

    judge.connect(utils.config.judge_server)

    loop.start()
    logger.info("Loop is started")

    heartbeat.start()
    logger.info("Heartbeat is started")

    logger.info("Services are started. Start serving...")
    yield
    logger.info("Killing services...")

    judge.loop_abort.set()
    loop.join()
    logger.info("Loop is stopped")

    heartbeat.join()
    logger.info("Heartbeat is stopped")

    judge.join_threads()
    logger.info("Threads are stopped")

    judge.stop_timers()
    logger.info("Timers are stopped")

    judge.stop_recv()
    logger.info("Recv is stopped")

    judge.disconnect()
    logger.info("Killed all services. Disconnecting....")


"""
API
"""

api = FastAPI(lifespan=lifespan)

"""
Static files
"""
api.mount("/file", StaticFiles(directory=db.declare.file_dir), name="file")
api.mount("/declare", StaticFiles(directory=declare.utils.data), name="declare")

"""
Declare
"""


# GET
@api.get("/api/declare", tags=["declare"])
def get_declare():
    return [file[:-5] for file in os.listdir(declare.utils.data)]


@api.get("/api/declare/{name}", tags=["declare"])
def get_declare_file(name: str, response: Response):
    try:
        return RedirectResponse(url=f"/declare/{name}.json")
    except FileNotFoundError:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "file not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'get declare {name} raise {error}')
        return error


"""
Problem
"""


# GET
@api.get("/api/problems", tags=["problem"])
def get_problems():
    return db.get_problem_ids()


@api.get("/api/problems/{id}", tags=["problem"])
def get_problem(id: str, response: Response):
    try:
        return db.get_problem(id)
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'get problem {id} raise {error}')
        return error


@api.get("/api/problems/{id}/docs", tags=["problem"])
def get_problem_docs(id: str, response: Response):
    try:
        docs = db.get_problem_docs(id)
        return RedirectResponse(url=f"/file/{docs}")
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except db.exception.ProblemDocsNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem docs not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'get problem docs {id} raise {error}')
        return error


# POST
@api.post("/api/problems", tags=["problem"])
def add_problem(problem: db.Problems, response: Response):
    try:
        db.add_problem(problem)
        return "Added!"
    except db.exception.ProblemAlreadyExisted:
        response.status_code = status.HTTP_409_CONFLICT
        return f"problem {problem.id} already exists"
    except db.exception.LanguageNotSupport as error:
        response.status_code = status.HTTP_501_NOT_IMPLEMENTED
        return f"language {error.args[0]} not support"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'add problem {id} raise {error}')
        return error


@api.post("/api/problems/{id}/docs", tags=["problem"])
def add_problem_docs(id: str, file: UploadFile, response: Response):
    try:
        db.add_problem_docs(id, file)
        return "added"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except db.exception.ProblemDocsAlreadyExist:
        response.status_code = status.HTTP_409_CONFLICT
        return "problem docs already exists"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'add problem docs {id} raise {error}')
        return error


@api.post("/api/problems/{id}/testcases", tags=["problem"])
def add_problem_testcases(id: str, file: UploadFile, response: Response):
    try:
        db.add_problem_testcases(id, file)
        return "added"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'add problem testcase {id} raise {error}')
        return error


# PATCH
@api.patch("/api/problems/{id}", tags=["problem"])
def problem_update(id: str, problem: db.UpdateProblems, response: Response):
    try:
        db.update_problem(id, problem)
        return "updated"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except db.exception.NothingToUpdate:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return "nothing to update"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'update problem {id} raise {error}')
        return error


@api.patch("/api/problems/{id}/docs", tags=["problem"])
def problem_docs_update(id: str, file: UploadFile, response: Response):
    try:
        db.update_problem_docs(id, file)
        return "updated"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except db.exception.ProblemDocsNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem docs not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'update problem docs {id} raise {error}')
        return error


@api.patch("/api/problems/{id}/testcases", tags=["problem"])
def problem_testcases_update(id: str, file: UploadFile, response: Response):
    try:
        db.update_problem_testcases(id, file)
        return "updated"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'update problem testcase {id} raise {error}')
        return error


# DELETE
@api.delete("/api/problems/{id}", tags=["problem"])
def problem_delete(id: str, response: Response):
    try:
        db.delete_problem(id)
        return "deleted"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'delete problem {id} raise {error}')
        return error


"""
Submission
"""


# GET
@api.get("/api/submissions", tags=["submission"])
def submissions():
    return db.get_submission_ids()


@api.get("/api/submissions/{id}", tags=["submission"])
def submission(id: str, response: Response):
    try:
        return db.get_submission(id)

    except db.exception.SubmissionNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'get problem {id} raise {error}')
        return error


# POST
@api.post("/api/submissions", tags=["submission"])
def add_submission(submission: db.Submissions, response: Response):
    try:
        db.add_submission(submission)
        return "Added!"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except db.exception.SubmissionAlreadyExist:
        response.status_code = status.HTTP_409_CONFLICT
        return "submission already exists"
    except db.exception.LanguageNotSupport as error:
        response.status_code = status.HTTP_501_NOT_IMPLEMENTED
        return f"language {error.args[0][0]}:{error.args[0][1]} not support"
    except db.exception.LanguageNotAccept as error:
        response.status_code = status.HTTP_406_NOT_ACCEPTABLE
        return f"language {error.args[0][0]}:{error.args[0][1]} not accept"
    except db.exception.CompilerNotSupport as error:
        response.status_code = status.HTTP_501_NOT_IMPLEMENTED
        return f"compiler {error.args[0][0]}:{error.args[0][1]} not support"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'create problem {submission.id} raise {error}')
        return error


"""
Judge
"""


# POST
@api.post("/api/judge/{id}", tags=["judge"])
def submission_judge(id: str, response: Response):
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

    judge.add_submission(submission.id, queue_manager.create(f"judge:{submission.id}"), threading.Event())
    return "added judge request"


# WS
@api.websocket("/api/judge/{id}")
async def submission_judge_ws(id: str, ws: WebSocket):
    await ws.accept()

    judge_abort = judge.judge_abort.get(id, None)
    if judge_abort is None:
        return await ws.close(status.WS_1013_TRY_AGAIN_LATER, "judge not started")

    if queue_manager.check(f"judge:{id}"):
        msg_queue = queue_manager.get(f"judge:{id}")
    else:
        return await ws.close(status.WS_1013_TRY_AGAIN_LATER, "judge not started")

    async def wait_for_abort():
        while True:
            try:
                msg = await ws.receive_text()
            except fastapi.WebSocketDisconnect:
                break
            if msg == 'abort':
                judge_abort.set()
                break
            await asyncio.sleep(1)

    @msg_queue.on('put')
    async def broadcast_msg(msg: str):
        if not loop.is_alive():
            return ws.send("judge loop is aborted")

        logger.info(msg)
        if msg[0] == 'error':
            return await ws.close(status.WS_1011_INTERNAL_ERROR, msg[1])
        elif msg[0] == 'abort':
            return await ws.close(status.WS_1000_NORMAL_CLOSURE, 'aborted')
        elif msg[0] == 'done':
            queue_manager.close(msg_queue.name)
            return await ws.close()
        else:
            msg = utils.padding(msg, 2)
            return await ws.send_json({
                "status": msg[0],
                "data": msg[1]
            })

    await asyncio.gather(wait_for_abort(), broadcast_msg())


if __name__ == '__main__':
    uvicorn.run(
        app=api,
        host='0.0.0.0',
        port=8000,
        log_level='info',
    )
