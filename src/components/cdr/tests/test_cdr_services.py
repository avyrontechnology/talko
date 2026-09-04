from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
import pytest_asyncio
from starlette_context.plugins import RequestIdPlugin

from src.components.cdr.dto import Contract
from src.components.cdr.services import CDRService
from src.utils.enums import UserRoleHierarchy


def fake_cdr_dict():
    return {
        "_id": 12345,
        "id": "12345",
        "partner_id": 10,
        "agent": 1,
        "lead_id": "5",
        "service_board_id": 20,
        "calling_mode": "outbound",
        "call_status": "completed",
        "call_recording": "http://recording.com/1",
        "customer": 1001,
        "total_call_duration": 120,
        "talk_time": 100,
        "client_number": "9999999999",
        "did_number": "8888888888",
        "agent_number": "7777777777",
        "reason": "No answer",
        "hangup_cause": "NORMAL_CLEARING",
        "reason_key": "NO_ANSWER",
        "hangup_by": "agent",
        "created_at": 1725184800,
        "updated_at": 1725185400,
        "action": "dial",
        "solution": "resolved",
        "sr_number": "SR-1001",
        "customer_status": "active",
        "agent_status": "available",
        "call_actions": [],
        "call_uuid": "uuid-12345",
    }


def fake_call_log_dict():
    return {
        "id": "67890",
        "partner_id": 10,
        "agent": 2,
        "lead_id": 6,
        "service_board_id": 21,
        "calling_mode": "inbound",
        "call_status": "missed",
        "call_recording": "http://recording.com/2",
        "customer": 1002,
        "total_call_duration": 60,
        "talk_time": 45,
        "client_number": "9991112222",
        "did_number": "8881112222",
        "agent_number": "7771112222",
        "reason": "Busy",
        "hangup_cause": "USER_BUSY",
        "reason_key": "BUSY",
        "hangup_by": "customer",
        "created_at": 1725188400,
        "updated_at": 1725188700,
        "action": "dial",
        "solution": "resolved",
        "sr_number": "SR-1002",
        "customer_status": "active",
        "agent_status": "available",
        "call_actions": [],
        "call_uuid": "uuid-67890",
    }


@pytest_asyncio.fixture
async def mock_context():
    mock_context_data = {
        "user_id": 1,
        "partner_id": 10,
        "request_id": "test-request-id",
    }
    with patch("starlette_context.context", new=MagicMock()) as mock_context:
        mock_context.data = mock_context_data
        mock_context.__getitem__.return_value = "test-request-id"
        yield mock_context_data


@pytest_asyncio.fixture
def mock_dependencies():
    repository = AsyncMock()
    logger = MagicMock()
    datetime_util = MagicMock()
    analytics_processor = AsyncMock()
    date_range_helper = MagicMock()
    return repository, logger, datetime_util, analytics_processor, date_range_helper


@pytest_asyncio.fixture
def cdr_service(mock_dependencies):
    repository, logger, datetime_util, analytics_processor, date_range_helper = (
        mock_dependencies
    )
    service = CDRService(
        repository, logger, datetime_util, analytics_processor, date_range_helper
    )
    service.__logger = logger
    return service


