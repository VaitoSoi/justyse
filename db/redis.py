import json
import typing
import logging
import utils

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
        list[typing.Callable]
    ] = {
        # 'get': [],
        # 'get_all': [],
        'put': [],
        'close': [],
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
            if not self.closed:
                self.events[event].append(func)
            return func

        return warper

    def off(self, event: typing.Literal['put', 'close']):
        self.events[event].clear()

    def offs(self):
        for key in self.events.keys():
            self.off(key)

    async def emit(self, event: typing.Literal['put', 'close'], *args, **kwargs):
        if self.closed:
            return

        # self.logger.debug(f"emit {event}, {args}, {kwargs}")

        for func in self.events[event]:
            if asyncio.iscoroutinefunction(func):
                await func(*args, **kwargs)
            else:
                func(*args, **kwargs)

    async def put(self, item: typing.Any, non_event: bool = False):
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
