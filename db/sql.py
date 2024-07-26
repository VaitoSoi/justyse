"""
For mixing-stored type
"""
import os
import typing
import uuid

from fastapi import UploadFile
from sqlmodel import create_engine, SQLModel, Session, select

from declare import File
from .declare import (
    file_dir,
    submission_dir,
    gen_path,
    unzip_testcases,
    Problems,
    Submissions,
    DBProblem,
    DBSubmission
)
from .exception import (
    ProblemNotFound,
    ProblemAlreadyExisted,
    ProblemDocsAlreadyExist,
    ProblemDocsNotFound,
    SubmissionNotFound,
    SubmissionAlreadyExist
)


# class SQLUsers(SQL_Base):
#     __tablename__ = "users"
#     id: Mapped[int] = mapped_column(primary_key=True, default=uuid.uuid4())
#     name: Mapped[str]
#     password: Mapped[typing.Optional[str]]
#     auth: Mapped[typing.Optional[str]] = mapped_column(default=None)


class SQLProblems(DBProblem, table=True):
    pass


class SQLSubmissions(DBSubmission, table=True):
    pass


sql_engine = create_engine(f"sqlite:///{os.getcwd()}/data/wiwj.db", echo=True)


def create_all():
    SQLModel.metadata.create_all(sql_engine)


"""
Problems
"""


# GET
def get_problem_ids() -> typing.List[str]:
    with Session(sql_engine) as session:
        statement = select(SQLProblems)
        return [problem.id for problem in session.exec(statement).all()]


def get_problem(id: str) -> typing.Optional[DBProblem]:
    if id not in get_problem_ids():
        raise ProblemNotFound(id)

    with Session(sql_engine) as session:
        statement = select(SQLProblems).where(SQLProblems.id == id)
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

    problem = DBProblem(**problem.model_dump())
    problem.dir = gen_path(problem.id)
    try:
        os.makedirs(problem.dir, exist_ok=False)
    except OSError:
        raise ProblemAlreadyExisted(problem.id)

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
def update_problem(id, problem_: Problems):
    if id not in get_problem_ids():
        raise ProblemNotFound(id)

    with Session(sql_engine) as session:
        statement = select(SQLProblems).where(SQLProblems.id == id)
        problem = session.exec(statement).first()

        if problem.id != id:
            delete_problem(id)

        for key, val in problem_.model_dump().items():
            setattr(problem, key, val)

        session.add(problem)


def update_problem_docs(id: str, file: UploadFile):
    problem = get_problem(id)
    if not problem.description.startswith("docs:"):
        raise ProblemDocsNotFound(id)

    with open(f"data/file/{problem.description[5:]}", "wb") as f:
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
        statement = select(SQLSubmissions)
        return session.exec(statement).all()


def get_submission(id: str) -> typing.Optional[Submissions]:
    if id not in get_problem_ids():
        raise SubmissionNotFound()
    with Session(sql_engine) as session:
        statement = select(SQLSubmissions).where(SQLSubmissions.id == id)
        submission = session.exec(statement).first()
    if not submission:
        raise SubmissionNotFound(id)
    return submission


# POST 
def add_submission(submission: Submissions):
    if submission.id in get_submission_ids():
        raise SubmissionAlreadyExist(submission.id)

    with open(submission["file_path"], "w") as file:
        file.write(submission['code'])
    del submission['code']
    submission = SQLSubmissions(**submission.model_dump())
    submission["dir"] = os.path.join(submission_dir, submission.id)
    submission["file_path"] = os.path.join(submission['dir'], File[submission.lang[0]].file.format(id=submission.id))

    with Session(sql_engine) as session:
        session.add(submission)
        session.commit()
