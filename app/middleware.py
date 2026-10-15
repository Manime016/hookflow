import os

from starlette.responses import JSONResponse


class RequestSizeLimitMiddleware:
    def __init__(self, app, maximum_bytes: int | None = None):
        self.app = app
        self.maximum_bytes = maximum_bytes or int(os.getenv("MAX_REQUEST_BYTES", "1048576"))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        chunks = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > self.maximum_bytes:
                response = JSONResponse(status_code=413, content={"detail": "Request body is too large"})
                await response(scope, receive, send)
                return
            chunks.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            if chunks:
                return chunks.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        scope.setdefault("state", {})["raw_body"] = b"".join(
            chunk.get("body", b"") for chunk in chunks
        )
        await self.app(scope, replay, send)
