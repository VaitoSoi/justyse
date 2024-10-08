import typing

import redis as redis_
from fastapi import UploadFile

import utils
from . import (
    file,
    sql,
    declare,
    exception,
    redis,
    operator
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
    UpdateUser,
    Role,
    DBRole,
    UpdateRole,
    SubmissionLog
)
from .logging import logger

__all__ = [
    "file",
    "sql",
    "redis",
    "declare",
    "exception",
    "operator",
    # Problems
    "Problems",
    "DBProblems",
    "UpdateProblems",
    "get_problems",
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
    "SubmissionLog",
    "get_submissions",
    "get_submission_ids",
    "get_submission",
    "add_submission",
    "update_submission",
    # "dump_result",
    # "get_result",
    "get_log_ids",
    "dump_logs",
    "get_logs",
    # Users
    "User",
    "UpdateUser",
    "DBUser",
    "get_users",
    "get_user_ids",
    "get_user_filter",
    "get_user",
    "add_user",
    "update_user",
    "delete_user",
    # Roles
    "Role",
    "DBRole",
    "UpdateRole",
    "get_roles",
    "get_role_ids",
    "get_role",
    "add_role",
    "update_role",
    "delete_role",
    "uid_has_permission",
    "has_permission",
]


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


"""
Problems
"""
get_problems: typing.Callable[[list[str]], list[dict]] = get("get_problems")
get_problem_ids: typing.Callable[[], typing.List[str]] = get("get_problem_ids")
get_problem_filter: typing.Callable[[typing.Callable[[DBProblems], typing.Any]], list[DBProblems]] = \
    get("get_problem_filter")
get_problem: typing.Callable[[str], DBProblems] = get("get_problem")
get_problem_docs: typing.Callable[[str], typing.Optional[str]] = get("get_problem_docs")
add_problem: typing.Callable[[Problems, DBUser], DBProblems] = get("add_problem")
add_problem_docs: typing.Callable[[str, UploadFile], None] = get("add_problem_docs")
add_problem_testcases: typing.Callable[[str, UploadFile], None] = get("add_problem_testcases")
update_problem: typing.Callable[[str, UpdateProblems], DBProblems] = get("update_problem")
update_problem_docs: typing.Callable[[str, UploadFile], None] = get("update_problem_docs")
update_problem_testcases: typing.Callable[[str, UploadFile], None] = get("update_problem_testcases")
delete_problem: typing.Callable[[str], None] = get("delete_problem")

"""
Submission
"""
get_submissions: typing.Callable[[list[str]], list[dict]] = get("get_submissions")
get_submission_ids: typing.Callable[[], typing.List[str]] = get("get_submission_ids")
get_submission_filter: typing.Callable[[typing.Callable[[DBSubmissions], typing.Any]], list[DBSubmissions]] = \
    get("get_submission_filter")
get_submission: typing.Callable[[str], DBSubmissions] = get("get_submission")
# get_submission_status: typing.Callable[[str], declare.SubmissionResult] = get("get_submission_status")
add_submission: typing.Callable[[Submissions, DBUser], DBSubmissions] = get("add_submission")
update_submission: typing.Callable[[str, UpdateSubmissions], DBSubmissions] = get("update_submission")
# dump_result: typing.Callable[[str, list[declare_.JudgeResult]], None] = get("dump_result")
# get_result: typing.Callable[[str], list[declare_.JudgeResult]] = get("get_result")
get_log_ids: typing.Callable[[str], typing.List[str]] = get("get_log_ids")
dump_logs: typing.Callable[[str, str, list[str]], None] = get("dump_logs")
get_logs: typing.Callable[[str, str], SubmissionLog] = get("get_logs")

"""
User
"""
get_users: typing.Callable[[list[str]], list[dict]] = get("get_users")
get_user_ids: typing.Callable[[], typing.List[str]] = get("get_user_ids")
get_user_filter: typing.Callable[[typing.Callable[[DBUser], typing.Any]], list[DBUser]] = get("get_user_filter")
get_user: typing.Callable[[str], DBUser] = get("get_user")
add_user: typing.Callable[[User, DBUser], DBUser] = get("add_user")
update_user: typing.Callable[[str, UpdateUser], DBUser] = get("update_user")
delete_user: typing.Callable[[str], None] = get("delete_user")

"""
Role
"""
get_roles: typing.Callable[[list[str]], list[dict]] = get("get_roles")
get_role_ids: typing.Callable[[], typing.List[str]] = get("get_role_ids")
get_role_filter: typing.Callable[[typing.Callable[[declare.Role], typing.Any]], list[declare.Role]] = \
    get("get_role_filter")
get_role: typing.Callable[[str], declare.Role] = get("get_role")
add_role: typing.Callable[[declare.Role], None] = get("add_role")
update_role: typing.Callable[[str, declare.Role], None] = get("update_role")
delete_role: typing.Callable[[str], None] = get("delete_role")
uid_has_permission: typing.Callable[[str, str], bool] = get("uid_has_permission")
has_permission: typing.Callable[[DBUser, str], bool] = get("has_permission")

"""
Redis queue
"""
redis_client: redis_.asyncio.Redis = None
queue_manager: redis.QueueManager = None


async def setup_redis():
    global redis_client, queue_manager
    redis_client = redis_.asyncio.Redis.from_url(utils.config.redis_server)
    try:
        await redis_client.ping()  # noqa
    except (redis_.exceptions.ConnectionError, redis_.exceptions.TimeoutError):
        logger.error(f'Failed to connect to Redis "{utils.config.redis_server}"')
        # logger.exception(error)
        logger.warning("You cant use judge service without Redis")
        redis_client = None
    except Exception as error:
        logger.error(f'Failed to connect to Redis "{utils.config.redis_server}"')
        logger.exception(error)
        redis_client = None
    else:
        queue_manager = redis.QueueManager(redis_client)
        logger.info(f"Connected to Redis: {utils.config.redis_server}")


def setup():
    get("setup")()

    try:
        get_role("@everyone")
    except exception.RoleNotFound:
        add_role(declare.Role(id="@everyone", name="@everyone", permissions=declare.DefaultPermissions))

    try:
        get_role("@admin")
    except exception.RoleNotFound:
        add_role(declare.Role(id="@admin", name="@admin", permissions=["@admin"]))

    try:
        get_user("@admin")
    except exception.UserNotFound:
        add_user(User(
            id="@admin",
            name=utils.config.admin.name,
            password=utils.config.admin.password,
            roles=["@admin"]
        ), creator="@system@")
