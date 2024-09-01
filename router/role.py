import logging

import fastapi

import db
import utils

role_router = fastapi.APIRouter(prefix="/role", tags=["role"])
logger = logging.getLogger("justyse.router.role")
logger.addHandler(utils.console_handler("Role router"))


# GET
@role_router.get("s",
                 summary="Get all roles",
                 response_model=list[str | dict])
def get_roles(keys: str | None = None):
    try:
        return db.get_role_ids() if keys is not None else db.get_roles(keys.split(","))

    except Exception as error:
        logger.error(f'get roles {keys} raise {error}')
        logger.exception(error)
        raise fastapi.HTTPException(status_code=500, detail=utils.InternalServerError)


@role_router.get("/{id}",
                 summary="Get role by id",
                 response_model=db.Role,
                 responses={
                     200: {"description": "Success",
                           "model": db.DBRole},
                     404: {"description": "Role not found",
                           "content": {"application/json": {"example": {"message": "Role not found"}}}},
                     500: utils.InternalServerErrorResponse
                 })
def get_role(id: str):
    try:
        return db.get_role(id)

    except db.exception.RoleNotFound:
        raise fastapi.HTTPException(status_code=404, detail={"message": "Role not found"})

    except Exception as error:
        logger.error(f'get role {id} raise {error}')
        logger.exception(error)
        raise fastapi.HTTPException(status_code=500, detail=utils.InternalServerError)


# POST
@role_router.post("",
                  summary="Add role",
                  status_code=fastapi.status.HTTP_201_CREATED,
                  response_model=db.DBRole,
                  responses={
                      201: {"description": "Success", "model": db.DBRole},
                      409: {"description": "Role already exists",
                            "content": {"application/json": {"example": {"message": "Role already exists"}}}},
                      500: utils.InternalServerErrorResponse
                  })
def add_role(role: db.Role):
    try:
        return db.add_role(role)

    except db.exception.RoleAlreadyExists:
        raise fastapi.HTTPException(status_code=409, detail={"message": "Role already exists"})

    except Exception as error:
        logger.error(f'add role {role} raise {error}')
        logger.exception(error)
        raise fastapi.HTTPException(status_code=500, detail=utils.InternalServerError)


# PATCH
@role_router.patch("/{id}",
                   summary="Update role",
                   status_code=fastapi.status.HTTP_202_ACCEPTED,
                   responses={
                       202: {"description": "Success",
                             "content": {"application/json": {"example": "updated"}}},
                       404: {"description": "Role not found",
                             "content": {"application/json": {"example": {"message": "Role not found"}}}},
                       500: utils.InternalServerErrorResponse
                   })
def update_role(id: str, role: db.Role):
    try:
        return db.update_role(id, role)

    except db.exception.RoleNotFound:
        raise fastapi.HTTPException(status_code=404, detail={"message": "Role not found"})

    except Exception as error:
        logger.error(f'update role {id} raise {error}')
        logger.exception(error)
        raise fastapi.HTTPException(status_code=500, detail=utils.InternalServerError)


# DELETE
@role_router.delete("/{id}",
                    summary="Delete role",
                    status_code=fastapi.status.HTTP_202_ACCEPTED,
                    responses={
                        202: {"description": "Success",
                              "content": {"application/json": {"example": "deleted"}}},
                        404: {"description": "Role not found",
                              "content": {"application/json": {"example": {"message": "Role not found"}}}},
                        500: utils.InternalServerErrorResponse
                    })
def delete_role(id: str):
    try:
        return db.delete_role(id)

    except db.exception.RoleNotFound:
        raise fastapi.HTTPException(status_code=404, detail={"message": "Role not found"})

    except Exception as error:
        logger.error(f'delete role {id} raise {error}')
        logger.exception(error)
        raise fastapi.HTTPException(status_code=500, detail=utils.InternalServerError)
