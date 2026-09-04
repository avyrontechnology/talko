import pytest
from pydantic import ValidationError

from src.components.dialer.dto import TalkoContract


class TestContractModels:

    def test_lead_list_item_success(self):
        data = {
            "id": 1,
            "name": "Test List",
            "description": "A test description",
            "field_map": ["phone", "name"],
        }
        item = TalkoContract.LeadListItem(**data)
        assert item.id == 1
        assert item.name == "Test List"

    def test_lead_list_item_invalid_id(self):
        with pytest.raises(ValidationError) as exc:
            TalkoContract.LeadListItem(id=0, name="Bad ID", description="desc", field_map=[])
        assert "id must be a positive integer" in str(exc.value)

    # LeadListsFetchResponse Tests
    def test_lead_lists_fetch_response_success(self):
        list_item = {
            "id": 10,
            "name": "Campaign A",
            "description": "desc",
            "field_map": ["f0"],
        }
        response_data = {
            "status": "success",
            "message": "Data retrieved",
            "data": {"lists": [list_item]},
        }
        resp = TalkoContract.LeadListsFetchResponse(**response_data)
        assert resp.status == "success"
        assert len(resp.data["lists"]) == 1
        assert isinstance(resp.data["lists"][0], TalkoContract.LeadListItem)

    # BulkLeadsCreateRequest Tests
    def test_bulk_leads_create_success(self):
        payload = {
            "data": [{"field_0": "1234567890", "field_1": "John"}],
            "duplicate_option": "overwrite",
        }
        req = TalkoContract.BulkLeadsCreateRequest(**payload)
        assert len(req.data) == 1
        assert req.data[0].field_0 == "1234567890"
        assert req.duplicate_option == "overwrite"

    def test_bulk_leads_create_default_duplicate_option(self):
        payload = {"data": [{"field_0": "1234567890"}]}
        req = TalkoContract.BulkLeadsCreateRequest(**payload)
        assert req.duplicate_option == "skip"

    def test_bulk_leads_missing_data_field(self):
        with pytest.raises(ValidationError) as exc:
            TalkoContract.BulkLeadsCreateRequest(data=None)
        assert "data array is required and cannot be empty" in str(exc.value)

    def test_bulk_leads_empty_list(self):
        with pytest.raises(ValidationError) as exc:
            TalkoContract.BulkLeadsCreateRequest(data=[])

        assert "data array is required and cannot be empty" in str(exc.value)

    def test_invalid_duplicate_option(self):
        payload = {"data": [{"field_0": "123"}], "duplicate_option": "delete_all"}
        with pytest.raises(ValidationError) as exc:
            TalkoContract.BulkLeadsCreateRequest(**payload)

        error_msg = str(exc.value)
        assert "duplicate_option must be one of" in error_msg
        assert "skip" in error_msg
        assert "overwrite" in error_msg
        assert "clone" in error_msg

    def test_bulk_leads_missing_phone_in_item(self):
        payload = {"data": [{"field_0": "111"}, {"field_1": "Missing field_0 here"}]}
        with pytest.raises(ValidationError) as exc:
            TalkoContract.BulkLeadsCreateRequest(**payload)
        assert "Each lead must contain field_0 (phone number). Error at index 1" in str(
            exc.value
        )

    # BulkLeadsCreateResponse Tests
    def test_bulk_leads_create_response_success(self):
        resp = TalkoContract.BulkLeadsCreateResponse(success=True, message="Leads uploaded")
        assert resp.success is True
        assert resp.message == "Leads uploaded"
