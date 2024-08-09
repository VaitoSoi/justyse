import os
import uuid

import pydantic

import db
import declare


class Server(declare.PydanticIndexable):
    uri: str
    name: str
    id: str | None


server_json = os.path.join(db.declare.data, "servers.json")
