from sync_logic import SyncRunner, env_bool


def main() -> None:
    if env_bool("SYNC_API_ENABLED", False):
        from api import run_api

        run_api()
        return

    SyncRunner().run_forever()


if __name__ == "__main__":
    main()