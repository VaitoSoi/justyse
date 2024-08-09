import json
import os
import typing


def read(file: str) -> typing.Optional[str]:
    if os.path.exists(file):
        return open(file, "r").read()
    return None


def read_json(file: str) -> typing.Dict[str, typing.Any]:
    with open(file, "r") as f:
        return json.load(f)


def write(file: str, data: str) -> None:
    with open(file, "w") as f:
        f.write(data)


def write_json(file: str, data: typing.Dict[str, typing.Any]) -> None:
    write(file, json.dumps(data, indent=4, ensure_ascii=False))
