-- Appointments and availability

CREATE TABLE IF NOT EXISTS appointments (
    id TEXT PRIMARY KEY,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    pet_id TEXT REFERENCES pets(id),
    owner_name TEXT,
    owner_phone TEXT,
    owner_email TEXT,
    pet_name TEXT,
    pet_species TEXT,
    service_type TEXT NOT NULL,
    scheduled_date DATE NOT NULL,
    scheduled_time TEXT NOT NULL,
    duration_minutes INTEGER DEFAULT 30,
    status TEXT DEFAULT 'confirmed',
    source TEXT DEFAULT 'phone',
    notes TEXT,
    staff_id TEXT REFERENCES staff(id),
    reminder_48h_sent INTEGER DEFAULT 0,
    reminder_24h_sent INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_appt_clinic_date ON appointments(clinic_id, scheduled_date);
CREATE INDEX IF NOT EXISTS idx_appt_status ON appointments(status);
CREATE INDEX IF NOT EXISTS idx_appt_owner_phone ON appointments(owner_phone);

CREATE TABLE IF NOT EXISTS availability_overrides (
    id TEXT PRIMARY KEY,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    override_date DATE NOT NULL,
    is_closed INTEGER DEFAULT 0,
    open_time TEXT,
    close_time TEXT,
    reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_avail_clinic_date ON availability_overrides(clinic_id, override_date);
