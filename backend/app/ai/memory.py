"""
Conversation memory utilities for Campus Mind AI.

This module owns conversation loading, authorization checks,
history retrieval, and saving chat exchanges.

It does not decide what the user is asking.
It does not calculate academic analytics.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models


DEFAULT_HISTORY_LIMIT = 12


def load_conversation(
    db: Session,
    user: models.User,
    conversation_id: int | None,
    kind: str,
) -> models.AIConversation | None:
    """
    Load a conversation belonging to the authenticated user.

    Returns None when no conversation_id was supplied.

    Raises:
        HTTPException(404): conversation does not belong to the user.
        HTTPException(422): conversation mode does not match the request.
    """
    if not conversation_id:
        return None

    conversation = db.get(models.AIConversation, conversation_id)

    if not conversation:
        raise HTTPException(404, "Conversation not found")

    if conversation.user_id != user.id:
        raise HTTPException(404, "Conversation not found")

    if conversation.kind != kind:
        raise HTTPException(422, "Conversation mode cannot be changed")

    return conversation


def load_history(
    db: Session,
    conversation: models.AIConversation | None,
    limit: int = DEFAULT_HISTORY_LIMIT,
) -> list[models.AIMessage]:
    """
    Load recent messages for an existing conversation.

    The current Campus Mind behavior uses the earliest 12 messages
    from the conversation query. We preserve that behavior here.
    """
    if not conversation:
        return []

    return db.scalars(
        select(models.AIMessage)
        .where(models.AIMessage.conversation_id == conversation.id)
        .order_by(models.AIMessage.id)
        .limit(limit)
    ).all()


def save_exchange(
    db: Session,
    user: models.User,
    conversation: models.AIConversation | None,
    kind: str,
    question: str,
    answer: str,
) -> models.AIConversation:
    """
    Create a conversation when necessary and save one user/assistant exchange.

    This preserves the current /api/ai/ask behavior:
    - create the conversation only after the answer is ready
    - add both messages
    - commit once
    """
    if not conversation:
        conversation = models.AIConversation(
            user_id=user.id,
            kind=kind,
        )
        db.add(conversation)
        db.flush()

    db.add_all(
        [
            models.AIMessage(
                conversation_id=conversation.id,
                role="user",
                content=question,
            ),
            models.AIMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=answer,
            ),
        ]
    )

    db.commit()

    return conversation