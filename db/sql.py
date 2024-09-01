"""
For mixing-stored type
"""
import ast
import os
import typing
import copy
import uuid

import sqlalchemy.sql.elements
from fastapi import UploadFile
from sqlalchemy import Engine
from sqlmodel import create_engine, SQLModel, Session, select

import declare
import utils
from declare import Language
from .declare import (
    files_dir,
    submissions_dir,
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
    # ProblemDocsAlreadyExist,
    ProblemDocsNotFound,
    InvalidProblemJudger,
    SubmissionNotFound,
    SubmissionAlreadyExist,
    UserNotFound,
    UserAlreadyExist,
    # NothingToUpdate,
    LanguageNotSupport,
    LanguageNotAccept,
    CompilerNotSupport,
    RoleNotFound,
    RoleAlreadyExists,
    PermissionDenied
)


# class SQLUsers(SQL_Base):
#     __tablename__ = "users"
#     id: Mapped[int] = mapped_column(primary_key=True, default=uuid.uuid4())
#     name: Mapped[str]
#     password: Mapped[typing.Optional[str]]
#     auth: Mapped[typing.Optional[str]] = mapped_column(default=None)


class SQLProblems(DBProblems, table=True):
    pass


class SQLSubmissions(DBSubmissions, table=True):
    pass


class SQLUsers(DBUser, table=True):
    pass


class SQLRoles(DBRole, table=True):
    pass


sql_engine: Engine = None


def setup():
    global sql_engine
    sql_engine = create_engine(
        f"sqlite:///{os.getcwd()}/data/justyse.db"
        if utils.config.store_place == "sql:sqlite" else
        f"sqlite:///:memory:"
        if utils.config.store_place == "sql:memory" else
        utils.config.store_place[4:],
        echo=os.getenv("ENV", "PROD") == "DEBUG"
    )
    SQLModel.metadata.create_all(sql_engine)


"""
Problems
"""


# GET
def get_problems(keys: list[str] = None) -> typing.List[dict]:
    keys = keys or ["id"]
    with Session(sql_engine) as session:
        statement = select(SQLProblems)
        return utils.filter_keys(session.exec(statement).all(), keys)


def get_problem_ids() -> typing.List[str]:
    with Session(sql_engine) as session:
        statement = select(SQLProblems.id)
        return session.exec(statement).all()


def get_problem_filter(
        selector: typing.Callable[
            [SQLProblems],
            sqlalchemy.sql.elements.BinaryExpression
        ],
        session: Session = None
) -> list[SQLProblems] | None:
    statement = select(SQLProblems).where(selector(SQLProblems))
    if session is None:
        with Session(sql_engine) as session:
            return session.exec(statement).all()
    else:
        return session.exec(statement).all()


def get_problem(id: str, session: Session = None) -> DBProblems:
    if id not in get_problem_ids():
        raise ProblemNotFound(id)

    statement = select(SQLProblems).where(SQLProblems.id == id)
    if session is None:
        with Session(sql_engine) as session:
            problem = session.exec(statement).first()
    else:
        problem = session.exec(statement).first()

    if problem is None:
        raise ProblemNotFound(id)

    return problem


def get_problem_docs(id: str) -> str:
    problem = get_problem(id)
    if not problem.description.startswith("docs:"):
        raise ProblemDocsNotFound(id)
    return problem.description[5:]


# POST
def add_problem(problem: Problems):
    if problem.id in get_problem_ids():
        raise ProblemAlreadyExisted(problem.id)

    problem = SQLProblems(**problem.model_dump())
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
        with open(os.path.join(problem.dir, "judger.py"), "w") as f:
            f.write(problem.judger)
        problem.judger = None

    if problem.test_type not in ["file", "std"]:
        raise TestTypeNotSupport()

    support_language = declare.Language['all']
    for lang in problem.accept_language:
        if lang not in support_language:
            raise LanguageNotSupport(lang)

    res = copy.copy(problem)

    with Session(sql_engine) as session:
        session.add(problem)
        session.commit()

    return res


def add_problem_docs(id: str, file: UploadFile):
    problem = get_problem(id)

    # if problem.description.startswith("docs:"):
    #     raise ProblemDocsAlreadyExist(id)

    file.filename = f"{uuid.uuid4().__str__()}.pdf"
    with open(f"{files_dir}/{file.filename}", "wb") as f:
        f.write(file.file.read())

    file.file.close()
    problem.description = f"docs:{file.filename}"
    update_problem(id, problem)


