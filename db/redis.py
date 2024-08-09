import json
import typing

import asyncio
import redis

from . import exception


class JudgeMessages:
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

    def __init__(self, client: redis.Redis, name: str, from_cache: bool = False):
        self.client = client
        self.name = name
        if from_cache:
            self.closed = True

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
        self.closed = True
        self.emit('close')
        self.offs()

    def empty(self):
        return self.__len__() == 0


class QueueManager:
    client: redis.Redis = None
    queues: dict[str, JudgeMessages] = {}

    def __init__(self, client: redis.Redis = None):
        if client is not None:
            self.connect(client)

    def connect(self, client: redis.Redis):
        self.client = client

    def create(self, name: str):
        if self.check(name):
            raise exception.QueueAlreadyExist(name)
        queue = JudgeMessages(self.client, name)
        self.queues[name] = queue
        return queue

    def add(self, queue: JudgeMessages, skip_check: bool = False):
        if not isinstance(queue, JudgeMessages):
            raise exception.QueueNotValid(type(queue))
        if skip_check is False and self.check(queue.name):
            raise exception.QueueAlreadyExist(queue.name)
        self.queues[queue.name] = queue

    def check(self, name: str):
        if self.client is None:
            raise exception.NotConnected()

        return name in self.queues and not self.queues[name].closed

    def get(self, name: str) -> JudgeMessages:
        if not self.check(name):
            raise exception.QueueNotFound(name)
        return self.queues[name]

    def check_cache(self, name: str):
        if self.client is None:
            raise exception.NotConnected()
        return self.client.llen(name) > 0

    def get_cache(self, name: str):
        if self.client is None:
            raise exception.NotConnected()

        if not self.check_cache(name):
            raise exception.QueueNotFound(name)

        return JudgeMessages(self.client, name, True)

    def close(self, name: str):
        if self.client is None:
            raise exception.NotConnected()

        queue = self.get(name)
        queue.close()



