from bson import ObjectId

from src.utils.mongo_utils import stringify_object_ids


class TestStringifyObjectIds:
    def test_converts_top_level(self):
        oid = ObjectId()
        out = stringify_object_ids({"_id": oid, "n": 1, "s": "x"})
        assert out == {"_id": str(oid), "n": 1, "s": "x"}

    def test_does_not_mutate_input(self):
        oid = ObjectId()
        doc = {"_id": oid}
        stringify_object_ids(doc)
        assert doc["_id"] is oid

    def test_empty(self):
        assert stringify_object_ids({}) == {}
