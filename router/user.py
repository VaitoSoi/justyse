import datetime
import logging
import typing

import fastapi
import fastapi.security
import jwt

import db
import utils

user_router = fastapi.APIRouter(prefix="/user", tags=["user"])
logger = logging.getLogger("uvicorn.error")


# GET
@user_router.get("s/")
def get_users():
    return db.get_user_ids()


@user_router.get("/me")
def get_me(me: typing.Annotated[db.DBUser, fastapi.Depends(utils.get_user)]):
    return me


@user_router.get("/{id}")
def get_user(id: str):
    try:
        return db.get_user(id).model_dump()
    except db.exception.UserNotFound:
        return fastapi.Response(status_code=404, content="User not found")
    except Exception as error:
        logger.error(f'get user {id} raise {error}')
        return fastapi.Response(status_code=500, content=str(error))


# POST
@user_router.post("/")
def add_user(user: db.User):
    try:
        db.add_user(user)
    except db.exception.UserAlreadyExist:
        return fastapi.Response(status_code=409, content="User already exist")
    except Exception as error:
        logger.error(f'add user {user.id} raise {error}')
        return fastapi.Response(status_code=500, content=str(error))


@user_router.post("/login")
def get_token(form_data: typing.Annotated[fastapi.security.OAuth2PasswordRequestForm, fastapi.Depends()]):
    user = db.get_user_filter(lambda x: x.name == form_data.username)
    if len(user) == 0:
        return fastapi.Response(status_code=404, content="User not found")
    user = user[0]
    if not utils.check_hash(form_data.password, user.password):
        return fastapi.Response(status_code=401, content="Password incorrect")
    token = jwt.encode(
        {"user": user.id, "exp": datetime.datetime.now() + datetime.timedelta(days=7)},
        utils.signature,
        algorithm="HS256"
    )
    return {"access_token": token, "token_type": "bearer"}


# PATCH
@user_router.patch("/{id}")
def update_user(id: str, user: db.User):
    try:
        db.update_user(id, user)
    except db.exception.UserNotFound:
        return fastapi.Response(status_code=404, content="User not found")
    except Exception as error:
        logger.error(f'update user {id} raise {error}')
        return fastapi.Response(status_code=500, content=str(error))


# DELETE
@user_router.delete("/{id}")
def delete_user(id: str):
    try:
        db.delete_user(id)
    except db.exception.UserNotFound:
        return fastapi.Response(status_code=404, content="User not found")
    except Exception as error:
        logger.error(f'delete user {id} raise {error}')
        return fastapi.Response(status_code=500, content=str(error))
