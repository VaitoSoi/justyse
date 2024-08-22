import logging
import queue
import threading
import time
import typing

import websockets

import db
import declare
import utils
from db.redis import RedisQueue
from . import exception, data
from .client import JudgeClient


class JudgeManager:
    _logger: logging.Logger
    _connections: typing.Dict[int, JudgeClient] = {}
    _thread_manager: utils.ThreadingManager

    _judge_queue: queue.Queue = queue.Queue()
    _judge_abort: dict[str, threading.Event] = {}
    _timers: list[threading.Thread] = []
    _judge_threads: list[threading.Thread] = []
    _heartbeat_thread: threading.Thread = None

    _reconnect_timeout: int = utils.config.reconnect_timeout
    _recv_timeout: int = utils.config.recv_timeout
    _max_retry: int = utils.config.max_retry
    _heartbeat_interval: int = utils.config.heartbeat_interval
    _retry: dict[str, int] = {}

    stop: threading.Event = threading.Event()

    def __init__(self,
                 threading_manager: utils.ThreadingManager,
                 reconnect_timeout: int = None,
                 recv_timeout: int = None,
                 max_retry: int = None):
        self._thread_manager = threading_manager

        if reconnect_timeout is not None:
            self._reconnect_timeout = reconnect_timeout

        if recv_timeout is not None:
            self._recv_timeout = recv_timeout

        if max_retry is not None:
            self._max_retry = max_retry

        self._logger = logging.getLogger("justyse.judge.manager")
        self._logger.addHandler(utils.console_handler("Judge Manager"))

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
                thread_manager=self._thread_manager,
                recv_timeout=self._recv_timeout
            )
            client.connect()
            return client

        except websockets.exceptions.InvalidURI as error:
            raise ValueError("Invalid judge server uri") from error

        except (OSError,
                websockets.exceptions.InvalidHandshake,
                websockets.exceptions.AbortHandshake,
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.ConnectionClosedError,
                TimeoutError) as error:
            raise exception.ConnectionError() from error

    def reconnect(self, id: str, retry: bool = True):
        while not self.stop.is_set():
            if id in self._retry and self._retry[id] == -1:
                self._retry.pop(id, None)
                return self._logger.info(f"Cancelled connect request to Judge server#{id}")

            server = data.get_server(id)
            uri = server.uri
            name = server.name
            try:
                client = self.connect(uri, id, name)
                self._logger.info(f"Reconnected to Judge server#{id} {uri}")
                self._retry.pop(id, None)
                self._connections[id] = client
                return client

            except exception.AlreadyConnected:
                self._retry.pop(id, None)
                self._logger.error(f"Already connected to Judge server#{id} {uri}")
                return

            except exception.ConnectionError:
                if not self.stop.is_set():
                    if not retry:
                        return self._logger.error(f"Failed to reconnect to Judge server#{id}: {uri}")

                    if id in self._retry and self._retry[id] >= self._max_retry:
                        return self._logger.error(f"Retry limit reached for Judge server#{id}: {uri}")

                    if id not in self._retry:
                        self._retry[id] = 0

                    self._retry[id] += 1

                    self._logger.error(f"Failed to reconnect to Judge server#{id}: {uri}. "
                                       f"Retry in {self._reconnect_timeout}s")
                    time.sleep(self._reconnect_timeout)

                else:
                    return

            except Exception as error:
                self._retry.pop(id, None)
                self._logger.error(f"Judge server#{id} raise exception while reconnecting, detail")
                self._logger.exception(error)
                return

    def disconnect(self, id):
        if id not in self._connections:
            raise exception.ServerNotFound(id)

        try:
            self._connections[id].close()

        except Exception as error:
            self._logger.error(f"Judge server#{id} raise exception while disconnecting: {str(error)}")

        self._retry[id] = -1
        self._connections.pop(id, None)

    def disconnects(self):
        for key, client in self._connections.items():
            if client is None:
                continue
            self.disconnect(key)
        self._connections.clear()

    def from_json(self, warn: bool = True):
        for server in data.get_servers().values():
            try:
                self._connections[server.id] = self.connect(server.uri, server.id, server.name)
                self._logger.info(f"Connected to Judge server#{server.id} {server.uri}")

            except exception.AlreadyConnected:
                self._logger.error(f"Already connected to Judge server#{server.id} {server.uri}")

            except exception.ConnectionError:
                self._logger.error(f"Failed to connect to Judge server#{server.id}: {server.uri}")
                self._logger.warning(f"Creating reconnect thread....")
                self._thread_manager.create_timer(
                    name=f"judge_manager.timers.reconnect:{server.id}",
                    interval=self._reconnect_timeout,
                    target=self.reconnect,
                    args=(server.id, True)
                )

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

        try:
            self._connections[server.id] = self.connect(server.uri, server.id, server.name)
            self._logger.info(f"Connected to Judge server#{server.id} {server.uri}")

        except exception.AlreadyConnected:
            self._logger.error(f"Already connected to Judge server#{server.id} {server.uri}")

        except exception.ConnectionError:
            self._logger.error(f"Failed to connect to Judge server#{server.id}: {server.uri}")
            self._logger.warning(f"Creating reconnect thread....")
            self._thread_manager.create_timer(
                name=f"judge_manager.timers.reconnect:{server.id}",
                interval=self._reconnect_timeout,
                target=self.reconnect,
                args=(server.id, True)
            )

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

    # def stop_recv(self):
    #     conenctions = [client for key, client in self._connections.items() if client is not None]
    #
    #     for client in conenctions:
    #         client.stop_judge.set()
    #         client.stop_recv.set()
    #
    #     for client in conenctions:
    #         if client.recv_thread.is_alive():
    #             client.recv_thread.join()
    #         client.close()

    def heartbeat(self):
        while not self.stop.is_set():
            for client in self._connections.copy().values():
                if client is None:
                    continue

                if client._is_closed:
                    self._connections[client._id].close()
                    self._connections[client._id] = None
                    self._logger.error(f"Judge server#{client._id} disconnected. Reconnecting...")
                    self.reconnect(client._id, True)

            time.sleep(5)

    def add_submission(self, submission_id: str, msg: RedisQueue, abort: threading.Event):
        msg.put(['waiting'])
        self._judge_abort[submission_id] = abort
        self._judge_queue.put((submission_id, msg))

    def loop(self, skip_check_connection: bool = False):

        while not self.stop.is_set():
            if len(self._get_connections().values()) == 0 and not skip_check_connection:
                self._logger.warning("Loop will sleep until a connection is created.")
                while len(self._get_connections().values()) == 0 and not self.stop.is_set():
                    self._thread_manager.clear_timers("judge_manager.timers.reconnect:*")
                    time.sleep(2)
                if not self.stop.is_set():
                    self._logger.info("Found one (or more :D) judge server, starting loop...")
                else:
                    break

            self._thread_manager.clear_timers("judge_manager.timers.reconnect:*")
            self._thread_manager.clear_threads("judge_manager.judge:*")

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
                                self._thread_manager.create_thread(
                                    target=self.judge_psps,
                                    kwargs={
                                        "submission": submission,
                                        "problem": problem,
                                        "msg": msg,
                                        "abort": abort
                                    },
                                    name=f"judge_manager.judge:{submission_id}",
                                )
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
                   msg: RedisQueue,
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
        points: float = 0
        overall: int = -2
        try:
            for status, data in connection.judge_iter(
                    submission=submission,
                    problem=problem,
                    test_range=(1, problem.total_testcases),
                    abort=abort
            ):
                if self.stop.is_set():
                    return

                if status in ['initting', 'judging']:
                    msg.put([status, data])

                elif status == 'result':
                    point = data.get('point', 0)
                    points += point
                    time += data.get('time', 0)
                    amemory += data.get('memory', (0, 0))[0]
                    pmemory += data.get('memory', (0, 0))[1]

                    msg.put([
                        status,
                        {
                            **data,
                            "point": point
                        }
                    ])

                elif status == 'overall':
                    overall = data

                elif status == 'compiler':
                    warn = data

                elif status in ['error:compiler', 'error:system']:
                    error = data.get('error', None)
                    overall = {
                        "status":
                            declare.StatusCode.SYSTEM_ERROR.value
                            if status == 'error:system' else
                            declare.StatusCode.COMPILE_ERROR.value
                    }
                    time = -1
                    amemory = -1
                    pmemory = -1
                    break

                elif status == 'aborted':
                    overall = {
                        "status": declare.StatusCode.ABORTED.value
                    }
                    time = -1
                    amemory = -1
                    pmemory = -1
                    break

                elif status == 'done':
                    break

        except Exception as e:
            time = -1
            amemory = -1
            pmemory = -1
            error = str(e)
            overall = {
                "status": declare.StatusCode.SYSTEM_ERROR.value
            }

        result = db.declare.SubmissionResult(
            status=overall if overall >= -1 else declare.StatusCode.SYSTEM_ERROR.value,
            warn=warn,
            error=error,
            time=time if time == -1 else (time / problem.total_testcases),
            memory=(
                amemory / problem.total_testcases if amemory != -1 else -1,
                pmemory / problem.total_testcases if pmemory != -1 else -1
            ),
            point=points
        )
        submission.result = result
        db.update_submission(submission.id, submission)

        msg.put(['overall', result.model_dump()])
        msg.put(['done'])

        return

    def judge_ptps(self,
                   submission: db.DBSubmissions,
                   problem: db.Problems,
                   msg: RedisQueue,
                   abort: threading.Event):
        msg.put(['catched', None])
        test_chunk = utils.chunks(range(1, problem.total_testcases + 1), len(self._connections))

        self._thread_manager.clear_threads("judge_manager.threads.judge:*")

        judge_msg = queue.Queue()
        for i, chunk in enumerate(test_chunk):
            if len(chunk) == 0:
                continue

            connection = list(self._connections.values())[i]
            self._thread_manager.create_thread(
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

        def running():
            return all([thread.is_alive() for thread in self._thread_manager["thread:judge_manager.threads.judge:*"]])

        statuss = {}
        warn: set[str] = set()
        error: set[str] = set()
        total_time: float = 0
        amemory: float = 0
        pmemory: float = 0
        points: float = 0
        overall: list[declare.StatusCode] = []
        while running() or not judge_msg.empty():
            status, data = judge_msg.get()
            # print([status, data])

            if status in ['initting', 'judging']:
                if status not in statuss:
                    statuss[status] = 0
                statuss[status] += 1

                if statuss[status] == len(self._connections):
                    msg.put([status, data])
                    del statuss[status]

            elif status == 'error':
                error.add(data)
                total_time = -1
                amemory = -1
                pmemory = -1

            elif status in ['debug', 'done']:
                pass

            elif status == 'compiler':
                warn.add(data)

            elif status == 'overall':
                overall.append(data)

            elif status == 'result':
                point = data.get('point', 0)
                points += point
                total_time += data.get('time', 0)
                amemory += data.get('memory', (0, 0))[0]
                pmemory += data.get('memory', (0, 0))[1]

                msg.put([
                    status,
                    {
                        **data,
                        "point": point
                    }
                ])

        result: db.declare.SubmissionResult = None
        if "aborted" in overall:
            result = db.declare.SubmissionResult(
                status=declare.StatusCode.ABORTED.value,
                time=-1,
                warn="",
                error="",
                memory=(-1, -1),
                point=-1
            )

        else:
            overall.sort(key=lambda result: result)
            result = db.declare.SubmissionResult(
                status=overall[0] if len(error) == 0 else declare.StatusCode.SYSTEM_ERROR.value,
                time=total_time if total_time == -1 else (total_time / problem.total_testcases),
                warn="\n".join(list(warn)),
                error="\n".join(list(error)),
                memory=(
                    amemory / problem.total_testcases if amemory != -1 else -1,
                    pmemory / problem.total_testcases if pmemory != -1 else -1
                ),
                point=points
            )

        submission.result = result
        msg.put(['overall', result.model_dump()])
        msg.put(['done'])

        db.update_submission(submission.id, submission)
        return
