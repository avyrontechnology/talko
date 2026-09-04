from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.components.call_operation.cdr_update import TalkoCDRUpdateTask
from src.exceptions import TalkoBadRequestError, TalkoResourceNotFound


@pytest.mark.asyncio
class TestCDRUpdateTask:

    def setup_method(self):
        """Initialize mocks and TalkoCDRUpdateTask instance before each test"""
        self.mock_cdr_repo = MagicMock()
        self.mock_vendor_repo = MagicMock()
        self.mock_call_repo = MagicMock()
        self.mock_logger = MagicMock()

        self.task = TalkoCDRUpdateTask(
            cdr_repository=self.mock_cdr_repo,
            vendor_config_repository=self.mock_vendor_repo,
            call_repository=self.mock_call_repo,
            logger=self.mock_logger,
        )

    async def test_fetch_vendor_config_success(self):
        self.mock_vendor_repo.get_vendor_config_by_vendor_type = AsyncMock(
            return_value=[{"cdr_url_handler": {"endpoint": "http://api"}}]
        )

        config = await self.task.fetch_vendor_config()
        assert config["cdr_url_handler"]["endpoint"] == "http://api"
        self.mock_logger.info.assert_called()

    async def test_fetch_vendor_config_not_found(self):
        self.mock_vendor_repo.get_vendor_config_by_vendor_type = AsyncMock(
            return_value=[]
        )
        with pytest.raises(TalkoResourceNotFound):
            await self.task.fetch_vendor_config()
        self.mock_logger.error.assert_called()

    async def test_fetch_cdr_data_missing_url_or_token(self):
        cdr_config = {"endpoint": None, "auth_credentials": {}}
        with pytest.raises(TalkoBadRequestError):
            await self.task.fetch_cdr_data("123", cdr_config)
        self.mock_logger.error.assert_called()

    async def test_get_incomplete_cdrs_returns_data(self):
        self.mock_cdr_repo.get_cdrs_by_criteria = AsyncMock(
            return_value=[{"call_id": "123", "call_status": "initiated"}]
        )

        cdrs = await self.task.get_incomplete_cdrs("tata_tele")
        assert len(cdrs) == 1
        assert cdrs[0]["call_id"] == "123"

    async def test_execute_no_incomplete_cdrs(self):
        self.task.fetch_vendor_config = AsyncMock(
            return_value={"cdr_url_handler": {"endpoint": "http://api"}}
        )
        self.task.get_incomplete_cdrs = AsyncMock(return_value=[])

        result = await self.task.execute("tata_tele")
        assert result == "No updates needed"

    async def test_execute_updates_cdrs_success(self):
        self.task.fetch_vendor_config = AsyncMock(
            return_value={"cdr_url_handler": {"endpoint": "http://api"}}
        )
        self.task.get_incomplete_cdrs = AsyncMock(
            return_value=[{"call_id": "123", "call_uuid": "abc"}]
        )
        self.task.fetch_cdr_data = AsyncMock(return_value={"status": "success"})

        with patch(
            "src.components.call_operation.cdr_update.TalkoTataTeleWebhookHandler"
        ) as mock_handler_class:
            mock_handler = mock_handler_class.return_value
            mock_handler.process_cdr_api_payload = AsyncMock(
                return_value={"status": "success", "call_id": "123"}
            )

            result = await self.task.execute("tata_tele")
            assert "Updated 1 CDRs" in result

    async def test_execute_missing_cdr_config(self):
        self.task.fetch_vendor_config = AsyncMock(return_value={})  # no cdr_url_handler
        with pytest.raises(TalkoBadRequestError):
            await self.task.execute("tata_tele")
        self.mock_logger.error.assert_called()

    async def test_execute_cdr_processing_exception(self):
        self.task.fetch_vendor_config = AsyncMock(
            return_value={"cdr_url_handler": {"endpoint": "http://api"}}
        )
        self.task.get_incomplete_cdrs = AsyncMock(
            return_value=[{"call_id": "123", "call_uuid": "abc"}]
        )
        self.task.fetch_cdr_data = AsyncMock(return_value={"status": "success"})

        with patch(
            "src.components.call_operation.cdr_update.TalkoTataTeleWebhookHandler"
        ) as mock_handler_class:
            mock_handler = mock_handler_class.return_value
            mock_handler.process_cdr_api_payload = AsyncMock(
                side_effect=Exception("fail")
            )

            result = await self.task.execute("tata_tele")
            assert "Updated 0 CDRs" in result

    async def test_execute_outer_exception(self):
        self.task.fetch_vendor_config = AsyncMock(side_effect=Exception("unexpected"))
        with pytest.raises(Exception):
            await self.task.execute("tata_tele")
        self.mock_logger.error.assert_called()

    async def test_fetch_single_cdr_with_pre_fetched_config_success(self):
        """Test successful fetch_single_cdr when cdr_config is provided (API path using vendor_config_id)"""
        cdr_config = {
            "endpoint": "https://api.tatatele.com/cdr",
            "auth_type": "bearer",
            "auth_credentials": {"token": "test-token"},
            "param_key": "call_id",
        }

        mock_payload = {
            "call_id": "TT123456789",
            "status": "completed",
            "duration": 145,
        }
        mock_processed_result = {
            "status": "success",
            "call_id": "TT123456789",
            "updated": True,
        }

        # Mock fetch_cdr_data
        self.task.fetch_cdr_data = AsyncMock(return_value=mock_payload)

        # Mock TalkoTataTeleWebhookHandler
        with patch(
            "src.components.call_operation.cdr_update.TalkoTataTeleWebhookHandler"
        ) as mock_handler_class:
            mock_handler = mock_handler_class.return_value
            mock_handler.process_cdr_api_payload = AsyncMock(
                return_value=mock_processed_result
            )

            result = await self.task.fetch_single_cdr(
                call_id="TT123456789", cdr_config=cdr_config, vendor_type="tata_tele"
            )

            assert result["status"] == "success"
            assert result["call_id"] == "TT123456789"
            assert result["raw_payload"] == mock_payload
            assert result["processed_result"] == mock_processed_result
            assert "TalkoCDR fetched and processed successfully" in result["message"]

            # Verify logging
            self.mock_logger.info.assert_any_call(
                "Fetching single TalkoCDR for call_id: TT123456789 using vendor_config_id flow"
            )

    async def test_fetch_single_cdr_fallback_to_fetch_vendor_config(self):
        """Test that fetch_single_cdr falls back to fetch_vendor_config when cdr_config is None"""
        self.task.fetch_vendor_config = AsyncMock(
            return_value={"cdr_url_handler": {"endpoint": "http://fallback-api"}}
        )

        mock_payload = {"call_id": "99999", "status": "answered"}
        self.task.fetch_cdr_data = AsyncMock(return_value=mock_payload)

        with patch(
            "src.components.call_operation.cdr_update.TalkoTataTeleWebhookHandler"
        ) as mock_handler_class:
            mock_handler = mock_handler_class.return_value
            mock_handler.process_cdr_api_payload = AsyncMock(
                return_value={"status": "success", "call_id": "99999"}
            )

            result = await self.task.fetch_single_cdr(
                call_id="99999", cdr_config=None, vendor_type="tata_tele"
            )

            assert result["status"] == "success"
            self.task.fetch_vendor_config.assert_called_once()

    async def test_fetch_single_cdr_raises_when_cdr_config_missing(self):
        """Test that TalkoBadRequestError is raised when cdr_config is empty"""
        with pytest.raises(TalkoBadRequestError):
            await self.task.fetch_single_cdr(
                call_id="12345", cdr_config={}, vendor_type="tata_tele"  # empty config
            )

    async def test_fetch_single_cdr_handles_exception_gracefully(self):
        """Test exception handling inside fetch_single_cdr"""
        self.task.fetch_cdr_data = AsyncMock(side_effect=Exception("Network timeout"))

        with pytest.raises(Exception):
            await self.task.fetch_single_cdr(
                call_id="12345",
                cdr_config={
                    "endpoint": "https://api.test.com",
                    "auth_credentials": {"token": "xyz"},
                },
            )

        self.mock_logger.error.assert_called()
        # Check error message contains call_id
        error_call = self.mock_logger.error.call_args[0][0]
        assert "Failed to fetch single TalkoCDR for call_id 12345" in error_call

    async def test_fetch_cdr_data_success_branch(self):
        """Cover success path in fetch_cdr_data"""
        cdr_config = {
            "endpoint": "http://dummy",
            "auth_type": "bearer",
            "auth_credentials": {"token": "dummy"},
        }

        class DummyResponse:
            status = 200

            async def json(self):
                return {"status": "ok"}

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class DummySession:
            def get(self, *args, **kwargs):
                return DummyResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("aiohttp.ClientSession", return_value=DummySession()):
            payload = await self.task.fetch_cdr_data("dummy_id", cdr_config)
            assert payload["status"] == "ok"

    async def test_fetch_cdr_data_failure_branch(self):
        """Cover failure path in fetch_cdr_data"""
        cdr_config = {
            "endpoint": "http://dummy",
            "auth_type": "bearer",
            "auth_credentials": {"token": "dummy"},
        }

        class DummyResponse:
            status = 500

            async def json(self):
                return {}

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        class DummySession:
            def get(self, *args, **kwargs):
                return DummyResponse()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

        with patch("aiohttp.ClientSession", return_value=DummySession()):
            with pytest.raises(TalkoBadRequestError):
                await self.task.fetch_cdr_data("dummy_id", cdr_config)
