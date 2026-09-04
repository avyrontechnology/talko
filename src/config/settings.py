from pydantic_settings import BaseSettings


class TalkoLocalSettings(BaseSettings):
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


class TalkoDevSettings(BaseSettings):
    pass


local_settings = TalkoLocalSettings()  # type: ignore
live_server_settings = TalkoLocalSettings()  # TODO: Change to TalkoDevSettings() when its setup
