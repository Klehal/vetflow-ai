"""Conversation and message models."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import json


class Channel(str, Enum):
    PHONE = "phone"
    CHAT = "chat"
    SMS = "sms"


@dataclass
class Conversation:
    id: str
    clinic_id: str
    channel: str
    external_id: Optional[str] = None
    caller_phone: Optional[str] = None
    caller_name: Optional[str] = None
    status: str = "active"
    escalated_to: Optional[str] = None
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "Conversation":
        data = dict(row)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Message:
    id: str
    conversation_id: str
    role: str
    content: str
    channel: str
    metadata: dict = None
    created_at: Optional[str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    @classmethod
    def from_row(cls, row: dict) -> "Message":
        data = dict(row)
        if isinstance(data.get("metadata"), str):
            data["metadata"] = json.loads(data["metadata"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
