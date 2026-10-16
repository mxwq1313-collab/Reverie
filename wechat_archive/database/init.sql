CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wxid TEXT NOT NULL UNIQUE CHECK (length(trim(wxid)) > 0),
    nickname TEXT NOT NULL CHECK (length(trim(nickname)) > 0),
    avatar TEXT
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    receiver_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    create_time TEXT NOT NULL,
    content TEXT NOT NULL CHECK (length(trim(content)) > 0),
    msg_type TEXT NOT NULL DEFAULT 'text' CHECK (msg_type = 'text')
);

CREATE INDEX idx_messages_sender_time ON messages(sender_id, create_time, id);
CREATE INDEX idx_messages_receiver_time ON messages(receiver_id, create_time, id);
CREATE INDEX idx_messages_time ON messages(create_time, id);
