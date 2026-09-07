from unittest.mock import MagicMock, patch

import pytest

from src.components.digital_assets.storage.factory import TalkoFactoryStorageManager
from src.components.digital_assets.storage.managers.cloudinary_manager import (
    TalkoCloudinaryStorageManager,
)
from src.core.environment import TalkoENV

# NOTE: TalkoENV binds os.environ at import time, so tests patch its
# attributes directly rather than os.environ.


def make_manager(monkeypatch, **overrides):
    vals = dict(
        CLOUDINARY_CLOUD_NAME="demo-cloud",
        CLOUDINARY_API_KEY="key",
        CLOUDINARY_API_SECRET="secret",
        CLOUDINARY_FOLDER="talko",
    )
    vals.update(overrides)
    for k, v in vals.items():
        monkeypatch.setattr(TalkoENV, k, v, raising=False)
    with patch("cloudinary.config"):
        return TalkoCloudinaryStorageManager()


class TestCloudinaryManagerInit:
    def test_missing_creds_raise(self, monkeypatch):
        for k in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
            monkeypatch.setattr(TalkoENV, k, "", raising=False)
        with patch("cloudinary.config"):
            with pytest.raises(RuntimeError, match="Cloudinary"):
                TalkoCloudinaryStorageManager()

    def test_public_id_mapping(self, monkeypatch):
        mgr = make_manager(monkeypatch)
        assert mgr._public_id("logos/a.png") == "talko/logos/a.png"
        assert mgr._public_id("/logos/a.png") == "talko/logos/a.png"


class TestCloudinaryUpload:
    @pytest.mark.asyncio
    async def test_upload_returns_secure_url(self, monkeypatch):
        import src.components.digital_assets.storage.managers.cloudinary_manager as mod

        mgr = make_manager(monkeypatch)
        file_obj = MagicMock()
        file_obj.filename = "logo.png"
        with patch.object(
            mod.cloudinary.uploader, "upload", return_value={"secure_url": "https://res.cloudinary.com/demo/image/upload/talko/logo.png", "public_id": "talko/logo.png"}
        ) as mock_upload:
            url = await mgr.upload_digital_asset(file_obj, "logo.png")
        assert url.startswith("https://res.cloudinary.com/")
        kwargs = mock_upload.call_args.kwargs
        assert kwargs["public_id"] == "talko/logo.png"
        assert kwargs["resource_type"] == "auto"

    @pytest.mark.asyncio
    async def test_upload_failure_raises_value_error(self, monkeypatch):
        import src.components.digital_assets.storage.managers.cloudinary_manager as mod

        mgr = make_manager(monkeypatch)
        file_obj = MagicMock()
        file_obj.filename = "logo.png"
        with patch.object(mod.cloudinary.uploader, "upload", side_effect=Exception("boom")):
            with pytest.raises(ValueError, match="logo.png"):
                await mgr.upload_digital_asset(file_obj, "logo.png")


class TestCloudinaryUrls:
    def test_presigned_url_signed_with_expiry(self, monkeypatch):
        import src.components.digital_assets.storage.managers.cloudinary_manager as mod

        mgr = make_manager(monkeypatch)
        with patch.object(mod.cloudinary.api, "resource", return_value={"resource_type": "image"}):
            with patch.object(
                mod.cloudinary.utils, "cloudinary_url", return_value=("https://signed.url/x", {})
            ) as mock_url:
                url = mgr.get_presigned_url("docs/a.pdf", view_only=False)
        assert url == "https://signed.url/x"
        kwargs = mock_url.call_args.kwargs
        assert kwargs["sign_url"] is True
        assert kwargs["flags"] == "attachment"
        assert kwargs["expires_at"] > 0

    def test_presigned_url_view_only_inline(self, monkeypatch):
        import src.components.digital_assets.storage.managers.cloudinary_manager as mod

        mgr = make_manager(monkeypatch)
        with patch.object(mod.cloudinary.api, "resource", side_effect=Exception("nf")):
            with patch.object(
                mod.cloudinary.utils, "cloudinary_url", return_value=("https://signed.url/y", {})
            ) as mock_url:
                mgr.get_presigned_url("docs/a.pdf", view_only=True)
        assert mock_url.call_args.kwargs["flags"] is None

    def test_delete_idempotent_across_types(self, monkeypatch):
        import src.components.digital_assets.storage.managers.cloudinary_manager as mod

        mgr = make_manager(monkeypatch)
        calls = []

        def fake_destroy(public_id, resource_type=None):
            calls.append(resource_type)
            return {"result": "ok" if resource_type == "video" else "not found"}

        with patch.object(mod.cloudinary.uploader, "destroy", side_effect=fake_destroy):
            mgr.delete_digital_asset("media/clip")  # must not raise
        assert calls[0] == "image"

    def test_delete_missing_asset_does_not_raise(self, monkeypatch):
        import src.components.digital_assets.storage.managers.cloudinary_manager as mod

        mgr = make_manager(monkeypatch)
        with patch.object(
            mod.cloudinary.uploader, "destroy", return_value={"result": "not found"}
        ):
            mgr.delete_digital_asset("media/gone")  # S3-like idempotent delete


class TestFactory:
    def test_factory_returns_cloudinary_manager(self, monkeypatch):
        mgr = make_manager(monkeypatch)  # noqa: F841 (ensures env valid)
        with patch(
            "src.components.digital_assets.storage.factory.cloudinary_manager.TalkoCloudinaryStorageManager"
        ) as cls:
            TalkoFactoryStorageManager.get_storage_class("CLOUDINARY")
        cls.assert_called_once_with()

    def test_unknown_provider_still_rejected(self):
        with pytest.raises(ValueError, match="Unknown storage"):
            TalkoFactoryStorageManager.get_storage_class("NOPE")
