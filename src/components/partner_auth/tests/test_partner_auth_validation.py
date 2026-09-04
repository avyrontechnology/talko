from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.components.partner_auth.validation import TalkoPartnerApiKeyValidator
from src.exceptions import TalkoResourceNotFound


@pytest.mark.asyncio
class TestPartnerApiKeyValidator:
    @pytest.fixture
    def validator(self):
        return TalkoPartnerApiKeyValidator(logger=MagicMock(), repository=AsyncMock())

    async def test_validate_key_exists_success(self, validator):
        key_id = ObjectId()
        validator.repository.find_by_id.return_value = {"_id": key_id}
        result = await validator.validate_key_exists(key_id)
        assert result["_id"] == key_id

    async def test_validate_key_exists_not_found(self, validator):
        validator.repository.find_by_id.return_value = None
        with pytest.raises(TalkoResourceNotFound):
            await validator.validate_key_exists(ObjectId())
