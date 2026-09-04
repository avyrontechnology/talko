import os

from dotenv import load_dotenv

load_dotenv()


class ENV:
    SERVICE_NAME = os.getenv("SERVICE_NAME", "Template Service")
    CONSOLE_GRPC_HOST = os.getenv("CONSOLE_GRPC_HOST", "int-console-grpc.makunaiglobal.ai")
    CONSOLE_GRPC_PORT = os.getenv("CONSOLE_GRPC_PORT", "50051")
    GRPC_CERT_PATH = os.getenv("GRPC_CERT_PATH", "certs/server.crt")
    GRPC_KEY_PATH = os.getenv("GRPC_KEY_PATH", "certs/server.key")
    GRPC_CA_CERT_PATH = os.getenv("GRPC_CA_CERT_PATH", "certs/ca.crt")
    DO_ENDPOINT_URL = os.getenv("DO_ENDPOINT_URL", "")
    DO_SPACE_NAME = os.getenv("DO_SPACE_NAME", "")
    DO_SECRET_ACCESS_KEY = os.getenv("DO_SECRET_ACCESS_KEY", "")
    DO_ACCESS_KEY_ID = os.getenv("DO_ACCESS_KEY_ID", "")
    ENVIRONMENT = os.getenv("ENV", "")
    STORAGE_SERVICE_PROVIDER = os.getenv("STORAGE_SERVICE_PROVIDER", "")
    CA = os.getenv("CA", "None")

    MONGO_DB = os.getenv("MONGO_DB", "hollerservice")
    MONGO_USER = os.getenv("MONGO_USER", "jaggerbomb")
    MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "jaggerbomb")
    MONGO_HOST = os.getenv("MONGO_HOST", "holler-mongodb")
    MONGO_PORT = os.getenv("MONGO_PORT", "27017")

    LOGGING_CONFIG_PATH = os.getenv("LOGGING_CONFIG_PATH", "src/config/log.py")

    CACHE_PROTOCOL = os.getenv("CACHE_PROTOCOL", "redis")
    CACHE_USERNAME = os.getenv("CACHE_USERNAME", "default")
    CACHE_PASSWORD = os.getenv("CACHE_PASSWORD", "pwd")
    CACHE_HOST = os.getenv("CACHE_HOST", "holler-redis")
    CACHE_PORT = os.getenv("CACHE_PORT", "6379")
    CACHE_DB = os.getenv("CACHE_DB", "1")

    RSA_PRIVATE_KEY = os.getenv("RSA_PRIVATE_KEY", "keys/private_key.pem")
    RSA_PUBLIC_KEY = os.getenv("RSA_PUBLIC_KEY", "keys/public_key.pem")

    MAGLO_BASE_URL = os.getenv("MAGLO_BASE_URL", "https://int-maglo-service.makunaiglobal.ai/maglo-service")
    CONSOLE_SERVICE_BASE_URL = os.getenv("CONSOLE_SERVICE_BASE_URL", "http://localhost:8001")
    CONSOLE_API_KEY = os.getenv("CONSOLE_API_KEY", "TEST_CONSOLE_API_KEY")

    MAILMG_API_URL = os.getenv("MAILMG_API_URL", "https://int-mailmg.makunaiglobal.ai/api/v1/email/send")
    MAILMG_CHANNEL_KEY = os.getenv("MAILMG_CHANNEL_KEY", "test_key")
    MAILMG_CLIENT_NAME = os.getenv("MAILMG_CLIENT_NAME", "holler")

    MAKUNAI_SESSION_URL = os.getenv("MAKUNAI_SESSION_URL", "https://int-makun-ai-service.makunaiglobal.ai/ai/v1/voice/sessions")
    MAKUNAI_SESSION_API_KEY = os.getenv("MAKUNAI_SESSION_API_KEY", "cc18990d45720d7d036a2a107127e4f24b7ed966f626e62621bdbebd4cc643a5")

    # Relays Tata Tele's dialer webhook (already-persisted CDR) onward to
    # makun-ai's campaign webhook — see DialerWebhookHandler._relay_to_makunai.
    MAKUNAI_CDR_WEBHOOK_URL = os.getenv("MAKUNAI_CDR_WEBHOOK_URL", "https://int-makun-ai-service.makunaiglobal.ai/ai/v1/voice/webhooks/tata-dialer-cdr")
    # Shared secret makun-ai's webhook route checks — must match its own
    # CDR_WEBHOOK_RELAY_SECRET. Hardcoded here temporarily for live testing,
    # same value as holler-oc-config's CDR_WEBHOOK_RELAY_SECRET — once that
    # Secret is actually applied to the cluster it overrides this default
    # anyway, so this is only a fallback.
    CDR_WEBHOOK_RELAY_SECRET = os.getenv(
        "CDR_WEBHOOK_RELAY_SECRET",
        "41139a57c40445ecf227b4cb36c9adb48be454591aac7cae95fa39557cc2c149",
    )

    @classmethod
    def validate_env_vars(cls):
        """
        Validate all required environment variables are defined.
        """
        missing_vars = [
            var
            for var in cls.__dict__
            if not var.startswith("__") and not getattr(cls, var)
        ]
        if missing_vars:
            raise EnvironmentError(
                "The following required environment variables are missing or empty: {}".format(
                    ", ".join(missing_vars)
                )
            )


if os.getenv("ENV"):
    ENV.validate_env_vars()
