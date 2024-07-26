"""
For file system-stored type
"""

import os
import os.path as path
import typing
import uuid

from fastapi import UploadFile

from declare import File
from utils import read_json, write_json
from .declare import (
    file_dir,
    problem_json,
    submission_dir,
    submission_json,
    gen_path,
    unzip_testcases,
    Problems,
    Submissions)
from .exception import (
    ProblemNotFound,
    ProblemAlreadyExisted,
    ProblemDocsAlreadyExist,
    ProblemDocsNotFound,
)

"""
Problems
"""


# GET
def get_problem_ids() -> typing.List[str]:
    return list(read_json(problem_json).keys())


def get_problem(id) -> typing.Optional[Problems]:
    if id not in get_problem_ids():
        raise ProblemNotFound()
    return Problems(**read_json(problem_json)[id])


def get_problem_docs(id: str) -> typing.Optional[str]:
    problem = get_problem(id)
    if not problem:
        raise ProblemNotFound()
    if not problem["description"].startswith("docs:"):
        raise ProblemDocsNotFound(id)
    return problem["description"][5:]


# POST
def add_problem(problem: Problems):
    problems = read_json(problem_json)
    if problem.id in problem:
        raise ProblemAlreadyExisted(problem.id)

    problems[problem.id] = problem.model_dump()
    problems[problem.id]["dir"] = gen_path(problem.id)
    try:
        os.makedirs(problems[problem.id]["dir"], exist_ok=False)
    except OSError:
        raise ProblemAlreadyExisted(problem.id)

    write_json(problem_json, problems)


def add_problem_docs(id: str, file: UploadFile):
    problem = get_problem(id)
    if problem is None:
        raise ProblemNotFound(id)
    if problem.description.startswith("docs:"):
        raise ProblemDocsAlreadyExist(problem.id)
    file.filename = f"{uuid.uuid4().__str__()}.pdf"
    with open(f"{file_dir}/{file.filename}", "wb") as f:
        f.write(file.file.read())
    file.file.close()

    problems = read_json(problem_json)
    problems[problem["id"]]["description"] = f"docs:{file.filename}"
    write_json(problem_json, problems)


def add_problem_testcases(id: str, upfile: UploadFile):
    problem = get_problem(id)

    unzip_testcases(problem, upfile)


# PATCH
def update_problem(id, problem: Problems):
    problem = problem.model_dump()
    problems = read_json(problem_json)
    if id not in problems:
        raise ProblemNotFound()

    if problem["id"] is not None and id != problem["id"]:
        problems[problem["id"]] = problems[id]
        problems[problem["id"]]["dir"] = gen_path(problem["id"])
        del problems[id]

    for key, val in problem.items():
        if val is not None and problems[id][key] != val:
            problems[id][key] = val

    write_json(problem_json, problems)


def update_problem_docs(id: str, file: UploadFile):
    problem = get_problem(id)

    if not problem:
        raise ProblemNotFound()

    if not problem.description.startswith("docs:"):
        raise ProblemDocsNotFound()

    with open(path.join(file_dir, problem['description'][5:]), "wb") as f:
        f.write(file.read())
    file.close()


def update_problem_testcases(id: str, upfile: UploadFile):
    add_problem_testcases(id=id, upfile=upfile)


# DELETE
def delete_problem(id: str):
    problems = read_json(problem_json)
    problem = problems[id]
    if id not in problem:
        raise ProblemNotFound()
    if problem["description"].startswith("docs:"):
        os.remove(path.join(file_dir, problem["description"][5:]))
    del problems[id]
    write_json(problem_json, problems)


"""
Submissions
"""


# GET
def get_submission_ids() -> typing.List[str]:
    return list(read_json(submission_json).keys())


def get_submission(id: str) -> typing.Optional[Submissions]:
    if id not in get_submission_ids():
        return None
    return Submissions(**read_json(submission_json)[id])


# POST
def add_submission(submission: Submissions):
    submission = submission.model_dump()
    submission["dir"] = path.join(submission_dir, submission['id'])
    submission["file_path"] = path.join(submission["dir"], File[submission["lang"][0]].file.format(id=submission["id"]))
    os.makedirs(submission["dir"], exist_ok=False)
    with open(submission["file_path"], "w") as file:
        file.write(submission["code"])
    del submission["code"]
    submissions = read_json(submission_json)
    submissions[submission["id"]] = submission
    write_json(submission_json, submissions)
