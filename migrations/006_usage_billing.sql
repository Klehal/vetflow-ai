-- Usage tracking and daily metrics

CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    event_type TEXT NOT NULL,
    quantity REAL DEFAULT 1,
    unit_cost REAL DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_usage_clinic_date ON usage_log(clinic_id, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_type ON usage_log(event_type);

CREATE TABLE IF NOT EXISTS daily_clinic_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    date DATE NOT NULL,
    phone_calls INTEGER DEFAULT 0,
    phone_minutes REAL DEFAULT 0,
    sms_sent INTEGER DEFAULT 0,
    sms_received INTEGER DEFAULT 0,
    chat_sessions INTEGER DEFAULT 0,
    appointments_booked INTEGER DEFAULT 0,
    appointments_cancelled INTEGER DEFAULT 0,
    intake_forms_submitted INTEGER DEFAULT 0,
    reminders_sent INTEGER DEFAULT 0,
    escalations INTEGER DEFAULT 0,
    UNIQUE(clinic_id, date)
);
