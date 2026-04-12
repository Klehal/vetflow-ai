"""Clinic (tenant) and staff models."""

from dataclasses import dataclass, field
from typing import Optional
import json


@dataclass
class Clinic:
    id: str
    name: str
    api_key: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    timezone: str = "America/Chicago"
    website_url: Optional[str] = None
    business_hours: dict = field(default_factory=dict)
    services: list = field(default_factory=list)
    emergency_keywords: list = field(default_factory=list)
    bland_agent_id: Optional[str] = None
    twilio_phone: Optional[str] = None
    widget_primary_color: str = "#2563eb"
    widget_greeting: str = "Hi! How can we help you and your pet today?"
    is_active: bool = True
    plan: str = "standard"
    monthly_price: float = 599.00
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "Clinic":
        data = dict(row)
        for json_field in ("business_hours", "services", "emergency_keywords"):
            if isinstance(data.get(json_field), str):
                data[json_field] = json.loads(data[json_field])
        data["is_active"] = bool(data.get("is_active", 1))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Staff:
    id: str
    clinic_id: str
    name: str
    role: str = "vet"
    phone: Optional[str] = None
    email: Optional[str] = None
    is_on_call: bool = False
    created_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "Staff":
        data = dict(row)
        data["is_on_call"] = bool(data.get("is_on_call", 0))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
