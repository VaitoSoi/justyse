import csv
import logging

from fastapi import status, HTTPException, UploadFile, APIRouter, Depends
from fastapi.responses import RedirectResponse, FileResponse

import db
import utils

problem_router = APIRouter(prefix="/problem", tags=["problem"])
logger = logging.getLogger("justyse.router.problem")
logger.propagate = False
logger.addHandler(utils.console_handler("Problem router"))


# GET
@problem_router.get("s",
                    summary="Get all problems",
                    response_model=list[str | dict],
                    # dependencies=[],
                    responses={
                        200: {
                            "description": "Success",
                            "content": {
                                "application/json": {
                                    "examples": {
                                        "Key is None or an empty string": {"values": ["id1", "id2"]},
                                        "Key is not None": {"value": [{}]}
                                    }
                                }
                            }
                        },
                        400: {
                            "description": "Invalid key",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "message": "Invalid key",
                                        "code": "invalid_key",
                                        "key": "key"
                                    }
                                }
                            }
                        },
                    })
def get_problems(
        keys: str | None = None,
        filter: str | None = None,
        user: db.DBUser = Depends(utils.has_permission("problems:view"))
):
    try:
        if filter:
            filters = filter.split(",")

            def filter_(problem: db.DBProblems | db.sql.SQLProblems):
                conditions = [db.operator.or_(db.operator.contain(problem.roles, "@everyone"),
                                              *[db.operator.contain(problem.roles, role) for role in user.roles])]

                for f in filters:
                    item, value = f.split(":")
                    if item == "id":
                        conditions.append(problem.id == value)
                    elif item == "title":
                        conditions.append(problem.title == value)
                    # elif item == "description":
                    #     conditions.append(problem.description == value)
                    elif item == "total_testcases":
                        conditions.append(problem.total_testcases == int(value))
                    elif item == "test_type":
                        conditions.append(problem.test_type == value)
                    elif item == "test_name":
                        conditions.append(problem.test_name == value.split(';'))
                    elif item == "accept_language":
                        conditions.append(problem.accept_language == value.split(';'))
                    # elif item == "limit":
                    #     conditions.append(problem.limit == value)
                    # elif item == "mode":
                    #     conditions.append(problem.mode == value)
                    elif item == "point_per_testcase":
                        conditions.append(problem.point_per_testcase == float(value))
                    # elif item == "judger":
                    #     conditions.append(problem.judger == value)
                    elif item == "roles":
                        conditions.append(problem.roles == value.split(';'))
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail={
                                "message": "Invalid filter",
                                "code": "invalid_filter",
                                "detail": {
                                    "filter": filter
                                }
                            }
                        )

                return conditions[0] if len(conditions) == 1 else db.operator.and_(*conditions)

            res = [item.model_dump() for item in db.get_problem_filter(filter_)]

            return utils.filter_keys(res, keys.split(',')) if keys else res

        else:
            def filter_(problem: db.DBProblems | db.sql.SQLProblems):
                return db.operator.or_(db.operator.contain(problem.roles, "@everyone"),
                                       *[db.operator.contain(problem.roles, role) for role in user.roles])

            if keys:
                return utils.filter_keys(db.get_problem_filter(filter_), keys.split(','))

            else:
                return [item["id"] for item in utils.filter_keys(db.get_problem_filter(filter_), ["id"])]

    except KeyError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail={
                                "message": "Invalid key",
                                "code": "invalid_key",
                                "key": error.args[0]
                            })

    except AttributeError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail={
                                "message": "Invalid key",
                                "code": "invalid_key",
                                "error": error.args[0]
                            })

    except Exception as error:
        logger.error('get all problems raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)


@problem_router.get("/{id}",
                    summary="Get problem by id",
                    response_model=db.DBProblems,
                    dependencies=[Depends(utils.has_permission("problem:view"))],
                    responses={
                        200: {
                            "description": "Success",
                            "model": db.DBProblems
                        },
                        404: {
                            "description": "Problem not found",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "message": "Problem not found",
                                        "code": "problem_not_found",
                                    }
                                }
                            }
                        },
                    })
