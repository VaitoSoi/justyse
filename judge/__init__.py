import datetime
import json
import logging
import os
import queue
import threading
import time
import typing
import zlib

import pydantic
import websockets
import websockets.sync.client as ws_sync

import db
import declare
import utils


class ServerBusy(Exception):
    pass


class MissingField(ValueError):
    pass


class JudgeClient:
    _send: typing.Callable[[typing.Any], typing.Awaitable[None]]
    logger = logging.getLogger("uvicorn.error")
    ws: ws_sync.ClientConnection
    is_juding: bool = False

    def __init__(self, urls):
        self.ws = ws_sync.connect(urls)

    def send(self, data: typing.Any):
        """
        Send data to the server.
        """

        if isinstance(data, dict) or isinstance(data, list) or isinstance(data, tuple):
            data = json.dumps(data)
        elif isinstance(data, pydantic.BaseModel):
            data = data.model_dump_json()

        return self.ws.send(data)

    def status(self) -> typing.Literal['idle', 'busy']:
        self.send(["status"])
        data = json.loads(self.ws.recv())
        return data['status']

    def init(self,
             submission: db.Submissions,
             problem: db.Problems,
             test_range: typing.Tuple[int, int],
             msg: queue.Queue):

        msg.put({'status': 'initing'})

        return self.send([
            'init',
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

    def code(self, path: str):
        code = utils.read(path)
        code_compress = len(code) > utils.config.compress_threshold
        if code_compress:
            code = zlib.compress(code)
        return self.send(['code', [code, code_compress]])

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

            self.send(["testcase", [i, input_content, output_content, compress]])

    def judge(self,
              submission: db.Submissions,
              problem: db.Problems,
              test_range: typing.Tuple[int, int],
              msg: queue.Queue,
              abort: threading.Event,
              skip_debug: bool = True,
              log_path: typing.Optional[str] = None):
        if self.is_juding:
            raise ServerBusy()
        self.is_juding = True
        judge_result = []
        debug = []

        status = self.status()
        if status == "busy":
            raise ServerBusy()

        self.send(['start', None])
        self.init(submission=submission, problem=problem, test_range=test_range, msg=msg)
        self.code(path=submission.file_path)
        self.testcases(problem=problem, test_range=test_range)

        msg.put({'status': 'judging'})
        self.send(["judge", None])

        while True:
            if abort.is_set():
                return msg.put_nowait({'status': 'aborted'})

            try:
                response = self.ws.recv()
            except websockets.ConnectionClosed:
                break
            else:
                response = json.loads(response)

                match response["status"]:
                    case 'result':
                        judge_result.append(response)
                        msg.put_nowait({'status': 'result', 'data': response['data']})

                    case 'done':
                        break

                    case _:
                        debug.append(response)
                        if skip_debug is False:
                            msg.put_nowait({'status': 'debug', 'data': response})

        msg.put_nowait({'status': 'done'})
        log = {
            "SubmissionID": submission.id,
            "ProblemID": problem.id,
            "Debug": debug,
            "Result": judge_result
        }
        # if not os.path.exists(os.path.dirname(log_path)):
        #     os.makedirs(os.path.dirname(log_path), exist_ok=True)
        if log_path:
            utils.write_json(log_path, log)
        self.is_juding = False


class JudgeManager:
    judge_queue: queue.Queue = queue.Queue()
    loop_abort: threading.Event = threading.Event()
    conenctions: typing.List[JudgeClient]
    logger: logging.Logger = logging.getLogger("uvicorn.error")
    threads: typing.List[threading.Thread] = []

    def __init__(self):
        self.conenctions = []

    def connect(self, uris: str):
        for uri in uris:
            try:
                client = JudgeClient(f"{uri}/session")
            except websockets.exceptions.InvalidURI as error:
                raise ValueError("invalid jugde server uri") from error
            except (OSError, websockets.exceptions.InvalidHandshake) as error:
                self.logger.error(f"judge server raise exception while connecting: {str(error)}")
            else:
                self.conenctions.append(client)
                self.logger.info(f"connected to {uri}")
        return self.conenctions

    def status(self):
        return [client.status() for client in self.conenctions if not client.is_juding]

    def idle(self):
        return all([status == 'idle' for status in self.status()])

    def is_free(self):
        return (
            "idle" in self.status() and len(self.threads) < len(self.conenctions)
            if utils.config.judge_mode == 0 else
            self.idle() and len(self.threads) == 0
        )

    def clear_thread(self):
        self.threads = [thread for thread in self.threads if thread.is_alive()]

    def join_threads(self, clean_thread):
        for thread in self.threads:
            if thread.is_alive():
                thread.join()

        if clean_thread:
            self.clear_thread()

    def add_submission(self, submission_id: str, msg: queue.Queue, abort: threading.Event):
        msg.put({'status': 'waiting'})
        self.judge_queue.put((submission_id, msg, abort))

    def loop(self):
        while True:
            if self.loop_abort.is_set():
                break

            self.clear_thread()

            if not self.judge_queue.empty() and self.is_free():
                submission_id, msg, abort = self.judge_queue.get()
                submission = db.get_submission(submission_id)
                if submission is None:
                    msg.put({'error': 'submission not found'})
                    continue
                problem = db.get_problem(submission.problem)
                if problem is None:
                    msg.put({'error': 'problem not found'})
                    continue

                if not abort.is_set():
                    try:
                        if utils.config.judge_mode == 0:
                            self.judge_psps(submission=submission, problem=problem, msg=msg, abort=abort)
                        else:
                            self.judge_ptps(submission=submission, problem=problem, msg=msg, abort=abort)
                    except ServerBusy:
                        self.judge_queue.put((submission_id, msg, abort))
                else:
                    msg.put({'status': 'abort'})

            time.sleep(1)

    def judge_psps(self,
                   submission: db.Submissions,
                   problem: db.Problems,
                   msg: queue.Queue,
                   abort: threading.Event):
        index = [
            i for i, client in enumerate(self.conenctions)
            if not client.is_juding and client.status() == 'idle'
        ]
        if len(index) == 0:
            raise ServerBusy()
        connection = self.conenctions[index[0]]

        now = datetime.datetime.now()
        thread = threading.Thread(
            target=connection.judge,
            kwargs={
                'submission': submission,
                'problem': problem,
                'test_range': (1, problem.total_testcases),
                'msg': msg,
                'abort': abort,
                'log_path': os.path.join(submission.dir, f"{now.strftime('%Y-%m-%d_%H:%M:%S')}_logging.json")
            }
        )
        thread.start()
        self.threads.append(thread)

        return

    def judge_ptps(self,
                   submission: db.Submissions,
                   problem: db.Problems,
                   msg: queue.Queue,
                   abort: threading.Event):

        test_chunk = utils.chunks(range(1, problem.total_testcases + 1), len(self.conenctions))

        now = datetime.datetime.now()
        log_dir = os.path.join(submission.dir, now.strftime("%Y-%m-%d_%H:%M:%S"))
        os.makedirs(log_dir, exist_ok=False)

        self.join_threads(True)
        judge_msg = queue.Queue()
        for i, chunk in enumerate(test_chunk):
            connection = self.conenctions[i]
            thread = threading.Thread(
                target=connection.judge,
                kwargs={
                    'submission': submission,
                    'problem': problem,
                    'test_range': (chunk[0], chunk[-1]),
                    'msg': judge_msg,
                    'abort': abort,
                    'log_path': os.path.join(submission.dir, now.strftime("%Y-%m-%d_%H:%M:%S"), f"js_{i}.json")
                }
            )
            thread.start()
            self.threads.append(thread)

        def running_thread():
            return all([thread.is_alive() for thread in self.threads])

        statuss = {}
        while running_thread() or not judge_msg.empty():
            message = judge_msg.get()
            if message['status'] in ['initing', 'judging', 'done']:
                if message['status'] not in statuss:
                    statuss[message['status']] = 0
                statuss[message['status']] += 1

                if statuss[message['status']] == len(self.threads):
                    msg.put(message)
                    del statuss[message['status']]
            elif message['status'] == 'debug':
                pass
            else:
                msg.put(message)
