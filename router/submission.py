import logging

from fastapi import APIRouter, HTTPException, status, Depends

import db
import utils

submission_router = APIRouter(prefix="/submission", tags=["submission"])
logger = logging.getLogger("justyse.router.submission")
logger.propagate = False
logger.addHandler(utils.console_handler("Submission ro."))


# GET
@submission_router.get("s",
                       summary="Get all submissions",
                       response_model=list[str | dict],
                       dependencies=[Depends(utils.has_permission("submissions:view"))],
                       responses={
                           200: {
                               "description": "Success",
                               "content": {
                                   "application/json": {
                                       "example": ["id1", "id2"]
                                   }
                               }
                           },
                           400: {
                               "description": "Invalid filter",
                               "content": {
                                   "application/json": {
                                       "example": {
                                           "message": "Invalid filter",
                                           "code": "invalid_filter",
                                           "detail": {
                                               "filter": "filter"
                                           }
                                       }
                                   }
                               }
                           }
                       })
def submissions(keys: str | None = None, filter: str | None = None):
    try:
        if keys:
            return db.get_submissions(keys.split(","))

        elif filter:
            filters = filter.split(",")

            def filter_(submission: db.DBSubmissions | db.sql.SQLSubmissions):
                conditions = []

                for f in filters:
                    item, value = f.split(":")

                    if item == "problem":
                        conditions.append(submission.problem == value)

                    elif item == "lang":
                        conditions.append(submission.lang == value)

                    elif item == "compiler":
                        conditions.append(submission.compiler == value)

                    elif item == "by":
                        conditions.append(submission.by == value)

                    elif item == "code":
                        conditions.append(submission.code == value)

                    else:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={
                                "message": "Invalid filter",
                                "code": "invalid_filter",
                                "detail": {
                                    "filter": f
                                }
                            }
                        )

                    return db.operator.and_(*conditions)

            res = [item.model_dump() for item in db.get_submission_filter(filter_)]

            return utils.filter_keys(res, keys.split(',')) if keys else res

        else:
            return db.get_submission_ids()

    except Exception as error:
        logger.error(f'get submissions raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error))


@submission_router.get("/{id}",
                       summary="Get submission by id",
                       response_model=db.DBSubmissions,
                       dependencies=[Depends(utils.has_permission("submission:view"))],
                       responses={
                           200: {
                               "description": "Success",
                               "model": db.DBSubmissions
                           },
                           404: {
                               "description": "Submission not found",
                               "content": {
                                   "application/json": {
                                       "example": {
                                           "message": "Submission not found",
                                           "code": "submission_not_found"
                                       }
                                   }
                               }
                           }
                       })
def submission(id: str):
    try:
        return db.get_submission(id)

    except db.exception.SubmissionNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Submission not found", "code": "submission_not_found"}
        )

    except Exception as error:
        logger.error(f'get submission {id} raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error))


# @submission_router.get("/{id}/status",
#                        summary="Get submission status by id",
#                        response_model=db.declare.SubmissionResult,
#                        dependencies=[Depends(utils.has_permission("submission:view"))],
#                        responses={
#                            200: {
#                                "description": "Success",
#                                "model": db.declare.SubmissionResult
#                            },
#                            404: {
#                                "description": "Submission not found",
#                                "content": {
#                                    "application/json": {
#                                        "example": {
#                                            "message": "Submission not found",
#                                            "code": "submission_not_found"
#                                        }
#                                    }
#                                }
#                            },
#                        })
# def submission_status(id: str):
#     try:
#         return db.get_submission_status(id)
#
#     except db.exception.SubmissionNotFound:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail={"message": "Submission not found", "code": "submission_not_found"}
#         )
#
#     except Exception as error:
#         logger.error(f'get submission {id} status raise error, detail')
#         logger.exception(error)
#         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(error))


# POST
@submission_router.post("",
                        summary="Add submission",
                        status_code=status.HTTP_201_CREATED,
                        response_model=db.DBSubmissions,
                        responses={
                            201: {
                                "description": "Success",
                                "model": db.DBSubmissions
                            },
                            404: {
                                "description": "Problem or User not found",
                                "content": {
                                    "application/json": {
                                        "examples": {
                                            "Problem not found": {
                                                "summary": "Problem not found",
                                                "value": {
                                                    "message": "Problem not found",
                                                    "code": "problem_not_found"
                                                }
                                            },
                                            "User not found": {
                                                "summary": "User not found",
                                                "value": {
                                                    "message": "User not found",
                                                    "code": "user_not_found"
                                                }
                                            }
                                        }
                                    }
                                }
                            },
                            406: {
                                "description": "Language not accept",
                                "content": {
                                    "application/json":
                                        {
                                            "example": {
                                                "message": "Language <language>:<version> not accept",
                                                "code": "language_not_accept"
                                            }
                                        }
                                }
                            },
                            409: {
                                "description": "Conflict",
                                "content": {
                                    "application/json": {
                                        "examples": {
                                            "Submission already exists": {
                                                "summary": "Submission already exists",
                                                "value": {
                                                    "message": "Submission already exists",
                                                    "code": "submission_already_exist"
                                                }
                                            },
                                            "Conflict user id": {
                                                "summary": "Conflict user id",
                                                "value": {
                                                    "message": "Conflict user id",
                                                    "code": "conflict_user_id"
                                                }
                                            }
                                        }
                                    }
                                }
                            },
                            501: {
                                "description": "Language or Compiler not support",
                                "content": {
                                    "application/json": {
                                        "examples": {
                                            "language_not_support": {
                                                "summary": "Language",
                                                "value": {
                                                    "message": "Language <language>:<version> not support",
                                                    "code": "language_not_support"
                                                }
                                            },
                                            "compiler_not_support": {
                                                "summary": "Compiler",
                                                "value": {
                                                    "message": "Compiler <compiler>:<version> not support",
                                                    "code": "compiler_not_support"
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        })
def add_submission(submission: db.Submissions, user: db.DBUser = Depends(utils.has_permission("submission:add"))):
    try:
        # if submission.by != user.id:
        #     raise HTTPException(
        #         status_code=status.HTTP_409_CONFLICT,
        #         detail={
        #             "message": "Conflict user id",
        #             "code": "conflict_user_id",
        #             "detail": {
        #                 "expected": user.id,
        #                 "got": submission.by
        #             }
        #         }
        #     )
        return db.add_submission(submission, user)

    except db.exception.UserNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "User not found",
                "code": "user_not_found"
            }
        )

    except db.exception.ProblemNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Problem not found",
                "code": "problem_not_found"
            })

    except db.exception.SubmissionAlreadyExist:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Submission already exists",
                "code": "submission_already_exist"
            })

    except db.exception.LanguageNotSupport as error:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "message": f"Language {error.args[0][0]}:{error.args[0][1]} not support",
                "code": "language_not_support"
            }
        )

    except db.exception.LanguageNotAccept as error:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail={
                "message": f"Language {error.args[0][0]}:{error.args[0][1]} not accept",
                "code": "language_not_accept"
            }
        )

    except db.exception.CompilerNotSupport as error:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "message": f"Compiler {error.args[0][0]}:{error.args[0][1]} not support",
                "code": "compiler_not_support"
            }
        )

    except HTTPException as error:
        raise error

    except Exception as error:
        logger.error(f'create submission {submission.id} raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)
