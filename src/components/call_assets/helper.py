import io
import re
import uuid
from urllib.parse import unquote, urlparse

import requests
from fastapi import UploadFile

from src.components.call_assets.messages import MISSING_FILE_PATH, SOMETHING_WENT_WRONG
from src.components.common.responses import (
    BadRequestResponse,
    InternalServerErrorResponse,
)
from src.components.digital_assets.storage.helper import StorageHelper
from src.core.environment import ENV
from src.exceptions import BadRequestError
from src.loggers.holler_service_logger import HollerServiceLogger


class AssetsHelper:
    """
    Helper functions for assets management
    """

    def __init__(self, logger: HollerServiceLogger) -> None:
        try:
            self.__logger: HollerServiceLogger = logger
        except Exception as e:
            self.__logger.error("Failed to initialize AssetsHelper: {}".format(str(e)))
            raise

    async def url_to_upload_file(self, file_url: str) -> UploadFile:
        """
        Downloads a file from the given URL and converts it to FastAPI's UploadFile,
        with a safe filename (query params replaced with underscores).
        """
        try:
            self.__logger.info(
                "Starting conversion of recording url to UploadFile object"
            )

            # Download the file content
            response = requests.get(file_url)
            response.raise_for_status()
            file_content = io.BytesIO(response.content)

            url_path = urlparse(file_url).path
            base_name = url_path.split("/")[-1]

            query = urlparse(file_url).query
            safe_query = re.sub(r"[^a-zA-Z0-9_-]", "_", query)
            file_name = f"{base_name}_{safe_query}" if safe_query else base_name

            self.__logger.info(
                "Conversion of URL is done with file_name: {}".format(file_name)
            )

            upload_file = UploadFile(filename=file_name, file=file_content)
            upload_file.file.seek(0)
            self.__logger.info(
                "UploadFile created: filename={}, size={} bytes".format(
                    upload_file.filename, len(upload_file.file.read())
                )
            )
            upload_file.file.seek(0)

            return upload_file

        except Exception as e:
            raise RuntimeError(
                "Failed to convert URL to UploadFile: {}".format(str(e))
            ) from e

    async def store_media_to_digital_ocean(
        self, file_obj: UploadFile, partner_id: int, asset_type: str
    ) -> str:
        """Uploads media to DigitalOcean Spaces safely."""
        try:
            if not file_obj:
                self.__logger.error("No file provided, skipping upload")
                return ""

            self.__logger.info("Uploading media to DigitalOcean")

            # Generate a unique file name (keep original extension if any)
            ext = (
                file_obj.filename.split(".")[-1] if "." in file_obj.filename else "mp3"
            )
            file_name = f"{uuid.uuid4().hex}.{ext}"

            # Build safe file path
            file_path = f"{ENV.ENVIRONMENT}/{partner_id}/{ENV.SERVICE_NAME}/{asset_type}/{file_name}"

            self.__logger.info(
                "Uploading file: {} to path: {}".format(file_name, file_path)
            )

            # Perform the upload
            await StorageHelper.upload_file(file_obj, file_path)

            uploaded_url = StorageHelper.get_presigned_url(file_path)
            self.__logger.info(
                "Uploaded {} to DigitalOcean at {}".format(file_name, file_path)
            )
            self.__logger.info(
                "URl of the recording at digital ocean: {}".format(uploaded_url)
            )

            return file_path

        except Exception as e:
            self.__logger.error(
                "Unexpected error while uploading media: {}".format(str(e))
            )
            raise

    async def get_recording_url_from_path(self, file_path: str) -> str:
        """
        Generates a recording URL (valid for 24hrs) for the given file_path using Digital Asset's presigned URL.
        Raises an exception if the URL cannot be generated.
        """
        if not file_path:
            self.__logger.warning("FilePath not found for recording URL generation")
            raise BadRequestError(MISSING_FILE_PATH)

        self.__logger.info(
            "Received file_path for URL generation: {}".format(file_path)
        )
        try:
            self.__logger.debug("Starting presigned URL generation")
            # If StorageHelper.get_presigned_url is blocking, consider running in a threadpool
            do_recording_url: str = StorageHelper.get_presigned_url(file_path)
            self.__logger.info("Finished URL generation")
            self.__logger.debug("Generated recording URL: {}".format(do_recording_url))
            return do_recording_url
        except Exception as e:
            self.__logger.error(
                "Failed to generate recording URL for file_path '{}': {}".format(
                    file_path, str(e)
                )
            )
            raise
