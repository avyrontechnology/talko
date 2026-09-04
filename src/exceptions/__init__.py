class LoggerException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class ResourceNotFound(Exception):
    def __init__(self, message=None):
        if message is None:
            message = "The requested resource was not found."
        super().__init__(message)


class ConflictError(Exception):
    def __init__(self, message=None):
        if message is None:
            message = "Conflict occurred with the current state of the resource."
        super().__init__(message)


class BadRequestError(Exception):
    def __init__(self, message=None):
        if message is None:
            message = "Bad request due to invalid or missing input."
        super().__init__(message)


class InvalidAnalyticTypeError(Exception):
    def __init__(self, message=None):
        if message is None:
            message = "Invalid analytics type provided."
        super().__init__(message)


class PayloadValidationError(Exception):
    def __init__(self, message=None, example_payload=None):
        if message is None:
            message = "Payload validation failed due to invalid or missing fields."
        self.message = message
        self.example_payload = example_payload
        super().__init__(message)


class InvalidPermissionTypeError(Exception):
    def __init__(self, message=None):
        if message is None:
            message = "Invalid permission type provided."
        super().__init__(message)

class DuplicateResourceError(Exception):
    def __init__(self, message: str = None) -> None:
        if message is None:
            message = "A resource with the same key already exists."
        super().__init__(message)

class InvalidAssetTypeError(Exception):
    def __init__(self, message=None):
        if message is None:
            message = "Invalid asset type provided."
        super().__init__(message)