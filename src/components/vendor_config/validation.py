from bson import ObjectId

from src.components.vendor.repository import TalkoVendorRepository
from src.components.vendor_config.dto import TalkoContract
from src.components.vendor_config.repository import TalkoVendorConfigRepository
from src.loggers.talko_service_logger import TalkoServiceLogger
from src.utils.common_validation import validate_required_fields


class TalkoVendorConfigValidator:
    """
    Validator class for vendor configuration operations.

    Ensures that vendors and their configurations exist or meet certain criteria
    before proceeding with create/update actions.
    """

    def __init__(
        self,
        repository: TalkoVendorRepository,
        logger: TalkoServiceLogger,
        vendor_config_repository: TalkoVendorConfigRepository,
    ):
        """
        Initialize the validator with repositories and logger.

        :param repository: Repository to access vendor data.
        :param logger: Logger for logging validation activities.
        :param vendor_config_repository: Repository to access vendor config data.
        """
        self.__repository = repository
        self.__logger = logger
        self.__vendor_config_repository = vendor_config_repository

    def validate_vendor_config_create(self, config: TalkoContract.VendorConfigCreate):
        """
        Validate required fields for creating a vendor config.

        :param config: VendorConfigCreate DTO instance.
        :raises ValueError: If any required field is missing.
        """
        required_fields = ["vendor_id"]
        validate_required_fields(config.model_dump(), required_fields, self.__logger)

    async def validate_vendor_exists(self, vendor_id: ObjectId):
        """
        Validate that a vendor exists and no config already exists for it.

        :param vendor_id: The ObjectId of the vendor.
        :raises ValueError: If the vendor doesn't exist/is inactive or config already exists.
        """
        vendor = await self.__repository.find_vendor_by_id(vendor_id)
        if not vendor or not vendor.get("is_active", False):
            self.__logger.error(
                "Vendor with ID {} not found or inactive.".format(vendor_id)
            )
            raise ValueError(
                "Vendor with ID {} not found or inactive.".format(vendor_id)
            )

    async def validate_vendor_config_exist_using_vendor_id(self, vendor_id: ObjectId):
        """
        Validate that a vendor config exists based on its Vendor ID.

        :param vendor_config_id: The ObjectId of the vendor config.
        :raises ValueError: If no vendor config exists for the given ID.
        """
        vendor_config_exists = await self.__vendor_config_repository.check_vendor_config_exists_for_existing_vendor(
            vendor_id
        )
        if vendor_config_exists:
            self.__logger.error(
                "Vendor config for vendor ID {} does exist.".format(vendor_id)
            )
            raise ValueError(
                "Vendor config for vendor ID {} does exist.".format(vendor_id)
            )

    async def validate_vendor_config_not_exist_using_vendor_id(
        self, vendor_id: ObjectId
    ):
        """
        Validate that a vendor config not exists based on its Vendor ID.

        :param vendor_config_id: The ObjectId of the vendor config.
        :raises ValueError: If no vendor config exists for the given ID.
        """
        vendor_config_exists = await self.__vendor_config_repository.check_vendor_config_exists_for_existing_vendor(
            vendor_id
        )
        if not vendor_config_exists:
            self.__logger.error(
                "Vendor config for vendor ID {} does not exist.".format(vendor_id)
            )
            raise ValueError(
                "Vendor config for vendor ID {} does not exist.".format(vendor_id)
            )

    async def validate_vendor_config_exists(self, vendor_config_id: ObjectId):
        """
        Validate that a vendor config exists based on its ID.

        :param vendor_config_id: The ObjectId of the vendor config.
        :raises ValueError: If no vendor config exists for the given ID.
        """
        vendor_config_exists = await self.__vendor_config_repository.check_vendor_config_exists_for_existing_vendor_using_pk_id(
            vendor_config_id
        )
        if not vendor_config_exists:
            self.__logger.error(
                "Vendor config for vendor config ID {} does not exist.".format(
                    vendor_config_id
                )
            )
            raise ValueError(
                "Vendor config for vendor config ID {} does not exist.".format(
                    vendor_config_id
                )
            )
