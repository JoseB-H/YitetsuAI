from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from attachments.models import Attachment
from attachments.limits import RequestSizeLimit
from attachments.routes import create_router as create_attachment_router
from llm import ChatEngine, ModelUnavailable, get_chat_engine
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ai_models import CAPABILITIES, list_capabilities
from database import (
    AuditLog,
    Base,
    Conversation,
    ConversationMessage,
    SessionLocal,
    User,
    UserSession,
    engine,
    get_db,
)
from interpretation import interpret_prompt

PASSWORD_HASH_ITERATIONS = 600_000
SESSION_DURATION = timedelta(days=30)


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        if connection.dialect.name == "postgresql":
            await connection.execute(
                text(
                    "ALTER TABLE conversations "
                    "ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                )
            )
        if connection.dialect.name == "postgresql":
            await connection.execute(
                text(
                    "ALTER TABLE conversation_messages ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'"
                )
            )
    app.state.chat_engine = ChatEngine()
    try:
        yield
    finally:
        await app.state.chat_engine.close()
        await engine.dispose()


app = FastAPI(
    title="YitetsuAI",
    version="0.3.0",
    description="Asistente con conversaciones persistentes y adjuntos multimodales privados.",
    lifespan=lifespan,
)

app.add_middleware(RequestSizeLimit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=255)


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=10_000)
    conversation_id: Optional[uuid.UUID] = None
    attachment_ids: list[uuid.UUID] | None = Field(default=None, max_length=20)


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="Nueva conversación", min_length=1, max_length=255)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt, PASSWORD_HASH_ITERATIONS
    )
    return f"pbkdf2_sha256${PASSWORD_HASH_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored_hash.split("$", maxsplit=3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def greeting_response(prompt: str) -> str | None:
    normalized_prompt = "".join(
        character
        for character in unicodedata.normalize("NFD", prompt.lower())
        if unicodedata.category(character) != "Mn"
    )
    normalized_prompt = re.sub(r"[¿?¡!.,;:]+", " ", normalized_prompt)
    normalized_prompt = " ".join(normalized_prompt.split())

    asks_name = any(
        re.search(pattern, normalized_prompt)
        for pattern in (
            r"\bcomo te llamas\b",
            r"\bcual es tu nombre\b",
            r"\bquien eres\b",
            r"\bcomo te puedo llamar\b",
        )
    )
    is_greeting = bool(
        re.match(
            r"^(hola|holi|buenos dias|buenas tardes|buenas noches|hey|hi|hello)\b",
            normalized_prompt,
        )
    )

    if asks_name:
        return "¡Hola! Soy YitetsuAI, un asistente de IA. Puedes llamarme Yitetsu. ¿En qué puedo ayudarte hoy?"
    if is_greeting and len(normalized_prompt.split()) <= 5:
        return "¡Hola! Soy YitetsuAI. ¿En qué puedo ayudarte hoy?"

    return None


async def record_audit(
    db: AsyncSession,
    action: str,
    user_id: uuid.UUID | None = None,
    metadata: dict[str, str] | None = None,
) -> None:
    db.add(AuditLog(user_id=user_id, action=action, metadata_json=metadata))


async def authenticate(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    if not authorization:
        return None
    scheme, separator, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not token.strip():
        raise HTTPException(status_code=401, detail="Invalid bearer token")

    result = await db.execute(
        select(User, UserSession)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == hash_token(token.strip()),
            UserSession.expires_at > datetime.now(timezone.utc),
        )
    )
    user_and_session = result.first()
    if user_and_session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_and_session[0]


async def require_user(user: User | None = Depends(authenticate)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(require_user)]


def user_response(user: User) -> dict[str, str]:
    return {
        "user_id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
    }


@app.get("/health")
async def health() -> dict[str, str]:
    async with SessionLocal() as db:
        await db.execute(select(1))
    return {"status": "ok", "service": "yitetsuai"}


