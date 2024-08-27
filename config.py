import inquirer.questions
from utils import write_json
import inquirer
import os
import typing
import socket

cpu_rec = os.cpu_count() / 4


def write_file(file: str, data: str) -> None:
    with open(file, "w") as f:
        f.write(data)


translate = {
    "default": {"choose_language": "Choose language | Chọn ngôn ngữ"},
    "choices": {
        "store_place": ["file", "sql"],
        "cache_place": ["redis"],
        "login_methods": ["pwd", "google", "facebook"],
        "pass_store": ["plain", "hashed"],
        "hash_func": ["argon2", "scrypt", "sha512", "sha256"],
        "testcase_strict": ["strict", "loose"],
        "judge_mode": [1, 0],
        "compress_threshold": [],
    },
    "vi": {
        "store_place": [
            "Chọn nơi các dữ liệu được lưu trữ",
            ["Trực tiếp trên máy", "SQL (SQLite)"],
        ],
        "cache_place": ["Chọn nơi cache dữ liệu", ["Redis"]],
        "login_methods": [
            "Chọn phương thức đăng nhập",
            ["Username + Mật khẩu", "Google", "Facebook"],
        ],
        "pass_store": [
            "Chọn cách mật khẩu được lưu trữ",
            ["Trực tiếp", "Băm (hashed)"],
        ],
        "hash_func": [
            "Chọn hàm băm (hash function)",
            ["Argon2", "Scrypt", "SHA-512", "SHA-256"],
        ],
        "testcase_strict": [
            "Chọn cách xử lý các file testcase có đuôi khác với đuôi được khai báo",
            ["Báo lỗi", "Bỏ qua"],
        ],
        "judge_mode": [
            "Chọn chế độ chạy phân luồng",
            [
                "Đa luồng - Chia đều các test cho các luồng",
                "Đa luồng - Mỗi luồng chạy một bài nộp",
            ],
        ],
        "compress_threshold": [
            "Chọn ngưỡng mà khi độ lớn của testcase vượt quá sẽ nén (đơn vị: byte)",
            [],
        ],
        "done": ["Đã lưu config ở data/config.json"],
    },
    "en": {
        "store_place": [
            "Choose place to store the data",
            ["Directly on the machine", "SQL (SQLite)"],
        ],
        "cache_place": ["Choose place to store cache", ["Redis"], ["redis"]],
        "login_methods": [
            "Choose login methods",
            ["Username + Password", "Google", "Facebook"],
        ],
        "pass_store": [
            "Choose how the password is stored",
            ["Plain text", "Hashed"],
        ],
        "hash_func": [
            "Choose hash function",
            ["Argon2", "scrypt", "SHA-512", "SHA-256"],
        ],
        "testcase_strict": [
            "Choose how to handle testcase files with different extensions than declared",
            ["Error", "Ignore"],
        ],
        "judge_mode": [
            "Choose threading mode",
            [
                "Multi - Evenly distribute tests to threads",
                "Multi - Each thread runs a submission",
            ],
        ],
        "compress_threshold": [
            "Choose the threshold at which the size of the testcase will be compressed (unit: byte)",
            [],
        ],
        "done": ["Saved config at data/config.json"],
    },
}


config: dict[str, str] = {}
config["lang"] = inquirer.prompt(
    [
        inquirer.List(
            "language",
            translate["default"]["choose_language"],
            ["vi", "en"],
            default="vi",
        )
    ]
)["language"]  # type: ignore

translate = translate[config["lang"]] | {"choices": translate["choices"]}


def get_translate(key, inp):
    return translate["choices"][key][translate[key][1].index(inp)]


def prompt(
    key: str,
    call: typing.Callable,
    validator: typing.Callable[[inquirer.questions.Question, typing.Any], bool] = None,
) -> str:
    inp = inquirer.prompt(
        [
            call(
                name=key,
                message=translate[key][0],
                choices=translate[key][1],
                validate=validator or True,
            )
        ]
    )[key]

    try:
        return (
            [get_translate(key, i) for i in inp]
            if isinstance(inp, list)
            else get_translate(key, inp)
        )
    except ValueError:
        return inp


def is_available_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) != 0


config["store_place"] = prompt("store_place", inquirer.List)
config["cache_place"] = prompt("cache_place", inquirer.List)
config["login_methods"] = prompt("login_methods", inquirer.Checkbox)
config["pass_store"] = prompt("pass_store", inquirer.List)
config["hash_func"] = prompt("hash_func", inquirer.List) if config["pass_store"] == "hashed" else None
config["testcase_strict"] = prompt("testcase_strict", inquirer.List)
config["judge_mode"] = prompt("judge_mode", inquirer.List)
config["compress_threshold"] = prompt("compress_threshold", inquirer.Text, validator=lambda _, a: a.isdigit())

write_json("data/config.json", config)

os.makedirs("data", exist_ok=True)
os.makedirs("data/problem", exist_ok=True)
os.makedirs("data/file", exist_ok=True)
os.makedirs("executions", exist_ok=True)

if config["store_place"] == "sql":
    ...
elif config["store_place"] == "file":
    os.makedirs("data/problems", exist_ok=True)
    os.makedirs("data/submissions", exist_ok=True)
    os.makedirs("data/users", exist_ok=True)
    os.makedirs("data/file", exist_ok=True)

    write_json("data/problems/problems.json", {})
    write_json("data/submissions/submissions.json", {})
    write_file("data/users/users.csv", "id,user,password")

print(translate["done"][0])
