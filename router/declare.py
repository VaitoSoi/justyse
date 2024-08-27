import logging
import os

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse

import declare
import utils

declare_router = APIRouter(prefix="/declare", tags=["declare"])
logger = logging.getLogger("justyse.router.declare")
logger.propagate = False
logger.addHandler(utils.console_handler("Declare router"))


# GET
@declare_router.get("",
                    response_model=list[str],
                    responses={
                        200: {
                            "description": "Get all declare files",
                            "content": {
                                "application/json": {
                                    "example": ["file1", "file2"]
                                }
                            }
                        }
                    })
def get_declare():
    return [file[:-5] for file in os.listdir(declare.utils.data)]


@declare_router.get("/{name}",
                    summary="Get declare file by name",
                    responses={
                        404: {"description": "File not found",
                              "content": {"application/json": {"example": {"message": "File not found"}}}}
                    })
def get_declare_file(name: str):
    try:
        return RedirectResponse(url=f"/declare/{name}.json")
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "File not found"})
    except Exception as error:
        logger.error(f'get declare {name} raise error, detail')
        logger.exception(error)
        return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)
