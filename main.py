from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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

PASSWORD_HASH_ITERATIONS = 600_000
SESSION_DURATION = timedelta(days=30)
ETHICAL_BLOCKLIST = ["automate", "eliminate jobs", "replace workers"]
CRITICAL_HINTS = ["however", "but", "alternatively"]


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
    yield
    await engine.dispose()


app = FastAPI(
    title="YitetsuAI",
    version="0.2.0",
    description="Ethical AI assistant MVP with persistent conversation history.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
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


class ConversationCreateRequest(BaseModel):
    title: str = Field(default="Nueva conversación", min_length=1, max_length=255)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_HASH_ITERATIONS)
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


def validate_response(response: str) -> tuple[bool, Optional[str]]:
    lowered = response.lower()

    if any(pattern in lowered for pattern in ETHICAL_BLOCKLIST):
        return False, "Blocked: the response suggests replacing or eliminating human work."
    if not any(hint in lowered for hint in CRITICAL_HINTS):
        return False, "The response must include critical reasoning with however/but/alternatively."
    if "limitations" not in lowered and "uncertainty" not in lowered:
        return False, "The response must acknowledge limitations or uncertainty."
    if "source" not in lowered and "evidence" not in lowered:
        return False, "The response should cite evidence or a source for transparency."
    return True, None


def build_ai_response(prompt: str) -> str:
    return (
        f"Here is a practical approach for '{prompt}': start with a small pilot, document the workflow, and keep human review in the loop; however, "
        "this approach may require more setup time and governance. "
        "Alternatively, an incremental rollout can reduce adoption risk while preserving the team's judgment. "
        "The recommendation is grounded in general AI implementation principles and public source material, but it has limitations because local context, data quality, and regulatory requirements can change the answer."
    )


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
    result = await db.execute(select(User).where(User.email == payload.email.strip().lower()))
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
    await db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token.strip())))
    await record_audit(db, "logout_user", user.id)
    await db.commit()
    return {"status": "ok"}


@app.get("/conversations")
async def list_conversations(user: CurrentUser, db: DbSession) -> list[dict[str, object]]:
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
            "created_at": conversation.created_at.isoformat() if conversation.created_at else None,
            "updated_at": conversation.updated_at.isoformat() if conversation.updated_at else None,
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
) -> list[dict[str, str | int]]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == user.id)
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
            "created_at": message.created_at.isoformat() if message.created_at else "",
        }
        for message in messages.scalars().all()
    ]
    await record_audit(db, "read_conversation", user.id, {"conversation_id": str(conversation_id)})
    await db.commit()
    return response_messages


@app.post("/chat")
async def chat(
    payload: ChatRequest,
    db: DbSession,
    user: User | None = Depends(authenticate),
) -> dict[str, object]:
    response_text = build_ai_response(payload.prompt)
    valid, reason = validate_response(response_text)
    if not valid:
        raise HTTPException(status_code=400, detail=reason)

    messages: list[dict[str, str]] = [
        {"role": "user", "content": payload.prompt},
        {"role": "assistant", "content": response_text},
    ]
    conversation_id: str | None = None

    if user is not None:
        conversation: Conversation | None = None
        if payload.conversation_id is not None:
            result = await db.execute(
                select(Conversation).where(
                    Conversation.id == payload.conversation_id,
                    Conversation.user_id == user.id,
                ).with_for_update()
            )
            conversation = result.scalar_one_or_none()
            if conversation is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
        else:
            conversation = Conversation(
                user_id=user.id,
                title=payload.prompt.strip()[:80],
            )
            db.add(conversation)
            await db.flush()

        current_sequence_result = await db.execute(
            select(func.coalesce(func.max(ConversationMessage.sequence_number), 0)).where(
                ConversationMessage.conversation_id == conversation.id
            )
        )
        next_sequence = current_sequence_result.scalar_one() + 1
        conversation_id = str(conversation.id)
        if conversation.title == "Nueva conversación":
            conversation.title = payload.prompt.strip()[:80]
        conversation.updated_at = datetime.now(timezone.utc)
        db.add_all(
            [
                ConversationMessage(
                    conversation_id=conversation.id,
                    sequence_number=next_sequence,
                    role="user",
                    content=payload.prompt,
                ),
                ConversationMessage(
                    conversation_id=conversation.id,
                    sequence_number=next_sequence + 1,
                    role="assistant",
                    content=response_text,
                ),
            ]
        )
        await record_audit(
            db,
            "chat_request",
            user.id,
            {"conversation_id": conversation_id},
        )
        await db.commit()
    else:
        await record_audit(db, "guest_chat_request")
        await db.commit()

    return {
        "response": response_text,
        "validated": True,
        "conversation_id": conversation_id,
        "messages": messages,
    }
