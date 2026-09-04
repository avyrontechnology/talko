from ..loggers.holler_service_logger import HollerServiceLogger


def validate_required_fields(
    data: dict, required_fields: list[str], logger: HollerServiceLogger
):
    """Validate that all required fields are present in the data."""
    missing_fields = [
        field for field in required_fields if field not in data or data[field] is None
    ]
    logger.info("Missing field: {}.".format(missing_fields))
    if missing_fields:
        logger.error("Missing required fields: {}".format(missing_fields))
        raise ValueError("Missing required fields: {}".format(missing_fields))
