"""
For mixing-stored type
"""

import typing
import os
import uuid
import zipfile
import shutil
from redis import Redis
from fastapi import UploadFile
from db.declare import file_dir, config, gen_path
from sqlalchemy import create_engine, String, ForeignKey
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, sessionmaker

SQL_Base = declarative_base()


class Users(SQL_Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, default=uuid.uuid4())
    name: Mapped[str]
    password: Mapped[typing.Optional[str]]
    auth: Mapped[typing.Optional[str]] = mapped_column(default=None)


class Problems(SQL_Base):
    __tablename__ = "problems"
    id: Mapped[str] = mapped_column(primary_key=True, default=uuid.uuid4().hex)
    title: Mapped[str] = mapped_column(String(32))
    description: Mapped[str]
    accept_language: Mapped[str]
    test_name: Mapped[str]
    total_testcases: Mapped[int]
    roles: Mapped[typing.Optional[str]]
    dir: Mapped[str] = mapped_column(default=None)
    docs: Mapped[str] = mapped_column(default=None)


class Submissions(SQL_Base):
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(primary_key=True, default=uuid.uuid4())
    problem: Mapped[str] = mapped_column(ForeignKey("problems.id"))
    language: Mapped[str] = mapped_column(default="cpp:17")
    code: Mapped[str]
    status: Mapped[str]


sql_engine = create_engine(f"sqlite:///{os.getcwd()}/data/wiwj.db")

SQL_Base.metadata.create_all(sql_engine)
redis_client = Redis(host="localhost", port=6379, db=0)
Session = sessionmaker(bind=sql_engine)

"""
Problems
"""


# GET
async def get_problem_ids():
    return [problem.id for problem in Session().query(Problems).all()]


async def get_problem(id: str):
    return Session().query(Problems).filter(Problems.id == id).first()


async def get_problem_docs(id: str):
    problem = await get_problem(id)
    if problem is None:
        return None
    if problem.docs is None:
        return None
    return os.path.join(problem.dir, problem.docs)


# POST
async def add_problem(problem: Problems):
    db = Session()
    problem.dir = gen_path(problem.id)
    db.add(problem)
    db.commit()
    db.refresh(problem)
    db.close()


async def add_problem_docs(id: str, file: UploadFile):
    problem = await get_problem(id)
    if problem is None:
        raise ValueError('problem not found')
    with open(f"{file_dir}/{file.filename}", "wb") as f:
        f.write(await file.read())
    await file.close()
    problem["docs"] = file.filename
    await update_problem(id, problem)


async def add_problem_testcases(id: str, upfile: UploadFile):
    problem = await get_problem(id)
    if problem is None:
        raise ValueError('problem not found')
    
    zip_file = upfile.filename
    with open(f"{problem['dir']}/{zip_file}", "wb") as f:
        f.write(await upfile.read())
    await upfile.close()
    with zipfile.ZipFile(f"{problem['dir']}/{zip_file}", "r") as zip_ref:
        zip_ref.extractall(f"{problem['dir']}/testcase")
    problem["test_name"] = problem.test_name.split(",")
    inp_ext = problem["test_name"][0].split(".")[-1]
    out_ext = problem["test_name"][1].split(".")[-1]
    inps = []
    outs = []
    for root, dirs, files in os.walk(f"{problem['dir']}/testcase"):
        for file in files:
            if file.endswith(f"{inp_ext}"):
                inps.append(file)
            elif file.endswith(f"{out_ext}"):
                outs.append(file)
            else:
                if config["testcase_strict"] == "strict":
                    raise ValueError(f"invalid testcase file: {file}")
    inps.sort()
    outs.sort()
    if problem.total_testcases != len(inps) or problem.total_testcases != len(outs):
        raise ValueError("invalid testcases count")

    for i in range(len(inps)):
        os.makedirs(f"{problem['dir']}/testcases/{i}")
        shutil.move(
            f"{problem['dir']}/testcase/{inps[i]}",
            f"{problem['dir']}/testcase/{i}/{inps[i]}",
        )
        shutil.move(
            f"{problem['dir']}/testcase/{outs[i]}",
            f"{problem['dir']}/testcase/{i}/{outs[i]}",
        )
    
    shutil.rmtree(f"{problem['dir']}/testcase")
    os.remove(f"{problem['dir']}/{zip_file}")


# PUT
async def update_problem(id, problem: Problems):
    db = Session()
    db.query(Problems).filter(Problems.id == id).update(problem)
    db.commit()
    db.close()


async def update_problem_docs(id: str, file: UploadFile):
    problem = await get_problem(id)
    if problem is None:
        raise ValueError('problem not found')
    if problem.docs is None:
        raise ValueError('problem docs not found')
    with open(f"data/file/{problem.docs}", "wb") as f:
        f.write(await file.read())
    await file.close()
    return "Updated!"


# DELETE
async def delete_problem(id):
    db = Session()
    query = db.query(Problems).filter(Problems.id == id)
    problem = query.first()
    if problem is None:
        raise ValueError('problem not found')
    if problem.docs is not None:
        os.remove(os.path.join(file_dir, problem.docs))
    query.delete()
    db.commit()
    db.close()
