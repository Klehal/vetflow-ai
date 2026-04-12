-- Clinics (tenants) and staff

CREATE TABLE IF NOT EXISTS clinics (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    address TEXT,
    city TEXT,
    state TEXT,
    zip_code TEXT,
    timezone TEXT DEFAULT 'America/Chicago',
    website_url TEXT,
    business_hours TEXT DEFAULT '{}',
    services TEXT DEFAULT '[]',
    emergency_keywords TEXT DEFAULT '[]',
    bland_agent_id TEXT,
    twilio_phone TEXT,
    widget_primary_color TEXT DEFAULT '#2563eb',
    widget_greeting TEXT DEFAULT 'Hi! How can we help you and your pet today?',
    api_key TEXT UNIQUE NOT NULL,
    is_active INTEGER DEFAULT 1,
    plan TEXT DEFAULT 'standard',
    monthly_price REAL DEFAULT 599.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS staff (
    id TEXT PRIMARY KEY,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    name TEXT NOT NULL,
    role TEXT DEFAULT 'vet',
    phone TEXT,
    email TEXT,
    is_on_call INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_staff_clinic ON staff(clinic_id);
