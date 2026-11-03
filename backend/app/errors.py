"""JSON-safe validation responses without reflecting submitted credentials/data."""
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def request_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    # Pydantic can retain non-finite input in error details. Returning that input
    # breaks JSON serialization; it can also echo passwords from invalid forms.
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": item["loc"], "msg": item["msg"], "type": item["type"]}
        for item in error.errors()
    ]})
