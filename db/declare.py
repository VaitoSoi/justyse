import os

def gen_path(id: str) -> str:
    return os.path.join(problem_dir, id)

file_dir = f"{os.getcwd()}/data/file"
problem_dir = f"{os.getcwd()}/data/problems"
problem_json = f"{problem_dir}/problems.json"
submission_dir = f"{os.getcwd()}/data/submissions"
submission_json = f"{submission_dir}/submissions.json"