"""Reminder and vaccination record models."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Reminder:
    id: str
    clinic_id: str
    type: str
    channel: str
    scheduled_for: str
    appointment_id: Optional[str] = None
    pet_id: Optional[str] = None
    recipient_phone: Optional[str] = None
    recipient_email: Optional[str] = None
    sent_at: Optional[str] = None
    status: str = "pending"
    error_message: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "Reminder":
        data = dict(row)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class VaccinationRecord:
    id: str
    clinic_id: str
    pet_id: str
    vaccine_name: str
    administered_date: str
    next_due_date: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "VaccinationRecord":
        data = dict(row)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
