"""Appointment and availability models."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class TimeSlot:
    date: str
    time: str
    duration_minutes: int = 30
    available: bool = True


@dataclass
class Appointment:
    id: str
    clinic_id: str
    service_type: str
    scheduled_date: str
    scheduled_time: str
    owner_name: Optional[str] = None
    owner_phone: Optional[str] = None
    owner_email: Optional[str] = None
    pet_name: Optional[str] = None
    pet_species: Optional[str] = None
    pet_id: Optional[str] = None
    duration_minutes: int = 30
    status: str = "confirmed"
    source: str = "chat"
    notes: Optional[str] = None
    staff_id: Optional[str] = None
    reminder_48h_sent: bool = False
    reminder_24h_sent: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "Appointment":
        data = dict(row)
        data["reminder_48h_sent"] = bool(data.get("reminder_48h_sent", 0))
        data["reminder_24h_sent"] = bool(data.get("reminder_24h_sent", 0))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AvailabilityOverride:
    id: str
    clinic_id: str
    override_date: str
    is_closed: bool = False
    open_time: Optional[str] = None
    close_time: Optional[str] = None
    reason: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "AvailabilityOverride":
        data = dict(row)
        data["is_closed"] = bool(data.get("is_closed", 0))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
