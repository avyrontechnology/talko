from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoUserRole:
    SUPERADMIN = "superadmin"
    MAINTAINER = "maintainer"
    VIEWER = "viewer"

    ALL = (SUPERADMIN, MAINTAINER, VIEWER)


class TalkoUserModel(TalkoTimestampedModel):
    email: str
    name: str
    phone: str | None = None
    # PBKDF2-SHA256 PHC-style string ("pbkdf2-sha256$iter$salt$hash").
    # Raw passwords are never stored.
    password_hash: str
    role: str = TalkoUserRole.VIEWER
    # Null only for cross-partner superadmins.
    partner_id: int | None = None
    is_active: bool = True

    class CollectionName:
        TALKO_USERS = "talko_users"
