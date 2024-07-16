import asyncio
import json
import logging
import os
import queue
import threading
import typing
import zlib

import websockets

import db
import declare
import utils

logger = logging.getLogger("uvicorn.error")
judge_mode = utils.config["judge_mode"]
jugde_queue = queue.Queue()
jugde_server: typing.List[typing.List[typing.Union[str, typing.Literal["idle", "busy"]]]]
if judge_mode == 0:
    jugde_server = [0, *utils.config["judge_server"]]
else:
    jugde_server = [[ip, "idle"] for ip in utils.config["judge_server"]]


async def _send(conn: websockets.WebSocketClientProtocol, data: typing.Any):
    await conn.send(json.dumps(data))


def judge(submission_id: str, msg_queue: queue.Queue):
    msg_queue.put({"status": "wating"})
    jugde_queue.put((submission_id, msg_queue))


async def judge_loop(abort: threading.Event):
    while True:
        if abort.is_set():
            break
        if not jugde_queue.empty():
            submission_id: str
            msg: queue.Queue
            submission_id, msg = jugde_queue.get()
            submission = await db.get_submission(submission_id)
            problem = await db.get_problem(submission["problem"])

            if judge_mode == 0:
                idle_server = utils.find("idle", jugde_server)
                if idle_server == -1:
                    jugde_queue.put((submission_id, msg))
                    await asyncio.sleep(5)
                    continue
                jugde_server[idle_server][1] = "busy"

                msg.put({"status": "judging"})

                server = None

                try:
                    server = await websockets.connect(
                        f"{jugde_server[idle_server][0]}/jugde"
                    )
                except websockets.exceptions.InvalidURI:
                    raise ValueError("invalid jugde server uri")
                except (OSError, websockets.exceptions.InvalidHandshake) as e:
                    logger.error(
                        "judge server raise exception while connecting: ", str(e)
                    )
                    msg.put({"status": "internal error"})
                    await asyncio.sleep(1)
                    continue

                async def send(data: typing.Any):
                    await _send(server, data)

                if abort.is_set():
                    break
                else:
                    msg.put({"status": "initing"})

                await send(
                    [
                        "init",
                        declare.JudgeSession(
                            submission_id=submission_id,
                            language=submission["lang"],
                            compiler=submission["compiler"],
                            test_range=(1, problem["total_testcases"]),
                            test_file=problem["test_name"],
                            test_type=problem["test_type"],
                            judge_mode=declare.JudgeMode(**problem["mode"]),
                            limit=declare.Limit(**problem["limit"]),
                        ).model_dump_json(),
                    ]
                )

                code = utils.read(submission["file_path"])
                compress = (
                        os.path.getsize(submission["file_path"])
                        > utils.config["compress_threshold"]
                )
                if compress:
                    code = zlib.compress(code)

                await send(["code", [code, compress]])

                if abort.is_set():
                    break
                else:
                    msg.put({"status": "sending testcases"})

                test_dir = os.path.join(problem["dir"], "testcases")
                for i in range(1, problem["total_testcases"] + 1):
                    input_file = os.path.join(test_dir, str(i), problem["test_name"][0])
                    output_file = os.path.join(
                        test_dir, str(i), problem["test_name"][1]
                    )
                    input_content = utils.read(input_file)
                    output_content = utils.read(output_file)

                    if not input_content and not output_content:
                        logger.error(f"input file or output file of test {problem.id}:{i} is empty")

                    total_size = os.path.getsize(input_file) + os.path.getsize(
                        output_file
                    )
                    compress = total_size >= utils.config["compress_threshold"]
                    if compress:
                        input_content = zlib.compress(input_content)
                        output_content = zlib.compress(output_content)

                    await send(
                        ["testcase", [i, input_content, output_content, compress]]
                    )

                if abort.is_set():
                    break
                else:
                    msg.put({"status": "judging"})

                await send(["judge", None])

                while True:
                    if abort.is_set():
                        break

                    try:
                        response = await server.recv()
                        response = json.loads(response)
                    except websockets.exceptions.ConnectionClosed:
                        break
                    if response[0] == "result":
                        msg.put({"result": response[1]})

                jugde_server[idle_server][1] = "idle"
                msg.put("close")
            elif judge_mode == 1:
                if jugde_server[0] == "idle":
                    jugde_queue.put((submission_id, msg))
                jugde_server[0] = "busy"

                msg.put({"status": "judging"})

                connection: typing.List[websockets.WebSocketClientProtocol] = []
                for i in jugde_server[1:]:
                    try:
                        connection.append(await websockets.connect(f"{i[0]}/jugde"))
                    except websockets.exceptions.InvalidURI:
                        raise ValueError("invalid jugde server uri")
                    except (OSError, websockets.exceptions.InvalidHandshake) as e:
                        logger.error(f"judge server {i} raise", str(e))
                        msg.put({"status": "internal error"})
                        continue

                if len(connection) == 0:
                    jugde_server[0] = "idle"
                    msg.put("close")
                    await asyncio.sleep(5)
                    continue

                async def send(data: typing.Any):
                    for conn in connection:
                        await _send(conn, data)

                async def sends(datas: typing.Iterable[typing.Any]):
                    for data, conn in zip(datas, connection):
                        await _send(conn, data)

                test_chunk = utils.chunks(
                    list(range(1, problem["total_testcases"] + 1)),
                    len(connection),
                )

                await sends(
                    [
                        [
                            "init",
                            declare.JudgeSession(
                                submission_id=submission_id,
                                language=submission["lang"],
                                compiler=submission["compiler"],
                                test_range=(chunk[0], chunk[-1]),
                                test_file=problem["test_name"],
                                test_type=problem["test_type"],
                                judge_mode=declare.JudgeMode(**problem["mode"]),
                                limit=declare.Limit(**problem["limit"]),
                            ).model_dump(),
                        ]
                        for chunk in test_chunk
                    ]
                )

                for c_index, chunk in enumerate(test_chunk):
                    for t_index, test in enumerate(chunk):
                        input_file = os.path.join(
                            problem["dir"],
                            "testcases",
                            str(test),
                            problem["test_name"][0],
                        )
                        output_file = os.path.join(
                            problem["dir"],
                            "testcases",
                            str(test),
                            problem["test_name"][1],
                        )
                        input_content = utils.read(input_file)
                        output_content = utils.read(output_file)

                        if not input_content or not output_content:
                            logger.error(f"input file or output file of test {problem.id}:{t_index} is empty")
                            continue

                        total_size = os.path.getsize(input_file) + os.path.getsize(
                            output_file
                        )
                        compress = total_size >= utils.config["compress_threshold"]
                        if compress:
                            input_content = zlib.compress(input_content)
                            output_content = zlib.compress(output_content)

                        await _send(
                            connection[c_index],
                            (
                                [
                                    "testcase",
                                    [
                                        test,
                                        input_content,
                                        output_content,
                                        compress,
                                    ],
                                ]
                            ),
                        )

        await asyncio.sleep(1)
