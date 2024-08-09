import contextlib

import uvicorn
from fastapi import FastAPI, APIRouter
from fastapi.staticfiles import StaticFiles

import db
import declare
from router import (
    submission_router,
    problem_router,
    declare_router,
    judge_router,
    server_router,
    jugde_start,
    judge_stop,
    user_router,
)

"""
Lifespan
"""


@contextlib.asynccontextmanager
async def lifespan(*args):
    await jugde_start(*args)
    yield
    await judge_stop(*args)


"""
Router
"""
api_router = APIRouter(prefix="/api", tags=["api"])
api_router.include_router(submission_router)
api_router.include_router(problem_router)
api_router.include_router(declare_router)
api_router.include_router(judge_router)
api_router.include_router(server_router)
api_router.include_router(user_router)

api = FastAPI(lifespan=lifespan)
api.include_router(api_router)

"""
Static files
"""
api.mount("/file", StaticFiles(directory=db.declare.file_dir), name="file")
api.mount("/declare", StaticFiles(directory=declare.utils.data), name="declare")

if __name__ == '__main__':
    uvicorn.run(
        app=api,
        host='0.0.0.0',
        port=8000,
        log_level='info',
    )