@pytest.mark.asyncio
class TestCDRService:

    async def test_get_cdrs_success(self, cdr_service, mock_dependencies, mock_context):
        repository, logger, _, _, _ = mock_dependencies
        repository.find_all_cdrs_on_the_basis_of_partner_id.return_value = [
            fake_cdr_dict()
        ]

        result = await cdr_service.get_cdrs(
            user_id=1, partner_id=10, limit=10, offset=0
        )

        assert isinstance(result, list)
        assert isinstance(result[0], Contract.CDRResponse)
        assert result[0].id == "12345"
        assert result[0].lead_id == "5"
        logger.info.assert_called()

    async def test_get_cdrs_customer_int_to_str(
        self, cdr_service, mock_dependencies, mock_context
    ):
        repository, logger, _, _, _ = mock_dependencies
        repository.find_all_cdrs_on_the_basis_of_partner_id.return_value = [
            {
                "_id": "123",
                "customer": 456,
                "partner_id": 10,
                "agent": 1,
                "lead_id": "5",
                "action": "answered",
                "calling_mode": "outbound",
                "solution": "support",
                "sr_number": "SR123",
                "call_status": "completed",
                "customer_status": "active",
                "agent_status": "busy",
                "call_actions": [],
                "call_uuid": "uuid-123",
                "hangup_by": "agent",
                "service_board_id": 22,
            }
        ]

        result = await cdr_service.get_cdrs(1, 10, 10, 0)

        assert len(result) == 1
        assert str(result[0].customer) == "456"
        logger.info.assert_called()

    async def test_get_cdrs_exception(
        self, cdr_service, mock_dependencies, mock_context
    ):
        repository, logger, _, _, _ = mock_dependencies
        repository.find_all_cdrs_on_the_basis_of_partner_id.side_effect = Exception(
            "DB error"
        )

        with pytest.raises(Exception, match="DB error"):
            await cdr_service.get_cdrs(1, 10, 10, 0)

        logger.error.assert_called()

    @patch("src.components.cdr.helper.CallLogQueryHelper")
    @patch("src.components.cdr.helper.GetAgentCallLogsHelper")
    @patch("src.components.cdr.helper.CommonCDRHelper")
    @patch("src.components.cdr.services.RPCServiceFactory.get_service")
    async def test_get_agent_call_logs_success(
        self,
        mock_get_service,
        mock_common_helper,
        mock_agent_helper,
        mock_query_helper,
        cdr_service,
        mock_dependencies,
        mock_context,
    ):
        repository, logger, _, _, _ = mock_dependencies
        repository.find_all_call_logs_on_the_basis_of_user_id.return_value = (
            [fake_call_log_dict()],
            1,
        )

        mock_query_helper.build_call_log_query.return_value = {"lead_id": 5}
        # Mock handle_hangup_cause and handle_reason_key to return strings
        mock_agent_helper.handle_hangup_cause.return_value = "USER_BUSY"
        mock_agent_helper.handle_reason_key.return_value = "BUSY"
        mock_agent_helper.process_cdrs.return_value = (
            [2],
            [Contract.CallLogResponse(**fake_call_log_dict())],
        )
        mock_agent_helper.agent_call_log_response.return_value = (
            Contract.AgentCallLogResponse(
                call_histories=[Contract.CallLogResponse(**fake_call_log_dict())],
                total_count=1,
            )
        )
        mock_common_helper.attach_agent_names.return_value = None

        grpc_client = AsyncMock()
        grpc_client.get_service_board_users_details.return_value = {
            2: {"name": "agent"}
        }
        mock_get_service.return_value = grpc_client

        result = await cdr_service.get_agent_call_logs(1, 2, 10, 0, 5)

        assert isinstance(result, Contract.AgentCallLogResponse)
        assert result.total_count == 1
        assert len(result.call_histories) == 1

    async def test_get_agent_call_logs_no_cdrs(
        self, cdr_service, mock_dependencies, mock_context
    ):
        repository, logger, _, _, _ = mock_dependencies
        repository.find_all_call_logs_on_the_basis_of_user_id.return_value = ([], 0)

        with patch(
            "src.components.cdr.helper.CallLogQueryHelper.build_call_log_query"
        ) as mock_query:
            mock_query.return_value = {"lead_id": 5}
            with patch(
                "src.components.cdr.helper.GetAgentCallLogsHelper.agent_call_log_response"
            ) as mock_response:
                mock_response.return_value = Contract.AgentCallLogResponse(
                    call_histories=[], total_count=0
                )
                await cdr_service.get_agent_call_logs(1, 2, 10, 0, 5)

    async def test_get_agent_call_logs_exception(
        self, cdr_service, mock_dependencies, mock_context
    ):
        repository, logger, _, _, _ = mock_dependencies
        repository.find_all_call_logs_on_the_basis_of_user_id.side_effect = Exception(
            "Query failed"
        )

        with patch(
            "src.components.cdr.helper.CallLogQueryHelper.build_call_log_query"
        ) as mock_query:
            mock_query.return_value = {"lead_id": 5}
            with pytest.raises(Exception, match="Query failed"):
                await cdr_service.get_agent_call_logs(1, 2, 10, 0, 5)

        logger.error.assert_called()

    async def test_get_agent_call_logs_empty(
        self, cdr_service, mock_dependencies, mock_context
    ):
        repository, logger, _, _, _ = mock_dependencies
        repository.find_all_call_logs_on_the_basis_of_user_id.return_value = ([], 0)

        with patch(
            "src.components.cdr.helper.CallLogQueryHelper.build_call_log_query"
        ) as mock_query:
            mock_query.return_value = {}
            with patch(
                "src.components.cdr.helper.GetAgentCallLogsHelper.agent_call_log_response"
            ) as mock_response:
                mock_response.return_value = Contract.AgentCallLogResponse(
                    call_histories=[], total_count=0
                )
                await cdr_service.get_agent_call_logs(
                    user_id=1,
                    partner_id=10,
                    lead_id=None,
                    limit=5,
                    offset=0,
                )

    @patch("src.components.cdr.helper.GetCallRecordHistoryHelper")
    @patch("src.components.cdr.helper.CommonCDRHelper")
    @patch("src.components.cdr.services.RPCServiceFactory.get_service")
    async def test_get_call_record_history_success(
        self,
        mock_get_service,
        mock_common_helper,
        mock_helper,
        cdr_service,
        mock_dependencies,
        mock_context,
    ):
        repository, logger, datetime_util, analytics_processor, _ = mock_dependencies
        analytics_processor.user_hierarchy_data.return_value = ([1, 2], "some_role")
        datetime_util.parse_time_str.return_value = (100, 200)

        repository.find_all_call_logs_on_the_basis_of_user_id.return_value = (
            [fake_call_log_dict()],
            1,
        )

        mock_helper.validate_call_status.return_value = None
        mock_helper.build_call_record_history_query.return_value = {}
        mock_helper.get_call_record_history_projection.return_value = {}
        mock_helper.handle_call_record_history_data.return_value = fake_call_log_dict()
        mock_helper.agent_call_record_history_response.return_value = (
            Contract.AgentCallRecordHistoryResponse(
                call_record=[
                    Contract.CallRecordHistoryResponse(**fake_call_log_dict())
                ],
                total_count=1,
            )
        )
        mock_common_helper.attach_agent_names.return_value = None

    @patch(
        "src.components.cdr.helper.GetCallRecordHistoryHelper.handle_call_record_history_data"
    )
    @patch(
        "src.components.cdr.helper.GetCallRecordHistoryHelper.get_call_record_history_projection"
    )
    @patch(
        "src.components.cdr.helper.GetCallRecordHistoryHelper.build_call_record_history_query"
    )
    @patch("src.components.cdr.helper.GetCallRecordHistoryHelper.validate_call_status")
    @patch("src.components.cdr.helper.CommonCDRHelper")
    @patch("src.components.cdr.services.RPCServiceFactory.get_service")
    async def test_get_call_record_history_filter(
        self,
        mock_get_service,
        mock_common_helper,
        mock_validate_status,
        mock_build_query,
        mock_projection,
        mock_handle_data,
        cdr_service,
        mock_dependencies,
        mock_context,
    ):
        repository, logger, datetime_util, analytics_processor, _ = mock_dependencies
        analytics_processor.user_hierarchy_data.return_value = ([1, 2], "some_role")
        datetime_util.parse_time_str.return_value = (100, 200)

        cdr_service._CDRService__date_range_helper = MagicMock()
        cdr_service._CDRService__date_range_helper.get_default_date_range.return_value = (
            100,
            200,
            "last_7_days",
        )

        repository.find_all_call_logs_on_the_basis_of_user_id.return_value = (
            [fake_call_log_dict()],
            1,
        )

        mock_handle_data.return_value = {
            "partner_id": 10,
            "agent": 2,
            "lead_id": 6,
            "service_board_id": 21,
            "calling_mode": "inbound",
            "call_status": "missed",
            "call_recording": "http://recording.com/2",
            "lead_number": "9991112222",
            "total_call_duration": 60,
            "talk_time": 45,
            "did_number": "8881112222",
            "agent_number": "7771112222",
            "reason": "Busy",
            "hangup_cause": "USER_BUSY",
            "reason_key": "BUSY",
            "hangup_by": "customer",
            "created_at": 1725188400,
            "call_connected": "0",
            "lead_name": "",
            "call_type": "outgoing",
            "agent_call_status": "available",
            "lead_call_status": "active",
            "number_type": "primary",
            "lead_secret": "",
        }

        grpc_client = AsyncMock()
        grpc_client.get_service_board_users_details.return_value = {
            2: {"name": "agent"}
        }
        mock_get_service.return_value = grpc_client

        payload = {"call_status": ["missed"]}
        result = await cdr_service.get_call_record_history(
            user_id=1, partner_id=10, limit=10, offset=0, payload=payload
        )

        assert result.total_count == 1

    @patch(
        "src.components.cdr.helper.GetCallRecordHistoryHelper.handle_call_record_history_data",
        return_value={},
    )
    async def test_get_call_record_history_with_empty_user_hierarchy(
        self, mock_handle_data, cdr_service, mock_dependencies
    ):
        repository, logger, datetime_util, analytics_processor, _ = mock_dependencies
        analytics_processor.user_hierarchy_data.return_value = ([], None)
        datetime_util.parse_time_str.return_value = (100, 200)

        result = await cdr_service.get_call_record_history(
            user_id=1, partner_id=10, limit=10, offset=0, payload={}
        )
        assert result.total_count == 0

    @patch(
        "src.components.cdr.helper.GetCallRecordHistoryHelper.handle_call_record_history_data",
        side_effect=Exception("DB error"),
    )
    async def test_get_call_record_history_with_exception(
        self, mock_handle_data, cdr_service, mock_dependencies
    ):
        repository, logger, datetime_util, analytics_processor, _ = mock_dependencies
        analytics_processor.user_hierarchy_data.return_value = ([1, 2], "some_role")
        datetime_util.parse_time_str.return_value = (100, 200)

        with pytest.raises(Exception):  # or CDRServiceError if custom error is used
            await cdr_service.get_call_record_history(
                user_id=1, partner_id=10, limit=10, offset=0, payload={}
            )

    @patch(
        "src.components.cdr.helper.GetCallRecordHistoryHelper.handle_call_record_history_data",
        side_effect=Exception("DB error"),
    )
    async def test_get_call_record_history_exception_logger_called(
        self, mock_handle_data, cdr_service, mock_dependencies
    ):
        repository, logger, datetime_util, analytics_processor, _ = mock_dependencies
        analytics_processor.user_hierarchy_data.return_value = ([1, 2], "some_role")
        datetime_util.parse_time_str.return_value = (100, 200)

        with pytest.raises(Exception):
            await cdr_service.get_call_record_history(
                user_id=1, partner_id=10, limit=10, offset=0, payload={}
            )

        logger.error.assert_called_once()

    async def test_get_url_from_path_success(self, cdr_service, mock_dependencies):
        """Test that do_recording_url is added when path_for_recording exists."""
        _, logger, _, _, _ = mock_dependencies

        cdr = {"path_for_recording": "some/path.mp3"}
        cdr_service.asset_helper = AsyncMock()
        cdr_service.asset_helper.get_recording_url_from_path.return_value = (
            "https://test-url"
        )

        await cdr_service.get_url_from_path(cdr)

        assert "do_recording_url" in cdr
        assert cdr["do_recording_url"] == "https://test-url"
        logger.info.assert_any_call(
            "CDR for fetching recording url from path: {'path_for_recording': 'some/path.mp3'}"
        )
        cdr_service.asset_helper.get_recording_url_from_path.assert_awaited_once_with(
            "some/path.mp3"
        )

    async def test_get_url_from_path_no_path(self, cdr_service, mock_dependencies):
        """Test that info log is written when path_for_recording is missing."""
        _, logger, _, _, _ = mock_dependencies
        cdr = {"some_other_field": "value"}
        cdr_service.asset_helper = AsyncMock()

        await cdr_service.get_url_from_path(cdr)

        cdr_service.asset_helper.get_recording_url_from_path.assert_not_called()
        logger.info.assert_any_call("Path not present for url generation")
        assert "do_recording_url" not in cdr

    async def test_get_url_from_path_exception(self, cdr_service, mock_dependencies):
        """Test that exception in URL generation is logged and raised."""
        _, logger, _, _, _ = mock_dependencies
        cdr = {"path_for_recording": "invalid/path.mp3"}
        cdr_service.asset_helper = AsyncMock()
        cdr_service.asset_helper.get_recording_url_from_path.side_effect = Exception(
            "URL generation failed"
        )

        with pytest.raises(Exception, match="URL generation failed"):
            await cdr_service.get_url_from_path(cdr)

        logger.error.assert_called_with(
            "Failed to generate URL: URL generation failed."
        )