@app.get("/ai/capabilities")
async def ai_capabilities() -> dict[str, object]:
    return {
        "count": len(CAPABILITIES),
        "components": list_capabilities(),
        "note": "Son componentes especializados del pipeline, no diez LLM descargados.",
    }


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register_user(payload: RegisterRequest, db: DbSession) -> dict[str, str]:
    user = User(
        email=payload.email.strip().lower(),
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
    )
    token = secrets.token_urlsafe(32)
    db.add(user)
    try:
        await db.flush()
        db.add(
            UserSession(
                token_hash=hash_token(token),
                user_id=user.id,
                expires_at=datetime.now(timezone.utc) + SESSION_DURATION,
            )
        )
        await record_audit(db, "register_user", user.id, {"email": user.email})
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="User already exists") from error

    return {**user_response(user), "token": token}


@app.post("/auth/login")
async def login_user(payload: LoginRequest, db: DbSession) -> dict[str, str]:
    result = await db.execute(
        select(User).where(User.email == payload.email.strip().lower())
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            token_hash=hash_token(token),
            user_id=user.id,
            expires_at=datetime.now(timezone.utc) + SESSION_DURATION,
        )
    )
    await record_audit(db, "login_user", user.id)
    await db.commit()
    return {**user_response(user), "token": token}


@app.get("/users/me")
async def get_current_user(user: CurrentUser, db: DbSession) -> dict[str, str]:
    await record_audit(db, "get_current_user", user.id)
    await db.commit()
    return user_response(user)


@app.post("/auth/logout")
async def logout_user(
    authorization: Annotated[str, Header()],
    user: CurrentUser,
    db: DbSession,
) -> dict[str, str]:
    _, _, token = authorization.partition(" ")
    await db.execute(
        delete(UserSession).where(UserSession.token_hash == hash_token(token.strip()))
    )
    await record_audit(db, "logout_user", user.id)
    await db.commit()
    return {"status": "ok"}


@app.get("/conversations")
async def list_conversations(
    user: CurrentUser, db: DbSession
) -> list[dict[str, object]]:
    message_count = (
        select(func.count(ConversationMessage.id))
        .where(ConversationMessage.conversation_id == Conversation.id)
        .correlate(Conversation)
        .scalar_subquery()
    )
    result = await db.execute(
        select(Conversation, message_count)
        .where(Conversation.user_id == user.id)
        .order_by(desc(Conversation.updated_at), desc(Conversation.created_at))
    )
    conversations = [
        {
            "conversation_id": str(conversation.id),
            "title": conversation.title,
            "created_at": conversation.created_at.isoformat()
            if conversation.created_at
            else None,
            "updated_at": conversation.updated_at.isoformat()
            if conversation.updated_at
            else None,
            "message_count": count,
        }
        for conversation, count in result.all()
    ]
    await record_audit(db, "list_conversations", user.id)
    await db.commit()
    return conversations


@app.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreateRequest,
    user: CurrentUser,
    db: DbSession,
) -> dict[str, str]:
    conversation = Conversation(user_id=user.id, title=payload.title.strip())
    db.add(conversation)
    await record_audit(db, "create_conversation", user.id)
    await db.commit()
    await db.refresh(conversation)
    return {
        "conversation_id": str(conversation.id),
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
    }


@app.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> list[dict[str, object]]:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user.id
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.sequence_number)
    )
    response_messages = [
        {
            "message_id": str(message.id),
            "sequence_number": message.sequence_number,
            "role": message.role,
            "content": message.content,
            "sources": message.sources,
            "created_at": message.created_at.isoformat() if message.created_at else "",
        }
        for message in messages.scalars().all()
    ]
    await record_audit(
        db, "read_conversation", user.id, {"conversation_id": str(conversation_id)}
    )
    await db.commit()
    return response_messages


@app.exception_handler(ModelUnavailable)
async def model_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


app.include_router(create_attachment_router(require_user))


