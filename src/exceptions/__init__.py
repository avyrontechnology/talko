class TalkoLoggerException(Exception):
    def __init__(self, *args: object) -> None:
        super().__init__(*args)


class TalkoResourceNotFound(Exception):
    def __init__(self, message=None):
        if message is None:
            message = "The requested resource was not found."
        super().__init__(message)


class TalkoConflictError(Exception):
    def __init__(self, message=None):
        if message is None:
            message = "Conflict occurred with the current state of the resource."
        super().__init__(message)


class TalkoBadRequestError(Exception):
    def __init__(self, message=None):
        if message is None:
            message = "Bad request due to invalid or missing input."
        super().__init__(message)


class TalkoInvalidAnalyticTypeError(Exception):
    def __init__(self, message=None):
        if message is None:
            message = "Invalid analytics type provided."
        super().__init__(message)


class TalkoPayloadValidationError(Exception):
    def __init__(self, message=None, example_payload=None):
        if message is None:
            message = "Payload validation failed due to invalid or missing fields."
        self.message = message
        self.example_payload = example_payload
        super().__init__(message)


class TalkoInvalidPermissionTypeError(Exception):
    def __init__(self, message=None):
        if message is None:
            message = "Invalid permission type provided."
        super().__init__(message)

class TalkoDuplicateResourceError(Exception):
    def __init__(self, message: str = None) -> None:
        if message is None:
            message = "A resource with the same key already exists."
        super().__init__(message)

class TalkoInvalidAssetTypeError(Exception):
    def __init__(self, message=None):
        if message is None:
            message = "Invalid asset type provided."
        super().__init__(message)