import uvicorn
from fastapi import FastAPI, APIRouter
from fastapi.staticfiles import StaticFiles

import db
import declare
from router.submission import submission_router
from router.problem import problem_router
from router.declare import declare_router
from router.judge import judge_router, start, stop
from contextlib import asynccontextmanager


"""
Lifespan
"""


@asynccontextmanager
async def lifespan(*args):
    await start(*args)
    yield
    await stop(*args)


"""
Router
"""
api_router = APIRouter(prefix="/api", tags=["api"])
api_router.include_router(submission_router)
api_router.include_router(problem_router)
api_router.include_router(declare_router)
api_router.include_router(judge_router)

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
