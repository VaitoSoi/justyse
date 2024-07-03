"""
For file system-stored type
"""

import os
import typing
import uuid
import zipfile
import shutil
from fastapi import UploadFile
from db.declare import (
    Problems,
    problem_json,
    file_dir,
    config,
    gen_path,
    read_json,
    write_json,
)

"""
Problems
"""


# GET
async def get_problem_ids() -> typing.List[str]:
    return list(read_json(problem_json).keys())


async def get_problem(id) -> Problems:
    return read_json(problem_json)[id]


async def get_problem_docs(id: str) -> str | None:
    problem = (await get_problem(id)).model_dump()
    if not problem["description"].startswith("docs:"):
        return None
    return problem["description"][5:]


# POST
async def add_problem(problem: Problems):
    problems = read_json(problem_json)
    problems[problem.id] = problem.model_dump()
    problems[problem.id]["dir"] = gen_path(problem.id)
    os.makedirs(problems[problem.id]["dir"], exist_ok=True)
    write_json(problem_json, problems)


async def add_problem_docs(id: str, file: UploadFile):
    problem = (await get_problem(id)).model_dump()
    if problem["description"].startswith("docs:"):
        raise ValueError()
    file.filename = f"{uuid.uuid4().__str__()}.pdf"
    with open(f"{file_dir}/{file.filename}", "wb") as f:
        f.write(await file.read())
    await file.close()
    problems = read_json(problem_json)
    problems[problem["id"]]["description"] = f"docs:{file.filename}"
    write_json(problem_json, problems)


async def add_problem_testcases(id: str, upfile: UploadFile):
    problem = (await get_problem(id)).model_dump()
    
    zip_file = upfile.filename
    with open(f"{problem['dir']}/{zip_file}", "wb") as f:
        f.write(await upfile.read())
    await upfile.close()
    with zipfile.ZipFile(f"{problem['dir']}/{zip_file}", "r") as zip_ref:
        zip_ref.extractall(f"{problem['dir']}/testcase")

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
    if len(inps) != len(outs):
        raise ValueError("invalid testcases count")

    for i in range(len(inps)):
        os.makedirs(f"{problem['dir']}/testcases/{i}", exist_ok=True)
        shutil.move(
            f"{problem['dir']}/testcase/{inps[i]}",
            f"{problem['dir']}/testcases/{i}/{inps[i]}",
        )
        shutil.move(
            f"{problem['dir']}/testcase/{outs[i]}",
            f"{problem['dir']}/testcases/{i}/{outs[i]}",
        )
    
    shutil.rmtree(f"{problem['dir']}/testcase")
    os.remove(f"{problem['dir']}/{zip_file}")


# PUT
async def update_problem(id, problem: Problems):
    problem["dir"] = gen_path(problem.id) # type: ignore
    problems = read_json(problem_json)
    if id == problem.id:
        problems[id] = problem
    else:
        del problems[id]
        problems[problem.id] = problem

    write_json(problem_json, problems)


async def update_problem_docs(id: str, file: UploadFile):
    problem = (await get_problem(id)).model_dump()
    if problem["description"].startswith("docs:"):
        raise ValueError()
    with open(f"data/file/{problem['description'][5]}", "wb") as f:
        f.write(await file.read())
    await file.close()

async def update_problem_testcases(id: str, upfile: UploadFile):
    problem = (await get_problem(id)).model_dump()

    zip_file = upfile.filename
    with open(f"{problem['dir']}/{zip_file}", "wb") as f:
        f.write(await upfile.read())
    await upfile.close()
    with zipfile.ZipFile(f"{problem['dir']}/{zip_file}", "r") as zip_ref:
        zip_ref.extractall(f"{problem['dir']}/testcase")
    
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
        os.makedirs(f"{problem['dir']}/testcases/{i}", exist_ok=True)
        shutil.move(
            f"{problem['dir']}/testcase/{inps[i]}",
            f"{problem['dir']}/testcases/{i}/{inps[i]}",
        )
        shutil.move(
            f"{problem['dir']}/testcase/{outs[i]}",
            f"{problem['dir']}/testcases/{i}/{outs[i]}",
        )

    shutil.rmtree(f"{problem['dir']}/testcase")
    os.remove(f"{problem['dir']}/{zip_file}")


# DELETE
async def delete_problem(id):
    problems = read_json(problem_json)
    problem = problems[id]
    if problem["description"].startswith("docs:"):
        os.remove(os.path.join(file_dir, problem["description"][5:]))
    del problems[id]
    write_json(problem_json, problems)
