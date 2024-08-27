import asyncio
import logging
# import threading
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
    # _thread_manager: utils.ThreadingManager

    _judge_queue: asyncio.Queue = asyncio.Queue()
    # _judge_abort: dict[str, asyncio.Event] = {}
    # _timers: list[threading.Thread] = []
    # _judge_threads: list[threading.Thread] = []
    # _heartbeat_thread: threading.Thread = None
    _judge_tasks: list[asyncio.Task] = []
    _reconnect_tasks: list[asyncio.Task] = []

    _reconnect_timeout: int = utils.config.reconnect_timeout
    _recv_timeout: int = utils.config.recv_timeout
    _max_retry: int = utils.config.max_retry
    _heartbeat_interval: int = utils.config.heartbeat_interval
    _retry: dict[str, int] = {}

    stop: asyncio.Event = asyncio.Event()

    def __init__(self,
                 # threading_manager: utils.ThreadingManager,
                 reconnect_timeout: int = None,
                 recv_timeout: int = None,
                 max_retry: int = None):
        # self._thread_manager = threading_manager

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

    async def connect_with_id(self, id: int):
        server = data.get_server(id)
        return await self.connect(
            uri=server.uri,
            id=server.id,
            name=server.name,
            # where="connect_with_id"
        )

    async def connect(self,
                      client: JudgeClient = None,
                      uri: str = None,
                      id: str = None,
                      name: str = None,
                      retry: bool = False,
                      # where: str = None
                      ):
        if uri is not None and uri in [connection.uri for _, connection in self._connections.items()
                                       if connection is not None]:
            return self._logger.error(f"Already connected to Judge server: {uri}")

        if client is None and (uri is None or id is None or name is None):
            raise ValueError("Invalid arguments")

        if client is not None:
            id = client.id
            uri = client.uri
            name = client.name

        if retry is True:
            if id in self._retry:
                if self._retry[id] in range(0, self._max_retry):
                    return self._logger.error(f"Already reconnecting to Judge server#{id}")
            else:
                self._retry[id] = 0

        while not self.stop.is_set():
            if retry is True and self._retry[id] == -1:
                self._retry.pop(id, None)
                return self._logger.warning(f"Cancelled connect request to Judge server#{id}")

            try:
                client = client or JudgeClient(
                    uri=f"{uri}/session" if not uri.endswith('/session') else uri,
                    id=id,
                    name=name,
                    # thread_manager=self._thread_manager,
                )
                await client.connect()
                self._logger.info(f"Connected to Judge server#{id}: {uri}")
                self._retry.pop(id, None)
                return client

            except websockets.exceptions.InvalidURI as error:
                raise ValueError("Invalid judge server uri") from error

            except (OSError,
                    websockets.exceptions.InvalidHandshake,
                    websockets.exceptions.AbortHandshake,
                    websockets.exceptions.ConnectionClosedError,
                    RuntimeError):
                # raise exception.ConnectionError() from error

                if not self.stop.is_set():
                    if not retry:
                        return self._logger.error(f"Failed to connect to Judge server#{id}: {uri}")

                    if id in self._retry and self._retry[id] >= self._max_retry:
                        return self._logger.error(f"Retry limit reached for Judge server#{id}: {uri}")

                    self._retry[id] += 1
                    self._logger.error(f"Failed to reconnect to Judge server#{id}: {uri}. "
                                       f"Retry in {self._reconnect_timeout}s")

                    await asyncio.sleep(self._reconnect_timeout)

            except Exception as error:
                self._logger.error(f"Judge server#{id} raise exception while connecting, detail")
                self._logger.exception(error)
                return None

    async def disconnect(self, id):
        if id not in self._connections:
            raise exception.ServerNotFound(id)

        try:
            await self._connections[id].close()

        except Exception as error:
            self._logger.error(f"Judge server#{id} raise exception while disconnecting, detail")
            self._logger.exception(error)

        self._retry[id] = -1
        self._connections.pop(id, None)

    async def disconnects(self):
        for key, client in self._connections.copy().items():
            if client is None:
                continue
            await self.disconnect(key)
        self._connections.clear()

    async def from_json(self, warn: bool = True):
        async def job(server: data.Server):
            self._connections[server.id] = await self.connect(uri=server.uri,
                                                              id=server.id,
                                                              name=server.name,
                                                              retry=True)

        for server in data.get_servers().values():
            self._reconnect_tasks.append(asyncio.create_task(job(server)))

        # if len(self._get_connections().values()) == 0 and warn is True:
        #     self._logger.warning("No judge server are connected")

        return self._connections

    async def add_server(self, server: data.Server):
        if server.id in self._connections:
            raise exception.AlreadyConnected(server.id)

        server.id = server.id if server.id is not None else str(len(self._connections))

        servers = utils.read_json(data.server_json)
        servers[server.id] = server.model_dump()
        utils.write_json(data.server_json, servers)

        self._reconnect_tasks.append(
            asyncio.create_task(
                self.connect(
                    uri=server.uri,
                    id=server.id,
                    name=server.name,
                    # where="add_server"
                )
            )
        )

    async def remove_server(self, id):
        if id not in self._connections:
            raise exception.ServerNotFound(id)
        await self.disconnect(id)

        servers = utils.read_json(data.server_json)
        servers.pop(id)
        utils.write_json(data.server_json, servers)

    async def status(self):
        return [await client.status() for key, client in self._connections.items() if client is not None]

    async def pause(self, id):
        await self._connections[id].pause()

    async def resume(self, id):
        await self._connections[id].resume()

    async def idle(self):
        return all([status["status"] == 'idle' for status in await self.status()])

    async def is_free(self):
        return (
            "idle" in [status["status"] for status in await self.status()]
            if utils.config.judge_mode == 0 else
            await self.idle()
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

    def clear_judge_task(self):
        self._judge_tasks = [task for task in self._judge_tasks if not task.done()]

    def clear_reconnect_tasks(self):
        self._reconnect_tasks = [task for task in self._reconnect_tasks if not task.done()]

    async def stop_tasks(self):
        for task in self._judge_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        for task in self._reconnect_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def heartbeat(self):
        while not self.stop.is_set():
            for client in self._connections.copy().values():
                if client.is_closed and client.id not in self._retry:
                    self._logger.warning(f"Judge server#{client.id} is closed, reconnecting...")
                    self._reconnect_tasks.append(
                        asyncio.create_task(
                            self.connect(
                                client=client,
                                retry=True,
                                # where="heartbeat"
                            )
                        )
                    )

            await asyncio.sleep(utils.config.heartbeat_interval)

    async def add_submission(self,
                             submission_id: str,
                             msg: RedisQueue,
                             # abort: asyncio.Event
                             ):
        await msg.put(['waiting'])
        # self._judge_abort[submission_id] = abort
        await self._judge_queue.put((submission_id, msg))

    async def loop(self, skip_check_connection: bool = False):
        while not self.stop.is_set():

            if len(self._get_connections().values()) == 0 and not skip_check_connection:
                self._logger.warning("Loop will sleep until a connection is created.")

                while len(self._get_connections().values()) == 0 and not self.stop.is_set():
                    self.clear_reconnect_tasks()
                    await asyncio.sleep(1)

                if not self.stop.is_set():
                    self._logger.info("Found one (or more :D) judge server, starting loop...")

                else:
                    break

            # self._thread_manager.clear_timers("judge_manager.timers.reconnect:*")
            # self._thread_manager.clear_threads("judge_manager.judge:*")
            self.clear_judge_task()
            self.clear_reconnect_tasks()

            # self._logger.debug(("looping...", [status['status'] for status in await self.status()]))
            if await self.is_free():
                # self._logger.debug("Judge server is free")
                data = await self._judge_queue.get()
                # self._logger.debug(data)
                submission_id, msg = data

                try:
                    submission = db.get_submission(submission_id)

                except db.exception.SubmissionNotFound:
                    await msg.put({'error': 'submission not found'})
                    continue

                try:
                    problem = db.get_problem(submission.problem)
                except db.exception.ProblemNotFound:
                    await msg.put({'error': 'problem not found'})
                    continue

                # abort = self._judge_abort.get(submission_id, None)

                # if not abort:
                #     await msg.put({'error': 'abort not found'})
                #     continue

                # if not abort.is_set():
                match utils.config.judge_mode:
                    case 0:
                        async def job():
                            try:
                                await self.judge_psps(
                                    submission=submission,
                                    problem=problem,
                                    msg=msg,
                                    # abort=abort
                                )
                            except exception.ServerBusy:
                                await self._judge_queue.put((submission_id, msg))

                            except asyncio.CancelledError:
                                await msg.put({'error': 'cancelled'})

                        self._judge_tasks.append(asyncio.create_task(job()))
                    case 1:
                        try:
                            await self.judge_ptps(
                                submission=submission,
                                problem=problem,
                                msg=msg,
                                # abort=abort
                            )
                        except exception.ServerBusy:
                            await self._judge_queue.put((submission_id, msg))

                        except asyncio.CancelledError:
                            await msg.put({'error': 'cancelled'})

                    case _:
                        raise ValueError("Invalid judge mode")

                # else:
                #     msg.put(['abort'])

            # self._logger.debug("Setup compelete, now wait........")

        # await asyncio.sleep(1)

    async def judge_psps(self,
                         submission: db.DBSubmissions,
                         problem: db.Problems,
                         msg: RedisQueue,
                         # abort: asyncio.Event
                         ):
        index = [
            i for i, client in self._connections.items()
            if not client.is_judging and (await client.status())['status'] == 'idle'
        ]
        self._logger.debug((index, [client.is_judging for client in self._connections.values()]))
        if len(index) == 0:
            # self._logger.warning("No available judge server")
            raise exception.ServerBusy()
        connection = self._connections[index[0]]
        await msg.put(['catched', connection.name])

        time: float = 0
        amemory: float = 0
        pmemory: float = 0
        warn: str = ""
        error: str = ""
        points: float = 0
        overall: int = -2
        try:
            async for status, data in connection.judge_iter(
                    submission=submission,
                    problem=problem,
                    test_range=(1, problem.total_testcases),
                    # abort=abort
            ):
                if self.stop.is_set():
                    return

                if status in ['initting', 'judging']:
                    await msg.put([status, data])

                elif status == 'result':
                    point = data.get('point', 0)
                    points += point
                    time += data.get('time', 0)
                    amemory += data.get('memory', (0, 0))[0]
                    pmemory += data.get('memory', (0, 0))[1]

                    await msg.put([
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
                    error = data
                    overall = (declare.StatusCode.SYSTEM_ERROR.value
                               if status == 'error:system' else
                               declare.StatusCode.COMPILE_ERROR.value)
                    time = -1
                    amemory = -1
                    pmemory = -1
                    break

                elif status == 'aborted':
                    overall = declare.StatusCode.ABORTED.value
                    time = -1
                    amemory = -1
                    pmemory = -1
                    break

                elif status == 'done':
                    break

        except Exception as e:
            self._logger.error(f"Judge server#{connection.id} raise exception while judging {submission.id}, detail")
            self._logger.exception(e)
            time = -1
            amemory = -1
            pmemory = -1
            error = str(e)
            overall = declare.StatusCode.SYSTEM_ERROR.value

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

        await msg.put(['overall', result.model_dump()])
        # await msg.put(['done'])
        await msg.close()

        return

    async def judge_ptps(self,
                         submission: db.DBSubmissions,
                         problem: db.Problems,
                         msg: RedisQueue,
                         # abort: asyncio.Event
                         ):
        await msg.put(['catched', None])
        test_chunk = utils.chunks(range(1, problem.total_testcases + 1), len(self._connections))

        # self._thread_manager.clear_threads("judge_manager.threads.judge:*")
        self.clear_judge_task()

        job_error = []
        judge_msg = asyncio.Queue()

        async def job(i, chunk):
            connection = list(self._connections.values())[i]
            try:
                async for status, data in connection.judge_iter(submission,
                                                                problem,
                                                                (chunk[0], chunk[-1]),
                                                                # abort
                                                                ):
                    await judge_msg.put((status, data))
            except Exception as e:
                self._logger.error(
                    f"Judge server#{connection.id} raise exception while judging {submission.id}, detail"
                )
                self._logger.exception(e)
                job_error.append(e)

        for i, chunk in enumerate(test_chunk):
            if len(chunk) == 0:
                continue

            task = asyncio.create_task(job(i, chunk))
            self._judge_tasks.append(task)

        def running():
            return all([not task.done() for task in self._judge_tasks])

        statuss = {}
        warns: set[str] = set()
        errors: set[str] = set()
        total_time: float = 0
        amemory: float = 0
        pmemory: float = 0
        points: float = 0
        overall: list[declare.StatusCode] = []
        while running() or not judge_msg.empty():
            if len(job_error) > 0:
                errors.update(job_error)
                job_error.clear()

            try:
                status, data = await asyncio.wait_for(judge_msg.get(), timeout=1)
            except asyncio.TimeoutError:
                continue
            # print([status, data])

            # self._logger.debug([status, data])

            if status in ['initting', 'judging']:
                if status not in statuss:
                    statuss[status] = 0
                statuss[status] += 1

                if statuss[status] == len(self._connections):
                    await msg.put([status, data])
                    del statuss[status]

            elif status in ['error:compiler', 'error:system']:
                overall.append({
                    "status":
                        declare.StatusCode.SYSTEM_ERROR.value
                        if status == 'error:system' else
                        declare.StatusCode.COMPILE_ERROR.value
                })
                errors.add(data)
            # total_time = -1
            # amemory = -1
            # pmemory = -1

            elif status in ['debug', 'done']:
                pass

            elif status == 'compiler':
                warns.add(data)

            elif status == 'overall':
                overall.append(data)

            elif status == 'aborted':
                overall.append(declare.StatusCode.ABORTED.value)

            elif status == 'result':
                point = data.get('point', 0)
                points += point
                total_time += data.get('time', 0)
                amemory += data.get('memory', (0, 0))[0]
                pmemory += data.get('memory', (0, 0))[1]

                await msg.put([
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
            print(overall, errors)
            result = db.declare.SubmissionResult(
                status=overall[0] if len(errors) == 0 else declare.StatusCode.SYSTEM_ERROR.value,
                time=total_time if total_time == -1 else (total_time / problem.total_testcases),
                warn="\n".join(list(warns)),
                error="\n".join(list(errors)),
                memory=(
                    amemory / problem.total_testcases if amemory != -1 else -1,
                    pmemory / problem.total_testcases if pmemory != -1 else -1
                ),
                point=points
            )

        submission.result = result
        await msg.put(['overall', result.model_dump()])
        # await msg.put(['done'])
        await msg.close()

        db.update_submission(submission.id, submission)

        return
