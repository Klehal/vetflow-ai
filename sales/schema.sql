CREATE TABLE IF NOT EXISTS clinics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    website TEXT,
    address TEXT,
    city TEXT DEFAULT 'Calgary',
    province TEXT DEFAULT 'AB',
    google_place_id TEXT UNIQUE,
    google_rating REAL,
    review_count INTEGER DEFAULT 0,
    has_online_booking INTEGER DEFAULT 0,
    has_website INTEGER DEFAULT 0,
    website_quality_score INTEGER DEFAULT 0,  -- 0-10, lower = worse
    hours_json TEXT,  -- JSON of business hours
    after_hours_gap INTEGER DEFAULT 0,  -- 1 if closed evenings/weekends
    score INTEGER DEFAULT 0,  -- lead quality score 0-100
    score_notes TEXT,  -- why this score
    status TEXT DEFAULT 'new',  -- new, contacted, replied, interested, booked, closed, dead
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS touchpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic_id INTEGER NOT NULL REFERENCES clinics(id),
    channel TEXT NOT NULL,  -- email, sms, call
    direction TEXT DEFAULT 'outbound',  -- outbound, inbound
    sequence_day INTEGER DEFAULT 1,  -- day 1, 3, 5, 7
    subject TEXT,
    body TEXT,
    sent_at TIMESTAMP,
    opened_at TIMESTAMP,
    replied_at TIMESTAMP,
    status TEXT DEFAULT 'pending',  -- pending, sent, failed, opened, replied, bounced
    sendgrid_message_id TEXT,
    twilio_sid TEXT,
    bland_call_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic_id INTEGER NOT NULL REFERENCES clinics(id),
    touchpoint_id INTEGER REFERENCES touchpoints(id),
    channel TEXT,
    body TEXT NOT NULL,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    classification TEXT,  -- interested, objection, not_now, unsubscribe, out_of_office, unknown
    ai_response TEXT,  -- suggested response
    handled INTEGER DEFAULT 0,
    handled_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bookings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic_id INTEGER NOT NULL REFERENCES clinics(id),
    calendly_event_id TEXT,
    scheduled_at TIMESTAMP,
    meeting_type TEXT DEFAULT 'demo',
    status TEXT DEFAULT 'scheduled',  -- scheduled, completed, no_show, cancelled
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT UNIQUE NOT NULL,
    clinics_found INTEGER DEFAULT 0,
    clinics_scored INTEGER DEFAULT 0,
    emails_sent INTEGER DEFAULT 0,
    sms_sent INTEGER DEFAULT 0,
    calls_placed INTEGER DEFAULT 0,
    replies_received INTEGER DEFAULT 0,
    interested_replies INTEGER DEFAULT 0,
    calls_booked INTEGER DEFAULT 0,
    deals_closed INTEGER DEFAULT 0,
    revenue_collected REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_clinics_status ON clinics(status);
CREATE INDEX IF NOT EXISTS idx_clinics_score ON clinics(score DESC);
CREATE INDEX IF NOT EXISTS idx_touchpoints_clinic ON touchpoints(clinic_id);
CREATE INDEX IF NOT EXISTS idx_touchpoints_status ON touchpoints(status);
CREATE INDEX IF NOT EXISTS idx_replies_clinic ON replies(clinic_id);
