from enum import Enum
import typing
import shutil
import os

class Status(Enum):
    ACCEPTED = 0
    WRONG_ANSWER = 1
    TIME_LIMIT_EXCEEDED = 2
    MEMORY_LIMIT_EXCEEDED = 3
    RUNTIME_ERROR = 4
    COMPILE_ERROR = 5
    SYSTEM_ERROR = 6


class Execution(Enum):
    Python = ["python -m compileall -q {id}.py", "python {id}.pyc"]
    C = [
        "gcc -o {id}.{ext} -O2 -Wall -lm -s -fmax-errors=5 -march=native -std=c{c_version} {id}.c",
        "./{id}.{ext}",
    ]
    Cpp = [
        "g++ -o {id}.{ext} -O2 -Wall -lm -s -fmax-errors=5 -march=native -stc=c++{cpp_version} {id}.cpp",
        "./{id}.{ext}",
    ]
    Java = ["javac -encoding UTF-8 {id}.java", "java {id}"]


async def jugde(
    id: str,
    lang: typing.Tuple[str, int],
    compiler: typing.Tuple[str, int],
    code: str,
) -> typing.Tuple[Status, str]:
    ext = os.name == "nt" and "exe" or ""
    id = f'{id}.solution'
    cmd = Execution[lang[0]].value
