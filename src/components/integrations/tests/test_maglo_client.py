from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
import pytest_asyncio

from src.components.integrations.console.maglo_client import MagloClient
from src.components.integrations.console.maglo_constants import MagloApiConstants
from src.loggers.holler_service_logger import HollerServiceLogger


@pytest.fixture
def mock_logger():
    """Mock logger"""
    logger = MagicMock(spec=HollerServiceLogger)
    logger.info = MagicMock()
    logger.debug = MagicMock()
    logger.error = MagicMock()
    logger.warning = MagicMock()
    return logger


@pytest_asyncio.fixture
async def maglo_client(mock_logger):
    """
    Async fixture: creates MagloClient and cleans up session after test.
    Uses pytest_asyncio.fixture for proper async handling.
    """
    client = MagloClient(logger=mock_logger)
    yield client
    if not client.session.closed:
        await client.close()


def create_mock_response(status, json_data=None, text_data=None):
    """Helper to create a properly mocked aiohttp response with async context manager support"""
    mock_resp = AsyncMock()
    mock_resp.status = status

    if json_data is not None:
        mock_resp.json = AsyncMock(return_value=json_data)

    if text_data is not None:
        mock_resp.text = AsyncMock(return_value=text_data)

    # Make it work as an async context manager
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    return mock_resp


@pytest.mark.asyncio
async def test_get_agent_details_success(maglo_client, mock_logger):
    mock_response_data = {
        "id": 33,
        "name": "Test Agent",
        "number": "+919876543210",
        "extension": "0601234567",
        "internet_calling_enable": True,
    }

    mock_resp = create_mock_response(200, json_data=mock_response_data)

    with patch.object(maglo_client.session, "get", return_value=mock_resp):
        result = await maglo_client.get_agent_details(agent_id=33, service_board_id=70)

        assert result == mock_response_data
        mock_logger.info.assert_called_with(
            "Fetching Maglo agent details - agent_id=33, board=70"
        )
        mock_logger.debug.assert_any_call(
            f"Maglo response for agent 33: {mock_response_data}"
        )


@pytest.mark.asyncio
async def test_get_agent_details_404(maglo_client, mock_logger):
    mock_resp = create_mock_response(404, text_data='{"detail": "Not found"}')

    with patch.object(maglo_client.session, "get", return_value=mock_resp):
        with pytest.raises(ValueError) as exc:
            await maglo_client.get_agent_details(33, 70)

        assert "Maglo error 404" in str(exc.value)
        mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_get_agent_details_connection_error(maglo_client, mock_logger):
    with patch.object(
        maglo_client.session, "get", side_effect=aiohttp.ClientConnectionError()
    ):
        with pytest.raises(aiohttp.ClientConnectionError):
            await maglo_client.get_agent_details(33, 70)

        mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_upsert_ivr_lead_success(maglo_client, mock_logger):
    mock_response_data = {"id": 123, "name": "Test Lead"}

    mock_resp = create_mock_response(200, json_data={"data": mock_response_data})

    with patch.object(maglo_client.session, "patch", return_value=mock_resp):
        result = await maglo_client.upsert_ivr_lead(12, 70, "+919876543210")
        assert result == mock_response_data


@pytest.mark.asyncio
async def test_upsert_ivr_lead_error(maglo_client, mock_logger):
    mock_resp = create_mock_response(400, text_data='{"error": "Bad request"}')

    with patch.object(maglo_client.session, "patch", return_value=mock_resp):
        with pytest.raises(ValueError) as exc:
            await maglo_client.upsert_ivr_lead(12, 70, "+919876543210")

        assert "Maglo IVR lead API error 400" in str(exc.value)
        mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_close_session(maglo_client, mock_logger):
    assert not maglo_client.session.closed
    await maglo_client.close()
    assert maglo_client.session.closed
    mock_logger.debug.assert_called_with("MagloClient session closed")


@pytest.mark.asyncio
async def test_timeout_configuration(maglo_client):
    assert (
        maglo_client.session.timeout.total == MagloApiConstants.REQUEST_TIMEOUT_SECONDS
    )


@pytest.mark.asyncio
async def test_headers_default(maglo_client):
    assert "accept" in maglo_client.headers
    assert maglo_client.headers["accept"] == "application/json"


@pytest.mark.asyncio
async def test_base_url_configuration(maglo_client):
    # Verify base URL is properly stripped of trailing slashes
    assert not maglo_client.base_url.endswith("/")
    assert maglo_client.base_url == MagloApiConstants.MAGLO_BASE_URL.rstrip("/")


@pytest.mark.asyncio
async def test_get_agent_details_params_sent_correctly(maglo_client, mock_logger):
    """Test that URL parameters are correctly formatted and sent"""
    mock_resp = create_mock_response(200, json_data={"id": 42})

    with patch.object(maglo_client.session, "get", return_value=mock_resp) as mock_get:
        await maglo_client.get_agent_details(agent_id=42, service_board_id=99)

        # Verify the get method was called with correct params
        call_args = mock_get.call_args
        assert call_args[1]["params"] == {"agent_id": "42", "service_board_id": "99"}


