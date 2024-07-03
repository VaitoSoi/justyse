import inquirer
import json
import os
import typing


def write_file(file: str, data: str) -> None:
    with open(file, "w") as f:
        f.write(data)


def write_json(file: str, data: typing.Dict[str, typing.Any]) -> None:
    with open(file, "w") as f:
        json.dump(data, f, indent=4)


translate = {
    "default": {
        "choose_language": ["Choose language | Chọn ngôn ngữ"],
    },
    "vi": {
        "store_place": [
            "Chọn nơi các dữ liệu được lưu trữ",
            ["Trực tiếp trên máy", "SQL (SQLite)"],
            ["file", "sql"],
        ],
        "cache_place": ["Chọn nơi cache dữ liệu", ["Redis"], ["redis"]],
        "login_methods": [
            "Chọn phương thức đăng nhập",
            ["Username + Mật khẩu", "Google", "Facebook"],
            ["pwd", "google", "facebook"],
        ],
        "pass_store": [
            "Chọn cách mật khẩu được lưu trữ",
            ["Trực tiếp", "Băm (hashed)"],
            ["plain", "hashed"],
        ],
        "hash_func": [
            "Chọn hàm băm (hash function)",
            ["bcrypt", "Argon2", "scrypt", "PBKDF2", "SHA-512", "SHA-256"],
            ["bcrypt", "argon2", "scrypt", "pbkdf2", "sha512", "sha256"],
        ],
        "testcase_strict": [
            "Chọn cách xử lý các file testcase có đuôi khác với đuôi được khai báo",
            ["Báo lỗi", "Bỏ qua"],
            ["strict", "loose"],
        ],
    },
    "en": {
        "store_place": [
            "Choose place to store the data",
            ["Directly on the machine", "SQL (SQLite)"],
            ["file", "sql"],
        ],
        "cache_place": ["Choose place to store cache", ["Redis"], ["redis"]],
        "login_methods": [
            "Choose login methods",
            ["Username + Password", "Google", "Facebook"],
            ["pwd", "google", "facebook"],
        ],
        "pass_store": [
            "Choose how the password is stored",
            ["Plain text", "Hashed"],
            ["plain", "hashed"],
        ],
        "hash_func": [
            "Choose hash function",
            ["bcrypt", "Argon2", "scrypt", "PBKDF2", "SHA-512", "SHA-256"],
            ["bcrypt", "argon2", "scrypt", "pbkdf2", "sha512", "sha256"],
        ],
        "testcase_strict": [
            "Choose how to handle testcase files with different extensions than declared",
            ["Error", "Ignore"],
            ["strict", "loose"],
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

translate = translate[config["lang"]]


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
        return translate[key][2][translate[key][1].index(inp)]
    except ValueError:
        return inp


config["store_place"] = prompt("store_place", inquirer.List)
config["cache_place"] = prompt("cache_place", inquirer.List)
config["login_methods"] = prompt("login_methods", inquirer.Checkbox)
config["pass_store"] = prompt("pass_store", inquirer.List)
config["hash_func"] = prompt("hash_func", inquirer.List) if config["pass_store"] == "hashed" else ""

os.makedirs("data", exist_ok=True)
write_json(
    "data/config.json",
    config,
)

if config["store_place"] == "Mixed (SQL + Redis)":
    os.makedirs("data/problems", exist_ok=True)
    os.makedirs("data/file", exist_ok=True)
elif config["store_place"] == "File system":
    os.makedirs("data/problems", exist_ok=True)
    os.makedirs("data/submissions", exist_ok=True)
    os.makedirs("data/users", exist_ok=True)
    os.makedirs("data/file", exist_ok=True)

    write_json("data/problems/problems.json", {})
    write_file("data/users/users.csv", "id,user,password")

print("Created config file at data/config.json")
