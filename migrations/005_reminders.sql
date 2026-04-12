-- Reminders and vaccination records

CREATE TABLE IF NOT EXISTS reminders (
    id TEXT PRIMARY KEY,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    type TEXT NOT NULL,
    appointment_id TEXT REFERENCES appointments(id),
    pet_id TEXT REFERENCES pets(id),
    recipient_phone TEXT,
    recipient_email TEXT,
    channel TEXT NOT NULL,
    scheduled_for TIMESTAMP NOT NULL,
    sent_at TIMESTAMP,
    status TEXT DEFAULT 'pending',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reminders_scheduled ON reminders(scheduled_for, status);
CREATE INDEX IF NOT EXISTS idx_reminders_clinic ON reminders(clinic_id);

CREATE TABLE IF NOT EXISTS vaccination_records (
    id TEXT PRIMARY KEY,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    pet_id TEXT NOT NULL REFERENCES pets(id),
    vaccine_name TEXT NOT NULL,
    administered_date DATE NOT NULL,
    next_due_date DATE,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_vacc_due ON vaccination_records(next_due_date);
CREATE INDEX IF NOT EXISTS idx_vacc_pet ON vaccination_records(pet_id);
