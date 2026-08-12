from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(HTTPException):
    """Every error the API returns has the same shape:

        {"error": {"code": "ITEM_NOT_FOUND", "message": "...", "details": {...}}}

    so the frontend has one place to handle failures.
    """

    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.message = message
        self.details = details or {}


def bad_request(code: str, message: str, **details) -> ApiError:
    return ApiError(status.HTTP_400_BAD_REQUEST, code, message, details)


def unauthorized(code: str = "UNAUTHORIZED", message: str = "Wymagane zalogowanie.") -> ApiError:
    return ApiError(status.HTTP_401_UNAUTHORIZED, code, message)


def forbidden(code: str, message: str, **details) -> ApiError:
    return ApiError(status.HTTP_403_FORBIDDEN, code, message, details)


def not_found(code: str, message: str, **details) -> ApiError:
    return ApiError(status.HTTP_404_NOT_FOUND, code, message, details)


def conflict(code: str, message: str, **details) -> ApiError:
    return ApiError(status.HTTP_409_CONFLICT, code, message, details)


def unprocessable(code: str, message: str, **details) -> ApiError:
    return ApiError(status.HTTP_422_UNPROCESSABLE_ENTITY, code, message, details)


def too_many(code: str, message: str, **details) -> ApiError:
    return ApiError(status.HTTP_429_TOO_MANY_REQUESTS, code, message, details)


def _body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status_code, content=_body(exc.code, exc.message, exc.details))

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException):
        code = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(
            exc.status_code, "HTTP_ERROR"
        )
        return JSONResponse(status_code=exc.status_code, content=_body(code, str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_body("VALIDATION_ERROR", "Nieprawidłowe dane wejściowe.", {"fields": exc.errors()}),
        )
