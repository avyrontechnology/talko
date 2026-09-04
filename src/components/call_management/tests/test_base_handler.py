from unittest.mock import MagicMock

import pytest

from src.components.call_management.handlers.base_handler import VendorCallHandler


# Dummy concrete class for testing abstract base class
class DummyVendorCallHandler(VendorCallHandler):
    async def make_call(self, to_number, from_number, call_url, agent_number):
        return {
            "status": "success",
            "to": to_number,
            "from": from_number,
            "url": call_url,
            "agent": agent_number,
        }

    async def hangup_call(self, call_id):
        return {"Success": True, "Message": "hangup", "call_id": call_id}

    async def transfer_call(self, call_id, destination_number):
        return {
            "status": "success",
            "call_id": call_id,
            "destination": destination_number,
        }


class TestVendorCallHandler:
    @pytest.mark.asyncio
    async def test_initialization_sets_attributes_correctly(self):
        """
        Test that VendorCallHandler initializes config, logger, and vendor_type correctly.
        """
        mock_logger = MagicMock()
        config = {
            "generic_url_handler": {"call_api": {"endpoint": "https://test.com/call"}}
        }

        handler = DummyVendorCallHandler(config, mock_logger, "DUMMY_VENDOR")

        assert handler.config == {"endpoint": "https://test.com/call"}
        assert handler.logger == mock_logger
        assert handler.vendor_type == "DUMMY_VENDOR"

    @pytest.mark.asyncio
    async def test_make_call_returns_expected_result(self):
        """
        Test that DummyVendorCallHandler.make_call returns expected dict.
        """
        mock_logger = MagicMock()
        handler = DummyVendorCallHandler(
            {"generic_url_handler": {"call_api": {}}}, mock_logger, "DUMMY_VENDOR"
        )

        result = await handler.make_call(
            to_number="+911234567890",
            from_number="+919876543210",
            call_url="https://callflow.url",
            agent_number="+910000000000",
        )

        assert result == {
            "status": "success",
            "to": "+911234567890",
            "from": "+919876543210",
            "url": "https://callflow.url",
            "agent": "+910000000000",
        }

    def test_instantiating_abstract_class_raises_type_error(self):
        """
        Test that directly instantiating VendorCallHandler raises TypeError.
        """
        with pytest.raises(TypeError):
            VendorCallHandler({}, MagicMock(), "DUMMY_VENDOR")
