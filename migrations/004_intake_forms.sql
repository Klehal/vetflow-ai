-- Pet owners, pets, and intake form submissions

CREATE TABLE IF NOT EXISTS owners (
    id TEXT PRIMARY KEY,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    address TEXT,
    emergency_contact_name TEXT,
    emergency_contact_phone TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_owners_clinic ON owners(clinic_id);
CREATE INDEX IF NOT EXISTS idx_owners_phone ON owners(clinic_id, phone);

CREATE TABLE IF NOT EXISTS pets (
    id TEXT PRIMARY KEY,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    owner_id TEXT NOT NULL REFERENCES owners(id),
    name TEXT NOT NULL,
    species TEXT NOT NULL,
    breed TEXT,
    date_of_birth DATE,
    weight_lbs REAL,
    sex TEXT,
    color TEXT,
    microchip_number TEXT,
    allergies TEXT,
    current_medications TEXT,
    medical_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pets_clinic ON pets(clinic_id);
CREATE INDEX IF NOT EXISTS idx_pets_owner ON pets(owner_id);

CREATE TABLE IF NOT EXISTS intake_submissions (
    id TEXT PRIMARY KEY,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    owner_id TEXT REFERENCES owners(id),
    pet_id TEXT REFERENCES pets(id),
    form_data TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_intake_clinic ON intake_submissions(clinic_id);
