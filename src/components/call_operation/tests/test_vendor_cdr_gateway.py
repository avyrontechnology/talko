from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.call_operation.vendor_cdr_gateway import VendorCDRGateway
from src.exceptions import BadRequestError


@pytest.mark.asyncio
class TestVendorCDRGateway:

    def setup_method(self):
        """Setup mocks before each test"""
        self.mock_cdr_update_task = MagicMock()
        self.mock_logger = MagicMock()

        # Make fetch_single_cdr async
        self.mock_cdr_update_task.fetch_single_cdr = AsyncMock()

        self.gateway = VendorCDRGateway(
            cdr_update_task=self.mock_cdr_update_task, logger=self.mock_logger
        )

    async def test_fetch_call_details_tata_tele_success(self):
        """Test successful routing to Tata Tele handler"""
        vendor_config = {
            "vendor_type": "tata_tele",
            "cdr_url_handler": {
                "endpoint": "https://api.tatatele.com/cdr",
                "auth_credentials": {"token": "test-token"},
            },
        }

        mock_result = {
            "status": "success",
            "call_id": "TT123456789",
            "raw_payload": {"status": "completed"},
            "processed_result": {"updated": True},
        }

        self.mock_cdr_update_task.fetch_single_cdr.return_value = mock_result

        result = await self.gateway.fetch_call_details(
            call_id="TT123456789", vendor_config=vendor_config
        )

        assert result == mock_result
        self.mock_cdr_update_task.fetch_single_cdr.assert_called_once_with(
            call_id="TT123456789",
            cdr_config=vendor_config["cdr_url_handler"],
            vendor_type="tata_tele",
        )
        self.mock_logger.info.assert_called_with(
            "Routing call details request for call_id=TT123456789 to vendor_type=tata_tele"
        )

    async def test_fetch_call_details_missing_vendor_type(self):
        """Test error when vendor_type is missing in config"""
        vendor_config = {
            "cdr_url_handler": {"endpoint": "http://test.com"}
            # vendor_type is missing
        }

        with pytest.raises(BadRequestError) as exc_info:
            await self.gateway.fetch_call_details(
                call_id="12345", vendor_config=vendor_config
            )

        assert "vendor_type missing in vendor configuration" in str(exc_info.value)

    async def test_fetch_call_details_missing_cdr_config(self):
        """Test error when cdr_url_handler is missing"""
        vendor_config = {
            "vendor_type": "tata_tele"
            # cdr_url_handler is missing
        }

        with pytest.raises(BadRequestError) as exc_info:
            await self.gateway.fetch_call_details(
                call_id="12345", vendor_config=vendor_config
            )

        assert "CDR configuration missing" in str(exc_info.value)
        self.mock_logger.error.assert_called()

    async def test_fetch_call_details_unsupported_vendor(self):
        """Test error when vendor_type is not supported"""
        vendor_config = {
            "vendor_type": "unknown_vendor",
            "cdr_url_handler": {"endpoint": "http://test.com"},
        }

        with pytest.raises(BadRequestError) as exc_info:
            await self.gateway.fetch_call_details(
                call_id="12345", vendor_config=vendor_config
            )

        assert "Unsupported vendor: unknown_vendor" in str(exc_info.value)

    async def test_fetch_call_details_propagates_exception(self):
        """Test that exceptions from handler are propagated"""
        vendor_config = {
            "vendor_type": "tata_tele",
            "cdr_url_handler": {"endpoint": "http://test.com"},
        }

        self.mock_cdr_update_task.fetch_single_cdr.side_effect = Exception(
            "API timeout"
        )

        with pytest.raises(Exception) as exc_info:
            await self.gateway.fetch_call_details(
                call_id="12345", vendor_config=vendor_config
            )

        assert "API timeout" in str(exc_info.value)
        self.mock_logger.error.assert_called_with(
            "Error in VendorCDRGateway: API timeout"
        )

    async def test__handle_tata_tele_is_called_correctly(self):
        """Test internal _handle_tata_tele method"""
        vendor_config = {
            "vendor_type": "tata_tele",
            "cdr_url_handler": {"endpoint": "https://api.test"},
        }

        mock_result = {"status": "success"}
        self.mock_cdr_update_task.fetch_single_cdr.return_value = mock_result

        result = await self.gateway.fetch_call_details(
            call_id="ABC123", vendor_config=vendor_config
        )

        assert result == mock_result
        self.mock_cdr_update_task.fetch_single_cdr.assert_called_once()

    def test_gateway_supports_multiple_vendors_in_registry(self):
        """Test that the registry contains expected handlers"""
        assert "tata_tele" in self.gateway._handlers
        # When you add new vendors, this test can be extended
        assert callable(self.gateway._handlers["tata_tele"])

    async def test_unsupported_vendor_logging(self):
        """Test proper logging for unsupported vendor"""
        vendor_config = {"vendor_type": "newfuturevendor", "cdr_url_handler": {}}

        with pytest.raises(BadRequestError):
            await self.gateway.fetch_call_details(
                call_id="123", vendor_config=vendor_config
            )


@pytest.mark.asyncio
class TestVendorCDRGatewayEdgeCases:

    async def test_empty_vendor_config(self):
        """Test behavior with completely empty vendor_config"""
        gateway = VendorCDRGateway(cdr_update_task=MagicMock(), logger=MagicMock())

        with pytest.raises(BadRequestError):
            await gateway.fetch_call_details(call_id="123", vendor_config={})
