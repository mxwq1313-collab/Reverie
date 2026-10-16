CREATE TABLE chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'private' CHECK (kind = 'private'),
    title TEXT
);

CREATE TABLE chat_members (
    chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE chat_sources (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    chat_id INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    PRIMARY KEY (source, external_id)
);

ALTER TABLE messages ADD COLUMN chat_id INTEGER REFERENCES chats(id) ON DELETE RESTRICT;
ALTER TABLE messages ADD COLUMN message_hash TEXT;
ALTER TABLE messages ADD COLUMN source TEXT;
ALTER TABLE messages ADD COLUMN source_id TEXT;
ALTER TABLE messages ADD COLUMN source_hash TEXT;
ALTER TABLE messages ADD COLUMN external_id TEXT;

CREATE INDEX idx_messages_hash ON messages(message_hash);
CREATE INDEX idx_messages_chat_time ON messages(chat_id, create_time, id);
CREATE INDEX idx_messages_source ON messages(source, source_id);
CREATE INDEX idx_chat_members_user ON chat_members(user_id, chat_id);

CREATE TABLE migration_history (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    backup_path TEXT
);
