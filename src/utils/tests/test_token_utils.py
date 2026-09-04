from src.utils.token_utils import TalkoApiKeyGenerator


class TestTalkoApiKeyGenerator:
    def test_generate_produces_prefixed_key(self):
        raw_key, key_prefix, key_hash = TalkoApiKeyGenerator.generate()
        assert raw_key.startswith(TalkoApiKeyGenerator.PREFIX)
        assert key_prefix == raw_key[: len(key_prefix)]
        assert raw_key.startswith(key_prefix)

    def test_generate_hash_matches_hash_key(self):
        raw_key, _key_prefix, key_hash = TalkoApiKeyGenerator.generate()
        assert TalkoApiKeyGenerator.hash_key(raw_key) == key_hash

    def test_generate_is_random(self):
        raw_key_1, _, _ = TalkoApiKeyGenerator.generate()
        raw_key_2, _, _ = TalkoApiKeyGenerator.generate()
        assert raw_key_1 != raw_key_2

    def test_hash_key_deterministic(self):
        assert TalkoApiKeyGenerator.hash_key("abc") == TalkoApiKeyGenerator.hash_key(
            "abc"
        )
        assert TalkoApiKeyGenerator.hash_key("abc") != TalkoApiKeyGenerator.hash_key(
            "abd"
        )

    def test_is_partner_key(self):
        raw_key, _, _ = TalkoApiKeyGenerator.generate()
        assert TalkoApiKeyGenerator.is_partner_key(raw_key) is True
        assert TalkoApiKeyGenerator.is_partner_key("some-other-opaque-key") is False
