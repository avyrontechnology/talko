import os

from dotenv import load_dotenv

load_dotenv()


class TalkoENV:
    SERVICE_NAME = os.getenv("SERVICE_NAME", "Template Service")
    DO_ENDPOINT_URL = os.getenv("DO_ENDPOINT_URL", "")
    DO_SPACE_NAME = os.getenv("DO_SPACE_NAME", "")
    DO_SECRET_ACCESS_KEY = os.getenv("DO_SECRET_ACCESS_KEY", "")
    DO_ACCESS_KEY_ID = os.getenv("DO_ACCESS_KEY_ID", "")
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")
    CLOUDINARY_FOLDER = os.getenv("CLOUDINARY_FOLDER", "talko")
    ENVIRONMENT = os.getenv("TalkoENV", "")
    STORAGE_SERVICE_PROVIDER = os.getenv("STORAGE_SERVICE_PROVIDER", "")
    CA = os.getenv("CA", "None")

    MONGO_DB = os.getenv("MONGO_DB", "talkoservice")
    MONGO_USER = os.getenv("MONGO_USER", "jaggerbomb")
    MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "jaggerbomb")
    MONGO_HOST = os.getenv("MONGO_HOST", "talko-mongodb")
    MONGO_PORT = os.getenv("MONGO_PORT", "27017")

    LOGGING_CONFIG_PATH = os.getenv("LOGGING_CONFIG_PATH", "src/config/log.py")

    CACHE_PROTOCOL = os.getenv("CACHE_PROTOCOL", "redis")
    CACHE_USERNAME = os.getenv("CACHE_USERNAME", "default")
    CACHE_PASSWORD = os.getenv("CACHE_PASSWORD", "pwd")
    CACHE_HOST = os.getenv("CACHE_HOST", "talko-redis")
    CACHE_PORT = os.getenv("CACHE_PORT", "6379")
    CACHE_DB = os.getenv("CACHE_DB", "1")

    RSA_PRIVATE_KEY = os.getenv("RSA_PRIVATE_KEY", "keys/private_key.pem")
    RSA_PUBLIC_KEY = os.getenv("RSA_PUBLIC_KEY", "keys/public_key.pem")

    MAKUNAI_SESSION_URL = os.getenv(
        "MAKUNAI_SESSION_URL", "https://int-makun-ai-service.makunaiglobal.ai/ai/v1/voice/sessions"
    )
    MAKUNAI_SESSION_API_KEY = os.getenv(
        "MAKUNAI_SESSION_API_KEY", "cc18990d45720d7d036a2a107127e4f24b7ed966f626e62621bdbebd4cc643a5"
    )

    # ── voiceai (external AI voice-agent engine) trunk integration ──────
    # When a call carries context_data.voiceai_agent_id (outbound calls placed
    # via voiceai's talko_api_server) or its DID is mapped below (inbound),
    # TalkoPSTNBridgeService relays Tata media to voiceai's WS instead of the
    # makun-ai LiveKit path — see src/components/pstn/voiceai_relay.py.
    # voiceai WS auth: Talko mints a single-use ticket per call via
    # POST {VOICEAI_API_BASE_URL}/auth/ws-ticket using VOICEAI_API_KEY (a voiceai
    # Bearer API key with calls:write scope), then opens
    # {VOICEAI_WS_BASE_URL}/chat/v1/{agent_id}?token={ticket}.
    VOICEAI_API_BASE_URL = os.getenv("VOICEAI_API_BASE_URL", "")
    VOICEAI_WS_BASE_URL = os.getenv("VOICEAI_WS_BASE_URL", "")
    VOICEAI_API_KEY = os.getenv("VOICEAI_API_KEY", "")
    VOICEAI_WS_TICKET_TIMEOUT_SECONDS = float(os.getenv("VOICEAI_WS_TICKET_TIMEOUT_SECONDS", "10"))
    VOICEAI_WS_CONNECT_TIMEOUT_SECONDS = float(os.getenv("VOICEAI_WS_CONNECT_TIMEOUT_SECONDS", "15"))
    # Optional inbound routing: JSON map of Talko DID -> voiceai agent_id,
    # e.g. '{"918045678901": "agent_abc123"}'. DIDs listed here bypass the
    # makun-ai path even without per-call context_data.
    VOICEAI_INBOUND_AGENT_MAP = os.getenv("VOICEAI_INBOUND_AGENT_MAP", "")
    # DID -> agent engine lookup (cached). Talko asks the voiceai engine's
    # GET {VOICEAI_API_BASE_URL}/phone-numbers/resolve per DID, Redis-cached.
    # Env map above stays as emergency override and wins when set.
    VOICEAI_DID_RESOLVE_TIMEOUT_SECONDS = float(os.getenv("VOICEAI_DID_RESOLVE_TIMEOUT_SECONDS", "0.3"))
    VOICEAI_DID_CACHE_TTL_SECONDS = int(os.getenv("VOICEAI_DID_CACHE_TTL_SECONDS", "60"))
    VOICEAI_DID_NEGATIVE_CACHE_TTL_SECONDS = int(os.getenv("VOICEAI_DID_NEGATIVE_CACHE_TTL_SECONDS", "10"))

    # Relays Tata Tele's dialer webhook (already-persisted TalkoCDR) onward to
    # makun-ai's campaign webhook — see TalkoDialerWebhookHandler._relay_to_makunai.
    MAKUNAI_CDR_WEBHOOK_URL = os.getenv(
        "MAKUNAI_CDR_WEBHOOK_URL", "https://int-makun-ai-service.makunaiglobal.ai/ai/v1/voice/webhooks/tata-dialer-cdr"
    )
    # Shared secret makun-ai's webhook route checks — must match its own
    # CDR_WEBHOOK_RELAY_SECRET. Hardcoded here temporarily for live testing,
    # same value as talko-oc-config's CDR_WEBHOOK_RELAY_SECRET — once that
    # Secret is actually applied to the cluster it overrides this default
    # anyway, so this is only a fallback.
    CDR_WEBHOOK_RELAY_SECRET = os.getenv(
        "CDR_WEBHOOK_RELAY_SECRET",
        "41139a57c40445ecf227b4cb36c9adb48be454591aac7cae95fa39557cc2c149",
    )

    # Fernet master key (generate via `Fernet.generate_key()`) used to
    # encrypt partner webhook signing secrets at rest — must be identical
    # across all pods/replicas, since any of them may need to decrypt a
    # secret to sign an outbound delivery. Rotating it invalidates every
    # stored webhook secret. No default: validate_env_vars() below forces
    # this to be provisioned as a real secret in deployed environments.
    WEBHOOK_SECRET_MASTER_KEY = os.getenv("WEBHOOK_SECRET_MASTER_KEY", "")

    # Talko-native user auth (user_auth component). No default: login refuses
    # to mint tokens until this is provisioned as a real secret.
    TALKO_JWT_SECRET = os.getenv("TALKO_JWT_SECRET", "")
    # Shared secret with the voiceai engine for signed carrier stream tokens
    # (see voiceai.platform.stream_token). When set, the relay mints its WS
    # auth token locally (~0ms) instead of POSTing /auth/ws-ticket (~1.3s).
    # Must equal the engine's VOICE_STREAM_SECRET.
    VOICE_STREAM_SECRET = os.getenv("VOICE_STREAM_SECRET", "")
    TALKO_JWT_TTL_HOURS = int(os.getenv("TALKO_JWT_TTL_HOURS", "72"))

    @classmethod
    def validate_env_vars(cls):
        """
        Validate all required environment variables are defined.
        """
        missing_vars = [var for var in cls.__dict__ if not var.startswith("__") and not getattr(cls, var)]
        if missing_vars:
            raise OSError(
                "The following required environment variables are missing or empty: {}".format(", ".join(missing_vars))
            )


if os.getenv("TalkoENV"):
    TalkoENV.validate_env_vars()
