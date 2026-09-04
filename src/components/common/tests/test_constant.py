import pytest

from src.components.common.constants import (
    CurrentUserMap,
    HollerErrorPrompt,
    PaginationConstants,
)


class TestHollerErrorPrompt:
    def test_token_required(self):
        assert HollerErrorPrompt.TOKEN_REQUIRED == "Token required"

    def test_unauthorized_header(self):
        assert HollerErrorPrompt.UNAUTHORIZED_HEADER == "Unauthorized Header"


class TestCurrentUserMap:
    def test_user_id(self):
        assert CurrentUserMap.USER_ID == "user_id"

    def test_user_role(self):
        assert CurrentUserMap.USER_ROLE == "user_role"

    def test_partner_id(self):
        assert CurrentUserMap.PARTNER_ID == "partner_id"

    def test_child_ids(self):
        assert CurrentUserMap.CHILD_IDS == "child_ids"

    def test_name(self):
        assert CurrentUserMap.NAME == "name"

    def test_email(self):
        assert CurrentUserMap.EMAIL == "email"


class TestPaginationConstants:
    def test_offset(self):
        assert PaginationConstants.offset == 1

    def test_limit(self):
        assert PaginationConstants.limit == 10

    def test_limit_max(self):
        assert PaginationConstants.LIMIT_MAX == 500
