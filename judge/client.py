import asyncio
import json
import logging
import os
# import queue
# import threading
import time
import typing

import pydantic
import websockets

import db
import declare
import utils
from . import exception


# import websockets.sync.client as ws_sync


class JudgeClient:
    _logger: logging.Logger

    uri: str
    id: str
    name: str
    _ws: websockets.WebSocketClientProtocol = None
    # _recv_timeout: int
    is_closed: bool = False
    _pause: bool = False
    # _thread_manager: utils.ThreadingManager

    _debug: typing.List[typing.Any] = []
    _status_msg: asyncio.Queue
    _judge_msg: asyncio.Queue
    _other_msg: asyncio.Queue

    is_judging: bool = False
    stop_judge: asyncio.Event = asyncio.Event()
    stop_recv: asyncio.Event = asyncio.Event()

    recv_task: asyncio.Task = None
    heartbeat_task: asyncio.Task = None
    # recv_thread: threading.Thread = None
    # heartbeat_thread: threading.Thread = None

    def __init__(self,
                 uri: str,
                 id: str,
                 name: str,):
        self.uri = uri
        self.id = id
        self.name = name
        # self._recv_timeout = recv_timeout
        # self._thread_manager = thread_manager
        self.is_closed = False

        self._debug = []
        self._status_msg = asyncio.Queue()
        self._judge_msg = asyncio.Queue()
        self._other_msg = asyncio.Queue()

        self.is_judging = False

        self._logger = logging.getLogger(f"justyse.judge.{id}")
        self._logger.addHandler(utils.console_handler(f"Judge server#{self.id}"))

    async def connect(self):
        if self.is_judging is True:
            raise exception.ServerBusy()

        self._ws = await websockets.connect(self.uri)
        fut = await self._ws.ping()
        await fut

        await self._send(['declare.language', [utils.read(declare.judge.language_json), 'false']])
        await self._send(['declare.compiler', [utils.read(declare.judge.compiler_json), 'false']])
        await self._send(['declare.load', []])

        # self._logger.debug(f"Connected to {self.name} server#{self._id}")

        self.is_closed = False
        self.stop_judge.clear()
        self.stop_recv.clear()
        self.recv_task = asyncio.create_task(self.recv())
        self.heartbeat_task = asyncio.create_task(self.ping())

    async def close(self):
        if self.is_closed:
            return
        self.is_closed = True
        self.stop_recv.set()
        await self._judge_msg.put(['closed'])
        await self._status_msg.put(['closed'])
        await self._other_msg.put(['closed'])

        if self.is_judging:
            self.stop_judge.set()

        if self.recv_task is not None:
            # self._logger.debug("Waiting for recv task to close")
            self.recv_task.cancel()
            try:
                await self.recv_task
            except asyncio.CancelledError:
                pass

        if self.heartbeat_task is not None:
            # self._logger.debug("Waiting for ping task to close")
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass

        try:
            await self._ws.close()

        except Exception:  # noqa
            pass

        self._ws = None

        # self._logger.debug(f"Closed {self.name} server#{self.id}")
        return

    async def ping(self):
        # self._logger.debug(f"Start heartbeat for {self.name} server#{self.id}")
        while not self.stop_recv.is_set():
            # self._logger.debug(f"Heartbeat for {self.name} server#{self.id}")
            try:
                start = time.time()
                fut = await self._ws.ping()
                await fut
                total = time.time() - start

                # self._logger.debug(f"Heartbeat: {total:.3f}s")

            except (websockets.exceptions.ConnectionClosed,
                    websockets.exceptions.ConnectionClosedError,
                    websockets.exceptions.ConnectionClosedOK):
                await self.close()
                break

            except TimeoutError:
                self._logger.debug("Heartbeat timeout")
                # self.close()
                continue

            except RuntimeError:
                self._logger.error(f"Heartbeat error: wrong data")
                # self.close()

            except asyncio.CancelledError:
                break

            except Exception as e:
                self._logger.error(f"Heartbeat error")
                self._logger.exception(e)
                # self.close()
                break

            await asyncio.sleep(utils.config.heartbeat_interval)

    async def recv(self) -> typing.Any:
        while True:
            if self.stop_recv.is_set():
                break

            try:
                async with asyncio.timeout(utils.config.recv_timeout):
                    msg = await self._ws.recv()

            except (websockets.exceptions.ConnectionClosed,
                    websockets.exceptions.ConnectionClosedError,
                    websockets.exceptions.ConnectionClosedOK):
                return await self.close()

            except asyncio.TimeoutError:
                continue

            except asyncio.CancelledError:
                break

            except Exception as e:
                self._logger.error(f"Recive error while recieving data from Judge server#{self.id}, detail")
                self._logger.exception(e)
                return await self.close()

            else:
                try:
                    msg = json.loads(msg)

                except json.JSONDecodeError as error:
                    self._logger.error(f"Recive error while decoding data from Judge server#{self.id}, detail")
                    self._logger.exception(error)
                    continue

                if msg[0] == 'status':
                    await self._status_msg.put(msg)

                elif msg[0].startswith("judge."):
                    await self._judge_msg.put(msg)

                else:
                    await self._other_msg.put(msg)

    async def _send(self, data: typing.Any):
        """
        Send data to the server.
        """

        if isinstance(data, dict) or isinstance(data, list) or isinstance(data, tuple):
            data = json.dumps(data)

        elif isinstance(data, pydantic.BaseModel):
            data = data.model_dump_json()

        try:
            return await self._ws.send(data)

        except (websockets.exceptions.ConnectionClosed,
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK):
            return self.close()

        except Exception as e:
            self._logger.error(f"Recive error while sending data to Judge server#{self.id}, detail:")
            self._logger.exception(e)
            return self.close()

    async def pause(self):
        self._pause = True

    async def resume(self):
        self._pause = False

    async def status(self) -> declare.Status:
        if self.is_closed:
            return {"status": "closed"}
        if self._pause:
            return {"status": "paused"}

        await self._send(["command.status"])
        response = await self._status_msg.get()
        if response[0] == 'closed':
            return {"status": "closed"}

        return declare.Status(**response[1])

    async def _init(self,
                    submission: db.Submissions,
                    problem: db.Problems,
                    test_range: typing.Tuple[int, int]):

        await self._send([
            'command.init',
            declare.JudgeSession(
                submission_id=submission.id,
                language=submission.lang,
                compiler=submission.compiler,
                test_range=test_range,
                test_file=problem.test_name,
                test_type=problem.test_type,
                judge_mode=problem.mode,
                point=problem.point_per_testcase,
                limit=problem.limit
            ).model_dump()
        ])

        response = await self._judge_msg.get()
        if response[0] == 'judge.init':
            if response[1].get("status", None) != 0:
                raise exception.InitalizationError(response[1].get("error", None))

        return self._debug.append("initalized")

    async def _code(self, path: str):
        code = utils.read(path)

        await self._send(['command.code', [code]])

        response = await self._judge_msg.get()
        if response[0] == 'judge.write:code':
            if response[1].get("status") != 0:
                raise exception.CodeWriteError(response[1].get("error", None))

        return self._debug.append("written:code")

    async def _testcases(self, problem: db.Problems, test_range: typing.Tuple[int, int]):
        test_dir = os.path.join(problem.dir, "testcases")
        for i in range(test_range[0], test_range[1] + 1):
            input_file = os.path.join(test_dir, str(i), problem.test_name[0])
            output_file = os.path.join(test_dir, str(i), problem.test_name[1])
            input_content = utils.read(input_file)
            output_content = utils.read(output_file)

            if not input_content and not output_content:
                self._logger.warning(f"input file or output file of test {i} is empty")

            await self._send(["command.testcase", [i, input_content, output_content]])

            response = await self._judge_msg.get()
            if response[0] == 'judge.write:testcase':
                if response[1].get("status") != 0:
                    raise exception.TestcaseWriteError(response[1].get("error", None))
                if response[1].get("index") != i:
                    raise exception.TestcaseMismatchError(f"Expect {i}, got {response[1].get('index')}")

            self._debug.append(f"written:testcase {i}")

    async def _judger(self, problem: db.Problems):
        if not os.path.exists(os.path.join(problem.dir, "judger.py")):
            return

        await self._send(['command.judger', utils.read(os.path.join(problem.dir, "judger.py"))])

        response = await self._judge_msg.get()
        if response[0] == 'judge.write:judger':
            if response[1].get("status") != 0:
                raise exception.JudgerWriteError(response[1].get("error", None))

        self._debug.append("written:judger")

    # async def judge(self,
    #                 submission: db.Submissions,
    #                 problem: db.Problems,
    #                 test_range: typing.Tuple[int, int],
    #                 abort: threading.Event,
    #                 msg_queue: asyncio.Queue,
    #                 skip_debug: bool = True) -> None:
    #     async for status, data in self.judge_iter(submission, problem, test_range, abort, skip_debug):
    #         await msg_queue.put([status, data])

    async def judge_iter(self,
                         submission: db.Submissions,
                         problem: db.Problems,
                         test_range: typing.Tuple[int, int],
                         # abort: asyncio.Event,
                         skip_debug: bool = True) -> typing.AsyncIterable[tuple[str, str | dict]]:

        status = await self.status()
        status = status["status"]
        if status == "busy":
            exception.ServerBusy()

        if self.stop_judge.is_set():
            return

        self.stop_judge.clear()
        self.is_judging = True
        self._debug = []

        yield 'initting', None
        await self._send(['command.start', None])
        await self._init(submission=submission, problem=problem, test_range=test_range)
        await self._code(path=submission.file_path)
        await self._testcases(problem=problem, test_range=test_range)
        if problem.judger is not None:
            await self._judger(problem)

        yield 'judging', None
        await self._send(["command.judge", None])

        while True:
            if self.stop_judge.is_set():
                await self._send(['command.abort'])
                yield 'abort', None
                return

            # if abort.is_set():
            #     self._logger.debug("Aborting...")
            #     await self._send(['command.abort'])
            #     abort.clear()

            try:
                response = await asyncio.wait_for(self._judge_msg.get(), 1)
            except asyncio.CancelledError:
                break
            except asyncio.TimeoutError:
                continue

            if response[0] == 'closed':
                break

            match response[0][6:]:
                case 'error:system':
                    yield 'error:system', response[1]

                case 'error:compiler':
                    yield 'error:compiler', response[1]

                case 'compiler':
                    yield 'compiler', response[1]

                case 'result':
                    yield 'result', response[1]

                case 'overall':
                    yield 'overall', response[1]

                case 'done':
                    break

                case 'aborted':
                    yield 'aborted', response[1]
                    break

                case _:
                    self._debug.append(response)
                    if skip_debug is False:
                        yield 'debug', response

        self.is_judging = False
        yield 'done', None
        return
