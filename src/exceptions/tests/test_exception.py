import pytest
from src.exceptions import (
    BadRequestError,
    ConflictError,
    LoggerException,
    ResourceNotFound,
    InvalidAnalyticTypeError,
    PayloadValidationError,
)


def test_logger_exception_with_message():
    with pytest.raises(LoggerException) as exc:
        raise LoggerException("Logging failed.")
    assert str(exc.value) == "Logging failed."


def test_logger_exception_with_multiple_args():
    with pytest.raises(LoggerException) as exc:
        raise LoggerException("Log", "Error", 404)
    assert exc.value.args == ("Log", "Error", 404)


def test_resource_not_found_default_message():
    with pytest.raises(ResourceNotFound) as exc:
        raise ResourceNotFound()
    assert str(exc.value) == "The requested resource was not found."


def test_resource_not_found_custom_message():
    with pytest.raises(ResourceNotFound) as exc:
        raise ResourceNotFound("User not found")
    assert str(exc.value) == "User not found"


def test_conflict_error_default_message():
    with pytest.raises(ConflictError) as exc:
        raise ConflictError()
    assert str(exc.value) == "Conflict occurred with the current state of the resource."


def test_conflict_error_custom_message():
    with pytest.raises(ConflictError) as exc:
        raise ConflictError("Resource already exists")
    assert str(exc.value) == "Resource already exists"


def test_bad_request_error_default_message():
    with pytest.raises(BadRequestError) as exc:
        raise BadRequestError()
    assert str(exc.value) == "Bad request due to invalid or missing input."


def test_bad_request_error_custom_message():
    with pytest.raises(BadRequestError) as exc:
        raise BadRequestError("Missing required field: name")
    assert str(exc.value) == "Missing required field: name"


def test_invalid_analytic_type_error_default_message():
    with pytest.raises(InvalidAnalyticTypeError) as exc:
        raise InvalidAnalyticTypeError()
    assert str(exc.value) == "Invalid analytics type provided."


def test_invalid_analytic_type_error_custom_message():
    with pytest.raises(InvalidAnalyticTypeError) as exc:
        raise InvalidAnalyticTypeError("Analytics type XYZ not supported")
    assert str(exc.value) == "Analytics type XYZ not supported"


def test_payload_validation_error_default_message():
    with pytest.raises(PayloadValidationError) as exc:
        raise PayloadValidationError()
    assert str(exc.value) == "Payload validation failed due to invalid or missing fields."
    assert exc.value.example_payload is None


def test_payload_validation_error_custom_message_and_example():
    example = {"field": "value"}
    with pytest.raises(PayloadValidationError) as exc:
        raise PayloadValidationError(
            message="Invalid payload", example_payload=example
        )
    assert str(exc.value) == "Invalid payload"
    assert exc.value.example_payload == example
