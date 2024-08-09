import hashlib
import typing
import uuid

import fastapi
import fastapi.security
import jwt
from passlib.hash import argon2, scrypt, sha256_crypt, sha512_crypt, bcrypt

import db
from .config import config

signature = hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest()
oauth2_scheme = fastapi.security.OAuth2PasswordBearer(tokenUrl="/api/user/login")


def rand_uuid(node: tuple[int, int] | int = -1) -> str:
    if (isinstance(node, int) and node not in range(-1, 5)) or \
            (isinstance(node, tuple) and (node[0] not in range(-1, 5) or node[1] not in range(-1, 5))):
        raise ValueError("Node must be between -1 and 4")

    key = str(uuid.uuid4())
    if isinstance(node, int):
        if node == -1:
            return key
        else:
            return key.split('-')[node]
    else:
        return key.split('-')[node[0]:node[1]]


def hash(s: str) -> str:
    match config.pass_store:
        case 'plain':
            return s
        case 'hashed':
            match config.hash_func:
                case "bcrypt":
                    return bcrypt.hash(s)
                case "argon2":
                    return argon2.hash(s)
                case "scrypt":
                    return scrypt.hash(s)
                case "sha512":
                    return sha512_crypt.hash(s)
                case "sha256":
                    return sha256_crypt.hash(s)
                case _:
                    raise ValueError(f"Unknown hash function")
        case _:
            raise ValueError(f"Unknown password store type")


def check_hash(s: str, h: str) -> bool:
    match config.pass_store:
        case 'plain':
            return s == h
        case 'hashed':
            match config.hash_func:
                case "bcrypt":
                    return bcrypt.verify(s, h)
                case "argon2":
                    return argon2.verify(s, h)
                case "scrypt":
                    return scrypt.verify(s, h)
                case "sha512":
                    return sha512_crypt.verify(s, h)
                case "sha256":
                    return sha256_crypt.verify(s, h)
                case _:
                    raise ValueError(f"Unknown hash function")
        case _:
            raise ValueError(f"Unknown password store type")


def decode_jwt(token: str) -> dict:
    print(token)
    if not token:
        raise fastapi.HTTPException(status_code=401, detail="Token is missing")
    try:
        return jwt.decode(token, signature, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise fastapi.HTTPException(status_code=401, detail="Token is expired")
    except jwt.InvalidSignatureError:
        raise fastapi.HTTPException(status_code=401, detail="Token is invalid")


def get_user(token: typing.Annotated[str, fastapi.Depends(oauth2_scheme)]) -> dict:
    decoded = decode_jwt(token)
    try:
        user = db.get_user(decoded["user"])
    except db.exception.UserNotFound:
        raise fastapi.HTTPException(status_code=404, detail="User not found")
    else:
        return user
