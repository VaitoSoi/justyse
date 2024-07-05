import inquirer
import json
import os
import typing
import socket


def write_file(file: str, data: str) -> None:
    with open(file, "w") as f:
        f.write(data)


def write_json(file: str, data: typing.Dict[str, typing.Any]) -> None:
    with open(file, "w") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)




translate = {
    "default": {"choose_language": "Choose language | Chọn ngôn ngữ"},
    "choices": {
        "store_place": ["file", "sql"],
        "cache_place": ["redis"],
        "login_methods": ["pwd", "google", "facebook"],
        "pass_store": ["plain", "hashed"],
        "hash_func": ["bcrypt", "argon2", "scrypt", "pbkdf2", "sha512", "sha256"],
        "testcase_strict": ["strict", "loose"],
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
            ["bcrypt", "Argon2", "scrypt", "PBKDF2", "SHA-512", "SHA-256"],
        ],
        "testcase_strict": [
            "Chọn cách xử lý các file testcase có đuôi khác với đuôi được khai báo",
            ["Báo lỗi", "Bỏ qua"],
        ],
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
            ["bcrypt", "Argon2", "scrypt", "PBKDF2", "SHA-512", "SHA-256"],
        ],
        "testcase_strict": [
            "Choose how to handle testcase files with different extensions than declared",
            ["Error", "Ignore"],
        ],
    },
}

config = {}
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

def prompt(key: str, call: typing.Callable) -> str:
    inp = inquirer.prompt(
        [
            call(
                key,
                translate[key][0],
                translate[key][1],
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
config["hash_func"] = (
    prompt("hash_func", inquirer.List) if config["pass_store"] == "hashed" else None
)

os.makedirs("data", exist_ok=True)
write_json(
    "data/config.json",
    config | {"container_port": 80},
)

if config["store_place"] == "sql":
    os.makedirs("data/problems", exist_ok=True)
    os.makedirs("data/file", exist_ok=True)
elif config["store_place"] == "file":
    os.makedirs("data/problems", exist_ok=True)
    os.makedirs("data/submissions", exist_ok=True)
    os.makedirs("data/users", exist_ok=True)
    os.makedirs("data/file", exist_ok=True)

    write_json("data/problems/problems.json", {})
    write_file("data/users/users.csv", "id,user,password")

print("Created config file at data/config.json")