def add_problem_testcases(id: str, upfile: UploadFile):
    problem = get_problem(id)

    unzip_testcases(problem, upfile)


# PATCH
def update_problem(id, problem_: typing.Union[DBProblems, UpdateProblems]):
    # if Problems(**problem.model_dump()) == problem_:
    #     raise NothingToUpdate()

    with Session(sql_engine) as session:
        problem = get_problem(id, session)

        for key, val in problem_.model_dump().items():
            if val is not None:
                setattr(problem, key, val)

        res = copy.copy(problem)

        session.commit()

        return res


def update_problem_docs(id: str, file: UploadFile):
    problem = get_problem(id)

    if not problem.description.startswith("docs:"):
        problem.description = f"docs:{uuid.uuid4().__str__()}.pdf"
        update_problem(id, problem)

    with open(os.path.join(files_dir, problem.description[5:]), "wb") as f:
        f.write(file.file.read())
    file.file.close()


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

def delete_problem(id):
    problem = get_problem(id)
    if problem.description.startswith("docs:"):
        os.remove(os.path.join(files_dir, problem.description[5:]))

    with Session(sql_engine) as session:
        session.delete(problem)
        session.commit()


"""
Submission
"""


# GET
def get_submissions(keys: list[str] = None) -> typing.List[dict]:
    keys = keys or ["id"]
    with Session(sql_engine) as session:
        statement = select(SQLSubmissions)
        return utils.filter_keys(session.exec(statement).all(), keys)


def get_submission_ids() -> typing.List[str]:
    with Session(sql_engine) as session:
        statement = select(SQLSubmissions.id)
        return session.exec(statement).all()


def get_submission_filter(
        selector: typing.Callable[
            [SQLSubmissions],
            sqlalchemy.sql.elements.BinaryExpression
        ],
        session: Session = None
) -> list[SQLSubmissions] | None:
    statement = select(SQLSubmissions).where(selector(SQLSubmissions))
    if session is None:
        with Session(sql_engine) as session:
            return session.exec(statement).all()
    else:
        return session.exec(statement).all()


def get_submission(id: str, session: Session = None) -> SQLSubmissions:
    if id not in get_submission_ids():
        raise SubmissionNotFound()
    statement = select(SQLSubmissions).where(SQLSubmissions.id == id)
    if session is None:
        with Session(sql_engine) as session:
            submission = session.exec(statement).first()
    else:
        submission = session.exec(statement).first()
    if not submission:
        raise SubmissionNotFound()
    return submission


# def get_submission_status(id: str) -> SubmissionResult:
#     submission = get_submission(id)
#     # results: list = [result for result in submission.results if result["status"] >= 0]
#     # results.sort(key=lambda x: (x["status"], x["time"]))
#     return submission.result


# POST 
def add_submission(submission: Submissions, submitter: DBUser):
    if submission.id in get_submission_ids():
        raise SubmissionAlreadyExist(submission.id)

    get_user(submission.by)

    submission = SQLSubmissions(**submission.model_dump())
    submission.by = submitter.id
    submission.dir = os.path.join(submissions_dir, submission.id)
    submission.file_path = os.path.join(submission['dir'],
                                        Language[submission.lang[0]].file.format(id=submission.id))

    problem = get_problem(submission.problem)
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

    os.makedirs(submission.dir, exist_ok=True)
    with open(submission["file_path"], "w") as file:
        file.write(submission['code'])
    submission.code = ""

    res = copy.copy(submission)

    with Session(sql_engine) as session:
        session.add(submission)
        session.commit()

    return res


# PATCH
def update_submission(id: str, submission_: UpdateSubmissions):
    with Session(sql_engine) as session:
        submission = get_submission(id, session)

        for key, val in submission_.model_dump().items():
            if val is not None:
                setattr(submission, key, val)

        session.commit()


# OTHER :D
# def get_results_ids() -> typing.List[str]:
#     with Session(sql_engine) as session:
#         statement = select(SQLJudgeResults.id)
#         return session.exec(statement).all()
#
#
# def dump_results(id: str, results: declare.JudgeResult):
#     if id in get_results_ids():
#         raise ResultAlreadyExist(id)
#     result = SQLJudgeResults(
#         id=id,
#         results=results
#     )
#     with Session(sql_engine) as session:
#         session.add(result)
#         session.commit()
#
#
# def get_results(id: str) -> declare.JudgeResult:
#     with Session(sql_engine) as session:
#         statement = select(SQLJudgeResults).where(SQLJudgeResults.id == id)
#         result = session.exec(statement).first()
#         if not result:
#             raise ResultNotFound(id)
#         return result.results


