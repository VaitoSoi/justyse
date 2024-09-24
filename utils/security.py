import hashlib
import os
import typing
import uuid

import fastapi
import fastapi.security as security
import jwt
from passlib.hash import argon2, scrypt, sha256_crypt, sha512_crypt, bcrypt

from . import exception
from .config import config

signature = os.getenv("SIGNATURE", hashlib.sha256(str(uuid.uuid4()).encode()).hexdigest())
oauth2_scheme = security.OAuth2PasswordBearer(tokenUrl="/api/user/login")
optional_oauth2_scheme = security.OAuth2PasswordBearer(tokenUrl="/api/user/login", auto_error=False)


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
                    raise ValueError(f"Unknown hash function: {config.hash_func}")
        case _:
            raise ValueError(f"Unknown password store: {config.pass_store}")


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
                    raise ValueError(f"Unknown hash function: {config.hash_func}")

        case _:
            raise ValueError(f"Unknown password store: {config.pass_store}")


def decode_jwt(token: str, verify_exp: bool = True) -> dict:
    if not token:
        raise exception.TokenNotFound()
    try:
        return jwt.decode(token, signature, verify_exp=verify_exp, algorithms=["HS256"])

    except jwt.ExpiredSignatureError:
        raise exception.TokenExpired()

    except jwt.InvalidSignatureError:
        raise exception.SignatureInvalid()


def get_user_id(oauth_scheme: security.OAuth2PasswordBearer = oauth2_scheme) -> dict:
    def wrapper(token: typing.Annotated[str, fastapi.Depends(oauth_scheme)]):
        try:
            decoded = decode_jwt(token)
            return decoded["user"] if decoded and "user" in decoded else None

        except exception.TokenNotFound:
            raise fastapi.HTTPException(
                status_code=401,
                detail={
                    "message": "Token not found",
                    "code": "token_not_found"
                }
            )

        except exception.TokenExpired:
            raise fastapi.HTTPException(
                status_code=401,
                detail={
                    "message": "Token expired",
                    "code": "token_expired"
                }
            )

        except exception.SignatureInvalid:
            raise fastapi.HTTPException(
                status_code=401,
                detail={
                    "message": "Token signature invalid",
                    "code": "token_signature_invalid"
                }
            )

    def optional_wrapper(token: typing.Optional[str] = fastapi.Depends(oauth_scheme)):
        try:
            decoded = decode_jwt(token)
            return decoded["user"] if decoded and "user" in decoded else None

        except Exception:
            return None

    return wrapper if oauth_scheme.auto_error is True else optional_wrapper


def get_user(oauth_scheme: security.OAuth2PasswordBearer = oauth2_scheme) -> dict:
    import db

    def wrapper(user_id: typing.Annotated[str, fastapi.Depends(get_user_id(oauth_scheme))]):
        try:
            return db.get_user(user_id)

        except db.exception.UserNotFound:
            if oauth_scheme.auto_error is True:
                raise fastapi.HTTPException(
                    status_code=404,
                    detail={
                        "message": "User not found",
                        "code": "user_not_found"
                    }
                )

    return wrapper


def has_permission(permission: str,
                   oauth_scheme: security.OAuth2PasswordBearer = oauth2_scheme) -> bool:
    import db

    def wrapper(user: typing.Annotated[db.DBUser, fastapi.Depends(get_user(oauth_scheme))]):
        if not user:
            if oauth_scheme.auto_error is True:
                raise fastapi.HTTPException(
                    status_code=401,
                    detail={
                        "message": "User not found",
                        "code": "user_not_found"
                    }
                )
            else:
                return None

        if db.has_permission(user, permission) is True:
            return user

        if oauth_scheme.auto_error is True:
            raise fastapi.HTTPException(
                status_code=403,
                detail={
                    "message": "Permission denied",
                    "code": "permission_denied",
                    "detail": {
                        "missing": permission
                    }
                })
        else:
            return None

    return wrapper


def viewable(
        object,
        user,
) -> bool:
    if any(["@everyone" in object.roles] + [role in object.roles for role in user.roles]):
        return True
    else:
        raise fastapi.HTTPException(
            status_code=403,
            detail={
                "message": "Permission denied",
                "code": "permission_denied",
                "detail": {
                    "missing": "view"
                }
            }
        )
