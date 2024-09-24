import datetime
import os
import shutil
import typing
import uuid
import zipfile

import sqlmodel
from fastapi import UploadFile

import utils
from declare import Limit, JudgeMode, Indexable
from utils import config
from .exception import ProblemNotFound, InvalidTestcaseExtension, InvalidTestcaseCount, ProblemTestcaseAlreadyExist
from .logging import logger


class Problems(Indexable):
    __tablename__ = "problems"
    id: str = sqlmodel.Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    title: str
    description: str = sqlmodel.Field(default="")

    total_testcases: int
    test_type: str
    test_name: typing.Tuple[str, str] = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))

    accept_language: typing.List[str] = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))
    limit: Limit = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))
    mode: JudgeMode = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))
    point_per_testcase: float = sqlmodel.Field(default=1.0)
    judger: str | None = sqlmodel.Field(default=None)

    roles: typing.List[str] = sqlmodel.Field(
        sa_column=sqlmodel.Column(sqlmodel.JSON),
        default=["@everyone"]
    )


class DBProblems(Problems):
    by: str = sqlmodel.Field(foreign_key="users.id")
    dir: str
    created_at: str = sqlmodel.Field(default_factory=lambda: str(datetime.datetime.now()))


@utils.partial_model
class UpdateProblems(Problems):
    pass


class SubmissionResult(Indexable):
    status: int
    warn: str | None
    error: str | None
    time: float | None
    point: float | None
    memory: tuple[float, float] | None


class Submissions(Indexable):
    __tablename__ = "submissions"
    id: str = sqlmodel.Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    problem: str = sqlmodel.Field(foreign_key="problems.id")
    lang: typing.Tuple[str, typing.Optional[str]] = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))
    compiler: typing.Tuple[str, typing.Optional[str]] = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))
    code: typing.Optional[str] = sqlmodel.Field(default=None)


class DBSubmissions(Submissions):
    by: str = sqlmodel.Field(foreign_key="users.id")
    dir: str = sqlmodel.Field(default=None)
    file_path: str = sqlmodel.Field(default=None)
    created_at: str = sqlmodel.Field(default_factory=lambda: str(datetime.datetime.now()))
    result: SubmissionResult | None = sqlmodel.Field(default=None, sa_column=sqlmodel.Column(sqlmodel.JSON))


@utils.partial_model
class UpdateSubmissions(Submissions):
    pass


class SubmissionLog(Indexable):
    __tablename__ = "submission_logs"
    id: str = sqlmodel.Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    submission: str = sqlmodel.Field(foreign_key="submissions.id")
    logs: list = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))
    created_at: str = sqlmodel.Field(default_factory=lambda: str(datetime.datetime.now()))


class User(Indexable):
    __tablename__ = "users"
    id: str = sqlmodel.Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    password: str = sqlmodel.Field(min_length=6, max_length=64)
    roles: typing.List[str] | None = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON), default=["@everyone"])


class DBUser(User):
    created_at: str = sqlmodel.Field(default_factory=lambda: str(datetime.datetime.now()))
    password: str = sqlmodel.Field(min_length=None, max_length=None)
    permissions: list[str] | None = sqlmodel.Field(default=None, sa_column=sqlmodel.Column(sqlmodel.JSON))


@utils.partial_model
class UpdateUser(User):
    pass


class Role(Indexable):
    __tablename__ = "roles"
    id: str = sqlmodel.Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    name: str
    permissions: typing.List[str] = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))


class DBRole(Role):
    created_at: str = sqlmodel.Field(default_factory=lambda: str(datetime.datetime.now()))


@utils.partial_model
class UpdateRole(Role):
    pass


DefaultPermissions = [
    "problem:view",
    "problems:view",
    "submission:view",
    "submission:add",
    "submissions:view",
    "submission:judge",
    "contest:view",
    "contests:view",
    "contest:join",
    "judge_server:view",
    "user:view",
    "users:view",
    "user:edit",
    "user:delete"
    "role:view",
]
DefaultUser = DBUser(
    id="default",
    name="default",
    password="default",
    roles=["@default"]
)


def gen_path(id: str) -> str:
    return os.path.join(problems_dir, id)


data = os.path.abspath("data")
files_dir = os.path.join(data, "files")
problems_dir = os.path.join(data, "problems")
submissions_dir = os.path.join(data, "submissions")
users_dir = os.path.join(data, "users")
problems_json = os.path.join(problems_dir, "problems.json")
submissions_json = os.path.join(submissions_dir, "submissions.json")
users_json = os.path.join(users_dir, "users.json")
roles_json = os.path.join(users_dir, "roles.json")
judges_dir = os.path.join(data, "judges")


def unzip_testcases(problem: DBProblems, upfile: UploadFile, overwrite: bool = False):
    if not problem:
        raise ProblemNotFound()

    if os.path.exists(os.path.join(problem.dir, "testcases")):
        if overwrite:
            shutil.rmtree(os.path.join(problem.dir, "testcases"))
        else:
            raise ProblemTestcaseAlreadyExist()

    zip_file = upfile.filename
    with open(f"{problem['dir']}/{zip_file}", "wb") as f:
        f.write(upfile.file.read())
    upfile.file.close()

    unzip_dir = os.path.join(problem["dir"], "unzipped")
    with zipfile.ZipFile(os.path.join(problem["dir"], zip_file), "r") as zip_ref:
        zip_ref.extractall(unzip_dir)

    inp_ext = problem["test_name"][0].split(".")[-1]
    out_ext = problem["test_name"][1].split(".")[-1]
    inps = []
    outs = []
    for root, dirs, files in os.walk(unzip_dir):
        for file in files:
            if file.endswith(f"{inp_ext}"):
                inps.append(file)
            elif file.endswith(f"{out_ext}"):
                outs.append(file)
            else:
                if config.testcase_strict == "strict":
                    raise InvalidTestcaseExtension(file)
                elif config.testcase_strict == "delete":
                    os.remove(os.path.join(root, file))
                elif config.testcase_strict == "warn":
                    logger.warning(f'Problem "{problem.id}", invalid testcase extension: {file}')
                elif config.testcase_strict == "ignore":
                    pass
    inps.sort()
    outs.sort()
    if problem["total_testcases"] != len(inps) or problem["total_testcases"] != len(outs):
        raise InvalidTestcaseCount(problem.total_testcases, (len(inps), len(outs)))

    for i in range(len(inps)):
        testcase_dir = os.path.abspath(os.path.join(problem["dir"], "testcases", str(i + 1)))
        os.makedirs(testcase_dir, exist_ok=True)
        shutil.move(os.path.join(unzip_dir, inps[i]), os.path.join(testcase_dir, problem["test_name"][0]))
        shutil.move(os.path.join(unzip_dir, outs[i]), os.path.join(testcase_dir, problem["test_name"][1]))

    shutil.rmtree(unzip_dir)
    os.remove(os.path.join(problem["dir"], zip_file))
