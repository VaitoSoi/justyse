import logging
import os

from fastapi import APIRouter, Response, status
from fastapi.responses import RedirectResponse

import declare

declare_router = APIRouter(prefix="/declare", tags=["declare"])
logger = logging.getLogger("uvicorn.error")


# GET
@declare_router.get("/", tags=["declare"])
def get_declare():
    return [file[:-5] for file in os.listdir(declare.utils.data)]


@declare_router.get("/{name}", tags=["declare"])
def get_declare_file(name: str, response: Response):
    try:
        return RedirectResponse(url=f"/declare/{name}.json")
    except FileNotFoundError:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "file not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'get declare {name} raise {error}')
        return error
