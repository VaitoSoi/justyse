import typing
import db.file as file
import db.mixed as mixed
from db.declare import Problems, config
from fastapi import UploadFile

def raise_invalid_method(key: str):
    raise ValueError(f"call invalid method {key}")


def get(
    key: str,
    file_replace: typing.Optional[typing.Awaitable] = None,
    mixed_replace: typing.Optional[typing.Awaitable] = None,
) -> typing.Awaitable:
    return (
        (file_replace or file.__dict__[key] or raise_invalid_method(key))
        if config["place"] == "file"
        else (mixed_replace or mixed.__dict__[key] or raise_invalid_method(key))
    )


def mixed_typing(problems: Problems) -> mixed.Problems:
    return mixed.Problems(
        **{
            key: ",".join(map(str, value)) if isinstance(value, list) else value
            for key, value in problems.model_dump().items()
        }
    )


"""
Problems
"""

get_problem_ids: typing.Callable[[], typing.Awaitable[typing.List[str]]] = get("get_problem_ids")
get_problem: typing.Callable[[str], typing.Awaitable[Problems]] = get("get_problem")
get_problem_docs: typing.Callable[[str], typing.Awaitable[str | None]] = get("get_problem_docs")
add_problem: typing.Callable[[Problems], typing.Awaitable[None]] = get(
    "add_problem",
    mixed_replace=mixed_typing,
)
add_problem_docs: typing.Callable[[str, UploadFile], typing.Awaitable[None]] = get("add_problem_docs")
add_problem_testcases: typing.Callable[[str, UploadFile], typing.Awaitable[None]] = get("add_problem_testcases")
update_problem: typing.Callable[[str, Problems], typing.Awaitable[None]] = get(
    "update_problem",
    mixed_replace=mixed_typing,
)
delete_problem: typing.Callable[[str], typing.Awaitable[None]] = get("delete_problem")