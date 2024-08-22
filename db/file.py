"""
For file system-stored type
"""

import os
import os.path as path
import typing
import uuid
import ast

from fastapi import UploadFile

import declare
import utils
from utils import read_json, write_json
from .declare import (
    files_dir,
    problems_json,
    submissions_dir,
    submissions_json,
    users_json,
    roles_json,
    gen_path,
    unzip_testcases,
    Problems,
    DBProblems,
    UpdateProblems,
    Submissions,
    DBSubmissions,
    UpdateSubmissions,
    User,
    DBUser,
    UpdateUser,
    Role,
    DBRole,
    UpdateRole
)
from .exception import (
    TestTypeNotSupport,
    ProblemNotFound,
    ProblemAlreadyExisted,
    ProblemDocsAlreadyExist,
    ProblemDocsNotFound,
    InvalidProblemJudger,
    SubmissionNotFound,
    SubmissionAlreadyExist,
    UserAlreadyExist,
    UserNotFound,
    # NothingToUpdate
    LanguageNotSupport,
    LanguageNotAccept,
    CompilerNotSupport,
    RoleNotFound,
    RoleAlreadyExist,
    PermissionDenied,
    PermissionNotFound
)


def setup():
    pass


"""
Problems
"""


# GET
def get_problems(keys: list[str] = None) -> list[dict]:
    keys = keys or ["id"]
    return [{key: problem[key] for key in keys} for problem in read_json(problems_json).values()]


def get_problem_ids() -> typing.List[str]:
    return list(read_json(problems_json).keys())


def get_problem_filter(func: typing.Callable[[DBProblems], bool]) -> list[DBProblems]:
    problems = read_json(problems_json)
    return [DBProblems(**v) for k, v in problems.items() if func(DBProblems(**v))]


def get_problem(id) -> DBProblems:
    if id not in get_problem_ids():
        raise ProblemNotFound()
    return Problems(**read_json(problems_json)[id])


def get_problem_docs(id: str) -> str:
    problem = get_problem(id)
    if not problem["description"].startswith("docs:"):
        raise ProblemDocsNotFound(id)
    return problem["description"][5:]


# POST
def add_problem(problem: Problems):
    problems = read_json(problems_json)
    if problem.id in problem:
        raise ProblemAlreadyExisted(problem.id)

    problem = DBProblems(**problem.model_dump())
    problem.dir = gen_path(problem.id)
    try:
        os.makedirs(problem.dir, exist_ok=False)
    except OSError:
        # raise ProblemAlreadyExisted(problem.id)
        pass

    if problem.judger is not None:
        try:
            ast.parse(problem.judger)
        except SyntaxError:
            raise InvalidProblemJudger()
        with open(path.join(problem.dir, "judger.py"), "w") as f:
            f.write(problem.judger)

    if problem.test_type not in ["file", "std"]:
        raise TestTypeNotSupport()

    support_language = declare.Language['all']
    for lang in problem.accept_language:
        if lang not in support_language:
            raise LanguageNotSupport(lang)

    problems[problem.id] = problem.model_dump()
    write_json(problems_json, problems)

    return problem


def add_problem_docs(id: str, file: UploadFile):
    problem = get_problem(id)
    if problem is None:
        raise ProblemNotFound(id)
    if problem.description.startswith("docs:"):
        raise ProblemDocsAlreadyExist(problem.id)

    file.filename = f"{uuid.uuid4().__str__()}.pdf"
    with open(f"{files_dir}/{file.filename}", "wb") as f:
        f.write(file.file.read())
    file.file.close()

    problems = read_json(problems_json)
    problems[problem["id"]]["description"] = f"docs:{file.filename}"
    write_json(problems_json, problems)


def add_problem_testcases(id: str, upfile: UploadFile):
    problem = get_problem(id)

    unzip_testcases(problem, upfile)


# PATCH
def update_problem(id, problem: UpdateProblems):
    problem = problem.model_dump()
    problems = read_json(problems_json)
    if id not in problems:
        raise ProblemNotFound(id)

    if problem["id"] is not None and id != problem["id"]:
        problems[problem["id"]] = problems[id]
        problems[problem["id"]]["dir"] = gen_path(problem["id"])
        del problems[id]

    # if problem == Problems(**problems[id]):
    #     raise NothingToUpdate()

    for key, val in problem.items():
        if val is not None and problems[id][key] != val:
            problems[id][key] = val

    write_json(problems_json, problems)

    return problems[id]


