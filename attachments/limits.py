"""Bound incoming requests before multipart parsing writes unlimited temporary files."""

from fastapi import HTTPException
from fastapi.responses import JSONResponse


class RequestSizeLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = 26 * 1024 * 1024 if scope["path"] == "/attachments" else 256 * 1024
        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            declared = 0
        if declared > limit:
            return await JSONResponse(
                {"detail": "Solicitud demasiado grande"}, status_code=413
            )(scope, receive, send)
        used = 0

        async def bounded_receive():
            nonlocal used
            message = await receive()
            used += len(message.get("body", b""))
            if used > limit:
                raise HTTPException(413, "Solicitud demasiado grande")
            return message

        await self.app(scope, bounded_receive, send)
