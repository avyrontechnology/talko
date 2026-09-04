from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from src.components.vendor.models import TalkoVendorModel
from src.components.vendor.repository import TalkoVendorRepository


@pytest.mark.asyncio
class TestVendorRepository:
    @classmethod
    def setup_class(cls):
        cls.mock_db_manager = MagicMock()
        cls.mock_logger = MagicMock()
        cls.repository = TalkoVendorRepository(cls.mock_db_manager, cls.mock_logger)
        cls.collection_name = TalkoVendorModel.CollectionName.VENDOR

    def setup_method(self):
        self.collection_mock = AsyncMock()
        collection_context = AsyncMock()
        collection_context.__aenter__.return_value = self.collection_mock
        self.mock_db_manager.collection.return_value = collection_context

    async def test_insert_vendor_success(self):
        self.collection_mock.insert_one.return_value.inserted_id = ObjectId(
            "60d5ec49f1c2ee7a3c56a5e2"
        )
        result = await self.repository.insert_vendor({"name": "Test Vendor"})
        assert isinstance(result, str)
        self.collection_mock.insert_one.assert_called_once()

    async def test_insert_vendor_exception(self):
        self.collection_mock.insert_one.side_effect = Exception("Insert failed")
        with pytest.raises(Exception, match="Insert failed"):
            await self.repository.insert_vendor({"name": "Test Vendor"})

    async def test_find_vendor_by_slug_success(self):
        self.collection_mock.find_one.return_value = {"slug": "test-slug"}
        result = await self.repository.find_vendor_by_slug("test-slug")
        assert result["slug"] == "test-slug"
        self.collection_mock.find_one.assert_called_with({"slug": "test-slug"})

    async def test_find_vendor_by_slug_exception(self):
        self.collection_mock.find_one.side_effect = Exception("Find by slug failed")
        with pytest.raises(Exception, match="Find by slug failed"):
            await self.repository.find_vendor_by_slug("test-slug")

    async def test_find_vendor_by_type_success(self):
        self.collection_mock.find_one.return_value = {"vendor_type": "airtel"}
        result = await self.repository.find_vendor_by_type("airtel", "Airtel Vendor")
        assert result["vendor_type"] == "airtel"
        self.collection_mock.find_one.assert_called_with(
            {"vendor_type": "airtel", "name": "Airtel Vendor"}
        )

    async def test_find_vendor_by_type_exception(self):
        self.collection_mock.find_one.side_effect = Exception("Find by type failed")
        with pytest.raises(Exception, match="Find by type failed"):
            await self.repository.find_vendor_by_type("airtel", "Airtel Vendor")

    async def test_find_vendor_by_id_success(self):
        obj_id = ObjectId("60d5ec49f1c2ee7a3c56a5e2")
        self.collection_mock.find_one.return_value = {"_id": obj_id, "is_active": True}
        result = await self.repository.find_vendor_by_id(obj_id)
        self.collection_mock.find_one.assert_called_with(
            {"_id": obj_id, "is_active": True}
        )
        assert result["_id"] == obj_id

    async def test_find_vendor_by_id_exception(self):
        obj_id = ObjectId()
        self.collection_mock.find_one.side_effect = Exception("Find by ID failed")
        with pytest.raises(Exception, match="Find by ID failed"):
            await self.repository.find_vendor_by_id(obj_id)

    async def test_find_vendor_by_id_all_success(self):
        obj_id = ObjectId("60d5ec49f1c2ee7a3c56a5e2")
        self.collection_mock.find_one.return_value = {"_id": obj_id}
        result = await self.repository.find_vendor_by_id_all(obj_id)
        self.collection_mock.find_one.assert_called_with({"_id": obj_id})
        assert result["_id"] == obj_id

    async def test_find_vendor_by_id_all_exception(self):
        obj_id = ObjectId()
        self.collection_mock.find_one.side_effect = Exception("Find all by ID failed")
        with pytest.raises(Exception, match="Find all by ID failed"):
            await self.repository.find_vendor_by_id_all(obj_id)

    async def test_update_vendor_status_success(self):
        obj_id = ObjectId("60d5ec49f1c2ee7a3c56a5e2")
        updated_data = {"_id": obj_id, "is_active": True, "updated_at": 1234567890}
        self.collection_mock.find_one_and_update.return_value = updated_data

        result = await self.repository.update_vendor_status(obj_id, True, 1234567890)

        self.collection_mock.find_one_and_update.assert_called_once_with(
            {"_id": obj_id},
            {"$set": {"is_active": True, "updated_at": 1234567890}},
            return_document=True,
        )
        assert result == updated_data

    async def test_update_vendor_status_not_found(self):
        obj_id = ObjectId("60d5ec49f1c2ee7a3c56a5e2")
        self.collection_mock.find_one_and_update.return_value = None

        with pytest.raises(ValueError, match=f"Vendor with ID {obj_id} not found"):
            await self.repository.update_vendor_status(obj_id, True, 1234567890)

    async def test_update_vendor_status_exception(self):
        obj_id = ObjectId()
        self.collection_mock.find_one_and_update.side_effect = Exception(
            "Update failed"
        )

        with pytest.raises(Exception, match="Update failed"):
            await self.repository.update_vendor_status(obj_id, True, 1234567890)


@pytest.mark.asyncio
class TestVendorRepo:
    def setup_method(self):
        self.db_manager = MagicMock()
        self.logger = MagicMock()
        self.repository = TalkoVendorRepository(self.db_manager, self.logger)

        self.collection_mock = MagicMock()
        self.db_manager.collection.return_value.__aenter__ = AsyncMock(
            return_value=self.collection_mock
        )
        self.db_manager.collection.return_value.__aexit__ = AsyncMock(return_value=None)

    async def test_find_all_vendors_active_only(self):
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[{"name": "Vendor A"}])
        self.collection_mock.find.return_value = mock_cursor

        result = await self.repository.find_all_vendors()

        self.collection_mock.find.assert_called_once_with({"is_active": True})
        mock_cursor.to_list.assert_called_once_with(length=None)
        assert result == [{"name": "Vendor A"}]

    async def test_find_all_vendors_include_inactive(self):
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[{"name": "Vendor B"}])
        self.collection_mock.find.return_value = mock_cursor

        result = await self.repository.find_all_vendors(include_inactive=True)

        self.collection_mock.find.assert_called_once_with({})
        mock_cursor.to_list.assert_called_once_with(length=None)
        assert result == [{"name": "Vendor B"}]

    async def test_find_all_vendors_exception(self):
        self.collection_mock.find.side_effect = Exception("Find all failed")

        with pytest.raises(Exception, match="Find all failed"):
            await self.repository.find_all_vendors()
