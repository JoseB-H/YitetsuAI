import hashlib
import os
import shutil
import uuid
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from database import AuditLog, Conversation, User, get_db
from attachments.models import Attachment
from attachments.storage import MAX_BYTES, MAX_PER_CONVERSATION, safe_filename, folder
from attachments.processing import process_file
from attachments.extract import ExtractionError


def serialize(item):
    return {
        "attachment_id": str(item.id),
        "conversation_id": str(item.conversation_id),
        "filename": item.filename,
        "kind": item.kind,
        "size_bytes": item.size_bytes,
        "sha256": item.sha256,
        "metadata": item.extraction.get("metadata", {}),
        "warnings": item.extraction.get("warnings", []),
        "unit_count": len(item.extraction.get("units", [])),
        "visual_count": len(item.extraction.get("visuals", [])),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def create_router(authenticate):
    router = APIRouter(prefix="/attachments", tags=["attachments"])

    @router.post("", status_code=201)
    async def upload(
        file: UploadFile = File(...),
        conversation_id: uuid.UUID | None = Form(None),
        user: User = Depends(authenticate),
        db: AsyncSession = Depends(get_db),
    ):
        try:
            name, extension, kind = safe_filename(file.filename)
        except ValueError as exc:
            raise HTTPException(415, str(exc)) from exc
        conversation = None
        if conversation_id:
            conversation = await db.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id, Conversation.user_id == user.id
                )
            )
            if not conversation:
                raise HTTPException(404, "Conversación no encontrada")
            count = await db.scalar(
                select(func.count())
                .select_from(Attachment)
                .where(Attachment.conversation_id == conversation_id)
            )
            if count >= MAX_PER_CONVERSATION:
                raise HTTPException(409, "Máximo 20 adjuntos por conversación")
        identifier = uuid.uuid4()
        directory = folder(identifier)
        directory.mkdir(mode=0o700)
        path = directory / ("original" + extension)
        size = 0
        digest = hashlib.sha256()
        committed = False
        try:
            with path.open("xb") as target:
                os.chmod(path, 0o600)
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise HTTPException(413, "Máximo 25 MB por archivo")
                    digest.update(chunk)
                    target.write(chunk)
            if size == 0:
                raise HTTPException(422, "El archivo está vacío")
            try:
                extracted = await process_file(path, kind)
            except ExtractionError as exc:
                raise HTTPException(422, str(exc)) from exc
            if conversation is None:
                conversation = Conversation(user_id=user.id, title=name[:80])
                db.add(conversation)
                await db.flush()
            else:
                await db.execute(
                    select(Conversation)
                    .where(Conversation.id == conversation.id)
                    .with_for_update()
                )
                count = await db.scalar(
                    select(func.count())
                    .select_from(Attachment)
                    .where(Attachment.conversation_id == conversation.id)
                )
                if count >= MAX_PER_CONVERSATION:
                    raise HTTPException(409, "Máximo 20 adjuntos por conversación")
            attachment = Attachment(
                id=identifier,
                user_id=user.id,
                conversation_id=conversation.id,
                filename=name,
                media_type=(file.content_type or "application/octet-stream")[:128],
                kind=kind,
                size_bytes=size,
                sha256=digest.hexdigest(),
                extraction=extracted,
            )
            db.add(attachment)
            db.add(
                AuditLog(
                    user_id=user.id,
                    action="attach_file",
                    metadata_json={"attachment_id": str(identifier), "kind": kind},
                )
            )
            await db.commit()
            committed = True
            await db.refresh(attachment)
            return serialize(attachment)
        finally:
            await file.close()
            if not committed:
                shutil.rmtree(directory, ignore_errors=True)

    @router.get("")
    async def listing(
        conversation_id: uuid.UUID,
        user: User = Depends(authenticate),
        db: AsyncSession = Depends(get_db),
    ):
        conversation = await db.scalar(
            select(Conversation.id).where(
                Conversation.id == conversation_id, Conversation.user_id == user.id
            )
        )
        if not conversation:
            raise HTTPException(404, "Conversación no encontrada")
        items = await db.scalars(
            select(Attachment)
            .where(
                Attachment.user_id == user.id,
                Attachment.conversation_id == conversation_id,
            )
            .order_by(Attachment.created_at)
        )
        return [serialize(item) for item in items]

    async def owned(identifier, user, db):
        item = await db.scalar(
            select(Attachment).where(
                Attachment.id == identifier, Attachment.user_id == user.id
            )
        )
        if not item:
            raise HTTPException(404, "Adjunto no encontrado")
        return item

    @router.get("/{attachment_id}")
    async def details(
        attachment_id: uuid.UUID,
        user: User = Depends(authenticate),
        db: AsyncSession = Depends(get_db),
    ):
        item = await owned(attachment_id, user, db)
        return {**serialize(item), "content": item.extraction.get("units", [])}

    @router.get("/{attachment_id}/download")
    async def download(
        attachment_id: uuid.UUID,
        user: User = Depends(authenticate),
        db: AsyncSession = Depends(get_db),
    ):
        item = await owned(attachment_id, user, db)
        path = folder(item.id) / (
            "original" + __import__("pathlib").Path(item.filename).suffix.lower()
        )
        if not path.exists():
            raise HTTPException(404, "El archivo original ya no está disponible")
        return FileResponse(
            path,
            filename=item.filename,
            media_type="application/octet-stream",
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
        )

    @router.delete("/{attachment_id}", status_code=204)
    async def remove(
        attachment_id: uuid.UUID,
        user: User = Depends(authenticate),
        db: AsyncSession = Depends(get_db),
    ):
        item = await owned(attachment_id, user, db)
        identifier = item.id
        await db.delete(item)
        db.add(
            AuditLog(
                user_id=user.id,
                action="remove_attachment",
                metadata_json={"attachment_id": str(identifier)},
            )
        )
        await db.commit()
        shutil.rmtree(folder(identifier), ignore_errors=True)
        return Response(status_code=204)

    return router
