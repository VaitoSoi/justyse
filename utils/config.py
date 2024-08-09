import os
import typing

import pydantic

from declare import PydanticIndexable
from .io import read_json


class Config(PydanticIndexable):
    lang: str
    store_place: str
    cache_place: typing.Literal["redis"]
    login_methods: typing.List[typing.Literal["pwd", "google", "facebook"]]
    pass_store: typing.Literal["plain", "hashed"]
    hash_func: typing.Literal[None, "bcrypt", "argon2", "scrypt", "pbkdf2", "sha512", "sha256"]
    container_port: int
    testcase_strict: typing.Literal["strict", "loose"]
    compress_threshold: int
    judge_server: typing.List[str] = pydantic.Field(default=None)
    # judge_count: int = pydantic.Field(default=None)
    judge_mode: typing.Literal[0, 1]
    redis_server: str


config = Config(**read_json(f"{os.getcwd()}/data/config.json"))
