import pydantic
import typing
import uuid
import os
import json

class Problems(pydantic.BaseModel):
    id: str = pydantic.Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str = pydantic.Field(default="")
    accept_language: typing.List[str]
    test_name: typing.List[str]
    total_testcases: int
    roles: typing.Optional[typing.List[str]] | str
    dir: str = pydantic.Field(default=None)


def gen_path(id: str) -> str:
    return os.path.join(base_dir, id)


def read_json(file: str) -> typing.Dict[str, typing.Any]:
    with open(file, "r") as f:
        return json.load(f)


def write_json(file: str, data: typing.Dict[str, typing.Any]) -> None:
    with open(file, "w") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

config = read_json(f"{os.getcwd()}/data/config.json")
base_dir = f"{os.getcwd()}/data/problems"
problem_json = f"{base_dir}/problems.json"
file_dir = f"{os.getcwd()}/data/file"