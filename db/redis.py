import json
import typing
import logging

import asyncio
import redis.asyncio as redis

from . import exception


class RedisQueue:
    client: redis.Redis
    name: str
    closed: bool = False
    events: dict[
        typing.Literal['get', 'put', 'close', 'get_all'],
        # list[tuple[typing.Callable, asyncio.AbstractEventLoop]]
        dict[str, typing.Callable]
    ] = {
        # 'get': [],
        # 'get_all': [],
        'put': {},
        'close': {},
    }
    logger: logging.Logger

    def __init__(self, client: redis.Redis, name: str, from_cache: bool = False):
        self.client = client
        self.name = name
        if from_cache:
            self.closed = True

        # self.logger = logging.getLogger(f"justyse.rq.{name}")
        # self.logger.addHandler(utils.console_handler(f"RQ:{name}"))

    def on(self, event: typing.Literal['get', 'put']):
        def warper(func: typing.Callable):
            id_ = id(func)
            if not self.closed:
                self.events[event][id_] = func
            return id_

        return warper

    def off(self, key: str):
        for event in self.events.keys():
            if key in self.events[event]:
                self.events[event].pop(key)
                break

    def off_(self, event: typing.Literal['put', 'close']):
        self.events[event].clear()

    def offs(self):
        for key in self.events.keys():
            self.off_(key)

    async def emit(self, event: typing.Literal['put', 'close'], *args, **kwargs):
        if self.closed:
            return

        for func in self.events[event].values():
            if asyncio.iscoroutinefunction(func):
                await func(*args, **kwargs)
            else:
                func(*args, **kwargs)

    async def put(self, item: typing.Any, non_event: bool = False, json_decode: bool = True):
        if json_decode:
            try:
                item = json.dumps(item)
            except (TypeError, json.JSONDecodeError):
                pass

        await self.client.rpush(self.name, item)
        if not non_event:
            await self.emit('put', item)

    async def get(self):
        item = await self.client.lrange(self.name, -1, -1)
        try:
            item = json.loads(item)
        except (TypeError, json.JSONDecodeError):
            pass
        return item

    async def get_all(self):
        items = await self.client.lrange(self.name, 0, -1)
        try:
            items = [json.loads(item) for item in items]
        except (TypeError, json.JSONDecodeError):
            pass
        return items

    async def write_log(self, submission_id: str):
        import db

        return await asyncio.to_thread(db.dump_logs, submission_id, self.name, await self.get_all())

    async def close(self, non_event: bool = False):
        if not non_event:
            await self.emit('close')
        self.closed = True
        self.offs()

    async def empty(self):
        return await self.client.llen(self.name) == 0


class QueueManager:
    client: redis.Redis = None
    queues: dict[str, RedisQueue] = {}

    def __init__(self, client: redis.Redis = None):
        if client is not None:
            self.connect(client)

    def connect(self, client: redis.Redis):
        self.client = client

    def create(self, name: str):
        if self.check(name):
            raise exception.QueueAlreadyExist(name)
        queue = RedisQueue(self.client, name)
        self.queues[name] = queue
        return queue

    def add(self, queue: RedisQueue, skip_check: bool = False):
        if not isinstance(queue, RedisQueue):
            raise exception.QueueNotValid(type(queue))
        if skip_check is False and self.check(queue.name):
            raise exception.QueueAlreadyExist(queue.name)
        self.queues[queue.name] = queue

    def check(self, name: str):
        if self.client is None:
            raise exception.NotConnected()

        return name in self.queues and not self.queues[name].closed

    def get(self, name: str) -> RedisQueue:
        if not self.check(name):
            raise exception.QueueNotFound(name)
        return self.queues[name]

    async def check_cache(self, name: str):
        if self.client is None:
            raise exception.NotConnected()
        return await self.client.llen(name) > 0

    async def get_cache(self, name: str):
        if self.client is None:
            raise exception.NotConnected()

        if not await self.check_cache(name):
            raise exception.QueueNotFound(name)

        return RedisQueue(self.client, name, True)

    async def close(self, name: str):
        if self.client is None:
            raise exception.NotConnected()

        queue = self.get(name)
        await queue.close()

    async def stop(self):
        for queue in self.queues.values():
            await queue.close()
        await self.client.close()
        self.client = None
        self.queues.clear()
