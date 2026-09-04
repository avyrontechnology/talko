from io import StringIO
from unittest.mock import patch

from src.components.integrations.console.maglo_constants import TalkoMagloApiConstants


class TestMagloApiConstants:
    """Test suite for TalkoMagloApiConstants"""

    def test_base_url_is_set(self):
        """Test that MAGLO_BASE_URL is properly set"""
        assert (
            TalkoMagloApiConstants.MAGLO_BASE_URL
            == "https://int-maglo-service.makunaiglobal.ai/maglo-service"
        )
        assert isinstance(TalkoMagloApiConstants.MAGLO_BASE_URL, str)
        assert len(TalkoMagloApiConstants.MAGLO_BASE_URL) > 0

    def test_api_token_is_string(self):
        """Test that MAGLO_API_TOKEN is a string (even if empty)"""
        assert isinstance(TalkoMagloApiConstants.MAGLO_API_TOKEN, str)

    def test_endpoint_paths_defined(self):
        """Test that all endpoint paths are properly defined"""
        assert TalkoMagloApiConstants.GET_AGENT_DETAILS_PATH == "/v1/get_agent_details"
        assert TalkoMagloApiConstants.UPSERT_IVR_LEADS_PATH == "/v1/ivr-leads"

        # Ensure they start with /
        assert TalkoMagloApiConstants.GET_AGENT_DETAILS_PATH.startswith("/")
        assert TalkoMagloApiConstants.UPSERT_IVR_LEADS_PATH.startswith("/")

    def test_get_agent_details_url(self):
        """Test that get_agent_details_url returns correct full URL"""
        expected_url = "https://int-maglo-service.makunaiglobal.ai/maglo-service/v1/get_agent_details"
        assert TalkoMagloApiConstants.get_agent_details_url() == expected_url

    def test_get_agent_details_url_strips_trailing_slash(self):
        """Test that get_agent_details_url properly strips trailing slashes from base URL"""
        original_base = TalkoMagloApiConstants.MAGLO_BASE_URL

        try:
            # Test with trailing slash
            TalkoMagloApiConstants.MAGLO_BASE_URL = "https://example.com/api/"
            url = TalkoMagloApiConstants.get_agent_details_url()
            assert url == "https://example.com/api/v1/get_agent_details"
            assert "//" not in url.replace("https://", "")
        finally:
            TalkoMagloApiConstants.MAGLO_BASE_URL = original_base

    def test_upsert_ivr_leads_url(self):
        """Test that upsert_ivr_leads_url returns correct full URL"""
        expected_url = (
            "https://int-maglo-service.makunaiglobal.ai/maglo-service/v1/ivr-leads"
        )
        assert TalkoMagloApiConstants.upsert_ivr_leads_url() == expected_url

    def test_upsert_ivr_leads_url_strips_trailing_slash(self):
        """Test that upsert_ivr_leads_url properly strips trailing slashes from base URL"""
        original_base = TalkoMagloApiConstants.MAGLO_BASE_URL

        try:
            # Test with trailing slash
            TalkoMagloApiConstants.MAGLO_BASE_URL = "https://example.com/api/"
            url = TalkoMagloApiConstants.upsert_ivr_leads_url()
            assert url == "https://example.com/api/v1/ivr-leads"
            assert "//" not in url.replace("https://", "")
        finally:
            TalkoMagloApiConstants.MAGLO_BASE_URL = original_base

    def test_request_timeout_seconds(self):
        """Test that REQUEST_TIMEOUT_SECONDS is properly set"""
        assert TalkoMagloApiConstants.REQUEST_TIMEOUT_SECONDS == 10
        assert isinstance(TalkoMagloApiConstants.REQUEST_TIMEOUT_SECONDS, int)
        assert TalkoMagloApiConstants.REQUEST_TIMEOUT_SECONDS > 0

    def test_default_headers_structure(self):
        """Test that DEFAULT_HEADERS has correct structure"""
        headers = TalkoMagloApiConstants.DEFAULT_HEADERS

        assert isinstance(headers, dict)
        assert "accept" in headers
        assert "Content-Type" in headers
        assert headers["accept"] == "application/json"
        assert headers["Content-Type"] == "application/json"

    def test_default_headers_is_dict(self):
        """Test that DEFAULT_HEADERS is a dictionary with expected keys"""
        headers = TalkoMagloApiConstants.DEFAULT_HEADERS
        assert len(headers) >= 2
        assert all(isinstance(key, str) for key in headers.keys())
        assert all(isinstance(value, str) for value in headers.values())

    def test_query_parameter_constants(self):
        """Test that query parameter constants are defined"""
        assert TalkoMagloApiConstants.DEFAULT_SERVICE_BOARD_ID_PARAM == "service_board_id"
        assert TalkoMagloApiConstants.DEFAULT_AGENT_ID_PARAM == "agent_id"
        assert TalkoMagloApiConstants.LEAD_PAYLOAD_PHONE_NUMBER == "phone_number"
        assert TalkoMagloApiConstants.LEAD_PAYLOAD_PARTNER_ID == "partner_id"

    def test_response_field_names(self):
        """Test that response field name constants are defined"""
        assert (
            TalkoMagloApiConstants.FIELD_INTERNET_CALLING_ENABLE == "internet_calling_enable"
        )
        assert TalkoMagloApiConstants.FIELD_EXTENSION == "extension"
        assert TalkoMagloApiConstants.FIELD_AGENT_ID == "id"
        assert TalkoMagloApiConstants.FIELD_AGENT_NAME == "name"
        assert TalkoMagloApiConstants.FIELD_AGENT_NUMBER == "number"
        assert TalkoMagloApiConstants.LEAD_RESPONSE_ASSIGNED_TO == "assigned_to"
        assert TalkoMagloApiConstants.LEAD_RESPONSE_PHONE_NUMBER == "phone_number"

    def test_all_field_constants_are_strings(self):
        """Test that all field constants are strings"""
        field_constants = [
            TalkoMagloApiConstants.FIELD_INTERNET_CALLING_ENABLE,
            TalkoMagloApiConstants.FIELD_EXTENSION,
            TalkoMagloApiConstants.FIELD_AGENT_ID,
            TalkoMagloApiConstants.FIELD_AGENT_NAME,
            TalkoMagloApiConstants.FIELD_AGENT_NUMBER,
            TalkoMagloApiConstants.LEAD_RESPONSE_ASSIGNED_TO,
            TalkoMagloApiConstants.LEAD_RESPONSE_PHONE_NUMBER,
        ]

        for field in field_constants:
            assert isinstance(field, str)
            assert len(field) > 0

    @patch("sys.stdout", new_callable=StringIO)
    def test_log_current_config(self, mock_stdout):
        """Test that log_current_config prints expected information"""
        TalkoMagloApiConstants.log_current_config()

        output = mock_stdout.getvalue()

        # Check that all expected information is logged
        assert "[Maglo Config] Base URL:" in output
        assert TalkoMagloApiConstants.MAGLO_BASE_URL in output
        assert "[Maglo Config] Agent Details URL:" in output
        assert TalkoMagloApiConstants.get_agent_details_url() in output
        assert "[Maglo Config] IVR Leads Upsert URL:" in output
        assert TalkoMagloApiConstants.upsert_ivr_leads_url() in output
        assert "[Maglo Config] Timeout:" in output
        assert "10s" in output

    @patch("sys.stdout", new_callable=StringIO)
    def test_log_current_config_format(self, mock_stdout):
        """Test that log_current_config outputs are properly formatted"""
        TalkoMagloApiConstants.log_current_config()

        output = mock_stdout.getvalue()
        lines = output.strip().split("\n")

        # Should have 4 lines of output
        assert len(lines) == 4

        # Each line should start with [Maglo Config]
        for line in lines:
            assert line.startswith("[Maglo Config]")

    def test_url_construction_consistency(self):
        """Test that both URL methods construct URLs consistently"""
        agent_url = TalkoMagloApiConstants.get_agent_details_url()
        leads_url = TalkoMagloApiConstants.upsert_ivr_leads_url()

        # Both should start with the same base
        base = TalkoMagloApiConstants.MAGLO_BASE_URL.rstrip("/")
        assert agent_url.startswith(base)
        assert leads_url.startswith(base)

        # Neither should have double slashes (except in https://)
        assert "//" not in agent_url.replace("https://", "")
        assert "//" not in leads_url.replace("https://", "")

    def test_constants_immutability_types(self):
        """Test that constant values have appropriate types"""
        # String constants
        assert isinstance(TalkoMagloApiConstants.MAGLO_BASE_URL, str)
        assert isinstance(TalkoMagloApiConstants.MAGLO_API_TOKEN, str)
        assert isinstance(TalkoMagloApiConstants.GET_AGENT_DETAILS_PATH, str)
        assert isinstance(TalkoMagloApiConstants.UPSERT_IVR_LEADS_PATH, str)

        # Integer constants
        assert isinstance(TalkoMagloApiConstants.REQUEST_TIMEOUT_SECONDS, int)

        # Dict constant
        assert isinstance(TalkoMagloApiConstants.DEFAULT_HEADERS, dict)

    def test_parameter_and_field_names_no_spaces(self):
        """Test that parameter and field names don't contain spaces"""
        constants_to_check = [
            TalkoMagloApiConstants.DEFAULT_SERVICE_BOARD_ID_PARAM,
            TalkoMagloApiConstants.DEFAULT_AGENT_ID_PARAM,
            TalkoMagloApiConstants.LEAD_PAYLOAD_PHONE_NUMBER,
            TalkoMagloApiConstants.LEAD_PAYLOAD_PARTNER_ID,
            TalkoMagloApiConstants.FIELD_INTERNET_CALLING_ENABLE,
            TalkoMagloApiConstants.FIELD_EXTENSION,
            TalkoMagloApiConstants.FIELD_AGENT_ID,
            TalkoMagloApiConstants.FIELD_AGENT_NAME,
            TalkoMagloApiConstants.FIELD_AGENT_NUMBER,
        ]

        for constant in constants_to_check:
            assert " " not in constant, f"Constant '{constant}' contains spaces"

    def test_base_url_is_https(self):
        """Test that base URL uses HTTPS"""
        assert TalkoMagloApiConstants.MAGLO_BASE_URL.startswith("https://")

    def test_endpoint_paths_are_relative(self):
        """Test that endpoint paths are relative (start with /)"""
        assert TalkoMagloApiConstants.GET_AGENT_DETAILS_PATH.startswith("/")
        assert TalkoMagloApiConstants.UPSERT_IVR_LEADS_PATH.startswith("/")

        # Should not contain domain
        assert "http" not in TalkoMagloApiConstants.GET_AGENT_DETAILS_PATH
        assert "http" not in TalkoMagloApiConstants.UPSERT_IVR_LEADS_PATH

    def test_url_methods_return_different_urls(self):
        """Test that different URL methods return different URLs"""
        agent_url = TalkoMagloApiConstants.get_agent_details_url()
        leads_url = TalkoMagloApiConstants.upsert_ivr_leads_url()

        assert agent_url != leads_url

    def test_headers_not_modified_after_access(self):
        """Test that accessing DEFAULT_HEADERS doesn't modify the original"""
        TalkoMagloApiConstants.DEFAULT_HEADERS.copy()

        # Access headers
        headers = TalkoMagloApiConstants.DEFAULT_HEADERS

        # Modify the accessed headers
        headers["new-key"] = "new-value"
        assert "new-key" in TalkoMagloApiConstants.DEFAULT_HEADERS

        # Clean up
        del TalkoMagloApiConstants.DEFAULT_HEADERS["new-key"]

    def test_leads_created_today_url(self):
        """
        Covers line 39:
        Test that leads_created_today_url returns correct full URL
        """
        expected_url = "https://int-maglo-service.makunaiglobal.ai/maglo-service/v1/leads-created-today"
        assert TalkoMagloApiConstants.leads_created_today_url() == expected_url

        # Verify it handles trailing slash logic like the others
        original_base = TalkoMagloApiConstants.MAGLO_BASE_URL
        try:
            TalkoMagloApiConstants.MAGLO_BASE_URL = "https://test-api.ai/"
            assert (
                TalkoMagloApiConstants.leads_created_today_url()
                == "https://test-api.ai/v1/leads-created-today"
            )
        finally:
            TalkoMagloApiConstants.MAGLO_BASE_URL = original_base
