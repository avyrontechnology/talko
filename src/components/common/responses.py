import json
from typing import Any, Dict, List, Optional, Union

from fastapi import Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse


class TalkoAPIResponse(Response):
    """
    Base class for API responses. All custom response types should inherit from this.
    """

    def __init__(
        self,
        content: Any,
        status_code: int = 200,
        media_type: str = "application/json",
        headers: Optional[Dict[str, Any]] = None,
    ):
        # Use `Response` to directly define content and media type
        super().__init__(
            content=content,
            status_code=status_code,
            media_type=media_type,
            headers=headers,
        )

    @staticmethod
    def to_json(content: Dict[str, Any]) -> str:
        """
        Convert content to a JSON string.
        """
        return json.dumps(content)


class TalkoSuccessResponse(JSONResponse):
    """
    A standardized success response with a customizable message and data.
    """

    def __init__(
        self,
        data: Optional[Union[List[Any], Dict[str, Any]]] = None,
        message: str = "Request successful",
        status: str = "success",
        headers: Optional[Dict[str, Any]] = None,
    ):
        self.data = jsonable_encoder(data)
        self.message = message
        self.status = status
        super().__init__(content=None, status_code=200, headers=headers)

    def render(self, content: Any) -> bytes:
        return super().render(
            {
                "status": self.status,
                "message": self.message,
                "data": self.data,
            }
        )


class TalkoValidationErrorResponse(TalkoAPIResponse):
    """
    A response class for handling validation errors.
    """

    def __init__(
        self,
        detail: str,
        error_code: str = "VALIDATION_ERROR",
        headers: Optional[Dict[str, Any]] = None,
    ):
        content = {
            "status": "error",
            "error_code": error_code,
            "detail": detail,
        }
        super().__init__(
            content=self.to_json(content),
            status_code=400,
            media_type="application/json",
            headers=headers,
        )


class TalkoUnauthorizedResponse(TalkoAPIResponse):
    """
    A response class for handling unauthorized access errors.
    """

    def __init__(
        self,
        detail: str = "Unauthorized access",
        headers: Optional[Dict[str, Any]] = None,
    ):
        content = {
            "status": "error",
            "error_code": "UNAUTHORIZED",
            "detail": detail,
        }
        super().__init__(
            content=self.to_json(content),
            status_code=401,
            media_type="application/json",
            headers=headers,
        )


class TalkoNotFoundResponse(TalkoAPIResponse):
    """
    A response class for handling 404 Not Found errors.
    """

    def __init__(
        self,
        detail: str = "Resource not found",
        headers: Optional[Dict[str, Any]] = None,
    ):
        content = {
            "status": "error",
            "error_code": "NOT_FOUND",
            "detail": detail,
        }
        super().__init__(
            content=self.to_json(content),
            status_code=404,
            media_type="application/json",
            headers=headers,
        )


class TalkoInternalServerErrorResponse(TalkoAPIResponse):
    """
    A response class for handling 500 Internal Server Error.
    """

    def __init__(
        self,
        detail: str = "Internal server error",
        headers: Optional[Dict[str, Any]] = None,
    ):
        content = {
            "status": "error",
            "error_code": "INTERNAL_SERVER_ERROR",
            "detail": detail,
        }
        super().__init__(
            content=self.to_json(content),
            status_code=500,
            media_type="application/json",
            headers=headers,
        )


class TalkoBadRequestResponse(TalkoAPIResponse):
    """
    A response class for handling 400 Bad Request errors.
    """

    def __init__(
        self, detail: str = "Bad request", headers: Optional[Dict[str, Any]] = None
    ):
        content = {
            "status": "error",
            "error_code": "BAD_REQUEST",
            "detail": detail,
        }
        super().__init__(
            content=self.to_json(content),
            status_code=400,
            media_type="application/json",
            headers=headers,
        )


class TalkoForbiddenPermissionResponse(TalkoAPIResponse):
    """
    A response class for handling 403 Forbidden errors (Permission Denied).
    """

    def __init__(
        self,
        detail: str = "Forbidden: You do not have permission to perform this action.",
        headers: Optional[Dict[str, Any]] = None,
    ):
        content = {
            "status": "error",
            "error_code": "FORBIDDEN",
            "detail": detail,
        }
        super().__init__(
            content=self.to_json(content),
            status_code=403,
            media_type="application/json",
            headers=headers,
        )


