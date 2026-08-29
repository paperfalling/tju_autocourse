# @Time    : 2025/09/05 14:16
# @Author  : papersus
# @File    : course_fetch.py
import tju_autocourse as atc


def _main() -> None:
    config = atc.get_config("./config.yaml")
    atc.set_config_meta(config["meta"])
    users = atc.create_users(config["users"])
    for user in users:
        user.prepare(save_path="./data")


if __name__ == "__main__":
    _main()
