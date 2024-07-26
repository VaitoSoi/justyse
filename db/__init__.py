import json
import typing

from fastapi import UploadFile

import utils
from . import (
    file,
    # sql,
    declare,
    exception
)
from .declare import Problems, Submissions


def get(key: str) -> typing.Callable:
    match utils.config.store_place:
        case "file":
            return getattr(file, key)

        # case "sql":
        #     return getattr(sql, key)

        case _:
            raise ValueError(f"unknown store place {utils.config.store_place}")


def sql_typing(callable: typing.Any) -> typing.Callable[[typing.Any], typing.Any]:
    return lambda dict: callable(
        **{
            key: json.dumps(value, separators=(",", ":"))
            if isinstance(value, dict) or isinstance(value, int) else
            value
            for key, value in dict.model_dump().items()
        }
    )


__all__ = [
    "file",
    "sql",
    "declare",
    "exception",
    # Problems
    "Problems",
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
    "get_submission_ids",
    "get_submission",
    "add_submission",
]

"""
Problems
"""
get_problem_ids: typing.Callable[[], typing.List[str]] = get("get_problem_ids")
get_problem: typing.Callable[[str], typing.Optional[Problems]] = get("get_problem")
get_problem_docs: typing.Callable[[str], typing.Optional[str]] = get("get_problem_docs")
add_problem: typing.Callable[[Problems], None] = get("add_problem")
add_problem_docs: typing.Callable[[str, UploadFile], None] = get("add_problem_docs")
add_problem_testcases: typing.Callable[[str, UploadFile], None] = get("add_problem_testcases")
update_problem: typing.Callable[[str, Problems], None] = get("update_problem")
update_problem_docs: typing.Callable[[str, UploadFile], None] = get("update_problem_docs")
update_problem_testcases: typing.Callable[[str, UploadFile], None] = get("update_problem_testcases")
delete_problem: typing.Callable[[str], None] = get("delete_problem")

"""
Submission
"""
get_submission_ids: typing.Callable[[], typing.List[str]] = get("get_submission_ids")
get_submission: typing.Callable[[str], typing.Optional[Submissions]] = get("get_submission")
add_submission: typing.Callable[[Submissions], None] = get("add_submission")