def update_problem_docs(id: str, file: UploadFile):
    problem = get_problem(id)

    if not problem.description.startswith("docs:"):
        raise ProblemDocsNotFound()

    with open(path.join(files_dir, problem['description'][5:]), "wb") as f:
        f.write(file.read())
    file.close()


def update_problem_testcases(id: str, upfile: UploadFile):
    problem = get_problem(id)

    unzip_testcases(problem, upfile, True)


# def update_problem_judger(id: str, code: str):
#     problem = get_problem(id)
#
#     try:
#         ast.parse(code)
#     except SyntaxError:
#         raise InvalidProblemJudger()
#
#     with open(os.path.join(problem.dir, "judger.py"), "w") as f:
#         f.write(code)


# DELETE
def delete_problem(id: str):
    problems = read_json(problems_json)
    if id not in problems:
        raise ProblemNotFound(id)
    problem = problems[id]
    if problem["description"].startswith("docs:"):
        os.remove(path.join(files_dir, problem["description"][5:]))
    del problems[id]
    write_json(problems_json, problems)


"""
Submissions
"""


# GET
def get_submission_ids() -> typing.List[str]:
    return list(read_json(submissions_json).keys())


def get_submission_filter(func: typing.Callable[[DBSubmissions], bool]) -> list[DBSubmissions]:
    submissions = read_json(submissions_json)
    return [DBSubmissions(**v) for k, v in submissions.items() if func(DBSubmissions(**v))]


def get_submission(id: str) -> typing.Optional[Submissions]:
    if id not in get_submission_ids():
        raise SubmissionNotFound(id)
    return Submissions(**read_json(submissions_json)[id])


# def get_submission_status(id: str) -> SubmissionResult:
#     submission = get_submission(id)
#     # results: list = [result for result in submission.results if result["status"] >= 0]
#     # results.sort(key=lambda x: (x["status"], x["time"]))
#     return submission.result


# POST
def add_submission(submission: Submissions, submitter: DBUser):
    if submission.id in get_submission_ids():
        raise SubmissionAlreadyExist(submission.id)

    submission = DBSubmissions(**submission.model_dump())
    submission["by"] = submitter.id
    submission["dir"] = path.join(submissions_dir, submission['id'])
    submission["file_path"] = path.join(submission["dir"],
                                        declare.Language[submission["lang"][0]].file.format(id=submission["id"]))

    problem = get_problem(submission["problem"])
    if (
            submission.lang[0] not in declare.Language['all'] or
            (declare.Language[submission.lang[0]].version is not None and
             submission.lang[1] not in declare.Language[submission.lang[0]].version)
    ):
        raise LanguageNotSupport(utils.padding(submission.lang, 2))
    if submission.lang[0] not in problem.accept_language:
        raise LanguageNotAccept(submission.lang)
    if (
            submission.compiler[0] not in declare.Compiler['all'] or
            (submission.compiler[1] != "latest" and
             submission.compiler[1] not in declare.Compiler[submission.compiler[0]].version)
    ):
        raise CompilerNotSupport(utils.padding(submission.compiler, 2))

    os.makedirs(submission["dir"], exist_ok=True)
    with open(submission["file_path"], "w") as file:
        file.write(submission["code"])
    submission.code = ""

    submissions = read_json(submissions_json)
    submissions[submission["id"]] = submission
    write_json(submissions_json, submissions)

    return submission


# PATCH
def update_submission(id: str, submission: UpdateSubmissions):
    submission = submission.model_dump()
    submissions = read_json(submissions_json)
    if id not in submissions:
        raise SubmissionNotFound(id)

    if submission["id"] is not None and id != submission["id"]:
        submissions[submission["id"]] = submissions[id]
        submissions[submission["id"]]["dir"] = path.join(submissions_dir, submission["id"])
        del submissions[id]

    # if submission == Submissions(**submissions[id]):
    #     raise NothingToUpdate()

    for key, val in submission.items():
        if val is not None and submissions[id][key] != val:
            submissions[id][key] = val

    write_json(submissions_json, submissions)
    return submissions[id]


