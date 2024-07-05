from fastapi import FastAPI, Response, status, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
import db

api = FastAPI()

api.mount("/file", StaticFiles(directory="data/file"), name="file")

"""
Problem
"""


# GET
@api.get("/problems")
async def problems():
    return await db.get_problem_ids()


@api.get("/problems/{id}")
async def problem(id: str, response: Response):
    if id in await db.get_problem_ids():
        return await db.get_problem(id)
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "Not found D:"


@api.get("/problems/{id}/docs")
async def problem_docs(id: str, response: Response):
    docs = await db.get_problem_docs(id)
    if docs is None:
        response.status_code = status.HTTP_404_NOT_FOUND
        return "Not found D:"
    return RedirectResponse(url=f"/file/{docs}")


# POST
@api.post("/problems")
async def add_problem(problem: db.Problems, response: Response):
    if problem.id not in await db.get_problem_ids():
        await db.add_problem(problem)
        return "Added!"
    else:
        response.status_code = status.HTTP_409_CONFLICT
        return f"Problem with id {problem.id} already exists D:"


@api.post("/problems/{id}/docs")
async def add_problem_docs(id: str, file: UploadFile, response: Response):
    if id not in await db.get_problem_ids():
        response.status_code = status.HTTP_404_NOT_FOUND
        return f"Can find problem with id {id} D:"
    try:
        await db.add_problem_docs(id, file)
        return "Added!"
    except ValueError:
        response.status_code = status.HTTP_409_CONFLICT
        return f"Problem docs with id {id} already exists. Use PUT instead :D"


@api.post("/problems/{id}/testcases")
async def add_problem_testcases(id: str, file: UploadFile, response: Response):
    if id not in await db.get_problem_ids():
        response.status_code = status.HTTP_404_NOT_FOUND
        return f"Can find problem with id {id} D:"
    try:
        await db.add_problem_testcases(id, file)
        return "Added!"
    except ValueError as e:
        response.status_code = status.HTTP_409_CONFLICT
        return str(e)


# PUT
@api.put("/problems/{id}")
async def problem_update(id: str, problem: db.Problems, response: Response):
    if id in await db.get_problem_ids():
        await db.update_problem(id, problem)
        return "Updated!"
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return f"Can find problem with id {id} D:"


@api.put("/problems/{id}/docs")
async def problem_docs_update(id: str, file: UploadFile, response: Response):
    if id not in await db.get_problem_ids():
        response.status_code = status.HTTP_404_NOT_FOUND
        return f"Can find problem with id {id} D:"
    try:
        await db.problem_docs_update(id, file)
        return "Updated!"
    except ValueError:
        response.status_code = status.HTTP_404_NOT_FOUND
        return f"Problem docs with id {id} is not exists D:"


# DELETE
@api.delete("/problems/{id}")
async def problem_delete(id: str, response: Response):
    if id in await db.get_problem_ids():
        await db.delete_problem(id)
        return "Deleted!"
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return f"Can find problem with id {id} D:"


