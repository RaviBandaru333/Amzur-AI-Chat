"""Thread + message persistence and DB-backed chat orchestration."""
import base64
from pathlib import Path
import uuid

import httpx
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.llm import get_llm_client, tracking_kwargs
from app.core.config import settings
from app.models import ChatMessageRow, ChatThread, User


def _model_type(model_id: str) -> str:
    """Classify model usage so non-chat models use the correct API route."""
    lowered = model_id.lower()
    if "embedding" in lowered:
        return "embedding"
    if "imagen" in lowered or "/image" in lowered or "image-" in lowered:
        return "image"
    return "chat"


def _tracking_without_user(test_type: str) -> dict:
    """Use explicit end-user email while preserving LiteLLM metadata headers/body."""
    return {k: v for k, v in tracking_kwargs(test_type).items() if k != "user"}


def _uploads_dir() -> Path:
    path = Path(settings.UPLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extension_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return "png"
    ctype = content_type.lower()
    if "jpeg" in ctype or "jpg" in ctype:
        return "jpg"
    if "webp" in ctype:
        return "webp"
    if "gif" in ctype:
        return "gif"
    return "png"


def _save_generated_image(image_bytes: bytes, ext: str = "png") -> str:
    filename = f"gen_{uuid.uuid4().hex}.{ext}"
    path = _uploads_dir() / filename
    path.write_bytes(image_bytes)
    return f"{settings.BACKEND_PUBLIC_URL.rstrip('/')}/uploads/{filename}"


def _decode_b64_image(b64_value: str) -> bytes | None:
    if not b64_value:
        return None
    payload = b64_value.split(",", 1)[1] if "," in b64_value else b64_value
    try:
        return base64.b64decode(payload)
    except Exception:
        return None


def _value_from_item(item, key: str):
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _generate_assistant_reply(
    *,
    client,
    llm_model: str,
    user_email: str,
    history: list[dict[str, str]],
    prompt: str,
) -> str:
    """Generate assistant output for chat, image, or embedding models."""
    mtype = _model_type(llm_model)

    if mtype == "chat":
        resp = client.chat.completions.create(
            model=llm_model,
            messages=history,
            max_tokens=1200,
            temperature=0.7,
            user=user_email,
            **_tracking_without_user("chat"),
        )
        return resp.choices[0].message.content or ""

    if mtype == "image":
        img_resp = client.images.generate(
            model=llm_model,
            prompt=prompt,
            user=user_email,
            **_tracking_without_user("image"),
        )
        first = img_resp.data[0] if img_resp.data else None
        if not first:
            return f"Image generation failed: no data returned by {llm_model}"

        # Some providers return base64 image content.
        b64_image = _value_from_item(first, "b64_json")
        image_bytes = _decode_b64_image(b64_image) if b64_image else None
        if image_bytes:
            local_url = _save_generated_image(image_bytes, "png")
            return (
                f"Generated image using {llm_model}.\n\n"
                f"![Generated image]({local_url})\n\n"
                f"[Open image]({local_url})"
            )

        # Some providers return a URL; fetch and store locally for reliable rendering.
        image_url = _value_from_item(first, "url")
        if image_url:
            try:
                with httpx.Client(timeout=30.0, follow_redirects=True) as http_client:
                    fetched = http_client.get(image_url)
                    fetched.raise_for_status()
                ext = _extension_from_content_type(fetched.headers.get("content-type"))
                local_url = _save_generated_image(fetched.content, ext)
                return (
                    f"Generated image using {llm_model}.\n\n"
                    f"![Generated image]({local_url})\n\n"
                    f"[Open image]({local_url})"
                )
            except Exception:
                # Fallback to direct provider URL if proxy-download fails.
                return (
                    f"Generated image using {llm_model}.\n\n"
                    f"![Generated image]({image_url})\n\n"
                    f"[Open image]({image_url})"
                )

        return (
            f"Image generation completed using {llm_model}, but no displayable image payload was returned."
        )

    emb_resp = client.embeddings.create(
        model=llm_model,
        input=prompt,
        user=user_email,
        **_tracking_without_user("embedding"),
    )
    vector = emb_resp.data[0].embedding if emb_resp.data else []
    dims = len(vector)
    preview = ", ".join(f"{v:.4f}" for v in vector[:8])
    ellipsis = ", ..." if dims > 8 else ""
    return (
        f"Generated embedding using {llm_model}.\n\n"
        f"Vector dimensions: {dims}\n"
        f"Preview: [{preview}{ellipsis}]"
    )


async def list_threads(db: AsyncSession, user: User) -> list[ChatThread]:
    res = await db.execute(
        select(ChatThread)
        .where(ChatThread.user_id == user.id)
        .order_by(ChatThread.updated_at.desc())
    )
    return list(res.scalars().all())


async def get_thread(db: AsyncSession, user: User, thread_id: uuid.UUID) -> ChatThread:
    res = await db.execute(
        select(ChatThread)
        .where(ChatThread.id == thread_id, ChatThread.user_id == user.id)
        .options(selectinload(ChatThread.messages))
    )
    thread = res.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


async def create_thread(
    db: AsyncSession, user: User, title: str | None = None
) -> ChatThread:
    thread = ChatThread(user_id=user.id, title=title or "New chat")
    db.add(thread)
    await db.commit()
    await db.refresh(thread)
    return thread


async def rename_thread(
    db: AsyncSession, user: User, thread_id: uuid.UUID, title: str
) -> ChatThread:
    thread = await get_thread(db, user, thread_id)
    thread.title = title.strip()[:200] or thread.title
    await db.commit()
    await db.refresh(thread)
    return thread


async def delete_thread(db: AsyncSession, user: User, thread_id: uuid.UUID) -> None:
    thread = await get_thread(db, user, thread_id)
    await db.delete(thread)
    await db.commit()


async def _save_message(
    db: AsyncSession, thread: ChatThread, role: str, content: str
) -> ChatMessageRow:
    msg = ChatMessageRow(thread_id=thread.id, role=role, content=content)
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


def _generate_title(user_message: str, model: str | None = None) -> str:
    """Ask the LLM for a short, descriptive thread title."""
    client = get_llm_client()
    llm_model = model or settings.LLM_MODEL
    try:
        resp = client.chat.completions.create(
            model=llm_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Generate a very short title (max 6 words, no quotes, "
                        "no trailing punctuation) summarising the user's first message."
                    ),
                },
                {"role": "user", "content": user_message[:1000]},
            ],
            max_tokens=24,
            temperature=0.3,
            **tracking_kwargs("thread_title"),
        )
        title = (resp.choices[0].message.content or "").strip().strip("\"'.") or "New chat"
        return title[:80]
    except Exception:
        # Fallback to a deterministic title slice if the LLM call fails.
        return user_message.strip().split("\n", 1)[0][:60] or "New chat"


