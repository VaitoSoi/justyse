import logging
import os
import queue
import threading
import time
import typing

import websockets

import db
import declare
import utils
from db.redis import JudgeMessages
from . import exception, data
from .client import JudgeClient


class JudgeManager:
    _logger: logging.Logger = logging.getLogger("uvicorn.error")
    _connections: typing.Dict[int, JudgeClient] = {}

    _judge_queue: queue.Queue = queue.Queue()
    _judge_abort: dict[str, threading.Event] = {}

    _reconnect_timeout: int = os.getenv("RECONNECT_TIMEOUT", 10)
    _recv_timeout: int = os.getenv("RECV_TIMEOUT", 5)
    _max_retry: int = os.getenv("MAX_RETRY", 5)
    _heartbeat_interval = os.getenv("HEARTBEAT_INTERVAL", 5)
    _retry: dict[str, int] = {}

    stop: threading.Event = threading.Event()
    threads: list[threading.Thread] = []

    def __init__(self, reconnect_timeout: int = None, recv_timeout: int = None, max_retry: int = None):
        if reconnect_timeout is not None:
            self._reconnect_timeout = reconnect_timeout

        if recv_timeout is not None:
            self._recv_timeout = recv_timeout

        if max_retry is not None:
            self._max_retry = max_retry

    def _get_connections(self):
        return {key: value for key, value in self._connections.items() if value is not None}

    def connect(self, uri: str, id: str, name: str):
        if uri in [connection._uri for _, connection in self._connections.items() if connection is not None]:
            raise exception.AlreadyConnected(uri)

        try:
            client = JudgeClient(
                uri=f"{uri}/session" if not uri.endswith('/session') else uri,
                id=id,
                name=name,
                recv_timeout=self._recv_timeout
            )
            client.connect()

        except websockets.exceptions.InvalidURI as error:
            raise ValueError("Invalid judge server uri") from error

        except (OSError,
                websockets.exceptions.InvalidHandshake,
                websockets.exceptions.ConnectionClosedError,
                websockets.exceptions.AbortHandshake) as error:
            raise exception.ConnectionError() from error

        else:
            return client

    def reconnect(self, id: str, retry: bool = True):
        if id in self._retry and self._retry[id] == -1:
            self._retry.pop(id, None)
            return self._logger.info(f"Cancelled connect request to Judge server#{id}")

        server = data.get_server(id)
        uri = server.uri
        name = server.name
        try:
            client = self.connect(uri, id, name)

        except exception.AlreadyConnected:
            self._retry.pop(id, None)
            self._logger.error(f"Already connected to Judge server#{id} {uri}")

        except exception.ConnectionError:
            if not self.stop.is_set():
                if not retry:
                    return self._logger.error(f"Failed to reconnect to Judge server#{id}: {uri}")
                if id in self._retry and self._retry[id] == self._max_retry:
                    return self._logger.error(f"Retry limit reached for Judge server#{id}: {uri}")

                if id not in self._retry:
                    self._retry[id] = 0
                self._retry[id] += 1

                self._logger.info(f"Failed to reconnect to Judge server#{id}: {uri}."
                                  f" Retry in {self._reconnect_timeout}s")
                timer = threading.Timer(self._reconnect_timeout, self.reconnect, args=(id, retry))
                timer.start()

        # except Exception as error:
        #     self._retry.pop(id, None)
        #     return self._logger.error(f"Judge server#{id} raise exception while reconnecting: {str(error)}")

        else:
            self._logger.info(f"Reconnected to Judge server#{id} {uri}")
            self._connections[id] = client
            self._retry.pop(id, None)
            return client

    def disconnect(self, id):
        if id not in self._connections:
            raise exception.ServerNotFound(id)

        try:
            self._connections[id].close()
        except Exception as error:
            self._logger.error(f"Judge server#{id} raise exception while disconnecting: {str(error)}")
        self._connections.pop(id, None)
        self._retry[id] = -1

    def disconnects(self):
        for key, client in self._connections.items():
            if client is None:
                continue
            self.disconnect(key)
        self._connections.clear()

    def from_json(self, warn: bool = True):
        for server in data.get_servers().values():
            try:
                self.reconnect(server.id, True)

            except Exception as error:
                self._logger.error(f"Judge server#{server.id} raise exception while connecting: {str(error)}")

        if len(self._get_connections().values()) == 0 and warn is True:
            self._logger.warning("No judge server are connected")

        return self._connections

    def add_server(self, server: data.Server):
        if server.id in self._connections:
            raise exception.AlreadyConnected(server.id)

        server.id = server.id if server.id is not None else str(len(self._connections))

        servers = utils.read_json(data.server_json)
        servers[server.id] = server.model_dump()
        utils.write_json(data.server_json, servers)

        client = self.reconnect(server.id, False)
        self._connections[server.id] = client
        return client

    def remove_server(self, id):
        if id not in self._connections:
            raise exception.ServerNotFound(id)
        self.disconnect(id)

        servers = utils.read_json(data.server_json)
        servers.pop(id)
        utils.write_json(data.server_json, servers)

    def status(self):
        return [client.status() for key, client in self._connections.items()]

    def pause(self, id):
        self._connections[id].pause()

    def resume(self, id):
        self._connections[id].resume()

    def idle(self):
        return all([status["status"] == 'idle' for status in self.status()])

    def is_free(self):
        return (
            "idle" in [status["status"] for status in self.status()]
            if utils.config.judge_mode == 0 else
            self.idle()
        )

    def clear_threads(self):
        self.threads = [thread for thread in self.threads if thread.is_alive()]

    def join_thread(self, clean: bool = False):
        for thread in self.threads:
            if thread.is_alive():
                thread.join()

        if clean is True:
            self.clear_threads()

    def stop_recv(self):
        conenctions = [client for key, client in self._connections.items() if client is not None]

        for client in conenctions:
            client.stop_jugde.set()
            client.stop_recv.set()

        for client in conenctions:
            if client.recv_thread.is_alive():
                client.recv_thread.join()
            client.close()

    def heartbeat(self):
        while True:
            if self.stop.is_set():
                break

            for client in self._connections.copy().values():
                if client is None:
                    continue

                if client._is_closed:
                    self._connections[client._id] = None
                    self._logger.error(f"Judge server#{client._id} disconnected. "
                                       f"Reconnecting in {self._reconnect_timeout}s")
                    timer = threading.Timer(self._reconnect_timeout, self.reconnect(client._id, True))
                    timer.start()

            time.sleep(5)

    def add_submission(self, submission_id: str, msg: JudgeMessages, abort: threading.Event):
        self._judge_abort[submission_id] = abort
        msg.put(['waiting'])
        self._judge_queue.put((submission_id, msg))

    def loop(self):
        while True:
            if self.stop.is_set():
                break

            if not self._judge_queue.empty() and self.is_free():
                submission_id, msg = self._judge_queue.get()

                try:
                    submission = db.get_submission(submission_id)
                except db.exception.SubmissionNotFound:
                    msg.put({'error': 'submission not found'})
                    continue

                abort = self._judge_abort[submission_id]

                try:
                    problem = db.get_problem(submission.problem)
                except db.exception.ProblemNotFound:
                    msg.put({'error': 'problem not found'})
                    continue

                if not abort.is_set():
                    try:
                        match utils.config.judge_mode:
                            case 0:
                                thread = threading.Thread(
                                    target=self.judge_psps,
                                    kwargs={
                                        "submission": submission,
                                        "problem": problem,
                                        "msg": msg,
                                        "abort": abort
                                    },
                                    name=f"handle-{submission_id}"
                                )
                                thread.start()
                                self.threads.append(thread)
                            case 1:
                                self.judge_ptps(
                                    submission=submission,
                                    problem=problem,
                                    msg=msg,
                                    abort=abort
                                )
                            case _:
                                raise ValueError("Invalid judge mode")
                    except exception.ServerBusy:
                        self._judge_queue.put((submission_id, msg, abort))
                else:
                    msg.put(['abort'])

            time.sleep(1)

    def judge_psps(self,
                   submission: db.DBSubmissions,
                   problem: db.Problems,
                   msg: JudgeMessages,
                   abort: threading.Event):
        index = [
            i for i, client in self._connections.items()
            if not client.is_judging and (client.status())[0] == 'idle'
        ]
        if len(index) == 0:
            raise exception.ServerBusy()
        connection = self._connections[index[0]]
        msg.put(['catched', connection.name])

        time: float = 0
        amemory: float = 0
        pmemory: float = 0
        warn: str = ""
        error: str = ""
        overall: declare.JudgeResult = {}
        try:
            for (status, data) in connection.judge_iter(
                    submission=submission,
                    problem=problem,
                    test_range=(1, problem.total_testcases),
                    abort=abort
            ):
                if self.stop.is_set():
                    return

                if status == 'result':
                    if data['position'] != 'overall':
                        msg.put([status, data])

                    if data['position'] == 'compiler':
                        if data['status'] == declare.StatusCode.COMPILE_WARN.value:
                            warn = data['warn']

                    elif data['position'] == 'overall':
                        overall = data

                    elif isinstance(data['position'], int):
                        if data['status'] == declare.StatusCode.ABORTED.value:
                            overall = {
                                "status": declare.StatusCode.ABORTED.value
                            }
                            time = -1
                            break
                        else:
                            time += data['time']
                            amemory += data['memory'][0]
                            pmemory += data['memory'][1]

                elif status == 'warn':
                    warn = data

                elif status in ['error', 'done']:
                    if status == 'error':
                        error = data['error']
                        overall = {
                            "status": declare.StatusCode.SYSTEM_ERROR.value
                        }
                        time = -1
                        amemory = -1
                        pmemory = -1
                    break
                else:
                    msg.put([status, data])

        except Exception as e:
            time = -1
            amemory = -1
            pmemory = -1
            error = str(e)
            overall = {
                "status": declare.StatusCode.SYSTEM_ERROR.value
            }

        print(overall)
        result = db.declare.SubmissionResult(
            status=overall["status"] if "status" in overall else declare.StatusCode.SYSTEM_ERROR.value,
            warn=warn,
            error=error,
            time=time if time == -1 else (time / problem.total_testcases),
            memory=(
                amemory / problem.total_testcases if amemory != -1 else -1,
                pmemory / problem.total_testcases if pmemory != -1 else -1
            )
        )
        submission.results.append(result)
        db.update_submission(submission.id, submission)

        msg.put(['overall', result.model_dump()])
        msg.put(['done'])

        return

    def judge_ptps(self,
                   submission: db.DBSubmissions,
                   problem: db.Problems,
                   msg: JudgeMessages,
                   abort: threading.Event):
        msg.put(['catched', None])
        test_chunk = utils.chunks(range(1, problem.total_testcases + 1), len(self._connections))

        self.join_thread(clean=True)

        judge_msg = queue.Queue()
        for i, chunk in enumerate(test_chunk):
            if len(chunk) == 0:
                continue

            connection = list(self._connections.values())[i]
            thread = threading.Thread(
                target=connection.judge,
                kwargs={
                    "submission": submission,
                    "problem": problem,
                    "test_range": (chunk[0], chunk[-1]),
                    "msg_queue": judge_msg,
                    "abort": abort
                },
                name=f"handle-{submission.id}-{i}"
            )
            thread.start()
            self.threads.append(thread)

        def running():
            return all([thread.is_alive() for thread in self.threads])

        statuss = {}
        warn: set[str] = set()
        error: set[str] = set()
        total_time: float = 0
        amemory: float = 0
        pmemory: float = 0
        overall: list[declare.JudgeResult] = []
        while running() or not judge_msg.empty():
            message = judge_msg.get()

            if message[0] in ['initting', 'judging']:
                if message[0] not in statuss:
                    statuss[message[0]] = 0
                statuss[message[0]] += 1

                if statuss[message[0]] == len(self.threads):
                    msg.put(message)
                    del statuss[message[0]]

            elif message[0] == 'error':
                error.add(message[1])
                total_time = -1
                amemory = -1
                pmemory = -1

            elif message[0] == 'warn':
                warn.add(message[1])

            elif message[0] in ['debug', 'done']:
                pass

            else:
                if len(error) > 0:
                    continue

                if message[1]['position'] != 'overall':
                    msg.put(message)

                if message[0] != 'result':
                    continue

                elif message[1]['position'] == 'overall':
                    overall.append(message[1])

                elif isinstance(message[1]['position'], int):
                    if message[1]['status'] == declare.StatusCode.ABORTED.value:
                        overall.append("aborted")
                        total_time = -1

                    else:
                        total_time += message[1]['time']
                        amemory += message[1]['memory'][0]
                        pmemory += message[1]['memory'][1]

        result: db.declare.SubmissionResult = None
        if "aborted" in overall:
            result = db.declare.SubmissionResult(
                status=declare.StatusCode.ABORTED.value,
                time=-1,
                warn="",
                error="",
            )

        else:
            overall.sort(key=lambda result: result['status'])
            result = db.declare.SubmissionResult(
                    status=overall[0]['status'] if len(error) == 0 else declare.StatusCode.SYSTEM_ERROR.value,
                    time=total_time if total_time == -1 else (total_time / problem.total_testcases),
                    warn="\n".join(list(warn)),
                    error="\n".join(list(error)),
                    memory=(
                        amemory / problem.total_testcases if amemory != -1 else -1,
                        pmemory / problem.total_testcases if pmemory != -1 else -1
                    )
                )

        submission.results.append(result)
        msg.put(['overall', result.model_dump()])
        msg.put(['done'])

        db.update_submission(submission.id, submission)
        return
