import io
import pytest
import re
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import UploadFile

from src.components.call_assets.messages import MISSING_FILE_PATH, SOMETHING_WENT_WRONG
from src.components.common.responses import InternalServerErrorResponse
from src.components.digital_assets.storage.helper import StorageHelper
from src.exceptions import BadRequestError
from src.components.call_assets.helper import AssetsHelper


@pytest.fixture
def mock_logger():
    """Fixture for a mock logger."""
    logger = MagicMock()
    return logger


@pytest.mark.asyncio
class TestAssetsHelper:
    """Test suite for AssetsHelper class."""

    async def test_url_to_upload_file_success(self, mock_logger):
        """Should convert a URL to UploadFile successfully."""
        helper = AssetsHelper(logger=mock_logger)

        mock_response = MagicMock()
        mock_response.content = b"fake audio data"
        mock_response.raise_for_status = MagicMock()

        with patch("src.components.call_assets.helper.requests.get", return_value=mock_response):
            upload_file = await helper.url_to_upload_file("https://example.com/file.mp3?token=123")

        assert isinstance(upload_file, UploadFile)
        assert upload_file.filename.startswith("file.mp3")
        assert upload_file.file.read() == b"fake audio data"

        mock_logger.info.assert_any_call("Starting conversion of recording url to UploadFile object")
        mock_logger.info.assert_any_call("Conversion of URL is done with file_name: {}".format(upload_file.filename))

    async def test_url_to_upload_file_failure(self, mock_logger):
        """Should raise RuntimeError if the request fails."""
        helper = AssetsHelper(logger=mock_logger)

        with patch("src.components.call_assets.helper.requests.get", side_effect=Exception("Network error")):
            with pytest.raises(RuntimeError, match="Failed to convert URL to UploadFile: Network error"):
                await helper.url_to_upload_file("https://bad-url")

    async def test_store_media_to_digital_ocean_success(self, mock_logger):
        """Should upload media to DigitalOcean and return file path."""
        helper = AssetsHelper(logger=mock_logger)

        file_obj = UploadFile(filename="sample.mp3", file=io.BytesIO(b"12345"))

        mock_presigned_url = "https://do-test-url.com/path"
        with patch.object(StorageHelper, "upload_file", new=AsyncMock()) as mock_upload, \
             patch.object(StorageHelper, "get_presigned_url", return_value=mock_presigned_url):
            path = await helper.store_media_to_digital_ocean(file_obj, partner_id=123, asset_type="recording")

        assert isinstance(path, str)
        assert "recording" in path
        mock_upload.assert_awaited_once()
        mock_logger.info.assert_any_call("Uploading media to DigitalOcean")

    async def test_store_media_to_digital_ocean_no_file(self, mock_logger):
        """Should skip upload if file object is missing."""
        helper = AssetsHelper(logger=mock_logger)

        path = await helper.store_media_to_digital_ocean(None, partner_id=123, asset_type="recording")

        assert path == ""
        mock_logger.error.assert_any_call("No file provided, skipping upload")

    async def test_store_media_to_digital_ocean_exception(self, mock_logger):
        """Should log error and raise when upload fails."""
        helper = AssetsHelper(logger=mock_logger)
        file_obj = UploadFile(filename="bad.mp3", file=io.BytesIO(b"12345"))

        with patch.object(StorageHelper, "upload_file", new=AsyncMock(side_effect=Exception("Upload failed"))):
            with pytest.raises(Exception, match="Upload failed"):
                await helper.store_media_to_digital_ocean(file_obj, partner_id=123, asset_type="recording")

        mock_logger.error.assert_any_call("Unexpected error while uploading media: Upload failed")

    async def test_get_recording_url_from_path_success(self, mock_logger):
        """Should return presigned URL successfully."""
        helper = AssetsHelper(logger=mock_logger)

        mock_url = "https://digital-ocean.com/test.mp3"
        with patch.object(StorageHelper, "get_presigned_url", return_value=mock_url):
            result = await helper.get_recording_url_from_path("partner1/service/test.mp3")

        assert result == mock_url
        mock_logger.info.assert_any_call("Received file_path for URL generation: partner1/service/test.mp3")
        mock_logger.debug.assert_any_call("Generated recording URL: {}".format(mock_url))

    async def test_get_recording_url_from_path_missing_path(self, mock_logger):
        """Should raise BadRequestError if file_path is missing."""
        helper = AssetsHelper(logger=mock_logger)

        with pytest.raises(BadRequestError, match=MISSING_FILE_PATH):
            await helper.get_recording_url_from_path("")

        mock_logger.warning.assert_any_call("FilePath not found for recording URL generation")

    async def test_get_recording_url_from_path_failure(self, mock_logger):
        """Should raise the original exception on presigned URL generation failure."""
        helper = AssetsHelper(logger=mock_logger)

        with patch.object(StorageHelper, "get_presigned_url", side_effect=Exception("DO failure")):
            with pytest.raises(Exception) as exc_info:
                await helper.get_recording_url_from_path("some/path.mp3")


            assert "DO failure" in str(exc_info.value)


        mock_logger.error.assert_any_call(
            "Failed to generate recording URL for file_path 'some/path.mp3': DO failure"
        )


    async def test_url_to_upload_file_query_special_chars(self, mock_logger):
        helper = AssetsHelper(logger=mock_logger)

        mock_response = MagicMock()
        mock_response.content = b"audio data"
        mock_response.raise_for_status = MagicMock()

        url = "https://example.com/file.mp3?token=abc123&name=test#fragment"

        with patch("src.components.call_assets.helper.requests.get", return_value=mock_response):
            upload_file = await helper.url_to_upload_file(url)

        # filename should replace unsafe chars with "_"
        assert upload_file.filename == "file.mp3_token_abc123_name_test"
        assert upload_file.file.read() == b"audio data"

    async def test_file_pointer_reset_after_read(self, mock_logger):
        helper = AssetsHelper(logger=mock_logger)

        mock_response = MagicMock()
        mock_response.content = b"data"
        mock_response.raise_for_status = MagicMock()

        with patch("src.components.call_assets.helper.requests.get", return_value=mock_response):
            upload_file = await helper.url_to_upload_file("https://example.com/file.mp3")

        # reading twice should give same content
        content_first = upload_file.file.read()
        upload_file.file.seek(0)
        content_second = upload_file.file.read()
        assert content_first == content_second == b"data"

    async def test_url_to_upload_file_unexpected_exception(self, mock_logger):
        helper = AssetsHelper(logger=mock_logger)

        with patch("src.components.call_assets.helper.requests.get", side_effect=ValueError("Boom")):
            with pytest.raises(RuntimeError, match="Failed to convert URL to UploadFile: Boom"):
                await helper.url_to_upload_file("https://bad-url")