class TalkoForbiddenResponse(TalkoAPIResponse):
    """
    A response class for handling 403 Forbidden Request errors.
    """

    def __init__(
        self,
        detail: str = "Forbidden request",
        headers: Optional[Dict[str, Any]] = None,
    ):
        content = {
            "status": "error",
            "error_code": "FORBIDDEN_REQUEST",
            "detail": detail,
        }
        super().__init__(
            content=self.to_json(content),
            status_code=403,
            media_type="application/json",
            headers=headers,
        )


class TalkoTooManyRequestsResponse(TalkoAPIResponse):
    """
    A response class for handling 429 Too Many Requests (rate limit) errors.
    """

    def __init__(
        self,
        detail: str = "Too many requests",
        headers: Optional[Dict[str, Any]] = None,
    ):
        content = {
            "status": "error",
            "error_code": "TOO_MANY_REQUESTS",
            "detail": detail,
        }
        super().__init__(
            content=self.to_json(content),
            status_code=429,
            media_type="application/json",
            headers=headers,
        )


class TalkoResourceCreatedResponse(JSONResponse):
    """
    A standardized Resource created response with a customizable message and data.
    """

    def __init__(
        self,
        data: Optional[Dict[str, Any]] = None,
        message: str = "Request successful",
        headers: Optional[Dict[str, Any]] = None,
    ):
        self.data = jsonable_encoder(data)
        self.message = message
        super().__init__(content=None, status_code=201, headers=headers)

    def render(self, content: Any) -> bytes:
        """
        Render the response content as JSON, allowing FastAPI's automatic serialization.
        """
        return super().render(
            {"status": "success", "message": self.message, "data": self.data}
        )


class TalkoSuccessNoContentResponse(TalkoAPIResponse):
    """
    A standardized success no content response with a customizable message.
    """

    def __init__(
        self,
        headers: Optional[Dict[str, Any]] = None,
    ):
        # Convert content to JSON string manually
        super().__init__(
            content=None,
            status_code=204,
            media_type="application/json",
            headers=headers,
        )


class TalkoResourceConflictResponse(TalkoAPIResponse):
    """
    A response class for handling 403 Forbidden Request errors.
    """

    def __init__(
        self,
        detail: str = "Conflict request",
        headers: Optional[Dict[str, Any]] = None,
    ):
        content = {
            "status": "error",
            "error_code": "RESOURCE_CONFLICT_REQUEST",
            "detail": detail,
        }
        super().__init__(
            content=self.to_json(content),
            status_code=409,
            media_type="application/json",
            headers=headers,
        )


class TalkoAcceptedResponse(JSONResponse):
    """
    A standardized response for 202 Accepted, used for asynchronous processing.
    """

    def __init__(
        self,
        data: Optional[Union[List[Any], Dict[str, Any]]] = None,
        message: str = "Request accepted for processing",
        headers: Optional[Dict[str, Any]] = None,
    ):
        self.data = jsonable_encoder(data)
        self.message = message
        super().__init__(content=None, status_code=202, headers=headers)

    def render(self, content: Any) -> bytes:
        """
        Render the response content as JSON.
        """
        return super().render(
            {"status": "success", "message": self.message, "data": self.data}
        )


class TalkoInvalidFileFormat(TalkoAPIResponse):
    """
    A response class for handling 500 Internal Server Error.
    """

    def __init__(
        self,
        detail: str = "Invalid File Format",
        headers: Optional[Dict[str, Any]] = None,
    ):
        content = {
            "status": "error",
            "error_code": "INVALID_FILE_FORMAT",
            "detail": detail,
        }
        super().__init__(
            content=self.to_json(content),
            status_code=400,
            media_type="application/json",
            headers=headers,
        )


class TalkoResourceNotFoundResponse(TalkoAPIResponse):
    """
    A response class for handling resource-specific 404 Not Found errors.
    """

    def __init__(
        self,
        detail: str,
        headers: Optional[Dict[str, Any]] = None,
    ):
        content = {
            "status": "error",
            "error_code": "RESOURCE_NOT_FOUND",
            "detail": f"{detail} not found",
        }
        super().__init__(
            content=self.to_json(content),
            status_code=404,
            media_type="application/json",
            headers=headers,
        )
