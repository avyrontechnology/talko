from ..loggers.talko_service_logger import TalkoServiceLogger


def validate_required_fields(data: dict, required_fields: list[str], logger: TalkoServiceLogger):
    """Validate that all required fields are present in the data."""
    missing_fields = [field for field in required_fields if field not in data or data[field] is None]
    logger.info(f"Missing field: {missing_fields}.")
    if missing_fields:
        logger.error(f"Missing required fields: {missing_fields}")
        raise ValueError(f"Missing required fields: {missing_fields}")