"""
User
"""


# GET
def get_users(keys: list[str] = None) -> typing.List[dict]:
    keys = keys or ["id"]
    with Session(sql_engine) as session:
        statement = select(SQLUsers)
        return utils.filter_keys(session.exec(statement).all(), keys)


def get_user_ids() -> typing.List[str]:
    with Session(sql_engine) as session:
        statement = select(SQLUsers.id)
        return session.exec(statement).all()


def get_user_filter(
        selector: typing.Callable[
            [SQLUsers],
            sqlalchemy.sql.elements.BinaryExpression
        ],
        session: Session = None
) -> list[SQLUsers] | None:
    statement = select(SQLUsers).where(selector(SQLUsers))
    if session is None:
        with Session(sql_engine) as session:
            return session.exec(statement).all()
    else:
        return session.exec(statement).all()


def get_user(id: str, session: Session = None) -> SQLUsers:
    if id not in get_user_ids():
        raise UserNotFound()
    statement = select(SQLUsers).where(SQLUsers.id == id)
    if session is None:
        with Session(sql_engine) as session:
            user = session.exec(statement).first()
    else:
        user = session.exec(statement).first()
    if not user:
        raise UserNotFound()
    return user


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

    user = SQLUsers(**user.model_dump())
    user.password = utils.hash(user.password)
    res = copy.copy(user)

    with Session(sql_engine) as session:
        session.add(user)
        session.commit()

    return res


# PATCH
def update_user(id: str, user_: UpdateUser):
    with Session(sql_engine) as session:
        user = get_user(id, session)

        for key, val in user_.model_dump().items():
            if val is not None:
                if key == "password":
                    val = utils.hash(val)
                setattr(user, key, val)

        res = copy.copy(user)

        session.commit()

        return res


# DELETE
def delete_user(id):
    user = get_user(id)
    with Session(sql_engine) as session:
        session.delete(user)
        session.commit()


"""
Role
"""


# GET
def get_roles(keys: list[str] = None) -> typing.List[dict]:
    keys = keys or ["id"]
    with Session(sql_engine) as session:
        statement = select(SQLRoles)
        return utils.filter_keys(session.exec(statement).all(), keys)


def get_role_ids() -> typing.List[str]:
    with Session(sql_engine) as session:
        statement = select(SQLRoles.id)
        return session.exec(statement).all()


def get_role_filter(
        selector: typing.Callable[
            [SQLRoles],
            sqlalchemy.sql.elements.BinaryExpression
        ],
        session: Session = None
) -> list[SQLRoles] | None:
    statement = select(SQLRoles).where(selector(SQLRoles))
    if session is None:
        with Session(sql_engine) as session:
            return session.exec(statement).all()
    else:
        return session.exec(statement).all()


def get_role(id: str, session: Session = None) -> SQLRoles:
    if id not in get_role_ids():
        raise RoleNotFound(id)
    statement = select(SQLRoles).where(SQLRoles.id == id)
    if session is None:
        with Session(sql_engine) as session:
            role = session.exec(statement).first()
    else:
        role = session.exec(statement).first()
    if not role:
        raise RoleNotFound()
    return role


# POST
def add_role(role: Role):
    if role.id in get_role_ids():
        raise RoleAlreadyExists(role.id)

    role = SQLRoles(**role.model_dump())
    res = copy.copy(role)

    with Session(sql_engine) as session:
        session.add(role)
        session.commit()

    return res


# PATCH
def update_role(id: str, role_: UpdateRole):
    with Session(sql_engine) as session:
        role = get_role(id, session)

        for key, val in role_.model_dump().items():
            if val is not None:
                setattr(role, key, val)

        session.commit()

        return role


# DELETE
def delete_role(id):
    role = get_role(id)
    with Session(sql_engine) as session:
        session.delete(role)
        session.commit()


# OTHER
def uid_has_permission(uid: str, permission: str) -> bool:
    return has_permission(get_user(uid), permission)


def has_permission(user: DBUser, permission: str) -> bool:
    return "@admin" in user.roles or len([role
                                          for role in get_role_filter(lambda role: role.id.in_(user.roles))
                                          if permission in role.permissions]) > 0