@app.post("/chat")
async def chat(
    payload: ChatRequest,
    db: DbSession,
    user: User | None = Depends(authenticate),
    chat_engine: ChatEngine = Depends(get_chat_engine),
) -> dict[str, object]:
    if not payload.prompt.strip():
        raise HTTPException(422, "La pregunta no puede estar vacía")
    if user is None and (payload.attachment_ids or payload.conversation_id):
        raise HTTPException(
            401, "Inicia sesión para utilizar conversaciones y adjuntos"
        )
    conversation = None
    history = []
    items = []
    if user is not None:
        if payload.conversation_id is not None:
            conversation = await db.scalar(
                select(Conversation)
                .where(
                    Conversation.id == payload.conversation_id,
                    Conversation.user_id == user.id,
                )
                .with_for_update()
            )
            if conversation is None:
                raise HTTPException(404, "Conversation not found")
            history = list(
                await db.scalars(
                    select(ConversationMessage)
                    .where(ConversationMessage.conversation_id == conversation.id)
                    .order_by(ConversationMessage.sequence_number.desc())
                    .limit(10)
                )
            )
            history.reverse()
            statement = (
                select(Attachment)
                .where(
                    Attachment.user_id == user.id,
                    Attachment.conversation_id == conversation.id,
                )
                .order_by(Attachment.created_at)
            )
            if payload.attachment_ids is not None:
                statement = statement.where(Attachment.id.in_(payload.attachment_ids))
            items = list(await db.scalars(statement))
            if payload.attachment_ids is not None and len(items) != len(
                set(payload.attachment_ids)
            ):
                raise HTTPException(
                    404, "Uno de los adjuntos no pertenece a esta conversación"
                )
        elif payload.attachment_ids:
            raise HTTPException(
                422, "Selecciona la conversación que contiene los adjuntos"
            )
    if sum(len(item.extraction.get("visuals", [])) for item in items) > 8:
        raise HTTPException(
            422,
            "Selecciona menos imágenes o videos: máximo ocho observaciones visuales por pregunta",
        )
    interpretation = interpret_prompt(payload.prompt)
    greeting = greeting_response(interpretation.interpreted) if not items else None
    if greeting:
        result = {
            "response": greeting,
            "sources": [],
            "warnings": [],
            "model": "greeting",
            "vision_model": None,
        }
    else:
        result = await chat_engine.answer(
            interpretation.interpreted.strip(), history, items
        )
    response_text = result["response"]
    messages = [
        {"role": "user", "content": payload.prompt, "sources": []},
        {"role": "assistant", "content": response_text, "sources": result["sources"]},
    ]
    conversation_id = None
    if user is not None:
        if conversation is None:
            conversation = Conversation(
                user_id=user.id, title=payload.prompt.strip()[:80]
            )
            db.add(conversation)
            await db.flush()
        current_sequence = await db.scalar(
            select(
                func.coalesce(func.max(ConversationMessage.sequence_number), 0)
            ).where(ConversationMessage.conversation_id == conversation.id)
        )
        next_sequence = current_sequence + 1
        if conversation.title == "Nueva conversación":
            conversation.title = payload.prompt.strip()[:80]
        conversation.updated_at = datetime.now(timezone.utc)
        conversation_id = str(conversation.id)
        db.add_all(
            [
                ConversationMessage(
                    conversation_id=conversation.id,
                    sequence_number=next_sequence,
                    role="user",
                    content=payload.prompt,
                    sources=[],
                ),
                ConversationMessage(
                    conversation_id=conversation.id,
                    sequence_number=next_sequence + 1,
                    role="assistant",
                    content=response_text,
                    sources=result["sources"],
                ),
            ]
        )
        await record_audit(
            db,
            "chat_request",
            user.id,
            {"conversation_id": conversation_id, "attachment_count": str(len(items))},
        )
    else:
        await record_audit(db, "guest_chat_request")
    await db.commit()
    return {
        **result,
        "interpreted_prompt": interpretation.interpreted,
        "corrections": [
            {"original": original, "corrected": corrected}
            for original, corrected in interpretation.corrections
        ],
        "conversation_id": conversation_id,
        "messages": messages,
        "limitations": [
            "La IA, OCR y transcripción pueden equivocarse. Verifica datos y decisiones importantes."
        ],
    }
