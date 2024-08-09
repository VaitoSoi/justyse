import typing
# import declare as declare_

from fastapi import UploadFile

import utils
from . import (
    file,
    sql,
    declare,
    exception,
    redis
)
from .declare import (
    Problems,
    Submissions,
    User,
    DBProblems,
    DBSubmissions,
    DBUser,
    UpdateProblems,
    UpdateSubmissions,
    UpdateUser
)


def get(key: str) -> typing.Callable:
    store_place = utils.config.store_place
    if store_place == "file":
        if key not in file.__dict__:
            raise NotImplementedError(f"unknown key {key}")
        return getattr(file, key)
    if store_place.startswith("sql"):
        if key not in sql.__dict__:
            raise NotImplementedError(f"unknown key {key}")
        return getattr(sql, key)
    raise ValueError(f"unknown store place {utils.config.store_place}")


__all__ = [
    "file",
    "sql",
    "redis",
    "declare",
    "exception",
    # Problems
    "Problems",
    "DBProblems",
    "UpdateProblems",
    "get_problem_ids",
    "get_problem",
    "get_problem_docs",
    "add_problem",
    "add_problem_docs",
    "add_problem_testcases",
    "update_problem",
    "update_problem_docs",
    "update_problem_testcases",
    "delete_problem",
    # Submissions
    "Submissions",
    "DBSubmissions",
    "UpdateSubmissions",
    "get_submission_ids",
    "get_submission",
    "add_submission",
    "update_submission",
    # "dump_result",
    # "get_result",
    # Users
    "User",
    "UpdateUser",
    "DBUser",
    "get_user_ids",
    "get_user_filter",
    "get_user",
    "add_user",
    "update_user",
    "delete_user"
]

"""
Problems
"""
get_problem_ids: typing.Callable[[], typing.List[str]] = get("get_problem_ids")
get_problem_filter: typing.Callable[[typing.Callable[[DBProblems], typing.Any]], list[DBProblems]] = \
    get("get_problem_filter")
get_problem: typing.Callable[[str], typing.Optional[Problems]] = get("get_problem")
get_problem_docs: typing.Callable[[str], typing.Optional[str]] = get("get_problem_docs")
add_problem: typing.Callable[[Problems], None] = get("add_problem")
add_problem_docs: typing.Callable[[str, UploadFile], None] = get("add_problem_docs")
add_problem_testcases: typing.Callable[[str, UploadFile], None] = get("add_problem_testcases")
update_problem: typing.Callable[[str, UpdateProblems], None] = get("update_problem")
update_problem_docs: typing.Callable[[str, UploadFile], None] = get("update_problem_docs")
update_problem_testcases: typing.Callable[[str, UploadFile], None] = get("update_problem_testcases")
delete_problem: typing.Callable[[str], None] = get("delete_problem")

"""
Submission
"""
get_submission_ids: typing.Callable[[], typing.List[str]] = get("get_submission_ids")
get_submission_filter: typing.Callable[[typing.Callable[[DBSubmissions], typing.Any]], list[DBSubmissions]] = \
    get("get_submission_filter")
get_submission: typing.Callable[[str], typing.Optional[Submissions]] = get("get_submission")
add_submission: typing.Callable[[Submissions], None] = get("add_submission")
update_submission: typing.Callable[[str, UpdateSubmissions], None] = get("update_submission")
# dump_result: typing.Callable[[str, list[declare_.JudgeResult]], None] = get("dump_result")
# get_result: typing.Callable[[str], list[declare_.JudgeResult]] = get("get_result")

"""
User
"""
get_user_ids: typing.Callable[[], typing.List[str]] = get("get_user_ids")
get_user_filter: typing.Callable[[typing.Callable[[DBUser], typing.Any]], list[DBUser]] = get("get_user_filter")
get_user: typing.Callable[[str], typing.Optional[User]] = get("get_user")
add_user: typing.Callable[[User], None] = get("add_user")
update_user: typing.Callable[[str, UpdateUser], None] = get("update_user")
delete_user: typing.Callable[[str], None] = get("delete_user")
