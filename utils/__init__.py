import typing
import json
import os
import shutil
from typing import Optional, Type, Any, Tuple, Callable
from copy import deepcopy
from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo


class Config(BaseModel):
    lang: str
    store_place: typing.Literal["file", "sql"]
    cache_place: typing.Literal["redis"]
    login_methods: typing.List[typing.Literal["pwd", "google", "facebook"]]
    pass_store: typing.Literal["plain", "hashed"]
    hash_func: typing.Literal["bcrypt", "argon2", "scrypt", "pbkdf2", "sha512", "sha256"]
    container_port: int
    testcase_strict: typing.Literal["strict", "loose"]
    compress_threshold: int
    judge_server: typing.List[str]
    judge_mode: typing.Literal[0, 1]


def read(file: str) -> typing.Optional[str]:
    if os.path.exists(file):
        return open(file, "r").read()
    return None


def read_json(file: str) -> typing.Dict[str, typing.Any]:
    with open(file, "r") as f:
        return json.load(f)


def write_json(file: str, data: typing.Dict[str, typing.Any]) -> None:
    with open(file, "w") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def delete_content(folder: str) -> None:
    for directory in os.listdir(folder):
        file_path = os.path.join(folder, directory)
        if os.path.isfile(file_path):
            os.unlink(file_path)
        else:
            shutil.rmtree(file_path)


config = Config(**read_json(f"{os.getcwd()}/data/config.json"))


# https://stackoverflow.com/a/76560886/17106809
def partial_model(model: Type[BaseModel]):
    def make_field_optional(
            field: FieldInfo,
            default: Any = None,
            default_factory: Callable[[], typing.Any] = lambda: None,
    ) -> Tuple[Any, FieldInfo]:
        new = deepcopy(field)
        new.default = default
        new.default_factory = default_factory
        new.annotation = Optional[field.annotation]  # type: ignore
        return new.annotation, new

    return create_model(
        f"Partial{model.__name__}",
        __base__=model,
        __module__=model.__module__,
        **{
            field_name: make_field_optional(field_info)
            for field_name, field_info in model.model_fields.items()
        },
    )


def find(key: typing.Any, arr: typing.List[typing.Any]) -> int:
    for index, value in enumerate(arr):
        if (isinstance(value, list) or isinstance(value, tuple)) and key in value:
            return index
        elif value == key:
            return index
    return -1


# https://stackoverflow.com/a/54802737/17106809
def chunks(arr: typing.Union[typing.List[typing.Any], typing.Tuple], n: int):
    """Yield n number of sequential chunks from list."""
    d, r = divmod(len(arr), n)
    for i in range(n):
        si = (d + 1) * (i if i < r else r) + d * (0 if i < r else i - r)
        yield arr[si:si + (d + 1 if i < r else d)]
