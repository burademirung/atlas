import uuid
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

RequestIdHeader = "X-Request-ID"


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get(RequestIdHeader) or uuid.uuid4().hex
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers[RequestIdHeader] = request_id
    return response
