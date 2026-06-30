from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

PROBLEM_MEDIA_TYPE = "application/problem+json"


class ProblemException(Exception):
    def __init__(self, status: int, title: str, detail: str | None = None) -> None:
        self.status = status
        self.title = title
        self.detail = detail


def _problem(status: int, title: str, detail: str | None, request: Request) -> JSONResponse:
    body: dict[str, object] = {"type": "about:blank", "title": title, "status": status}
    if detail:
        body["detail"] = detail
    rid = getattr(request.state, "request_id", None)
    if rid:
        body["instance"] = rid
    return JSONResponse(status_code=status, content=body, media_type=PROBLEM_MEDIA_TYPE)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ProblemException)
    async def _problem_handler(request: Request, exc: ProblemException) -> JSONResponse:
        return _problem(exc.status, exc.title, exc.detail, request)

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        title = exc.detail if isinstance(exc.detail, str) else "HTTP Error"
        return _problem(exc.status_code, title, None, request)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(422, "Validation Error", str(exc.errors()), request)
