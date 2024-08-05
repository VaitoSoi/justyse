import json
import logging
import os
import queue
import threading
import typing
import zlib

import pydantic
import websockets
import websockets.sync.client as ws_sync

import db
import declare
import utils
from . import exception


class JudgeClient:
    _logger = logging.getLogger("uvicorn.error")

    _uri: str
    _id: str
    _ws: ws_sync.ClientConnection = None
    _recv_timeout: int
    _is_closed: bool = False

    _debug: typing.List[typing.Any] = []
    _status_msg: queue.Queue = queue.Queue()
    _judge_msg: queue.Queue = queue.Queue()
    _other_msg: queue.Queue = queue.Queue()

    is_judging: bool = False
    stop_jugde: threading.Event = threading.Event()
    stop_recv: threading.Event = threading.Event()
    recv_thread: threading.Thread

    def __init__(self, uri: str, id: str, recv_timeout: int = 5):
        self.uri = uri
        self.id = id
        self.recv_timeout = recv_timeout
        self.is_closed = False

        self.debug = []
        self.status_msg = queue.Queue()
        self.judge_msg = queue.Queue()
        self.other_msg = queue.Queue()

        self.is_judging = False

    def connect(self):
        if self.is_judging is True:
            raise exception.ServerBusy()

        self._ws = ws_sync.connect(self.uri)

        self._send(['declare.language', [utils.read(declare.judge.language_json), 'false']])
        self._send(['declare.compiler', [utils.read(declare.judge.compiler_json), 'false']])
        self._send(['declare.load', []])

        self.stop_jugde.clear()
        self.stop_recv.clear()
        self.recv_thread = threading.Thread(target=self.recv)
        self.recv_thread.start()

    def close(self):
        self.is_closed = True

        if self.is_judging:
            self.stop_jugde.set()

        self.stop_recv.set()
        if self.recv_thread.is_alive():
            self.recv_thread.join()

        try:
            self._ws.close()
        except (websockets.exceptions.ConnectionClosed,
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK):
            pass

        return

    def recv(self) -> typing.Any:
        while True:
            if self.stop_recv.is_set():
                break

            try:
                msg = self._ws.recv(self.recv_timeout)
            except (websockets.exceptions.ConnectionClosed,
                    websockets.exceptions.ConnectionClosedError,
                    websockets.exceptions.ConnectionClosedOK):
                self.is_closed = True
                self.judge_msg.put(['closed'])
                self.status_msg.put(['closed'])
                self.other_msg.put(['closed'])
                return None

            except TimeoutError:
                continue

            try:
                msg = json.loads(msg)

            except json.JSONDecodeError:
                pass

            if msg[0] == 'status':
                self.status_msg.put(msg)

            elif msg[0].startswith("judge."):
                self.judge_msg.put(msg)

            else:
                # print(f'recieved {msg}')
                self.other_msg.put(msg)

    def _send(self, data: typing.Any):
        """
        Send data to the server.
        """

        if isinstance(data, dict) or isinstance(data, list) or isinstance(data, tuple):
            data = json.dumps(data)

        elif isinstance(data, pydantic.BaseModel):
            data = data.model_dump_json()

        try:
            return self._ws.send(data)

        except (websockets.exceptions.ConnectionClosed,
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK):
            self.close()

        return

    def status(self) -> tuple[typing.Literal['idle', 'busy'], str | None, str | None]:
        if self.is_closed:
            return "closed"

        self._send(["command.status"])
        return self.status_msg.get()[1]

    def _init(self,
              submission: db.Submissions,
              problem: db.Problems,
              test_range: typing.Tuple[int, int]):

        self._send([
            'command.init',
            declare.JudgeSession(
                submission_id=submission.id,
                language=submission.lang,
                compiler=submission.compiler,
                test_range=test_range,
                test_file=problem.test_name,
                test_type=problem.test_type,
                judge_mode=problem.mode,
                limit=problem.limit
            ).model_dump()
        ])

        response = self.judge_msg.get()

        if response[0] != 'judge.initialized':
            raise exception.InitalizationError()

        return self.debug.append("initalized")

    def _code(self, path: str):
        code = utils.read(path)
        code_compress = len(code) > utils.config.compress_threshold
        if code_compress:
            code = zlib.compress(code)

        self._send(['command.code', [code, code_compress]])

        response = self.judge_msg.get()
        if response[0] != 'judge.written:code':
            raise exception.CodeWriteError()

        return self.debug.append("written:code")

    def _testcases(self, problem: db.Problems, test_range: typing.Tuple[int, int]):
        test_dir = os.path.join(problem.dir, "testcases")
        for i in range(test_range[0], test_range[1] + 1):
            input_file = os.path.join(test_dir, str(i), problem.test_name[0])
            output_file = os.path.join(test_dir, str(i), problem.test_name[1])
            input_content = utils.read(input_file)
            output_content = utils.read(output_file)

            if not input_content and not output_content:
                self._logger.warning(f"input file or output file of test {i} is empty")

            total_size = os.path.getsize(input_file) + os.path.getsize(output_file)
            compress = total_size >= utils.config.compress_threshold
            if compress:
                input_content = zlib.compress(input_content)
                output_content = zlib.compress(output_content)

            self._send(["command.testcase", [i, input_content, output_content, compress]])

            response = self.judge_msg.get()
            if response[0] != 'judge.written:testcase':
                raise exception.TestcaseWriteError()
            if response[1] != i:
                raise exception.TestcaseMismatchError()

            self.debug.append(f"written:testcase {i}")

    def judge(self,
              submission: db.Submissions,
              problem: db.Problems,
              test_range: typing.Tuple[int, int],
              abort: threading.Event,
              msg_queue: queue.Queue,
              skip_debug: bool = True) -> None:

        try:
            for result, data in self.judge_iter(submission, problem, test_range, abort, skip_debug):
                msg_queue.put([result, data])
        except Exception as e:
            msg_queue.put(['error', e])

    def judge_iter(self,
                   submission: db.Submissions,
                   problem: db.Problems,
                   test_range: typing.Tuple[int, int],
                   abort: threading.Event,
                   skip_debug: bool = True) -> typing.Iterator[tuple[str, typing.Any]]:

        status = (self.status())[0]
        if status == "busy":
            exception.ServerBusy()

        if self.stop_jugde.is_set():
            return

        judge_result = []
        self.stop_jugde.clear()
        self.is_judging = True
        self.debug = []

        yield 'initting', None
        self._send(['command.start', None])
        self._init(submission=submission, problem=problem, test_range=test_range)
        self._code(path=submission.file_path)
        self._testcases(problem=problem, test_range=test_range)

        yield 'judging', None
        self._send(["command.judge", None])

        while True:
            if self.stop_jugde.is_set():
                self._send(['abort'])
                return

            if abort.is_set():
                self._send(['abort'])
                abort.clear()

            response = self.judge_msg.get()
            match response[0][6:]:
                case 'result':
                    judge_result.append(response)
                    yield 'result', response[1]

                case 'done':
                    break

                case _:
                    self.debug.append(response)
                    if skip_debug is False:
                        yield 'debug', response

        yield 'done', None

        self.is_judging = False
        return None
