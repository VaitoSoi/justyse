import os

import db
import declare
import utils
from . import exception


class Server(declare.PydanticIndexable):
    uri: str
    name: str
    id: str | None


server_json = os.path.join(db.declare.data, "servers.json")


def get_keys() -> list[str]:
    return list(utils.read_json(server_json).keys())


def get_servers() -> dict[str, Server]:
    return {key: Server(**server) for key, server in utils.read_json(server_json).items()}


def get_server(id: str) -> Server:
    if id not in get_keys():
        raise exception.ServerNotFound(id)
    return Server(**utils.read_json(server_json)[id])
