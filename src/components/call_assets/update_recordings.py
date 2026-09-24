from typing import Any

from fastapi import UploadFile

from src.components.call_assets.helper import TalkoAssetsHelper
from src.components.call_assets.repository import TalkoAssetRepository
from src.components.call_management.repository import TalkoCallRepository
from src.components.cdr.repository import TalkoCDRRepository
from src.components.digital_assets.constants import TalkoDigitalAssetEnum
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoRecordingsUpdateTask:
    """
    Encapsulates logic for checking and saving unsaved call recordings
    """

    def __init__(
        self,
        logger: TalkoServiceLogger,
        cdr_repository: TalkoCDRRepository,
        call_repository: TalkoCallRepository,
        assets_repository: TalkoAssetRepository,
        assets_helper: TalkoAssetsHelper,
    ) -> None:
        """
        Initialize the TalkoRecordingsUpdateTask.
        Args:
            logger: Logger instance for logging task details.
            cdr_repository: Repository for accessing TalkoCDR records.
            assets_repository: Repository for accessing call_assets functions.
        """
        self.__logger: TalkoServiceLogger = logger
        self.__cdr_repository: TalkoCDRRepository = cdr_repository
        self.__call_repository: TalkoCallRepository = call_repository
        self.__assets_repository: TalkoAssetRepository = assets_repository
        self.__helper: TalkoAssetsHelper = assets_helper

    async def get_cdrs_with_unsaved_recordings(self, limit: int = 15, skip: int = 0) -> list[dict[str, Any]]:
        """
        Fetch CDRs where:
            - call_status is 'answered'
            - call_recording is not empty
            - is_recording_saved is False
        """
        self.__logger.info("Fetching cdrs with unsaved recordings")

        query: dict[str, Any] = {
            "call_status": "answered",
            "call_recording": {"$ne": ""},
            "is_recording_saved": False,  # recordings that are not saved
        }

        cdrs: list[dict[str, Any]] = await self.__cdr_repository.get_cdrs_by_criteria(query, limit=limit, skip=skip)
        self.__logger.info(f"Found {len(cdrs)} records from CDRs whose recordings is not saved")
        return cdrs

    async def process_reocrdings_urls(self) -> str:

        # 1. fetch cdrs with whose recordings is not saved yet
        pending_cdrs: list[dict[str, Any]] = await self.get_cdrs_with_unsaved_recordings()

        self.__logger.info(f"Fetched {len(pending_cdrs)} incomplete TalkoCDR(s) with unsaved recordings")

        if not pending_cdrs:
            self.__logger.info("No records found with unsaved recordings")
            return "No updates needed"

        # 2. go through each record of the cdr and get the recording url and save it to digital ocean

        for cdr in pending_cdrs:
            try:
                # code for Uploading call recording to digital ocean starts here
                identifier = cdr["call_id"]
                received_recording_url: str = cdr["call_recording"]
                if not cdr["is_recording_saved"]:
                    self.__logger.info(f"Recording url found for {identifier}, url: {received_recording_url}")
                    try:
                        # Converting recording url to UploadFile type obj
                        file_obj: UploadFile = await self.__helper.url_to_upload_file(received_recording_url)

                        # Upload to DigitalOcean
                        file_path: str = await self.__helper.store_media_to_digital_ocean(
                            file_obj, cdr["partner_id"], TalkoDigitalAssetEnum.GLOBAL_MEDIA_CONSTANT.name
                        )
                        self.__logger.info(f"Call recording uploaded successfully at {file_path}")

                        # creating record for the recordings in db
                        await self.__assets_repository.create_digital_asset(
                            cdr["partner_id"],
                            TalkoDigitalAssetEnum.GLOBAL_MEDIA_CONSTANT.name,
                            file_path,
                            cdr["agent"],
                            cdr["caller_id_number"],
                            cdr["talk_time"],
                            cdr["agent"],
                            cdr["call_id"],
                        )

                        # update is_recording_saved to True for the current record in the cdr
                        result: bool = await self.__call_repository.update_cdr(
                            str(cdr["_id"]), {"is_recording_saved": True, "path_for_recording": file_path}
                        )
                        if not result:
                            self.__logger.info(f"Unable to update is_recording_saved for {identifier}")
                        self.__logger.info(f"Successfully Updated is_recording_saved for {identifier}")
                    except Exception as e:
                        self.__logger.error(f"Failed to upload call recording: {str(e)}")
                else:
                    self.__logger.info(f"Recording is already saved for {identifier}")
            except Exception as e:
                temp_call_id: str = cdr.get("call_id", str(cdr.get("_id", "unknown")))
                self.__logger.error(f"Error processing TalkoCDR {temp_call_id}: {str(e)}")
        return "Recordings saved"
