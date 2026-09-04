from unittest.mock import MagicMock

from src.components.cdr.helper import GetCallRecordHistoryHelper


class TestAddCustomFieldsFilter:
    def test_adds_dot_notation_condition_per_slug(self):
        logger = MagicMock()
        query = {"partner_id": 132}

        GetCallRecordHistoryHelper.add_custom_fields_filter(
            query, {"lead_source": "Referral", "lead_score": 87}, logger
        )

        assert query == {
            "partner_id": 132,
            "custom_fields.lead_source": "Referral",
            "custom_fields.lead_score": 87,
        }

    def test_none_leaves_query_untouched(self):
        logger = MagicMock()
        query = {"partner_id": 132}

        GetCallRecordHistoryHelper.add_custom_fields_filter(query, None, logger)

        assert query == {"partner_id": 132}

    def test_empty_dict_leaves_query_untouched(self):
        logger = MagicMock()
        query = {"partner_id": 132}

        GetCallRecordHistoryHelper.add_custom_fields_filter(query, {}, logger)

        assert query == {"partner_id": 132}


class TestBuildCallRecordHistoryQueryCustomFields:
    def test_custom_fields_param_flows_into_query(self):
        logger = MagicMock()

        query = GetCallRecordHistoryHelper.build_call_record_history_query(
            lead_id=None,
            service_board_id=323,
            partner_id=132,
            logger=logger,
            custom_fields={"lead_source": "Referral"},
        )

        assert query["custom_fields.lead_source"] == "Referral"
        assert query["partner_id"] == 132
        assert query["service_board_id"] == 323

    def test_omitting_custom_fields_adds_no_dotted_keys(self):
        logger = MagicMock()

        query = GetCallRecordHistoryHelper.build_call_record_history_query(
            lead_id=None,
            service_board_id=323,
            partner_id=132,
            logger=logger,
        )

        assert not any(k.startswith("custom_fields.") for k in query)
