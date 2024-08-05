import os
import shutil
import typing
import uuid
import zipfile
import datetime

import sqlmodel
from fastapi import UploadFile

import utils
from declare import Limit, JudgeResult, JudgeMode, Indexable, TestType
from utils import config
from .exception import ProblemNotFound, InvalidTestcaseExtension, InvalidTestcaseCount


class Problems(Indexable):
    __tablename__ = "problems"
    id: str = sqlmodel.Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    title: str
    description: str = sqlmodel.Field(default="")
    accept_language: typing.List[str] = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))
    test_name: typing.List[str] = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))
    total_testcases: int
    test_type: str
    roles: typing.Optional[typing.List[str]] | str = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))
    limit: Limit = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))
    mode: JudgeMode = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))


class DBProblems(Problems):
    dir: str = sqlmodel.Field(default=None)
    created_at: str = sqlmodel.Field(default_factory=lambda: str(datetime.datetime.now()))


@utils.partial_model
class UpdateProblems(Problems):
    pass


class SubmissionResult(Indexable):
    status: int
    warn: str | None
    error: str | None
    time: float | None
    memory: tuple[float, float] | None


class Submissions(Indexable):
    id: str = sqlmodel.Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    problem: str = sqlmodel.Field(foreign_key="problems.id")
    lang: typing.Tuple[str, typing.Optional[str]] = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))
    compiler: typing.Tuple[str, typing.Optional[str]] = sqlmodel.Field(sa_column=sqlmodel.Column(sqlmodel.JSON))
    code: typing.Optional[str] = sqlmodel.Field(default=None)


class DBSubmissions(Submissions):
    dir: str = sqlmodel.Field(default=None)
    file_path: str = sqlmodel.Field(default=None)
    result: typing.Optional[SubmissionResult] = sqlmodel.Field(default=None, sa_column=sqlmodel.Column(sqlmodel.JSON))
    created_at: str = sqlmodel.Field(default_factory=lambda: str(datetime.datetime.now()))


@utils.partial_model
class UpdateSubmissions(Submissions):
    pass


class User(Indexable):
    pass


def gen_path(id: str) -> str:
    return os.path.join(problem_dir, id)


data = os.path.abspath("data")
file_dir = os.path.join(data, "files")
problem_dir = os.path.join(data, "problems")
submission_dir = os.path.join(data, "submissions")
problem_json = f"{problem_dir}/problems.json"
submission_json = f"{submission_dir}/submissions.json"


def unzip_testcases(problem: Problems, upfile: UploadFile):
    if not problem:
        raise ProblemNotFound()

    if os.path.exists(os.path.join(problem.dir, "testcases")):
        shutil.rmtree(os.path.join(problem.dir, "testcases"))

    zip_file = upfile.filename
    with open(f"{problem['dir']}/{zip_file}", "wb") as f:
        f.write(upfile.file.read())
    upfile.file.close()

    unzip_dir = os.path.join(problem["dir"], "testcase")
    with zipfile.ZipFile(os.path.join(problem["dir"], zip_file), "r") as zip_ref:
        zip_ref.extractall(unzip_dir)

    inp_ext = problem["test_name"][0].split(".")[-1]
    out_ext = problem["test_name"][1].split(".")[-1]
    inps = []
    outs = []
    for root, dirs, files in os.walk(os.path.join(problem["dir"], "testcase")):
        for file in files:
            if file.endswith(f"{inp_ext}"):
                inps.append(file)
            elif file.endswith(f"{out_ext}"):
                outs.append(file)
            else:
                if config["testcase_strict"] == "strict":
                    raise InvalidTestcaseExtension(file)
    inps.sort()
    outs.sort()
    if problem["total_testcases"] != len(inps) or problem["total_testcases"] != len(outs):
        raise InvalidTestcaseCount(f"expect: {problem.total_testcases}, got {len(inps)} inps and {len(outs)} outs")

    for i in range(len(inps)):
        testcase_dir = os.path.abspath(os.path.join(problem["dir"], "testcases", str(i + 1)))
        os.makedirs(testcase_dir, exist_ok=True)
        shutil.move(os.path.join(unzip_dir, inps[i]), os.path.join(testcase_dir, problem["test_name"][0]))
        shutil.move(os.path.join(unzip_dir, outs[i]), os.path.join(testcase_dir, problem["test_name"][1]))

    shutil.rmtree(unzip_dir)
    os.remove(os.path.join(problem["dir"], zip_file))
