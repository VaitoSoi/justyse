import logging

from fastapi import APIRouter, Response, status

import db

submission_router = APIRouter(prefix="/submission", tags=["submission"])
logger = logging.getLogger("uvicorn.error")


# GET
@submission_router.get("s/", tags=["submission"])
def submissions():
    return db.get_submission_ids()


@submission_router.get("/{id}", tags=["submission"])
def submission(id: str, response: Response):
    try:
        return db.get_submission(id)

    except db.exception.SubmissionNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'get problem {id} raise {error}')
        return error


# POST
@submission_router.post("/", tags=["submission"])
def add_submission(submission: db.Submissions, response: Response):
    try:
        db.add_submission(submission)
        return "Added!"
    except db.exception.ProblemNotFound:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "problem not found"
    except db.exception.SubmissionAlreadyExist:
        response.status_code = status.HTTP_409_CONFLICT
        return "submission already exists"
    except db.exception.LanguageNotSupport as error:
        response.status_code = status.HTTP_501_NOT_IMPLEMENTED
        return f"language {error.args[0][0]}:{error.args[0][1]} not support"
    except db.exception.LanguageNotAccept as error:
        response.status_code = status.HTTP_406_NOT_ACCEPTABLE
        return f"language {error.args[0][0]}:{error.args[0][1]} not accept"
    except db.exception.CompilerNotSupport as error:
        response.status_code = status.HTTP_501_NOT_IMPLEMENTED
        return f"compiler {error.args[0][0]}:{error.args[0][1]} not support"
    except Exception as error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        logger.error(f'create problem {submission.id} raise {error}')
        return error