def get_problem(id: str, user: db.DBUser = Depends(utils.has_permission("problem:view"))):
    try:
        problem = db.get_problem(id)
        utils.viewable(problem, user)
        return problem

    except db.exception.ProblemNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Problem not found", "code": "problem_not_found"}
        )

    except HTTPException as error:
        raise error

    except Exception as error:
        logger.error(f'get problem {id} raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)


@problem_router.get("/{id}/docs",
                    summary="Get problem docs by id",
                    # dependencies=[Depends(utils.has_permission("problem:view"))],
                    responses={
                        404: {
                            "description": "Problem or Problem docs not found",
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
                                        "Problem docs not found": {
                                            "summary": "Problem docs not found",
                                            "value": {
                                                "message": "Problem docs not found",
                                                "code": "problem_docs_not_found"
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    })
def get_problem_docs(id: str, redirect: bool = True, user: db.DBUser = Depends(utils.has_permission("problem:view"))):
    try:
        utils.viewable(db.get_problem(id), user)
        docs = db.get_problem_docs(id)
        if redirect:
            return RedirectResponse(url=f"/file/{docs}")
        else:
            return f"/file/{docs}"

    except db.exception.ProblemNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Problem not found", "code": "problem_not_found"}
        )

    except db.exception.ProblemDocsNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Problem docs not found", "code": "problem_docs_not_found"}
        )

    except HTTPException as error:
        raise error

    except Exception as error:
        logger.error(f'get problem docs {id} raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)


@problem_router.get("/{id}/statics",
                    summary="Get problem statics by id",
                    response_model=list[db.DBSubmissions] | str,
                    dependencies=[Depends(utils.has_permission("problem:view"))],
                    responses={
                        200: {
                            "description": "Success",
                            "model": list[db.DBSubmissions]
                        },
                        404: {
                            "description": "Problem not found",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "message": "Problem not found",
                                        "code": "problem_not_found"
                                    }
                                }
                            }
                        }
                    })
