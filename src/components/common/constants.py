class HollerErrorPrompt:
    TOKEN_REQUIRED: str = "Token required"
    UNAUTHORIZED_HEADER: str = "Unauthorized Header"


class CurrentUserMap:
    USER_ID: str = "user_id"
    USER_ROLE: str = "user_role"
    PARTNER_ID: str = "partner_id"
    CHILD_IDS: str = "child_ids"
    NAME: str = "name"
    EMAIL: str = "email"
    ADMIN_ROLE_HIERARCHY_LEVEL: int = 1
    MANAGER_ROLE_HIERARCHY_LEVEL: int = 4
    AGENT_ROLE_HIERARCHY_LEVEL: int = 8
    TEAM_LEAD_ROLE_HIERARCHY_LEVEL: int


class PaginationConstants:
    offset: int = 1
    limit: int = 10
    LIMIT_MAX: int = 500
