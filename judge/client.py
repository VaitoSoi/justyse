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
    logger = logging.getLogger("uvicorn.error")
    ws: ws_sync.ClientConnection = None
    is_juding: bool = False
    id: str
    uri: str
    debug: typing.List[typing.Any] = []
    recv_thread: threading.Thread
    stop_recv: threading.Event = threading.Event()
    judge_msg: queue.Queue = queue.Queue()
    status_msg: queue.Queue = queue.Queue()
    other_msg: queue.Queue = queue.Queue()

    def __init__(self, uri: str, id: str):
        self.uri = uri
        self.id = id
        self.connect()

    def connect(self):
        if self.is_juding is True:
            raise exception.ServerBusy()

        self.ws = ws_sync.connect(self.uri)

        self.stop_recv.clear()
        self.recv_thread = threading.Thread(target=self.recv, name=f"judge-{self.id}-recv")
        self.recv_thread.start()

        self.send(['declare.language', [utils.read(declare.judge.language_json), 'false']])
        self.send(['declare.compiler', [utils.read(declare.judge.compiler_json), 'false']])
        self.send(['declare.load', []])

    def close(self):
        self.stop_recv.set()
        if self.recv_thread is not None and self.recv_thread.is_alive():
            self.recv_thread.join()
        self.ws.close()

    def recv(self) -> typing.Any:
        while True:
            if self.stop_recv.is_set():
                return

            try:
                msg = self.ws.recv(timeout=5)
            except (websockets.exceptions.ConnectionClosedError,
                    websockets.exceptions.ConnectionClosed,
                    websockets.exceptions.ConnectionClosedOK):
                self.logger.error("Connection closed")
                break
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
                self.other_msg.put(msg)

    def recv_check(self):
        if self.stop_recv.is_set() or not self.recv_thread.is_alive():
            raise exception.NotReceiving()
        return True

    def get_judge_msg(self):
        self.recv_check()
        return self.judge_msg.get()

    def get_other_msg(self):
        self.recv_check()
        return self.other_msg.get()

    def send(self, data: typing.Any):
        """
        Send data to the server.
        """

        if isinstance(data, dict) or isinstance(data, list) or isinstance(data, tuple):
            data = json.dumps(data)
        elif isinstance(data, pydantic.BaseModel):
            data = data.model_dump_json()

        try:
            return self.ws.send(data)
        except (websockets.exceptions.ConnectionClosed,
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.ConnectionClosedOK):
            self.logger.error(f"judge server {self.id} connection closed")
            self.stop_recv.set()
            return

    def status(self) -> typing.Literal['idle', 'busy']:
        self.send(["command.status"])
        self.recv_check()
        data = self.status_msg.get()
        return data[1]

    def init(self,
             submission: db.Submissions,
             problem: db.Problems,
             test_range: typing.Tuple[int, int],
             msg: queue.Queue):

        msg.put(['initing'])

        self.send([
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

        response = self.get_judge_msg()
        if response[0] != 'judge.initialized':
            raise exception.InitalizationError()

        return self.debug.append("initalized")

    def code(self, path: str):
        code = utils.read(path)
        code_compress = len(code) > utils.config.compress_threshold
        if code_compress:
            code = zlib.compress(code)
        self.send(['command.code', [code, code_compress]])

        response = self.get_judge_msg()
        if response[0] != 'judge.written:code':
            raise exception.CodeWriteError()

        return self.debug.append("written:code")

    def testcases(self, problem: db.Problems, test_range: typing.Tuple[int, int]):
        test_dir = os.path.join(problem.dir, "testcases")
        for i in range(test_range[0], test_range[1] + 1):
            input_file = os.path.join(test_dir, str(i), problem.test_name[0])
            output_file = os.path.join(test_dir, str(i), problem.test_name[1])
            input_content = utils.read(input_file)
            output_content = utils.read(output_file)

            if not input_content and not output_content:
                self.logger.error(f"input file or output file of test {i} is empty")

            total_size = os.path.getsize(input_file) + os.path.getsize(output_file)
            compress = total_size >= utils.config.compress_threshold
            if compress:
                input_content = zlib.compress(input_content)
                output_content = zlib.compress(output_content)

            self.send(["command.testcase", [i, input_content, output_content, compress]])

            response = self.get_judge_msg()
            if response[0] != 'judge.written:testcase':
                raise exception.TestcaseWriteError()
            if response[1] != i:
                raise exception.TestcaseMismatchError()

            self.debug.append(f"written:testcase {i}")

    def judge(self,
              submission: db.Submissions,
              problem: db.Problems,
              test_range: typing.Tuple[int, int],
              msg: queue.Queue,
              abort: threading.Event,
              skip_debug: bool = True,
              log_path: typing.Optional[str] = None):
        status = self.status()
        if status == "busy":
            raise exception.ServerBusy()
        if self.is_juding:
            raise exception.ServerBusy()

        self.is_juding = True
        judge_result = []
        self.debug = []

        self.send(['command.start', None])
        self.init(submission=submission, problem=problem, test_range=test_range, msg=msg)
        self.code(path=submission.file_path)
        self.testcases(problem=problem, test_range=test_range)

        msg.put(['judging'])
        self.send(["command.judge", None])

        while True:
            if abort.is_set():
                return msg.put(['aborted'])

            response = self.judge_msg.get()
            match response[0][6:]:
                case 'result':
                    judge_result.append(response)
                    msg.put(['result', response[1]])

                case 'done':
                    break

                case _:
                    self.debug.append(response)
                    if skip_debug is False:
                        msg.put(['debug', response])

        msg.put(['done'])
        log = {
            "JudgeID": self.id,
            "SubmissionID": submission.id,
            "ProblemID": problem.id,
            "Debug": self.debug,
            "Result": judge_result
        }
        if log_path:
            utils.write_json(log_path, log)
        self.is_juding = False
