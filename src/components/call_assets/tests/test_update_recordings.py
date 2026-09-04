import io
import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import UploadFile

from src.components.call_assets.tasks import RecordingsUpdateTask


@pytest.mark.asyncio
class TestRecordingsUpdateTask:
    def setup_method(self):
        """Initialize mocks and RecordingsUpdateTask instance before each test"""
        self.mock_logger = MagicMock()
        self.mock_cdr_repo = MagicMock()
        self.mock_call_repo = AsyncMock()
        self.mock_assets_repo = MagicMock()
        self.mock_helper = MagicMock()

        self.task = RecordingsUpdateTask(
            logger=self.mock_logger,
            cdr_repository=self.mock_cdr_repo,
            call_repository=self.mock_call_repo,
            assets_repository=self.mock_assets_repo,
            assets_helper=self.mock_helper
        )

    async def test_process_recordings_urls_success(self):
        """Test successful processing of pending recordings"""
        pending_cdrs = [
            {
                "_id": "68df705318ccc1bc467baad6",
                "call_status": "answered",
                "call_recording": "https://example.com/recording.mp3",
                "is_recording_saved": False,
                "partner_id": 1,
                "call_id": "1759473746.321400",
                "agent": 2,
                "caller_id_number": "1111111111",
                "talk_time": 60
            }
        ]

        self.mock_cdr_repo.get_cdrs_by_criteria = AsyncMock(return_value=pending_cdrs)
        self.mock_helper.url_to_upload_file = AsyncMock(
            return_value=UploadFile(file=io.BytesIO(b"dummy content"), filename="recording.mp3")
        )
        self.mock_helper.store_media_to_digital_ocean = AsyncMock(
            return_value="digitalocean/path/recording.mp3"
        )
        self.mock_assets_repo.create_digital_asset = AsyncMock(return_value=None)
        self.mock_call_repo.update_cdr = AsyncMock(return_value=True)

        result = await self.task.process_reocrdings_urls()

        assert result == "Recordings saved"
        self.mock_logger.info.assert_any_call(
            "Successfully Updated is_recording_saved for 1759473746.321400"
        )

    async def test_process_recordings_urls_no_pending_cdrs(self):
        """Test when there are no pending CDRs"""
        self.mock_cdr_repo.get_cdrs_by_criteria = AsyncMock(return_value=[])

        result = await self.task.process_reocrdings_urls()
        assert result == "No updates needed"
        self.mock_logger.info.assert_any_call("No records found with unsaved recordings")

    async def test_process_recordings_urls_inner_exception(self):
        """Test inner exception during upload/asset creation is logged"""
        pending_cdrs = [
            {
                "_id": "1",
                "call_status": "answered",
                "call_recording": "https://example.com/recording.mp3",
                "is_recording_saved": False,
                "partner_id": 1,
                "call_id": "call_1",
                "agent": "agent_1",
                "caller_id_number": "1111111111",
                "talk_time": 60
            }
        ]

        self.mock_cdr_repo.get_cdrs_by_criteria = AsyncMock(return_value=pending_cdrs)
        self.mock_helper.url_to_upload_file = AsyncMock(side_effect=Exception("Upload failed"))

        result = await self.task.process_reocrdings_urls()
        assert result == "Recordings saved"
        self.mock_logger.error.assert_called_with("Failed to upload call recording: Upload failed")

    async def test_process_recordings_urls_outer_exception(self):
        """Test outer exception during CDR processing is logged"""
        pending_cdrs = [
            {
                "_id": "2",
                "call_status": "answered",
                "call_recording": "https://example.com/recording.mp3",
                "is_recording_saved": False,
                "partner_id": 1,
                # missing call_id to trigger KeyError
                "agent": "agent_1",
                "caller_id_number": "1111111111",
                "talk_time": 60
            }
        ]

        self.mock_cdr_repo.get_cdrs_by_criteria = AsyncMock(return_value=pending_cdrs)
        self.mock_helper.url_to_upload_file = AsyncMock(
            return_value=UploadFile(file=io.BytesIO(b"data"), filename="rec.mp3")
        )

        result = await self.task.process_reocrdings_urls()
        assert result == "Recordings saved"
        assert any("Error processing CDR" in call[0][0] for call in self.mock_logger.error.call_args_list)

    async def test_process_recordings_urls_already_saved(self):
            """
            Test that if a CDR has 'is_recording_saved' = True,
            the method logs 'Recording is already saved' and does not attempt upload.
            """
            pending_cdrs = [
                {
                    "_id": "3",
                    "call_status": "answered",
                    "call_recording": "https://example.com/recording.mp3",
                    "is_recording_saved": True,
                    "partner_id": 1,
                    "call_id": "call_3",
                    "agent": "agent_3",
                    "caller_id_number": "1111111111",
                    "talk_time": 60,
                }
            ]

            self.mock_cdr_repo.get_cdrs_by_criteria = AsyncMock(return_value=pending_cdrs)

            result = await self.task.process_reocrdings_urls()

            # The method should return the normal string
            assert result == "Recordings saved"

            # Assert that upload helper methods were NOT called
            self.mock_helper.url_to_upload_file.assert_not_called()
            self.mock_helper.store_media_to_digital_ocean.assert_not_called()
            self.mock_assets_repo.create_digital_asset.assert_not_called()
            self.mock_call_repo.update_cdr.assert_not_called()

            # Assert logger logs the "already saved" message
            self.mock_logger.info.assert_any_call("Recording is already saved for call_3")