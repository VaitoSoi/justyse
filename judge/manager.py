import datetime
import logging
import os
import queue
import threading
import time
import typing

import websockets

import db
import utils
from db.queue import RedisQueue
from . import exception
from .client import JudgeClient


class JudgeManager:
    judge_queue: queue.Queue = queue.Queue()
    loop_abort: threading.Event = threading.Event()
    judge_abort: dict[str, threading.Event] = {}
    conenctions: typing.List[JudgeClient] = []
    logger: logging.Logger = logging.getLogger("uvicorn.error")
    threads: typing.List[threading.Thread] = []
    timers: typing.List[threading.Timer] = []
    reconnect_timeout: int = 5

    def __init__(self, reconnect_timeout: int = 5):
        self.reconnect_timeout = reconnect_timeout

    def connect_(self, uri: str, id: str):
        if uri in [connection.uri for connection in self.conenctions if connection is not None]:
            raise exception.AlreadyConnected(uri)

        try:
            client = JudgeClient(f"{uri}/session" if not uri.endswith('/session') else uri, id)

        except websockets.exceptions.InvalidURI as error:
            raise ValueError("Invalid judge server uri") from error

        except (OSError,
                websockets.exceptions.InvalidHandshake,
                websockets.exceptions.ConnectionClosedError) as error:
            self.logger.error(f"Fail to connect to Judge server#{id} {uri}: {str(error)}")
            return None

        else:
            return client

    def connect(self, uris: list[str], warn: bool = True):
        for index, uri in enumerate(uris):
            # self.logger.info(f"Connecting to Judge server#{index} {uri}")

            try:
                client = self.connect_(uri, str(index))

            except exception.AlreadyConnected:
                self.logger.error(f"Already connected")

            except Exception as error:
                self.logger.error(f"Judge server raise exception while connecting: {str(error)}")

            else:
                if client is not None:
                    self.conenctions.append(client)
                    self.logger.info(f"Connected to Judge server#{index} {uri}")

                else:
                    self.conenctions.append(None)
                    self.logger.info(f"Retry in {self.reconnect_timeout}s")
                    timer = threading.Timer(self.reconnect_timeout, self.reconnect, args=(uri, str(index)))
                    timer.start()
                    self.timers.append(timer)

        if len([connection for connection in self.conenctions if connection is not None]) == 0 and warn is True:
            self.logger.warning("No judge server are connected")

        return self.conenctions

    def reconnect(self, uris: str, id: str, retry: bool = True):
        client = self.connect_(uris, id)
        if client is not None:
            self.conenctions[id] = client
        elif retry is True and not self.loop_abort.is_set():
            self.logger.info(f"Retry in {self.reconnect_timeout}s")
            timer = threading.Timer(self.reconnect_timeout, self.reconnect, args=(uris, id))
            timer.start()
            self.timers.append(timer)
        return client

    def disconnect(self):
        for client in self.conenctions:
            if client is None:
                continue
            try:
                client.ws.close()
            except Exception as error:
                self.logger.error(f"Judge server raise exception while disconnecting: {str(error)}")
        self.conenctions.clear()

    def status(self):
        return [client.status() for client in self.conenctions if not client.is_juding]

    def idle(self):
        return all([status[0] == 'idle' for status in self.status()])

    def is_free(self):
        return (
            "idle" in [status[0] for status in self.status()] and len(self.threads) < len(self.conenctions)
            if utils.config.judge_mode == 0 else
            self.idle() and len(self.threads) == 0
        )

    def clear_thread(self):
        self.threads = [thread for thread in self.threads if thread.is_alive()]

    def join_threads(self, clean_thread: bool = False):
        for thread in self.threads:
            if thread.is_alive():
                thread.join()

        if clean_thread is True:
            self.clear_thread()

    def clear_timers(self):
        self.timers = [timer for timer in self.timers if timer.is_alive()]

    def stop_timers(self, clean_timers: bool = False):
        for timer in self.timers:
            timer.cancel()

        if clean_timers is True:
            self.clear_timers()

    def stop_recv(self):
        conenctions = [client for client in self.conenctions if client is not None]

        for client in conenctions:
            client.stop_recv.set()

        for client in conenctions:
            client.recv_thread.join()

    def heartbeat(self):
        while True:
            if self.loop_abort.is_set():
                break

            for index, client in enumerate(self.conenctions):
                if client is not None and not client.recv_thread.is_alive():
                    self.conenctions.pop(index)
                    self.logger.error(f"Judge server {index} disconnected")
                    self.logger.info(f"reconnecting to judge server in 5s")
                    timer = threading.Timer(5, self.reconnect, args=(client.uri, index, True))
                    timer.start()
                    self.timers.append(timer)
            time.sleep(5)

    def add_submission(self, submission_id: str, msg: RedisQueue, abort: threading.Event):
        msg.put(['waiting'])
        self.judge_abort[submission_id] = abort
        self.judge_queue.put((submission_id, msg))

    def loop(self):
        while True:
            if self.loop_abort.is_set():
                break

            self.clear_thread()
            self.clear_timers()

            print(not self.judge_queue.empty(), self.is_free())

            if not self.judge_queue.empty() and self.is_free():
                submission_id, msg = self.judge_queue.get()

                try:
                    submission = db.get_submission(submission_id)
                except db.exception.SubmissionNotFound:
                    msg.put({'error': 'submission not found'})
                    continue

                abort = self.judge_abort[submission_id]

                try:
                    problem = db.get_problem(submission.problem)
                except db.exception.ProblemNotFound:
                    msg.put({'error': 'problem not found'})
                    continue

                if not abort.is_set():
                    try:
                        if utils.config.judge_mode == 0:
                            self.judge_psps(submission=submission, problem=problem, msg=msg, abort=abort)
                        else:
                            self.judge_ptps(submission=submission, problem=problem, msg=msg, abort=abort)
                    except exception.ServerBusy:
                        self.judge_queue.put((submission_id, msg, abort))
                else:
                    msg.put(['abort'])

            time.sleep(1)

    def judge_psps(self,
                   submission: db.Submissions,
                   problem: db.Problems,
                   msg: RedisQueue,
                   abort: threading.Event):
        index = [
            i for i, client in enumerate(self.conenctions)
            if not client.is_juding and client.status()[0] == 'idle'
        ]
        if len(index) == 0:
            raise exception.ServerBusy()
        connection = self.conenctions[index[0]]

        def judge():
            connection.judge(
                submission=submission,
                problem=problem,
                test_range=(1, problem.total_testcases),
                msg=msg,
                abort=abort,
                log_path=os.path.join(
                    submission.dir,
                    f"{datetime.datetime.now().strftime('%Y-%m-%d_%H:%M:%S')}_logging.json"
                )
            )
            # self.request.pop(submission.id)

        thread = threading.Thread(target=judge)
        thread.start()
        self.threads.append(thread)

        return

    def judge_ptps(self,
                   submission: db.Submissions,
                   problem: db.Problems,
                   msg: RedisQueue,
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
            if message[0] in ['initing', 'judging', 'done']:
                if message[0] not in statuss:
                    statuss[message[0]] = 0
                statuss[message[0]] += 1

                if statuss[message[0]] == len(self.threads):
                    msg.put(message)
                    del statuss[message[0]]
            elif message[0] == 'debug':
                pass
            else:
                msg.put(message)

        # self.request.pop(submission.id)
