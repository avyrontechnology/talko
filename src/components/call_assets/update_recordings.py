from fastapi import UploadFile

from typing import Any, Dict, List


from src.components.call_assets.helper import AssetsHelper
from src.components.call_assets.repository import AssetRepository
from src.components.call_assets.messages import FAILED_TO_UPDATE_RECORDING_STATUS
from src.components.call_management.repository import CallRepository
from src.components.cdr.repository import CDRRepository
from src.components.digital_assets.constants import DigitalAssetEnum
from src.exceptions import BadRequestError
from src.loggers.holler_service_logger import HollerServiceLogger


class RecordingsUpdateTask:
    """
    Encapsulates logic for checking and saving unsaved call recordings
    """
    def __init__(self, logger: HollerServiceLogger, cdr_repository: CDRRepository,call_repository:CallRepository,  assets_repository: AssetRepository, assets_helper: AssetsHelper) -> None:
        """
        Initialize the RecordingsUpdateTask.
        Args:
            logger: Logger instance for logging task details.
            cdr_repository: Repository for accessing CDR records.
            assets_repository: Repository for accessing call_assets functions.
        """
        self.__logger: HollerServiceLogger = logger
        self.__cdr_repository: CDRRepository = cdr_repository
        self.__call_repository: CallRepository = call_repository
        self.__assets_repository: AssetRepository = assets_repository
        self.__helper: AssetsHelper = assets_helper

    async def get_cdrs_with_unsaved_recordings(self, limit: int = 15, skip: int = 0) -> List[Dict[str, Any]]:
        """
        Fetch CDRs where:
            - call_status is 'answered'
            - call_recording is not empty
            - is_recording_saved is False
        """
        self.__logger.info("Fetching cdrs with unsaved recordings")

        query: Dict[str, Any] = {
            "call_status": "answered",
            "call_recording": {"$ne": ""},
            "is_recording_saved": False,  # recordings that are not saved
        }

        cdrs: List[Dict[str, Any]] = await self.__cdr_repository.get_cdrs_by_criteria(query, limit=limit, skip=skip)
        self.__logger.info("Found {} records from CDRs whose recordings is not saved".format(len(cdrs)))
        return cdrs

    async def process_reocrdings_urls(self) -> str:

        # 1. fetch cdrs with whose recordings is not saved yet
        pending_cdrs: List[Dict[str, Any]] = await self.get_cdrs_with_unsaved_recordings()

        self.__logger.info("Fetched {} incomplete CDR(s) with unsaved recordings".format(len(pending_cdrs)))

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
                    self.__logger.info("Recording url found for {}, url: {}".format(identifier, received_recording_url))
                    try:
                        # Converting recording url to UploadFile type obj
                        file_obj: UploadFile = await self.__helper.url_to_upload_file(received_recording_url)

                        # Upload to DigitalOcean
                        file_path: str = await self.__helper.store_media_to_digital_ocean(
                            file_obj,
                            cdr["partner_id"],
                            DigitalAssetEnum.GLOBAL_MEDIA_CONSTANT.name
                        )
                        self.__logger.info("Call recording uploaded successfully at {}".format(file_path))

                        # creating record for the recordings in db
                        await self.__assets_repository.create_digital_asset(
                            cdr["partner_id"], 
                            DigitalAssetEnum.GLOBAL_MEDIA_CONSTANT.name, 
                            file_path, 
                            cdr["agent"],
                            cdr["caller_id_number"],
                            cdr["talk_time"],
                            cdr["agent"],
                            cdr["call_id"],
                        )
                            
                        # update is_recording_saved to True for the current record in the cdr
                        result: bool = await self.__call_repository.update_cdr(str(cdr["_id"]), 
                        {
                            "is_recording_saved": True,
                            "path_for_recording": file_path
                        }
                        )
                        if not result:
                            self.__logger.info("Unable to update is_recording_saved for {}".format(identifier))
                        self.__logger.info("Successfully Updated is_recording_saved for {}".format(identifier))
                    except Exception as e:
                        self.__logger.error("Failed to upload call recording: {}".format(str(e)))
                else:
                    self.__logger.info("Recording is already saved for {}".format(identifier))
            except Exception as e:
                temp_call_id: str = cdr.get("call_id", str(cdr.get("_id", "unknown")))
                self.__logger.error("Error processing CDR {}: {}".format(temp_call_id, str(e)))
        return "Recordings saved"
