"""CRUD operations for owners, pets, and intake submissions."""

import json
from typing import Optional
from src.db.database import Database
from src.models.pet import Owner, Pet, IntakeSubmission


class PetRepo:
    def __init__(self, db: Database):
        self.db = db

    async def create_owner(self, owner: Owner) -> Owner:
        await self.db.execute(
            """INSERT INTO owners (id, clinic_id, first_name, last_name, phone, email,
                address, emergency_contact_name, emergency_contact_phone)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (owner.id, owner.clinic_id, owner.first_name, owner.last_name,
             owner.phone, owner.email, owner.address,
             owner.emergency_contact_name, owner.emergency_contact_phone),
        )
        return owner

    async def get_owner_by_phone(self, clinic_id: str, phone: str) -> Optional[Owner]:
        row = await self.db.fetch_one(
            "SELECT * FROM owners WHERE clinic_id = ? AND phone = ?", (clinic_id, phone),
        )
        return Owner.from_row(row) if row else None

    async def create_pet(self, pet: Pet) -> Pet:
        await self.db.execute(
            """INSERT INTO pets (id, clinic_id, owner_id, name, species, breed,
                date_of_birth, weight_lbs, sex, color, microchip_number,
                allergies, current_medications, medical_notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pet.id, pet.clinic_id, pet.owner_id, pet.name, pet.species, pet.breed,
             pet.date_of_birth, pet.weight_lbs, pet.sex, pet.color,
             pet.microchip_number, pet.allergies, pet.current_medications, pet.medical_notes),
        )
        return pet

    async def get_pets_by_owner(self, owner_id: str) -> list[Pet]:
        rows = await self.db.fetch_all("SELECT * FROM pets WHERE owner_id = ?", (owner_id,))
        return [Pet.from_row(r) for r in rows]

    async def submit_intake(self, submission: IntakeSubmission) -> IntakeSubmission:
        await self.db.execute(
            "INSERT INTO intake_submissions (id, clinic_id, owner_id, pet_id, form_data, status) VALUES (?, ?, ?, ?, ?, ?)",
            (submission.id, submission.clinic_id, submission.owner_id, submission.pet_id,
             json.dumps(submission.form_data), submission.status),
        )
        return submission

    async def get_intake_submissions(self, clinic_id: str, status: str = None) -> list[IntakeSubmission]:
        if status:
            rows = await self.db.fetch_all(
                "SELECT * FROM intake_submissions WHERE clinic_id = ? AND status = ? ORDER BY submitted_at DESC",
                (clinic_id, status),
            )
        else:
            rows = await self.db.fetch_all(
                "SELECT * FROM intake_submissions WHERE clinic_id = ? ORDER BY submitted_at DESC",
                (clinic_id,),
            )
        return [IntakeSubmission.from_row(r) for r in rows]