# OTHER :D
# def dump_result(id: str, results: list[declare.JudgeResult]):
#     if id.startswith("judge::"):
#         id = id[7:]
#     submission_id, queue_id = id.split(":")
#     submission = get_submission(submission_id)
#     if path.exists(f"{submission['dir']}/result/{queue_id}.json"):
#         raise ResultAlreadyExist(id)
#
#     utils.write_json(f"{submission['dir']}/result/{queue_id}.json", results)
#
#
# def get_result(id: str) -> list[declare.JudgeResult]:
#     if id.startswith("judge::"):
#         id = id[7:]
#     submission_id, queue_id = id.split(":")
#     submission = get_submission(submission_id)
#     if not path.exists(f"{submission['dir']}/result/{queue_id}.json"):
#         raise ResultNotFound(f"{submission['dir']}/result/{queue_id}.json")
#     return utils.read_json(f"{submission['dir']}/result/{queue_id}.json")


"""
User
"""


# GET
def get_user_ids() -> typing.List[str]:
    return list(read_json(users_json).keys())


def get_user_filter(func: typing.Callable[[DBUser], bool]) -> list[DBUser]:
    return [DBUser(**v) for k, v in read_json(users_json).items() if func(DBUser(**v))]


def get_user(id: str) -> typing.Optional[DBUser]:
    if id not in get_user_ids():
        raise UserNotFound(id)
    return DBUser(**read_json(users_json)[id])


# POST
def add_user(user: User, creator: DBUser | str | None = None):
    if user.id in get_user_ids():
        raise UserAlreadyExist(user.id)

    if isinstance(creator, str) and creator == "@system@":
        pass

    elif not user.roles or not creator:
        user.roles = ["@default"]

    else:
        roles = [get_role(role) for role in user.roles]
        for role in roles:
            for permission in role.permissions:
                if not has_permission(creator, permission):
                    raise PermissionDenied(permission)
                if permission not in declare.Permission:
                    raise PermissionNotFound(permission)

    user = DBUser(**user.model_dump())

    user.password = utils.hash(user.password)
    users = read_json(users_json)
    users[user.id] = user.model_dump()
    write_json(users_json, users)

    return user


# PATCH
def update_user(id: str, user: UpdateUser):
    user = user.model_dump()
    users = read_json(users_json)
    if id not in users:
        raise UserNotFound(id)

    if user["id"] is not None and id != user["id"]:
        users[user["id"]] = users[id]
        del users[id]

    for key, val in user.items():
        if val is not None and users[id][key] != val:
            if key == 'password':
                val = utils.hash(val)

            users[id][key] = val

    write_json(users_json, users)
    return users[id]


# DELETE
def delete_user(id: str):
    users = read_json(users_json)
    if id not in users:
        raise UserNotFound(id)
    del users[id]
    write_json(users_json, users)


"""
Role
"""


# GET
def get_role_ids() -> typing.List[str]:
    return list(read_json(roles_json).keys())


def get_role_filter(func: typing.Callable[[DBRole], bool]) -> list[DBRole]:
    return [DBRole(**v) for k, v in read_json(roles_json).items() if func(DBRole(**v))]


def get_role(id: str) -> typing.Optional[DBRole]:
    if id not in get_role_ids():
        raise RoleNotFound(id)
    return DBRole(**read_json(roles_json)[id])


# POST
def add_role(role: Role):
    if role.id in get_role_ids():
        raise RoleAlreadyExist(role.id)

    roles = read_json(roles_json)
    roles[role.id] = role.model_dump()
    write_json(roles_json, roles)

    return role


# PATCH
def update_role(id: str, role: UpdateRole):
    role = role.model_dump()
    roles = read_json(roles_json)
    if id not in roles:
        raise RoleNotFound(id)

    if role["id"] is not None and id != role["id"]:
        roles[role["id"]] = roles[id]
        del roles[id]

    for key, val in role.items():
        if val is not None and roles[id][key] != val:
            roles[id][key] = val

    write_json(roles_json, roles)

    return roles[id]


# DELETE
def delete_role(id: str):
    roles = read_json(roles_json)
    if id not in roles:
        raise RoleNotFound(id)
    del roles[id]
    write_json(roles_json, roles)


# OTHER
def uid_has_permission(uid: str, permission: str) -> bool:
    return has_permission(get_user(uid), permission)


def has_permission(user: DBUser, permission: str) -> bool:
    return ("@admin" in user.roles or
            len(get_role_filter(lambda role: role.id in user.roles and permission in role.permissions)) > 0)
