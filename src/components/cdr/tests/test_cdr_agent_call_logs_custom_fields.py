from unittest.mock import MagicMock

from src.components.cdr.helper import TalkoCallLogQueryHelper


class TestBuildCallLogQueryCustomFields:
    def test_custom_fields_param_flows_into_query(self):
        logger = MagicMock()

        query = TalkoCallLogQueryHelper.build_call_log_query(
            lead_id=None,
            logger=logger,
            partner_id=132,
            entity_type="Lead",
            entity_id=12345,
            custom_fields={"lead_source": "Referral"},
        )

        assert query["custom_fields.lead_source"] == "Referral"
        assert query["partner_id"] == 132

    def test_omitting_custom_fields_adds_no_dotted_keys(self):
        logger = MagicMock()

        query = TalkoCallLogQueryHelper.build_call_log_query(
            lead_id=None,
            logger=logger,
            partner_id=132,
            entity_type="Lead",
            entity_id=12345,
        )

        assert not any(k.startswith("custom_fields.") for k in query)

    def test_multiple_custom_field_conditions_are_anded(self):
        logger = MagicMock()

        query = TalkoCallLogQueryHelper.build_call_log_query(
            lead_id=None,
            logger=logger,
            partner_id=132,
            entity_type="Lead",
            entity_id=12345,
            custom_fields={"lead_source": "Referral", "lead_score": 87},
        )

        assert query["custom_fields.lead_source"] == "Referral"
        assert query["custom_fields.lead_score"] == 87
