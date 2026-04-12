-- Conversations and messages (phone, chat, SMS)

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    channel TEXT NOT NULL,
    external_id TEXT,
    caller_phone TEXT,
    caller_name TEXT,
    status TEXT DEFAULT 'active',
    escalated_to TEXT REFERENCES staff(id),
    summary TEXT,
    sentiment TEXT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conv_clinic ON conversations(clinic_id);
CREATE INDEX IF NOT EXISTS idx_conv_channel ON conversations(channel);
CREATE INDEX IF NOT EXISTS idx_conv_phone ON conversations(caller_phone);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    channel TEXT NOT NULL,
    metadata TEXT DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_msg_conversation ON messages(conversation_id);
