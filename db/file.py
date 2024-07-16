"""
For file system-stored type
"""

import os
import os.path as path
import typing
import uuid
import zipfile
import shutil
from fastapi import UploadFile
from .declare import (
    file_dir,
    problem_json,
    submission_dir,
    submission_json,
    gen_path,
)
from declare import Problems, Submissions, File
from utils import (
    config,
    read_json,
    write_json,
)

"""
Problems
"""


# GET
async def get_problem_ids() -> typing.List[str]:
    return list(read_json(problem_json).keys())


async def get_problem(id) -> typing.Optional[Problems]:
    if id not in await get_problem_ids():
        return None
    return read_json(problem_json)[id]


async def get_problem_docs(id: str) -> str | None:
    problem = await get_problem(id)
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
    problem = await get_problem(id)
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
    problem = await get_problem(id)

    if path.exists(path.join(problem["dir"], "testcases")):
        shutil.rmtree(path.join(problem["dir"], "testcases"))

    zip_file = upfile.filename
    with open(f"{problem['dir']}/{zip_file}", "wb") as f:
        f.write(await upfile.read())
    await upfile.close()
    with zipfile.ZipFile(path.join(problem["dir"], zip_file), "r") as zip_ref:
        zip_ref.extractall(path.join(problem["dir"], "testcase"))

    inp_ext = problem["test_name"][0].split(".")[-1]
    out_ext = problem["test_name"][1].split(".")[-1]
    inps = []
    outs = []
    for root, dirs, files in os.walk(path.join(problem["dir"], "testcase")):
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
    if problem["total_testcases"] != len(inps) or problem["total_testcases"] != len(
        outs
    ):
        raise ValueError("invalid testcases count")

    for i in range(len(inps)):
        os.makedirs(path.join(problem["dir"], "testcases", str(i + 1)), exist_ok=True)
        shutil.move(
            path.join(problem["dir"], "testcase", inps[i]).__str__(),
            path.join(problem["dir"], "testcases", str(i + 1), problem["test_name"][0]).__str__(),
        )
        shutil.move(
            path.join(problem["dir"], "testcase", outs[i]).__str__(),
            path.join(problem["dir"], "testcases", str(i + 1), problem["test_name"][1]).__str__(),
        )

    shutil.rmtree(path.join(problem["dir"], "testcase"))
    os.remove(path.join(problem["dir"], zip_file))


# PUT
async def update_problem(id, problem: Problems):
    problem = problem.model_dump()
    problems = read_json(problem_json)
    if problem["id"] is not None and id != problem["id"]:
        problems[problem["id"]] = problems[id]
        problems[problem["id"]]["dir"] = gen_path(problem["id"])
        del problems[id]

    for key, val in problem.items():
        if val is not None and problems[id][key] != val:
            problems[id][key] = val

    write_json(problem_json, problems)


async def update_problem_docs(id: str, file: UploadFile):
    problem = await get_problem(id)
    with open(path.join(file_dir, problem['description'][5:]), "wb") as f:
        f.write(await file.read())
    await file.close()


async def update_problem_testcases(id: str, upfile: UploadFile):
    await add_problem_testcases(id=id, upfile=upfile)


# DELETE
async def delete_problem(id):
    problems = read_json(problem_json)
    problem = problems[id]
    if problem["description"].startswith("docs:"):
        os.remove(path.join(file_dir, problem["description"][5:]))
    del problems[id]
    write_json(problem_json, problems)


"""
Submissions
"""


# GET
async def get_submission_ids() -> typing.List[str]:
    return list(read_json(submission_json).keys())


async def get_submission(id: str) -> typing.Optional[Submissions]:
    return read_json(submission_json)[id]


# POST
async def add_submission(submission: Submissions):
    submission = submission.model_dump()
    submission["file_path"] = path.join(
        submission_dir, File[submission["lang"][0]].file.format(id=submission["id"])
    )
    with open(submission["file_path"], "w") as file:
        file.write(submission["code"])
    del submission["code"]
    submissions = read_json(submission_json)
    submissions[submission["id"]] = submission
    write_json(submission_json, submissions)
