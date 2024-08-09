import logging

from fastapi import status, Response, UploadFile, APIRouter
from fastapi.responses import RedirectResponse

import db

problem_router = APIRouter(prefix="/problem", tags=["problem"])
logger = logging.getLogger("uvicorn.error")


# GET
@problem_router.get("s/")
def get_problems():
    return db.get_problem_ids()


@problem_router.get("/{id}")
def get_problem(id: str, response: Response):
    try:
        return db.get_problem(id)
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'get problem {id} raise {error}')
        return error


@problem_router.get("/{id}/docs")
def get_problem_docs(id: str, response: Response):
    try:
        docs = db.get_problem_docs(id)
        return RedirectResponse(url=f"/file/{docs}")
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except db.exception.ProblemDocsNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem docs not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'get problem docs {id} raise {error}')
        return error


# POST
@problem_router.post("/")
def add_problem(problem: db.Problems, response: Response):
    try:
        db.add_problem(problem)
        return "Added!"
    except db.exception.ProblemAlreadyExisted:
        response.status_code = status.HTTP_409_CONFLICT
        return f"problem {problem.id} already exists"
    except db.exception.LanguageNotSupport as error:
        response.status_code = status.HTTP_501_NOT_IMPLEMENTED
        return f"language {error.args[0]} not support"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'add problem {id} raise {error}')
        return error


@problem_router.post("/{id}/docs")
def add_problem_docs(id: str, file: UploadFile, response: Response):
    try:
        db.add_problem_docs(id, file)
        return "added"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except db.exception.ProblemDocsAlreadyExist:
        response.status_code = status.HTTP_409_CONFLICT
        return "problem docs already exists"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'add problem docs {id} raise {error}')
        return error


@problem_router.post("/{id}/testcases")
def add_problem_testcases(id: str, file: UploadFile, response: Response):
    try:
        db.add_problem_testcases(id, file)
        return "added"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'add problem testcase {id} raise {error}')
        return error


# PATCH
@problem_router.patch("/{id}")
def problem_update(id: str, problem: db.UpdateProblems, response: Response):
    try:
        db.update_problem(id, problem)
        return "updated"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except db.exception.NothingToUpdate:
        response.status_code = status.HTTP_304_NOT_MODIFIED
        return "nothing to update"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'update problem {id} raise {error}')
        return error


@problem_router.patch("/{id}/docs")
def problem_docs_update(id: str, file: UploadFile, response: Response):
    try:
        db.update_problem_docs(id, file)
        return "updated"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except db.exception.ProblemDocsNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem docs not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'update problem docs {id} raise {error}')
        return error


@problem_router.patch("/{id}/testcases")
def problem_testcases_update(id: str, file: UploadFile, response: Response):
    try:
        db.update_problem_testcases(id, file)
        return "updated"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'update problem testcase {id} raise {error}')
        return error


# DELETE
@problem_router.delete("/{id}")
def problem_delete(id: str, response: Response):
    try:
        db.delete_problem(id)
        return "deleted"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'delete problem {id} raise {error}')
        return error
