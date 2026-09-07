import time

import cloudinary
import cloudinary.api
import cloudinary.uploader
import cloudinary.utils

from src.components.digital_assets import constants
from src.components.digital_assets.logger_adapter import TalkoLoggerAdapter
from src.components.digital_assets.messages import NO_CRED_FOUND_CLOUDINARY
from src.components.digital_assets.storage.base import TalkoBaseStorageManager
from src.core.environment import TalkoENV

logger = TalkoLoggerAdapter().get_logger()

# resource_type is per-asset in Cloudinary ("auto" upload resolves to
# image/video/raw). Lookups try each kind in order.
_RESOURCE_TYPES = ("image", "video", "raw")


class TalkoCloudinaryStorageManager(TalkoBaseStorageManager):
    """
    Storage manager for Cloudinary.

    file_path convention is unchanged from the S3-compatible managers:
    it is stored as the Cloudinary public_id under CLOUDINARY_FOLDER,
    so existing DB rows (asset URLs aside) keep working.
    """

    def __init__(self):
        cloud_name = TalkoENV.CLOUDINARY_CLOUD_NAME
        api_key = TalkoENV.CLOUDINARY_API_KEY
        api_secret = TalkoENV.CLOUDINARY_API_SECRET
        if not (cloud_name and api_key and api_secret):
            raise RuntimeError(NO_CRED_FOUND_CLOUDINARY)
        self.cloud_name = cloud_name
        self.folder = (TalkoENV.CLOUDINARY_FOLDER or "").strip().strip("/")
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True,
        )
        logger.info(
            "TalkoCloudinaryStorageManager initialized with cloud: %s", cloud_name
        )

    def _public_id(self, file_path: str) -> str:
        clean = (file_path or "").strip().lstrip("/")
        if self.folder:
            clean = "{}/{}".format(self.folder, clean)
        return clean

    def _discover_resource_type(self, public_id: str) -> str:
        """Best-effort resource_type lookup; falls back to image."""
        for resource_type in _RESOURCE_TYPES:
            try:
                cloudinary.api.resource(public_id, resource_type=resource_type)
                return resource_type
            except Exception:
                continue
        logger.warning(
            "Could not discover resource_type for %s; defaulting to image",
            public_id,
        )
        return "image"

    def get_presigned_url(self, file_path: str, view_only: bool = False) -> str:
        """
        Generates a signed, expiring delivery URL (Cloudinary's equivalent
        of an S3 presigned URL).

        Args:
            file_path: public_id path previously used at upload time.
            view_only: True renders inline; False forces download
                (attachment flag), mirroring the S3 disposition mapping.
        """
        try:
            public_id = self._public_id(file_path)
            logger.info("Generating signed URL for file: %s", file_path)
            resource_type = self._discover_resource_type(public_id)
            url, _ = cloudinary.utils.cloudinary_url(
                public_id,
                resource_type=resource_type,
                sign_url=True,
                expires_at=int(time.time()) + constants.URL_EXPIRATION_TIME,
                flags="attachment" if not view_only else None,
            )
            logger.info("Successfully generated signed URL for file: %s", file_path)
            return url
        except Exception as e:
            logger.error(
                "Failed to generate signed URL for file %s: %s", file_path, e
            )
            raise RuntimeError("Failed to generate signed URL: {}".format(e))

    async def upload_digital_asset(self, file_obj, file_path: str) -> str:
        """
        Uploads a digital asset to Cloudinary and returns its secure URL.
        """
        try:
            public_id = self._public_id(file_path)
            logger.info(
                "Uploading file '%s' to Cloudinary at public_id: %s",
                file_obj.filename,
                public_id,
            )
            result = cloudinary.uploader.upload(
                file_obj.file,
                public_id=public_id,
                resource_type="auto",
                overwrite=True,
            )
            secure_url = result.get("secure_url")
            if not secure_url:
                raise ValueError("Cloudinary upload returned no secure_url: {}".format(result))
            logger.info(
                "Successfully uploaded file '%s' to public_id: %s",
                file_obj.filename,
                public_id,
            )
            return secure_url
        except Exception as e:
            logger.error(
                "An error occurred while uploading file '%s' to path '%s': %s",
                getattr(file_obj, "filename", "?"),
                file_path,
                str(e),
            )
            raise ValueError(
                "An error occurred while uploading file '{}': {}".format(file_path, str(e))
            )

    def delete_digital_asset(self, file_path: str) -> None:
        """
        Deletes a digital asset from Cloudinary. Missing assets are treated
        as success (idempotent, same as S3 delete semantics).
        """
        public_id = self._public_id(file_path)
        logger.info("Deleting file from Cloudinary at public_id: %s", public_id)
        errors = []
        for resource_type in _RESOURCE_TYPES:
            try:
                result = cloudinary.uploader.destroy(
                    public_id, resource_type=resource_type
                )
                if result.get("result") == "ok":
                    logger.info("Successfully deleted file at path: %s", file_path)
                    return
            except Exception as e:
                errors.append("{}: {}".format(resource_type, e))
        if errors:
            logger.warning(
                "Cloudinary destroy attempts for %s had errors (treated as deleted): %s",
                file_path,
                errors,
            )
        logger.info("Delete completed for path: %s", file_path)
