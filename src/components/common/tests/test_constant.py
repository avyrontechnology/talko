import pytest

from src.components.common.constants import (
    TalkoCurrentUserMap,
    TalkoErrorPrompt,
    TalkoPaginationConstants,
)


class TestTalkoErrorPrompt:
    def test_token_required(self):
        assert TalkoErrorPrompt.TOKEN_REQUIRED == "Token required"

    def test_unauthorized_header(self):
        assert TalkoErrorPrompt.UNAUTHORIZED_HEADER == "Unauthorized Header"


class TestCurrentUserMap:
    def test_user_id(self):
        assert TalkoCurrentUserMap.USER_ID == "user_id"

    def test_user_role(self):
        assert TalkoCurrentUserMap.USER_ROLE == "user_role"

    def test_partner_id(self):
        assert TalkoCurrentUserMap.PARTNER_ID == "partner_id"

    def test_child_ids(self):
        assert TalkoCurrentUserMap.CHILD_IDS == "child_ids"

    def test_name(self):
        assert TalkoCurrentUserMap.NAME == "name"

    def test_email(self):
        assert TalkoCurrentUserMap.EMAIL == "email"


class TestPaginationConstants:
    def test_offset(self):
        assert TalkoPaginationConstants.offset == 1

    def test_limit(self):
        assert TalkoPaginationConstants.limit == 10

    def test_limit_max(self):
        assert TalkoPaginationConstants.LIMIT_MAX == 500
