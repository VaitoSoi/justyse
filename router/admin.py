import fnmatch
import logging
import click
import asyncio

import fastapi

import db
import utils

admin_router = fastapi.APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[fastapi.Depends(utils.security.has_permission("@admin"))]
)
# logger: logging.Logger = None
logger = logging.getLogger("justyse.router.admin")
logger.propagate = False
logger.addHandler(utils.console_handler("Admin router"))
queue: db.redis.RedisQueue = None
injected: list[str] = []


class InjectHandler(logging.Handler):
    loop: asyncio.AbstractEventLoop

    def __init__(self, *args, **kwargs):
        self.loop = kwargs.get("loop", asyncio.get_running_loop())
        super().__init__()

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        msg = click.unstyle(msg)
        asyncio.run_coroutine_threadsafe(queue.put(msg, True, False), self.loop)
        # print("putted", msg)


def start(*args):
    if db.queue_manager:
        global queue
        queue = db.queue_manager.create("admin")


def inject():
    if queue is None:
        return

    non_injected = [
        name
        for name in list(logging.root.manager.loggerDict.keys())
        if name not in injected and (
                name in utils.config.capture_logger or
                any(fnmatch.fnmatch(name, pattern) for pattern in utils.config.capture_logger)
        )
    ]

    for name in non_injected:
        logger_ = logging.getLogger(name)
        handler_ = InjectHandler(loop=asyncio.get_running_loop())
        if logger_.handlers:
            handler_.setFormatter(logger_.handlers[-1].formatter)
        logger_.addHandler(handler_)
        injected.append(name)
        logger.info(f"Injected logger {name}")


@admin_router.get("/log",
                  summary="Get log",
                  response_model=list[str | dict])
async def get_log():
    return await queue.get_all()


@admin_router.websocket("/log/ws")
async def get_log_ws(websocket: fastapi.WebSocket):
    await websocket.accept()
    if not queue:
        return await websocket.close(fastapi.status.WS_1011_INTERNAL_ERROR, "Redis not connected")

    for log in queue.get_all():
        await websocket.send_text(log)

    @queue.on("put")
    async def send_log():
        log = queue.get()
        await websocket.send_text(log)
