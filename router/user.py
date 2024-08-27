import datetime
import logging
import typing

import fastapi
import fastapi.security
import jwt

import db
import utils

user_router = fastapi.APIRouter(prefix="/user", tags=["user"])
logger = logging.getLogger("justyse.router.user")
logger.propagate = False
logger.addHandler(utils.console_handler("User router"))


# GET
@user_router.get("s",
                 summary="Get all users id",
                 response_model=list[str])
def get_users(keys: typing.Optional[str] = None):
    return db.get_user_ids() if keys is None else db.get_users(keys.split(","))


@user_router.get("/me",
                 summary="Get current user",
                 response_model=db.DBUser)
def get_me(me: typing.Annotated[db.DBUser, fastapi.Depends(utils.get_user())]):
    return me


@user_router.get("/{id}",
                 summary="Get user by id",
                 response_model=db.DBUser,
                 responses={
                     200: {"description": "Success",
                           "model": db.DBUser},
                     404: {"description": "User not found",
                           "content": {"application/json": {"example": {"message": "User not found"}}}}
                 })
def get_user(id: str):
    try:
        return db.get_user(id)

    except db.exception.UserNotFound:
        raise fastapi.HTTPException(status_code=404, detail={"message": "User not found"})

    except Exception as error:
        logger.error(f'get user {id} raise {error}')
        raise fastapi.HTTPException(status_code=500, detail=str(error))


# POST
@user_router.post("",
                  summary="Add user",
                  status_code=fastapi.status.HTTP_201_CREATED,
                  response_model=db.DBUser,
                  responses={
                      201: {"description": "Success",
                            "content": {"application/json": {"example": "added"}}},
                      409: {"description": "User already exist",
                            "content": {"application/json": {"example": {"message": "User already exist"}}}}

                  })
def add_user(user: db.User, request: fastapi.Request):
    creator: db.DBUser = db.declare.DefaultUser
    auth = request.headers.get("Authorization")
    if auth:
        creator = utils.get_user(auth.split(" ")[1])

    try:
        return db.add_user(user, creator)

    except db.exception.UserAlreadyExist:
        raise fastapi.HTTPException(status_code=409, detail={"message": "User already exist"})

    except db.exception.PermissionDenied as error:
        raise fastapi.HTTPException(
            status_code=403,
            detail={
                "message": "Permission denied",
                "code": "permission_denied",
                "detail": {
                    "missing": error.args[0]
                }
            }
        )

    except db.exception.RoleNotFound as error:
        raise fastapi.HTTPException(
            status_code=404,
            detail={
                "message": "Role not found",
                "code": "role_not_found",
                "detail": {
                    "role": error.args[0]
                }
            }
        )

    except Exception as error:
        logger.error(f'add user {user.id} raise {error}')
        raise fastapi.HTTPException(status_code=500, detail=str(error))


@user_router.post("/login",
                  summary="Login user",
                  responses={
                      400: {"description": "expires_delta too long",
                            "content": {"application/json": {"example": {"message": "expires_delta too long"}}}},
                      404: {"description": "User not found",
                            "content": {"application/json": {"example": {"message": "User not found"}}}},
                      401: {"description": "Password incorrect",
                            "content": {"application/json": {"example": {"message": "Password incorrect"}}}}
                  })
def get_token(form_data: typing.Annotated[fastapi.security.OAuth2PasswordRequestForm, fastapi.Depends()],
              expires_delta: datetime.timedelta = datetime.timedelta(days=7)):
    if expires_delta > datetime.timedelta(days=14):
        raise fastapi.HTTPException(status_code=400, detail={"message": "expires_delta too long"})
    user = db.get_user_filter(lambda x: x.name == form_data.username)
    if len(user) == 0:
        raise fastapi.HTTPException(status_code=404, detail={"message": "User not found"})
    user = user[0]
    if not utils.check_hash(form_data.password, user.password):
        raise fastapi.HTTPException(status_code=401, detail={"message": "Password incorrect"})
    token = jwt.encode(
        {"user": user.id, "exp": datetime.datetime.now() + expires_delta},
        utils.signature,
        algorithm="HS256"
    )
    return {"access_token": token, "token_type": "bearer"}


@user_router.post("/refresh",
                  summary="Refresh token",
                  responses={
                      400: {"description": "expires_delta too long",
                            "content": {"application/json": {"example": {"message": "expires_delta too long"}}}}
                  })
def refresh_token(token: str = fastapi.Depends(utils.oauth2_scheme),
                  expires_delta: datetime.timedelta = datetime.timedelta(days=7)):
    if expires_delta > datetime.timedelta(days=14):
        raise fastapi.HTTPException(status_code=400, detail={"message": "expires_delta too long"})
    decoded = utils.decode_jwt(token, verify_exp=False)
    user = db.get_user(decoded["user"])
    token = jwt.encode(
        {"user": user.id, "exp": datetime.datetime.now() + expires_delta},
        utils.signature,
        algorithm="HS256"
    )
    return {"access_token": token, "token_type": "bearer"}


# PATCH
@user_router.patch("/{id}",
                   summary="Update user",
                   responses={
                       404: {"description": "User not found",
                             "content": {"application/json": {"example": {"message": "User not found"}}}}
                   })
def update_user(id: str, user: db.User):
    try:
        db.update_user(id, user)
    except db.exception.UserNotFound:
        raise fastapi.HTTPException(status_code=404, detail={"message": "User not found"})
    except Exception as error:
        logger.error(f'update user {id} raise {error}')
        raise fastapi.HTTPException(status_code=500, detail=str(error))


# DELETE
@user_router.delete("/{id}",
                    summary="Delete user",
                    responses={
                        404: {"description": "User not found",
                              "content": {"application/json": {"example": {"message": "User not found"}}}}
                    })
def delete_user(id: str):
    try:
        db.delete_user(id)
    except db.exception.UserNotFound:
        raise fastapi.HTTPException(status_code=404, detail={"message": "User not found"})
    except Exception as error:
        logger.error(f'delete user {id} raise {error}')
        raise fastapi.HTTPException(status_code=500, detail=str(error))
