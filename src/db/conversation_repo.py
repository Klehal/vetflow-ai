"""CRUD operations for conversations and messages."""

import json
from typing import Optional
from src.db.database import Database
from src.models.conversation import Conversation, Message


class ConversationRepo:
    def __init__(self, db: Database):
        self.db = db

    async def create_conversation(self, conv: Conversation) -> Conversation:
        await self.db.execute(
            """INSERT INTO conversations (id, clinic_id, channel, external_id,
                caller_phone, caller_name, status)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (conv.id, conv.clinic_id, conv.channel, conv.external_id,
             conv.caller_phone, conv.caller_name, conv.status),
        )
        return conv

    async def get_conversation(self, conv_id: str) -> Optional[Conversation]:
        row = await self.db.fetch_one("SELECT * FROM conversations WHERE id = ?", (conv_id,))
        return Conversation.from_row(row) if row else None

    async def get_active_conversation(self, clinic_id: str, caller_phone: str, channel: str) -> Optional[Conversation]:
        row = await self.db.fetch_one(
            """SELECT * FROM conversations WHERE clinic_id = ? AND caller_phone = ?
               AND channel = ? AND status = 'active' ORDER BY started_at DESC LIMIT 1""",
            (clinic_id, caller_phone, channel),
        )
        return Conversation.from_row(row) if row else None

    async def end_conversation(self, conv_id: str, summary: str = None, sentiment: str = None):
        await self.db.execute(
            "UPDATE conversations SET status = 'resolved', summary = ?, sentiment = ?, ended_at = CURRENT_TIMESTAMP WHERE id = ?",
            (summary, sentiment, conv_id),
        )

    async def escalate_conversation(self, conv_id: str, staff_id: str):
        await self.db.execute(
            "UPDATE conversations SET status = 'escalated', escalated_to = ? WHERE id = ?",
            (staff_id, conv_id),
        )

    async def get_conversations_by_clinic(self, clinic_id: str, limit: int = 50) -> list[Conversation]:
        rows = await self.db.fetch_all(
            "SELECT * FROM conversations WHERE clinic_id = ? ORDER BY started_at DESC LIMIT ?",
            (clinic_id, limit),
        )
        return [Conversation.from_row(r) for r in rows]

    async def add_message(self, msg: Message) -> Message:
        await self.db.execute(
            "INSERT INTO messages (id, conversation_id, role, content, channel, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            (msg.id, msg.conversation_id, msg.role, msg.content, msg.channel, json.dumps(msg.metadata)),
        )
        return msg

    async def get_messages(self, conversation_id: str, limit: int = 50) -> list[Message]:
        rows = await self.db.fetch_all(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ?",
            (conversation_id, limit),
        )
        return [Message.from_row(r) for r in rows]

    async def get_recent_messages(self, conversation_id: str, limit: int = 20) -> list[Message]:
        rows = await self.db.fetch_all(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at DESC LIMIT ?",
            (conversation_id, limit),
        )
        return [Message.from_row(r) for r in reversed(rows)]