async def send_message(
    db: AsyncSession,
    user: User,
    thread_id: uuid.UUID,
    content: str,
    model: str | None = None,
) -> tuple[ChatThread, ChatMessageRow, ChatMessageRow]:
    """Persist user message, call LLM with full history, persist assistant reply."""
    thread = await get_thread(db, user, thread_id)
    is_first = len(thread.messages) == 0

    user_msg = await _save_message(db, thread, "user", content)

    history = [{"role": m.role, "content": m.content} for m in thread.messages]
    history.append({"role": "user", "content": content})

    client = get_llm_client()
    llm_model = model or settings.LLM_MODEL
    try:
        reply = _generate_assistant_reply(
            client=client,
            llm_model=llm_model,
            user_email=user.email,
            history=history,
            prompt=content,
        )
    except Exception as exc:
        reply = (
            f"Model '{llm_model}' could not complete this request. "
            f"Details: {exc}"
        )

    assistant_msg = await _save_message(db, thread, "assistant", reply)

    if is_first:
        thread.title = _generate_title(content, model)
        await db.commit()
        await db.refresh(thread)

    return thread, user_msg, assistant_msg


async def edit_message(
    db: AsyncSession,
    user: User,
    thread_id: uuid.UUID,
    message_id: uuid.UUID,
    new_content: str,
    model: str | None = None,
) -> ChatThread:
    """Edit a user message, delete all messages after it, and regenerate assistant responses."""
    thread = await get_thread(db, user, thread_id)

    # Find the message to edit
    msg_res = await db.execute(
        select(ChatMessageRow).where(ChatMessageRow.id == message_id)
    )
    message = msg_res.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    # Verify it's a user message (only allow editing user messages)
    if message.role != "user":
        raise HTTPException(
            status_code=400, detail="Can only edit user messages, not assistant responses"
        )

    # Verify message belongs to this thread
    if message.thread_id != thread.id:
        raise HTTPException(status_code=404, detail="Message not found in this thread")

    # Find the index of the message in the thread
    msg_index = next(
        (i for i, m in enumerate(thread.messages) if m.id == message_id), None
    )
    if msg_index is None:
        raise HTTPException(status_code=404, detail="Message not found in thread")

    # Delete all messages after this one
    messages_to_delete = thread.messages[msg_index + 1 :]
    for m in messages_to_delete:
        await db.delete(m)

    # Update the message content
    message.content = new_content.strip()
    await db.commit()

    # Rebuild history up to and including the edited message
    history = [
        {"role": m.role, "content": m.content}
        for m in thread.messages[: msg_index + 1]
    ]

    # Generate new assistant response
    client = get_llm_client()
    llm_model = model or settings.LLM_MODEL
    try:
        reply = _generate_assistant_reply(
            client=client,
            llm_model=llm_model,
            user_email=user.email,
            history=history,
            prompt=new_content,
        )
    except Exception as exc:
        reply = (
            f"Model '{llm_model}' could not complete this request. "
            f"Details: {exc}"
        )

    await _save_message(db, thread, "assistant", reply)

    # Refresh and return
    await db.refresh(thread, ["messages"])
    return thread
