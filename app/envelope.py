"""The { "data": ..., "error": ... } response envelope required by the spec."""
from fastapi.responses import JSONResponse


def ok(data, status_code: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"data": data, "error": None})


def fail(message: str, status_code: int, details=None) -> JSONResponse:
    error = {"message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"data": None, "error": error})
