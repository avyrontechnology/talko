from pydantic_settings import BaseSettings


class LocalSettings(BaseSettings):
    # database_url: "postgresql+asyncpg://jaggerbomb:jaggerbomb@maglo-db/magloservice"
    echo_sql: bool = True
    test: bool = False
    project_name: str = "Maglo Service"
    oauth_token_secret: str = "my_dev_secret"
    log_level: str = "DEBUG"
    # telecom_service = "TOCOM"
    redis_host: str = "console-redis"
    redis_port: int = 6379
    redis_password: str = "pwd"


class DevSettings(BaseSettings):
    pass


local_settings = LocalSettings()  # type: ignore
live_server_settings = LocalSettings()  # TODO: Change to DevSettings() when its setup
