from src.utils.slugify import slugify_name, unique_slug


class TestSlugifyName:
    def test_basic(self):
        assert slugify_name("Tata Tele") == "tata-tele"

    def test_special_chars(self):
        assert slugify_name("  Acme_Corp!! ") == "acme-corp"

    def test_empty_falls_back(self):
        assert slugify_name("", fallback="vendor").startswith("vendor-")
        assert slugify_name("!!!", fallback="vendor").startswith("vendor-")


class TestUniqueSlug:
    def test_no_collision(self):
        assert unique_slug("tata", set()) == "tata"

    def test_collision_increments(self):
        assert unique_slug("tata", {"tata", "tata-2"}) == "tata-3"
