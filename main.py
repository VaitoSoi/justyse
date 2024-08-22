import contextlib
import logging

import fastapi
import uvicorn
import uvicorn.logging
from fastapi import FastAPI, APIRouter
import fastapi.logger
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import db
import declare
import utils
from router import (
    submission_router,
    problem_router,
    declare_router,
    judge_router,
    server_router,
    judge_start,
    judge_stop,
    user_router,
    # admin_router,
    admin_start,
    admin_inject,
)

"""
Lifespan
"""

# print("\n".join(list(logging.root.manager.loggerDict.keys())))
justyse_logger = logging.getLogger("justyse")
justyse_logger.propagate = False
justyse_logger.setLevel(logging.DEBUG)

uvicorn_logger = logging.getLogger("uvicorn")
uvicorn_logger.handlers.clear()
uvicorn_error_logger = logging.getLogger("uvicorn.error")
uvicorn_error_logger.handlers.clear()
uvicorn_error_logger.addHandler(utils.console_handler("Uvicorn"))
uvicorn_access_logger = logging.getLogger("uvicorn.access")
uvicorn_access_logger.handlers.clear()
uvicorn_access_logger.addHandler(utils.console_handler("Access", utils.AccessFormatter))

fastapi_logger = logging.getLogger("fastapi")
fastapi_logger.handlers.clear()
fastapi_logger.addHandler(utils.console_handler("FastAPI"))

threading_manager = utils.ThreadingManager()


@contextlib.asynccontextmanager
async def lifespan(*args):
    db.setup()
    db.setup_redis()
    if db.redis_client:
        db.redis_client.delete("admin") # noqa

    admin_start(*args)
    admin_inject()
    judge_start(threading_manager)

    yield

    judge_stop(*args)


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

app = FastAPI(
    lifespan=lifespan,
    title="Justyse API",
    summary="A program for code judging",
    version="beta",
    openapi_url="/api/openapi.json",
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    swagger_ui_parameters={
        "persistAuthorization": True,
    },
    responses={
        500: utils.InternalServerErrorResponse,
        401: {
            "description": "Unauthorized",
            "content": {
                "application/json": {
                    "examples": {
                        "Token not found": {
                            "summary": "Token not found",
                            "value": {
                                "message": "Token not found",
                                "code": "token_not_found"
                            }
                        },
                        "Token expired": {
                            "summary": "Token expired",
                            "value": {
                                "message": "Token expired",
                                "code": "token_expired"
                            }
                        },
                        "Token signature invalid": {
                            "summary": "Token signature invalid",
                            "value": {
                                "message": "Token signature invalid",
                                "code": "token_signature_invalid"
                            }
                        },
                    }
                }
            }
        },
        403: {
            "description": "Permission denied",
            "content": {
                "application/json": {
                    "example": {
                        "message": "Permission denied",
                        "code": "permission_denied",
                        "detail": {
                            "missing": "<permission>"
                        }
                    }
                }
            }
        },
    },
)
app.include_router(api_router)


@app.exception_handler(fastapi.HTTPException)
async def http_exception_handler(request: fastapi.Request, exc):
    return fastapi.responses.JSONResponse(
        status_code=exc.status_code,
        content=exc.detail,
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

"""
Static files
"""
app.mount("/file", StaticFiles(directory=db.declare.files_dir), name="file")
app.mount("/declare", StaticFiles(directory=declare.utils.data), name="declare")

if __name__ == '__main__':
    uvicorn.run(
        app=app,
        host='0.0.0.0',
        port=8000,
        log_level='info',
    )
