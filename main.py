import asyncio
import logging
import queue
import sys
import threading
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Response, status, UploadFile, WebSocket
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.websockets import WebSocketDisconnect

import db
import declare
import utils
from judge import JudgeManager

"""
Init
"""
abort = threading.Event()
judge
loop = threading.Thread(target=asyncio.run, args=(judge_loop(abort=abort),))
logger: logging.Logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    loop.start()
    global logger
    logger = logging.getLogger("uvicorn.error")
    yield
    abort.set()
    loop.join()


"""
API
"""

api = FastAPI(lifespan=lifespan)

"""
Static files
"""
api.mount("/file", StaticFiles(directory="data/file"), name="file")

"""
Problem
"""


# GET
@api.get("/api/problems", tags=["problem"])
async def problems():
    return await db.get_problem_ids()


@api.get("/api/problems/{id}", tags=["problem"])
async def problem(id: str, response: Response):
    if id in await db.get_problem_ids():
        return await db.get_problem(id)
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "Not found D:"


@api.get("/api/problems/{id}/docs", tags=["problem"])
async def problem_docs(id: str, response: Response):
    docs = await db.get_problem_docs(id)
    if docs is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "Not found D:"
    return RedirectResponse(url=f"/file/{docs}")


# POST
@api.post("/api/problems", tags=["problem"])
async def add_problem(problem: declare.Problems, response: Response):
    if problem.id not in await db.get_problem_ids():
        await db.add_problem(problem)
        return "Added!"
    else:
        response.status_code = status.HTTP_409_CONFLICT
        return f"Problem with id {problem.id} already exists D:"


@api.post("/api/problems/{id}/docs", tags=["problem"])
async def add_problem_docs(id: str, file: UploadFile, response: Response):
    if id not in await db.get_problem_ids():
        response.status_code = status.HTTP_404_NOT_FOUND
        return f"Can find problem with id {id} D:"
    try:
        await db.add_problem_docs(id, file)
        return "Added!"
    except ValueError:
        response.status_code = status.HTTP_409_CONFLICT
        return f"Problem docs with id {id} already exists. Use PUT instead :D"


@api.post("/api/problems/{id}/testcases", tags=["problem"])
async def add_problem_testcases(id: str, file: UploadFile, response: Response):
    if id not in await db.get_problem_ids():
        response.status_code = status.HTTP_404_NOT_FOUND
        return f"Can find problem with id {id} D:"
    try:
        await db.add_problem_testcases(id, file)
        return "Added!"
    except ValueError as e:
        response.status_code = status.HTTP_409_CONFLICT
        return str(e)


# PUT


@utils.partial_model
class Problem(declare.Problems):
    pass


@api.put("/api/problems/{id}", tags=["problem"])
async def problem_update(id: str, problem: Problem, response: Response):
    if id in await db.get_problem_ids():
        await db.update_problem(id, problem)
        return "Updated!"
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return f"Can find problem with id {id} D:"


@api.put("/api/problems/{id}/docs", tags=["problem"])
async def problem_docs_update(id: str, file: UploadFile, response: Response):
    if id not in await db.get_problem_ids():
        response.status_code = status.HTTP_404_NOT_FOUND
        return f"Can find problem with id {id} D:"
    try:
        await db.update_problem_docs(id, file)
        return "Updated!"
    except ValueError:
        response.status_code = status.HTTP_404_NOT_FOUND
        return f"Problem docs with id {id} is not exists D:"


@api.put("/api/problems/{id}/testcases", tags=["problem"])
async def problem_testcases_update(id: str, file: UploadFile, response: Response):
    if id not in await db.get_problem_ids():
        response.status_code = status.HTTP_404_NOT_FOUND
        return f"Can find problem with id {id} D:"
    try:
        await db.update_problem_testcases(id, file)
        return "Updated!"
    except ValueError as e:
        response.status_code = status.HTTP_409_CONFLICT
        return str(e)


# DELETE
@api.delete("/api/problems/{id}", tags=["problem"])
async def problem_delete(id: str, response: Response):
    if id in await db.get_problem_ids():
        await db.delete_problem(id)
        return "Deleted!"
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return f"Can find problem with id {id} D:"


"""
Submission
"""


# GET
@api.get("/api/submissions", tags=["submission"])
async def submissions():
    return await db.get_submission_ids()


@api.get("/api/submissions/{id}", tags=["submission"])
async def submission(id: str, response: Response):
    if id in await db.get_submission_ids():
        return await db.get_submission(id)
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "Not found D:"


# POST
@api.post("/api/submissions", tags=["submission"])
async def add_submission(submission: declare.Submissions):
    await db.add_submission(submission)
    return "Added!"


# WS
@api.websocket("/api/jugde/{id}")
async def submission_judge_ws(id: str, ws: WebSocket):
    submission = await db.get_submission(id)
    if submission is None:
        await ws.close(status.WS_1003_UNSUPPORTED_DATA, "submission not found D:")
    problem = await db.get_problem(submission["problem"])
    if problem is None:
        await ws.close(status.WS_1003_UNSUPPORTED_DATA, "problem not found D:")

    try:
        await ws.accept()
        msg_queue = queue.Queue(10)
        judge(submission_id=submission["id"], msg_queue=msg_queue)
        while True:
            if abort.is_set():
                break
            if not loop.is_alive():
                raise Exception("judge loop is aborted")
            if not msg_queue.empty():
                msg = msg_queue.get()
                if msg == "close":
                    await ws.close()
                    break
                await ws.send_json(msg)
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f'judge session {submission.id} raise{e}')
        await ws.close(status.WS_1011_INTERNAL_ERROR, e)


if __name__ == '__main__':
    try:
        uvicorn.run(
            app=api,
            host='0.0.0.0',
            port=8000,
            log_level='info',
        )
    except KeyboardInterrupt:
        abort.set()
        loop.join()
        sys.exit(0)
