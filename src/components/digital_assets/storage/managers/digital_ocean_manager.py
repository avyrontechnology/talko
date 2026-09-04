import mimetypes

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError

from src.components.digital_assets import constants
from src.components.digital_assets.logger_adapter import TalkoLoggerAdapter
from src.components.digital_assets.messages import NO_CRED_FOUND_DO
from src.components.digital_assets.storage.base import TalkoBaseStorageManager
from src.core.environment import TalkoENV

logger = TalkoLoggerAdapter().get_logger()


class TalkoDOStorageManager(TalkoBaseStorageManager):
    """
    Storage manager for DigitalOcean Space.
    """

    def __init__(self):
        self.endpoint_url = TalkoENV.DO_ENDPOINT_URL
        self.space_name = TalkoENV.DO_SPACE_NAME
        self.secret_access_key = TalkoENV.DO_SECRET_ACCESS_KEY
        self.access_key_id = TalkoENV.DO_ACCESS_KEY_ID
        self.env = TalkoENV.ENVIRONMENT

        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            endpoint_url=self.endpoint_url,
            config=Config(signature_version="s3v4"),
        )
        logger.info("TalkoDOStorageManager initialized with endpoint: %s", self.endpoint_url)

    def get_presigned_url(self, file_path: str, view_only: bool = False) -> str:
        """
        Generates a presigned URL for accessing a file stored in DigitalOcean Spaces.

        Args:
            file_path (str): The name of the file for which to generate the presigned URL.
            view_only (bool): Whether to set the content disposition to 'inline' (True) or 'attachment' (False).
                        Default is True for in-browser viewing.

        Returns:
            str: The presigned URL for accessing the file.

        Raises:
            RuntimeError: If credentials are missing or the URL generation fails.
        """
        try:
            logger.info("Generating presigned URL for file: %s", file_path)
            content_disposition = "inline" if view_only else "attachment"
            presigned_url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.space_name,
                    "Key": file_path,
                    "ResponseContentDisposition": content_disposition,
                },
                ExpiresIn=constants.URL_EXPIRATION_TIME,
            )
            logger.info("Successfully generated presigned URL for file: %s", file_path)
            return presigned_url

        except NoCredentialsError:
            logger.error(NO_CRED_FOUND_DO)
            raise RuntimeError(NO_CRED_FOUND_DO)

        except ClientError as e:
            logger.error(
                "Failed to generate presigned URL for file %s: %s", file_path, e
            )
            raise RuntimeError(f"Failed to generate presigned URL: {e}")

    async def upload_digital_asset(self, file_obj, file_path: str) -> str:
        """
        Uploads a digital asset (file) to an S3-compatible storage service.

        Args:
            file_obj (file-like object): The file object to upload.
            file_path (str): The path where the file will be stored in the DigitalOcean Space.

        Returns:
            str: The URL of the uploaded file in the S3-compatible storage service.

        Raises:
            ValueError: If the upload fails.
            Exception: If there are issues with the S3 client or the upload process.
        """
        try:
            logger.info(
                "Uploading file '%s' to DigitalOcean Space at path: %s",
                file_obj.filename,
                file_path,
            )
            content_type, _ = mimetypes.guess_type(file_obj.filename)
            content_type = content_type or "application/octet-stream"

            self.s3_client.upload_fileobj(
                file_obj.file,
                self.space_name,
                file_path,
                ExtraArgs={"ContentType": content_type},
            )
            logger.info(
                "Successfully uploaded file '%s' to path: %s",
                file_obj.filename,
                file_path,
            )
            presigned_url = self.get_presigned_url(file_path)

            return presigned_url

        except ClientError as e:
            logger.error(
                "Failed to upload file '%s' to path '%s': %s",
                file_path,
                file_obj.filename,
                e.response["Error"]["Message"],
            )
            raise ValueError(
                f"Failed to upload file '{file_path}': {e.response['Error']['Message']}"
            )
        except Exception as e:
            logger.error(
                "An error occurred while uploading file '%s' to path '%s': %s",
                file_obj.filename,
                file_path,
                str(e),
            )
            raise ValueError(
                f"An error occurred while uploading file '{file_path}': {str(e)}"
            )

    def delete_digital_asset(self, file_path: str) -> None:
        """
        Deletes a digital asset (file) from DigitalOcean Spaces.

        Args:
            file_path (str): The path of the file to delete in the DigitalOcean Space.

        Raises:
            RuntimeError: If credentials are missing or the deletion fails.
        """
        try:
            logger.info("Deleting file from DigitalOcean Space at path: %s", file_path)
            self.s3_client.delete_object(Bucket=self.space_name, Key=file_path)
            logger.info("Successfully deleted file at path: %s", file_path)

        except NoCredentialsError:
            logger.error(NO_CRED_FOUND_DO)
            raise RuntimeError(NO_CRED_FOUND_DO)

        except ClientError as e:
            logger.error("Failed to delete file at path %s: %s", file_path, e)
            raise RuntimeError(f"Failed to delete file '{file_path}': {e}")