@pytest.mark.asyncio
async def test_upsert_ivr_lead_payload_structure(maglo_client, mock_logger):
    """Test that the payload is correctly structured for IVR lead upsert"""
    mock_resp = create_mock_response(200, json_data={"data": {"id": 123}})

    with patch.object(
        maglo_client.session, "patch", return_value=mock_resp
    ) as mock_patch:
        await maglo_client.upsert_ivr_lead(12, 70, "+919876543210")

        # Verify the patch method was called with correct payload
        call_args = mock_patch.call_args
        expected_payload = {
            MagloApiConstants.LEAD_PAYLOAD_PARTNER_ID: 12,
            MagloApiConstants.DEFAULT_SERVICE_BOARD_ID_PARAM: 70,
            MagloApiConstants.LEAD_PAYLOAD_PHONE_NUMBER: "+919876543210",
        }
        assert call_args[1]["json"] == expected_payload


@pytest.mark.asyncio
async def test_reassign_lead_by_phone_success(maglo_client, mock_logger):
    mock_response_data = {"lead_request_id": 555, "assigned_to": 34}
    mock_resp = create_mock_response(200, json_data={"data": mock_response_data})

    with patch.object(maglo_client.session, "patch", return_value=mock_resp):
        result = await maglo_client.reassign_lead_by_phone(
            phone_number="+919876543210",
            partner_id=12,
            service_board_id=70,
            agent_id=34,
        )
        assert result == mock_response_data


@pytest.mark.asyncio
async def test_reassign_lead_by_phone_payload_structure(maglo_client, mock_logger):
    """performed_by must carry the new agent's id, not a separate actor id"""
    mock_resp = create_mock_response(200, json_data={"data": {}})

    with patch.object(
        maglo_client.session, "patch", return_value=mock_resp
    ) as mock_patch:
        await maglo_client.reassign_lead_by_phone(
            phone_number="+919876543210",
            partner_id=12,
            service_board_id=70,
            agent_id=34,
        )

        call_args = mock_patch.call_args
        assert call_args[0][0] == MagloApiConstants.reassign_lead_by_phone_url()
        expected_payload = {
            MagloApiConstants.LEAD_PAYLOAD_PHONE_NUMBER: "+919876543210",
            MagloApiConstants.LEAD_PAYLOAD_PARTNER_ID: 12,
            MagloApiConstants.DEFAULT_SERVICE_BOARD_ID_PARAM: 70,
            MagloApiConstants.DEFAULT_AGENT_ID_PARAM: 34,
            MagloApiConstants.LEAD_PAYLOAD_PERFORMED_BY: 34,
        }
        assert call_args[1]["json"] == expected_payload


@pytest.mark.asyncio
async def test_reassign_lead_by_phone_error(maglo_client, mock_logger):
    mock_resp = create_mock_response(404, text_data='{"error": "Lead not found"}')

    with patch.object(maglo_client.session, "patch", return_value=mock_resp):
        with pytest.raises(ValueError) as exc:
            await maglo_client.reassign_lead_by_phone(
                phone_number="+919876543210",
                partner_id=12,
                service_board_id=70,
                agent_id=34,
            )

        assert "Maglo lead reassignment API error 404" in str(exc.value)
        mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_get_leads_created_today_success(maglo_client, mock_logger):
    """Test successful fetch of leads created today."""
    mock_data = {
        "current_date": "2026-03-03",
        "service_boards": [{"id": 1, "leads_count": 5}],
    }
    mock_response_json = {"status": "success", "data": mock_data}

    mock_resp = create_mock_response(200, json_data=mock_response_json)

    with patch.object(
        maglo_client.session, "post", return_value=mock_resp
    ) as mock_post:
        result = await maglo_client.get_leads_created_today(api_key="test_key")

        assert result == mock_data
        # Verify payload
        call_args = mock_post.call_args
        assert call_args[1]["json"] == {MagloApiConstants.API_KEY_FIELD: "test_key"}
        mock_logger.info.assert_called_with("Fetching leads created today")


@pytest.mark.asyncio
async def test_get_leads_created_today_api_error_status(maglo_client, mock_logger):
    """Test 200 OK but with a 'failure' status in the JSON body."""
    mock_response_json = {"status": "error", "message": "Invalid API Key"}

    mock_resp = create_mock_response(200, json_data=mock_response_json)

    with patch.object(maglo_client.session, "post", return_value=mock_resp):
        with pytest.raises(ValueError) as exc:
            await maglo_client.get_leads_created_today("bad_key")

        assert "Maglo API error: Invalid API Key" in str(exc.value)
        mock_logger.error.assert_called_with(
            "Failed to fetch leads created today: Maglo API error: Invalid API Key"
        )


@pytest.mark.asyncio
async def test_get_leads_created_today_http_failure(maglo_client, mock_logger):
    """Test non-200 HTTP response for leads created today."""
    mock_resp = create_mock_response(500, text_data="Internal Server Error")

    with patch.object(maglo_client.session, "post", return_value=mock_resp):
        with pytest.raises(ValueError) as exc:
            await maglo_client.get_leads_created_today("test_key")

        assert "Maglo returned 500" in str(exc.value)
        mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_get_leads_created_today_exception(maglo_client, mock_logger):
    """Test general exception handling in get_leads_created_today."""
    with patch.object(
        maglo_client.session, "post", side_effect=RuntimeError("Unexpected")
    ):
        with pytest.raises(RuntimeError):
            await maglo_client.get_leads_created_today("test_key")

        mock_logger.error.assert_called_with(
            "Failed to fetch leads created today: Unexpected"
        )
