import os
import typing

import pydantic

from declare import PydanticIndexable
from .io import read_json


class AdminUser(PydanticIndexable):
    name: str = pydantic.Field(default="admin", min_length=4, max_length=32)
    password: str = pydantic.Field(
        default="Justyse_API#ByVaito&Puyol@Admin!PleaseChangeThisPassword",
        min_length=6,
        max_length=128
    )


class Config(PydanticIndexable):
    lang: str

    store_place: str
    # cache_place: typing.Literal["redis"]

    # login_methods: typing.List[typing.Literal["pwd", "google", "facebook"]]
    pass_store: typing.Literal["plain", "hashed"]
    hash_func: typing.Literal[None, "bcrypt", "argon2", "scrypt", "pbkdf2", "sha512", "sha256"]
    admin: AdminUser = pydantic.Field(default_factory=AdminUser)
    username_length: tuple[int, int] = pydantic.Field(default=(4, 32))
    password_length: tuple[int, int] = pydantic.Field(default=(6, 128))

    container_port: int
    redis_server: str

    judge_server: typing.List[str] = pydantic.Field(default=None)
    judge_mode: typing.Literal[0, 1]
    testcase_strict: typing.Literal["strict", "delete", "warn", "ignore"]
    # compress_threshold: int
    reconnect_timeout: int = pydantic.Field(default=10)
    recv_timeout: int = pydantic.Field(default=5)
    send_timeout: int = pydantic.Field(default=5)
    max_retry: int = pydantic.Field(default=5)
    heartbeat_interval: int = pydantic.Field(default=5)

    capture_logger: list[str] = pydantic.Field(default=['justyse.*', 'uvicorn.*', 'fastapi'])
    logging_padding: int = pydantic.Field(default=15)
    color: bool = pydantic.Field(default=True)


config = Config(**read_json(f"{os.getcwd()}/data/config.json"))
