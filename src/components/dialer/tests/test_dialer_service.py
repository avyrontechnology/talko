import re
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
import requests
from bson import ObjectId

from src.components.dialer import messages as dialer_messages
from src.components.dialer.services import DialerService
from src.exceptions import BadRequestError, ResourceNotFound


class MockLeadListItem:
    def __init__(self, **kwargs):
        self.data = kwargs

    def model_dump(self):
        return self.data


@pytest.fixture
def mock_partner_config_repo():
    return Mock()


@pytest.fixture
def mock_vendor_config_repo():
    return Mock()


@pytest.fixture
def mock_logger():
    return Mock()


@pytest.fixture
def dialer_service(mock_partner_config_repo, mock_vendor_config_repo, mock_logger):
    return DialerService(
        partner_config_repository=mock_partner_config_repo,
        vendor_config_repository=mock_vendor_config_repo,
        logger=mock_logger,
    )


class TestDialerService:

    # -------------------------------------------------------------------------
    # fetch_lead_lists Tests
    # -------------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_dialer_disabled(
        self, dialer_service, mock_partner_config_repo
    ):
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": False}
        )
        with pytest.raises(BadRequestError, match=dialer_messages.DIALER_NOT_ENABLED):
            await dialer_service.fetch_lead_lists(1)

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_missing_vendor_id(
        self, dialer_service, mock_partner_config_repo
    ):
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True}
        )
        with pytest.raises(
            BadRequestError,
            match=dialer_messages.NO_VENDOR_CONFIGURATION_LINKED_PARTNER,
        ):
            await dialer_service.fetch_lead_lists(1)

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_invalid_objectid(
        self, dialer_service, mock_partner_config_repo
    ):
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": "invalid-id"}
        )
        with pytest.raises(
            BadRequestError,
            match=dialer_messages.INVALID_VENDOR_CONFIGURATION_ID_FORMAT,
        ):
            await dialer_service.fetch_lead_lists(1)

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_vendor_not_found(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(return_value=None)
        with pytest.raises(
            ResourceNotFound, match=dialer_messages.VENDOR_CONFIGURATION_NOT_FOUND
        ):
            await dialer_service.fetch_lead_lists(1)

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_missing_handler(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={"dialer_url_handler": {}}
        )
        with pytest.raises(
            BadRequestError,
            match=dialer_messages.DIALER_URL_HANDLER_CONFIGURATION_MISSING,
        ):
            await dialer_service.fetch_lead_lists(1)

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_success(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "lead_lists_fetch": {
                        "endpoint": "http://tata.api",
                        "auth_type": "none",
                    }
                }
            }
        )

        mock_response = Mock()
        mock_response.json.return_value = [
            {"id": 1, "name": "List A", "description": "desc"}
        ]
        mock_response.raise_for_status = Mock()
        dialer_service.client.get = AsyncMock(return_value=mock_response)
        result = await dialer_service.fetch_lead_lists(1)

        assert len(result) == 1
        assert result[0]["name"] == "List A"

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_request_exception(
        self,
        dialer_service,
        mock_partner_config_repo,
        mock_vendor_config_repo,
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "lead_lists_fetch": {"endpoint": "h", "auth_type": "none"}
                }
            }
        )

        # Mock the async client to raise an exception
        dialer_service.client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection Timeout")
        )

        with pytest.raises(BadRequestError, match="Failed to fetch lead lists"):
            await dialer_service.fetch_lead_lists(1)

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_missing_endpoint_url(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "lead_lists_fetch": {
                        # "endpoint" is missing here
                        "auth_type": "none"
                    }
                }
            }
        )

        with pytest.raises(
            BadRequestError,
            match=dialer_messages.MISSING_ENDPOINT_IN_LEAD_LISTS_FETCH_CONFIGURATION,
        ):
            await dialer_service.fetch_lead_lists(1)

    # bulk_create_leads Tests

    @pytest.mark.asyncio
    async def test_bulk_create_leads_invalid_payload(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": str(ObjectId())}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {"bulk_leads_create": {"endpoint": "h/{id}"}}
            }
        )
        expected_msg = f".*{dialer_messages.NO_DATA_PROVIDED_FOR_BULK_CREATE}"

        with pytest.raises(BadRequestError, match=expected_msg):
            await dialer_service.bulk_create_leads(1, "list_123", {"wrong_key": []})

    @pytest.mark.asyncio
    async def test_bulk_create_leads_invalid_lead_format(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "bulk_leads_create": {"endpoint": "h/{id}", "auth_type": "none"}
                }
            }
        )

        payload = {"data": ["not-a-dict"]}
        with pytest.raises(BadRequestError, match="must be an object"):
            await dialer_service.bulk_create_leads(1, "list_123", payload)

    @pytest.mark.asyncio
    async def test_bulk_create_leads_missing_field0(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "bulk_leads_create": {"endpoint": "h/{id}", "auth_type": "none"}
                }
            }
        )

        payload = {"data": [{"name": "Missing Phone"}]}

        raw_msg = "Internal error while processing in bulk lead upload: Each lead must contain field_0 (phone number)"

        with pytest.raises(BadRequestError, match=re.escape(raw_msg)):
            await dialer_service.bulk_create_leads(1, "list_123", payload)

    @pytest.mark.asyncio
    async def test_bulk_create_leads_invalid_duplicate_option(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "bulk_leads_create": {"endpoint": "h/{id}", "auth_type": "none"}
                }
            }
        )

        payload = {
            "data": [{"field_0": "123"}],
            "duplicate_option": "delete_all",
        }  # Invalid option
        with pytest.raises(BadRequestError, match="Invalid 'duplicate_option'"):
            await dialer_service.bulk_create_leads(1, "list_123", payload)

    @pytest.mark.asyncio
    async def test_bulk_create_leads_success(
        self,
        dialer_service,
        mock_partner_config_repo,
        mock_vendor_config_repo,
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "bulk_leads_create": {
                        "endpoint": "http://tata.api/lists/{id}/leads",
                        "auth_type": "bearer",
                        "auth_credentials": {"token": "tok"},
                    }
                }
            }
        )

        mock_resp = Mock()
        mock_resp.json.return_value = {"batch_id": "999", "status": "success"}
        mock_resp.raise_for_status = Mock()

        dialer_service.client.post = AsyncMock(return_value=mock_resp)
        payload = {"data": [{"field_0": "919876543210"}], "duplicate_option": "skip"}
        result = await dialer_service.bulk_create_leads(1, "list_xyz", payload)
        assert result["batch_id"] == "999"
        dialer_service.client.post.assert_called_once()
        args, kwargs = dialer_service.client.post.call_args
        assert args[0] == "http://tata.api/lists/list_xyz/leads"
        assert kwargs["headers"]["Authorization"] == "Bearer tok"
        assert kwargs["json"] == payload

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_missing_specific_handler(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={"dialer_url_handler": {"some_other_handler": {}}}
        )

        with pytest.raises(
            BadRequestError,
            match=dialer_messages.LEAD_LISTS_FETCH_CONFIGURATION_NOT_FOUND,
        ):
            await dialer_service.fetch_lead_lists(1)

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_missing_token(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "lead_lists_fetch": {
                        "endpoint": "h",
                        "auth_type": "bearer",
                        "auth_credentials": {},
                    }  # No token
                }
            }
        )
        with pytest.raises(BadRequestError, match="Missing bearer token"):
            await dialer_service.fetch_lead_lists(1)

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_api_failure(
        self,
        dialer_service,
        mock_partner_config_repo,
        mock_vendor_config_repo,
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "lead_lists_fetch": {"endpoint": "h", "auth_type": "none"}
                }
            }
        )

        # Mock connection refused
        dialer_service.client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection Refused")
        )

        with pytest.raises(BadRequestError, match="Failed to fetch lead lists"):
            await dialer_service.fetch_lead_lists(1)

    @pytest.mark.asyncio
    async def test_bulk_create_leads_no_partner_config(
        self, dialer_service, mock_partner_config_repo
    ):
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value=None
        )
        with pytest.raises(BadRequestError, match=dialer_messages.DIALER_NOT_ENABLED):
            await dialer_service.bulk_create_leads(1, "l", {})

    @pytest.mark.asyncio
    async def test_bulk_create_leads_missing_url_handler(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={"other_key": "no_handler_here"}
        )

        with pytest.raises(
            BadRequestError,
            match=dialer_messages.DIALER_URL_HANDLER_CONFIGURATION_MISSING,
        ):
            await dialer_service.bulk_create_leads(1, "l", {})

    @pytest.mark.asyncio
    async def test_bulk_create_leads_request_exception(
        self,
        dialer_service,
        mock_partner_config_repo,
        mock_vendor_config_repo,
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "bulk_leads_create": {"endpoint": "h", "auth_type": "none"}
                }
            }
        )

        # Mock post failure
        dialer_service.client.post = AsyncMock(
            side_effect=httpx.TimeoutException("Timeout")
        )

        payload = {"data": [{"field_0": "1234567890"}]}
        with pytest.raises(BadRequestError, match="Failed to create bulk leads"):
            await dialer_service.bulk_create_leads(1, "list_123", payload)

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_missing_bearer_token(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "lead_lists_fetch": {
                        "endpoint": "http://test",
                        "auth_type": "bearer",
                        "auth_credentials": {},
                    }
                }
            }
        )
        with pytest.raises(BadRequestError, match="Missing bearer token"):
            await dialer_service.fetch_lead_lists(1)

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_network_error(
        self,
        dialer_service,
        mock_partner_config_repo,
        mock_vendor_config_repo,
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "lead_lists_fetch": {"endpoint": "h", "auth_type": "none"}
                }
            }
        )

        dialer_service.client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection failed")
        )

        with pytest.raises(BadRequestError, match="Failed to fetch lead lists"):
            await dialer_service.fetch_lead_lists(1)

    @pytest.mark.asyncio
    async def test_bulk_create_leads_missing_handler_config(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        # Vendor config exists, but bulk_leads_create key is missing
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={"dialer_url_handler": {"something_else": {}}}
        )

        with pytest.raises(
            BadRequestError,
            match=dialer_messages.BULK_LEADS_CREATION_CONFIGURATION_NOT_FOUND,
        ):
            await dialer_service.bulk_create_leads(
                1, "list_123", {"data": [{"field_0": "123"}]}
            )

    @pytest.mark.asyncio
    async def test_bulk_create_leads_missing_bearer_token(
        self, dialer_service, mock_partner_config_repo, mock_vendor_config_repo
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "bulk_leads_create": {
                        "endpoint": "http://test",
                        "auth_type": "bearer",
                        "auth_credentials": {},  # No token
                    }
                }
            }
        )
        with pytest.raises(BadRequestError, match="Missing bearer token"):
            await dialer_service.bulk_create_leads(
                1, "list_123", {"data": [{"field_0": "123"}]}
            )

    @pytest.mark.asyncio
    async def test_fetch_lead_lists_request_exception_path(
        self,
        dialer_service,
        mock_partner_config_repo,
        mock_vendor_config_repo,
    ):
        vid = str(ObjectId())
        mock_partner_config_repo.find_partner_config_by_partner_id = AsyncMock(
            return_value={"dialer_enabled": True, "vendor_config_id": vid}
        )
        mock_vendor_config_repo.find_config_by_id = AsyncMock(
            return_value={
                "dialer_url_handler": {
                    "lead_lists_fetch": {"endpoint": "h", "auth_type": "none"}
                }
            }
        )

        dialer_service.client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection error")
        )

        with pytest.raises(BadRequestError, match="Failed to fetch lead lists"):
            await dialer_service.fetch_lead_lists(1)
