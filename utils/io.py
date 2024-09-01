import json
import os
import typing


def read(file: str) -> typing.Optional[str]:
    if os.path.exists(file):
        return open(file, "r").read()
    return None


def read_json(file: str) -> typing.Dict[str, typing.Any]:
    return json.load(open(file, "r"))


def write(file: str, data: str) -> None:
    return open(file, "w").write(data)


def write_json(file: str, data: typing.Dict[str, typing.Any]) -> None:
    return write(file, json.dumps(data, indent=4, ensure_ascii=False))