def get_problem_statics(id: str,
                        to_file: bool = False,
                        redirect: bool = False,
                        download: bool = False,
                        user: db.DBUser = Depends(utils.has_permission("problem:view"))):
    try:
        utils.viewable(db.get_problem(id), user)
        statics = []
        for uid in db.get_user_ids():
            submissions = db.get_submission_filter(
                lambda submission: db.operator.and_(submission.problem == id,
                                                    submission.by == uid,
                                                    submission.result != None)
            )
            if submissions:
                submissions.sort(key=lambda x: (x.result['point'], x.result['time'], x.result['memory']), reverse=True)
                statics.append(submissions[0])

        if to_file:
            with open(f"{db.declare.files_dir}/{id}.csv", "w") as file:
                writer = csv.DictWriter(file, fieldnames=["id", "user", "status", "time", "memory", "point"])
                writer.writeheader()
                for static in statics:
                    writer.writerow({
                        "id": static.id,
                        "user": static.by,
                        "status": static.result['status'],
                        "time": static.result['time'],
                        "memory": static.result['memory'],
                        "point": static.result['point']
                    })

            if download:
                return FileResponse(f"{db.declare.files_dir}/{id}.csv", filename=f"{id}.csv")
            if redirect:
                return RedirectResponse(url=f"/file/{id}.csv")
            else:
                return f"/file/{id}.csv"
        else:
            return statics

    except db.exception.ProblemNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Problem not found", "code": "problem_not_found"}
        )

    except HTTPException as error:
        raise error

    except Exception as error:
        logger.error(f'get problem statics {id} raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)


@problem_router.get("s/statics",
                    summary="Get all problems statics",
                    response_model=list[list[int | str]] | str,
                    dependencies=[Depends(utils.has_permission("problems:view"))],
                    responses={
                        200: {
                            "description": "Success"
                        }
                    })
def get_problems_statics(to_file: bool = True, redirect: bool = True, download: bool = False):
    try:
        problems = db.get_problem_ids()
        users = db.get_user_ids()
        statics: list[list[int]] = [[db.get_user(id).name, 0] + ['-'] * len(problems) for id in users]
        for i in range(len(users)):
            for j in range(len(problems)):
                submissions = db.get_submission_filter(
                    lambda x: db.operator.and_(x.problem == problems[j], x.by == users[i])
                )
                if submissions:
                    submissions.sort(key=lambda x: (x.result['point'], x.result['time'], x.result['memory']),
                                     reverse=True)
                    statics[i][j + 2] = submissions[0].result['point']

        for i in range(len(statics)):
            statics[i][1] = sum([point if point != '-' else 0 for point in statics[i][2:]])

        statics.sort(key=lambda x: x[1], reverse=True)

        if to_file:
            with open(f"{db.declare.files_dir}/statics.csv", "w") as file:
                writer = csv.DictWriter(file, fieldnames=["username", "total"] + problems)
                writer.writeheader()
                for static in statics:
                    writer.writerow({
                        "username": static[0],
                        "total": static[1],
                        **{problems[j]: static[j + 2] for j in range(len(problems))}
                    })

            if download:
                return FileResponse(f"{db.declare.files_dir}/statics.csv", filename="statics.csv")
            if redirect:
                return RedirectResponse(url="/file/statics.csv")
            else:
                return "/file/statics.csv"
        else:
            return [["username", "total"] + problems] + statics

    except db.exception.ProblemNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Problem not found", "code": "problem_not_found"}
        )

    except Exception as error:
        logger.error(f'get all problems statics raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)


# POST
@problem_router.post("",
                     summary="Add problem",
                     status_code=status.HTTP_201_CREATED,
                     response_model=db.DBProblems,
                     responses={
                         201: {
                             "description": "Success",
                             "model": db.DBProblems
                         },
                         409: {
                             "description": "Problem already exists",
                             "content": {
                                 "application/json": {
                                     "example": {
                                         "message": "Problem already exists",
                                         "code": "problem_already_exists"
                                     }
                                 }
                             }
                         },
                         400: {
                             "description": "Invalid judger",
                             "content": {
                                 "application/json": {
                                     "example": {
                                         "message": "Invalid judger",
                                         "code": "invalid_judger"
                                     }
                                 }
                             }
                         },
                         501: {
                             "description": "Language or Test type not supported",
                             "content": {
                                 "application/json": {
                                     "examples": {
                                         "Language not supported": {
                                             "message": "Language <language>:<version> not supported",
                                             "code": "language_not_supported"
                                         },
                                         "Test type not supported": {
                                             "message": "Test type not supported",
                                             "code": "test_type_not_supported"
                                         }
                                     }
                                 }
                             }
                         }
                     })
def add_problem(problem: db.Problems, user: db.DBUser = Depends(utils.has_permission("problem:add"))):
    try:
        return db.add_problem(problem, user)

    except db.exception.ProblemAlreadyExisted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Problem already exists", "code": "problem_already_exists"}
        )

    except db.exception.LanguageNotSupport as error:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "message": f"Language {error.args[0][0]}:{error.args[0][1]} not supported",
                "code": "language_not_supported"
            }
        )

    except db.exception.InvalidProblemJudger:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Invalid judger", "code": "invalid_judger"}
        )

    except db.exception.TestTypeNotSupport:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={"message": "Test type not supported", "code": "test_type_not_supported"}
        )

    except Exception as error:
        logger.error(f'add problem {problem.id} raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)


@problem_router.post("/{id}/docs",
                     summary="Add problem docs",
                     status_code=status.HTTP_201_CREATED,
                     dependencies=[Depends(utils.has_permission("problem:add"))],
                     responses={
                         201: {
                             "description": "Success",
                             "content": {
                                 "application/json": {
                                     "example": {"message": "added"}
                                 }
                             }
                         },
                         404: {
                             "description": "Problem not found",
                             "content": {
                                 "application/json": {
                                     "example": {
                                         "message": "Problem not found",
                                         "code": "problem_not_found"
                                     }
                                 }
                             }
                         },
                         409: {
                             "description": "Problem docs already exists",
                             "content": {
                                 "application/json": {
                                     "example": {
                                         "message": "Problem docs already exists",
                                         "code": "problem_docs_already_exists"
                                     }
                                 }
                             }
                         }
                     })
def add_problem_docs(id: str, file: UploadFile):
    try:
        db.add_problem_docs(id, file)
        return {"message": "added"}

    except db.exception.ProblemNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Problem not found", "code": "problem_not_found"}
        )

    except db.exception.ProblemDocsAlreadyExist:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "Problem docs already exists", "code": "problem_docs_already_exists"}
        )

    except Exception as error:
        logger.error(f'add problem docs {id} raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)


@problem_router.post("/{id}/testcases",
                     summary="Add problem testcases",
                     status_code=status.HTTP_201_CREATED,
                     dependencies=[Depends(utils.has_permission("problem:add"))],
                     responses={
                         201: {
                             "description": "Success",
                             "content": {
                                 "application/json": {
                                     "example": {
                                         "message": "added"
                                     }
                                 }
                             }
                         },
                         404: {
                             "description": "Problem not found",
                             "content": {
                                 "application/json": {
                                     "example": {
                                         "message": "Problem not found",
                                         "code": "problem_not_found"
                                     }
                                 }
                             }
                         },
                         400: {
                             "description": "Invalid testcase extension",
                             "content": {
                                 "application/json": {
                                     "examples": {
                                         "Invalid testcase extension": {
                                             "message": "Invalid testcase extension",
                                             "code": "invalid_testcase_extension"
                                         },
                                         "Invalid testcase count": {
                                             "message": "Invalid testcase count, "
                                                        "expected {expected_inp} inp(s) and out(s), "
                                                        "got {got_inp} inp(s), {got_out} out(s)",
                                             "code": "invalid_testcase_count"
                                         }
                                     }
                                 }
                             }
                         },
                         409: {
                             "description": "Problem testcase already exists",
                             "content": {
                                 "application/json": {
                                     "example": {
                                         "message": "Problem testcase already exists",
                                         "code": "problem_testcase_already_exists"
                                     }
                                 }
                             }
                         }
                     })
def add_problem_testcases(id: str, file: UploadFile):
    try:
        db.add_problem_testcases(id, file)
        return {"message": "added"}

    except db.exception.ProblemNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "message": "Problem not found",
            "code": "problem_not_found"
        })

    except db.exception.ProblemTestcaseAlreadyExist:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "message": "Problem testcase already exists",
            "code": "problem_testcase_already_exists"
        })

    except db.exception.InvalidTestcaseExtension:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={
            "message": "Invalid testcase extension",
            "code": "invalid_testcase_ext"
        })

    except db.exception.InvalidTestcaseCount as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={
            "message": f"Invalid testcase count, expected {error.args[0]} inp(s) and out(s), "
                       f"got {error.args[1][1]} inp(s), {error.args[1][1]} out(s)",
            "code": "invalid_testcase_count"
        })

    except Exception as error:
        logger.error(f'add problem testcase {id} raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)


# PATCH
@problem_router.patch("/{id}",
                      summary="Update problem",
                      response_model=db.DBProblems,
                      status_code=status.HTTP_202_ACCEPTED,
                      dependencies=[Depends(utils.has_permission("problem:edit"))],
                      responses={
                          202: {
                              "description": "Success",
                              "model": db.DBProblems
                          },
                          404: {
                              "description": "Problem not found",
                              "content": {
                                  "application/json": {
                                      "example": {
                                          "message": "Problem not found",
                                          "code": "problem_not_found"
                                      }
                                  }
                              }
                          },
                          400: {
                              "description": "Invalid testcase extension",
                              "content": {
                                  "application/json": {
                                      "examples": {
                                          "Invalid testcase extension": {
                                              "message": "Invalid testcase extension",
                                              "code": "invalid_testcase_extension"
                                          },
                                          "Invalid testcase count": {
                                              "message": "Invalid testcase count, "
                                                         "expected {expected_inp} inp(s) and out(s), "
                                                         "got {got_inp} inp(s), {got_out} out(s)",
                                              "code": "invalid_testcase_count"
                                          }
                                      }
                                  }
                              }
                          },
                          304: {
                              "description": "Nothing to update",
                              "content": {
                                  "application/json": {
                                      "example": {
                                          "message": "Nothing to update"
                                      }
                                  }
                              }
                          }
                      })
def problem_update(id: str, problem: db.UpdateProblems):
    try:
        return db.update_problem(id, problem)

    except db.exception.ProblemNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={
            "message": "Problem not found",
            "code": "problem_not_found"
        })

    except db.exception.ProblemTestcaseAlreadyExist:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
            "message": "Problem testcase already exists",
            "code": "problem_testcase_already_exists"
        })

    except db.exception.InvalidTestcaseExtension:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={
            "message": "Invalid testcase extension",
            "code": "invalid_testcase_ext"
        })

    except db.exception.InvalidTestcaseCount as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={
            "message": f"Invalid testcase count, expected {error.args[0]} inp(s) and out(s), "
                       f"got {error.args[1][1]} inp(s), {error.args[1][1]} out(s)",
            "code": "invalid_testcase_count"
        })

    except Exception as error:
        logger.error(f'update problem {id} raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)


@problem_router.patch("/{id}/docs",
                      summary="Update problem docs",
                      status_code=status.HTTP_202_ACCEPTED,
                      dependencies=[Depends(utils.has_permission("problem:edit"))],
                      responses={
                          202: {
                              "description": "Success",
                              "content": {
                                  "application/json": {
                                      "example": {
                                          "message": "updated"
                                      }
                                  }
                              }
                          },
                          404: {
                              "description": "Problem not found",
                              "content": {
                                  "application/json": {
                                      "example": {
                                          "message": "Problem not found",
                                          "code": "problem_not_found"
                                      }
                                  }
                              }
                          },
                          304: {
                              "description": "Nothing to update",
                              "content": {
                                  "application/json": {
                                      "example": {
                                          "message": "Nothing to update"
                                      }
                                  }
                              }
                          }
                      })
def problem_docs_update(id: str, file: UploadFile):
    try:
        db.update_problem_docs(id, file)
        return {"message": "updated"}

    except db.exception.ProblemNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Problem not found", "code": "problem_not_found"}
        )

    except db.exception.ProblemDocsNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"message": "Problem docs not found"})

    except Exception as error:
        logger.error(f'update problem docs {id} raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)


@problem_router.patch("/{id}/testcases",
                      summary="Update problem testcases",
                      status_code=status.HTTP_202_ACCEPTED,
                      dependencies=[Depends(utils.has_permission("problem:edit"))],
                      responses={
                          202: {
                              "description": "Success",
                              "content": {
                                  "application/json": {
                                      "example": {
                                          "message": "updated"
                                      }
                                  }
                              }
                          },
                          404: {
                              "description": "Problem not found",
                              "content": {
                                  "application/json": {
                                      "example": {
                                          "message": "Problem not found",
                                          "code": "problem_not_found"
                                      }
                                  }
                              }
                          },
                          304: {
                              "description": "Nothing to update",
                              "content": {
                                  "application/json": {
                                      "example": {
                                          "message": "Nothing to update"
                                      }
                                  }
                              }
                          }
                      })
def problem_testcases_update(id: str, file: UploadFile):
    try:
        db.update_problem_testcases(id, file)
        return {"message": "updated"}

    except db.exception.ProblemNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Problem not found", "code": "problem_not_found"}
        )

    except db.exception.InvalidTestcaseExtension:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={
            "message": "Invalid testcase extension",
            "code": "invalid_testcase_ext"
        })

    except db.exception.InvalidTestcaseCount as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={
            "message": f"Invalid testcase count, expected {error.args[0]} inp(s) and out(s), "
                       f"got {error.args[1][1]} inp(s), {error.args[1][1]} out(s)",
            "code": "invalid_testcase_count"
        })

    except Exception as error:
        logger.error(f'update problem testcase {id} raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)


# DELETE
@problem_router.delete("/{id}",
                       status_code=status.HTTP_202_ACCEPTED,
                       summary="Delete problem",
                       dependencies=[Depends(utils.has_permission("problem:delete"))],
                       responses={
                           202: {
                               "description": "Success",
                               "content": {
                                   "application/json": {
                                       "example": {"message": "deleted"}
                                   }
                               }
                           },
                           404: {
                               "description": "Problem not found",
                               "content": {
                                   "application/json": {
                                       "example": {
                                           "message": "Problem not found",
                                           "code": "problem_not_found"
                                       }
                                   }
                               }
                           }
                       })
def problem_delete(id: str):
    try:
        db.delete_problem(id)
        return {"message": "deleted"}

    except db.exception.ProblemNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": "Problem not found", "code": "problem_not_found"}
        )

    except Exception as error:
        logger.error(f'delete problem {id} raise error, detail')
        logger.exception(error)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=utils.InternalServerError)
