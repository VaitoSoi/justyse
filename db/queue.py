import json
import typing

import asyncio
import redis

from . import exception


class RedisQueue:
    client: redis.Redis
    name: str
    closed: bool = False
    events: dict[
        typing.Literal['get', 'put', 'close', 'get_all'],
        list[tuple[typing.Callable, asyncio.AbstractEventLoop]]
    ] = {
        'get': [],
        'put': [],
        'close': [],
        'get_all': []
    }
    # tasks: list[asyncio.Task] = []

    def __init__(self, client: redis.Redis, name: str):
        self.client = client
        self.name = name

    def __len__(self):
        return self.client.llen(self.name)

    def on(self, event: typing.Literal['get', 'put'], loop: asyncio.AbstractEventLoop = None):
        def warper(func: typing.Callable):
            if not self.closed:
                self.events[event].append((func, loop))
            return func

        return warper

    def off(self, event: typing.Literal['get', 'put', 'close', 'get_all']):
        self.events[event].clear()

    def offs(self):
        for key in self.events.keys():
            self.off(key)

    def emit(self, event: typing.Literal['get', 'put', 'close', 'get_all'], *args, **kwargs):
        if self.closed:
            return
        for func, loop in self.events[event]:
            if asyncio.iscoroutinefunction(func):
                if loop is None:
                    asyncio.run(func(*args, **kwargs))
                else:
                    asyncio.run_coroutine_threadsafe(func(*args, **kwargs), loop)
            else:
                func(*args, **kwargs)

    def put(self, item: typing.Any):
        try:
            item = json.dumps(item)
        except (TypeError, json.JSONDecodeError):
            pass

        self.client.rpush(self.name, item)
        self.emit('put', item)

    def get(self):
        item = self.client.lrange(self.name, -1, -1)
        try:
            item = json.loads(item)
        except (TypeError, json.JSONDecodeError):
            pass
        self.emit('get', item)
        return item

    def get_all(self):
        items = self.client.lrange(self.name, 0, -1)
        try:
            items = [json.loads(item) for item in items]
        except (TypeError, json.JSONDecodeError):
            pass
        self.emit('get_all', items)
        return items

    def close(self):
        self.emit('close')
        self.closed = True
        self.offs()

    def empty(self):
        return self.__len__() == 0


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

    def check(self, name: str, add: bool = False):
        if self.client is None:
            raise exception.NotConnected()

        if name not in self.queues and add is True and (self.client.llen(name)) > 0:
            self.add(RedisQueue(self.client, name), True)
            return True

        return name in self.queues and not self.queues[name].closed

    def get(self, name: str) -> RedisQueue:
        if not (self.check(name)):
            raise exception.QueueNotFound(name)
        return self.queues[name]

    def close(self, name: str):
        if self.client is None:
            raise exception.NotConnected()

        queue = self.get(name)
        queue.close()
