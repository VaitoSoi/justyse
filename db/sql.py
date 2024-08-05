"""
For mixing-stored type
"""
import os
import typing
import uuid

from fastapi import UploadFile
from sqlmodel import create_engine, SQLModel, Session, select
from sqlalchemy import Engine

import declare
import utils
from declare import Language
from .declare import (
    file_dir,
    submission_dir,
    gen_path,
    unzip_testcases,
    Problems,
    Submissions,
    DBProblems,
    DBSubmissions,
    UpdateProblems,
    UpdateSubmissions
)
from .exception import (
    TestTypeNotSupport,
    ProblemNotFound,
    ProblemAlreadyExisted,
    ProblemDocsAlreadyExist,
    ProblemDocsNotFound,
    SubmissionNotFound,
    SubmissionAlreadyExist,
    # NothingToUpdate,
    LanguageNotSupport,
    LanguageNotAccept,
    CompilerNotSupport
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


sql_engine: Engine = None


def create_all():
    global sql_engine
    sql_engine = create_engine(
        f"sqlite:///{os.getcwd()}/data/justyse.db"
        if utils.config.store_place == "sql:sqlite" else
        f"sqlite:///:memory:"
        if utils.config.store_place == "sql:memory" else
        utils.config.store_place[4:],
        # echo=True
    )
    SQLModel.metadata.create_all(sql_engine)


"""
Problems
"""


# GET
def get_problem_ids() -> typing.List[str]:
    with Session(sql_engine) as session:
        statement = select(SQLProblems.id)
        return [problem for problem in session.exec(statement).all()]


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
        return ProblemDocsNotFound(id)
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

    if problem.test_type not in ["file", "std"]:
        raise TestTypeNotSupport()

    support_language = declare.Language['all']
    for lang in problem.accept_language:
        if lang not in support_language:
            raise LanguageNotSupport(lang)

    with Session(sql_engine) as session:
        session.add(problem)
        session.commit()


def add_problem_docs(id: str, file: UploadFile):
    problem = get_problem(id)

    if problem.description.startswith("docs:"):
        raise ProblemDocsAlreadyExist(id)

    file.filename = f"{uuid.uuid4().__str__()}.pdf"
    with open(f"{file_dir}/{file.filename}", "wb") as f:
        f.write(file.file.read())

    file.file.close()
    problem.description = f"docs:{file.filename}"
    update_problem(id, problem)


def add_problem_testcases(id: str, upfile: UploadFile):
    problem = get_problem(id)

    if not problem:
        raise ProblemNotFound(id)

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

        session.commit()


def update_problem_docs(id: str, file: UploadFile):
    problem = get_problem(id)
    if not problem.description.startswith("docs:"):
        raise ProblemDocsNotFound(id)

    with open(os.path.join(file_dir, problem.description[5:]), "wb") as f:
        f.write(file.file.read())
    file.file.close()


def update_problem_testcases(id: str, file: UploadFile):
    add_problem_testcases(id, file)


# DELETE
def delete_problem(id):
    problem = get_problem(id)
    if problem.description.startswith("docs:"):
        os.remove(os.path.join(file_dir, problem.description[5:]))

    with Session(sql_engine) as session:
        session.delete(problem)
        session.commit()


"""
Submission
"""


# GET
def get_submission_ids() -> typing.List[str]:
    with Session(sql_engine) as session:
        statement = select(SQLSubmissions.id)
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


# POST 
def add_submission(submission: Submissions):
    if submission.id in get_submission_ids():
        raise SubmissionAlreadyExist(submission.id)

    submission = SQLSubmissions(**submission.model_dump())
    submission.dir = os.path.join(submission_dir, submission.id)
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

    with Session(sql_engine) as session:
        session.add(submission)
        session.commit()


# PATCH
def update_submission(id: str, submission_: UpdateSubmissions):
    with Session(sql_engine) as session:
        submission = get_submission(id, session)

        for key, val in submission_.model_dump().items():
            if val is not None:
                setattr(submission, key, val)

        session.commit()
