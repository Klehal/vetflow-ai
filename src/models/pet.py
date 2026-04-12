"""Pet owner, pet, and intake form models."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Owner:
    id: str
    clinic_id: str
    first_name: str
    last_name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    created_at: Optional[str] = None

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @classmethod
    def from_row(cls, row: dict) -> "Owner":
        data = dict(row)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Pet:
    id: str
    clinic_id: str
    owner_id: str
    name: str
    species: str
    breed: Optional[str] = None
    date_of_birth: Optional[str] = None
    weight_lbs: Optional[float] = None
    sex: Optional[str] = None
    color: Optional[str] = None
    microchip_number: Optional[str] = None
    allergies: Optional[str] = None
    current_medications: Optional[str] = None
    medical_notes: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "Pet":
        data = dict(row)
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class IntakeSubmission:
    id: str
    clinic_id: str
    form_data: dict
    owner_id: Optional[str] = None
    pet_id: Optional[str] = None
    status: str = "pending"
    submitted_at: Optional[str] = None
    reviewed_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> "IntakeSubmission":
        data = dict(row)
        import json
        if isinstance(data.get("form_data"), str):
            data["form_data"] = json.loads(data["form_data"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
