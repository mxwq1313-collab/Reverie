CREATE TABLE chats_v3 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_key TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'private' CHECK(kind IN ('private','group')),
    title TEXT
);
INSERT INTO chats_v3 SELECT * FROM chats;
DROP TABLE chats;
ALTER TABLE chats_v3 RENAME TO chats;

CREATE TABLE messages_v3 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    receiver_id INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    create_time TEXT NOT NULL,
    content TEXT,
    msg_type TEXT NOT NULL DEFAULT 'text' CHECK(msg_type IN ('text','image','video','audio','file','location','system')),
    chat_id INTEGER REFERENCES chats(id) ON DELETE RESTRICT,
    message_hash TEXT,
    source TEXT,
    source_id TEXT,
    source_hash TEXT,
    external_id TEXT,
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
    CHECK(msg_type != 'text' OR (content IS NOT NULL AND length(trim(content)) > 0)),
    CHECK(msg_type = 'system' OR sender_id IS NOT NULL)
);
INSERT INTO messages_v3(id,sender_id,receiver_id,create_time,content,msg_type,chat_id,message_hash,source,source_id,source_hash,external_id)
SELECT id,sender_id,receiver_id,create_time,content,msg_type,chat_id,message_hash,source,source_id,source_hash,external_id FROM messages;
DROP TABLE messages;
ALTER TABLE messages_v3 RENAME TO messages;

CREATE TABLE media (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('image','video','audio','file')),
    relative_uri TEXT,
    sha256 TEXT,
    size_bytes INTEGER CHECK(size_bytes IS NULL OR size_bytes >= 0),
    availability TEXT NOT NULL CHECK(availability IN ('missing','pending','ready','unsupported')),
    variant TEXT NOT NULL CHECK(variant IN ('original','compressed','thumbnail'))
);
CREATE TABLE message_media (
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    media_id TEXT NOT NULL REFERENCES media(id) ON DELETE RESTRICT,
    ordinal INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(message_id,media_id)
);
CREATE TABLE message_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    namespace TEXT NOT NULL,
    source_key TEXT NOT NULL,
    source_hash TEXT,
    identity_strategy TEXT NOT NULL
);
CREATE INDEX idx_message_sources_key ON message_sources(namespace,source_key);
CREATE TABLE import_sessions (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('active','complete','cancelled','failed')),
    last_batch_id TEXT,
    cursor TEXT,
    updated_at TEXT NOT NULL
);
CREATE TABLE import_batches (
    session_id TEXT NOT NULL REFERENCES import_sessions(id) ON DELETE CASCADE,
    batch_id TEXT NOT NULL,
    digest TEXT NOT NULL,
    record_count INTEGER NOT NULL CHECK(record_count >= 0),
    committed_at TEXT NOT NULL,
    PRIMARY KEY(session_id,batch_id)
);
CREATE TABLE archive_metadata (
    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
    archive_identity TEXT NOT NULL UNIQUE,
    content_revision INTEGER NOT NULL CHECK(content_revision >= 0)
);
CREATE TRIGGER messages_revision_insert AFTER INSERT ON messages BEGIN
    UPDATE archive_metadata SET content_revision=content_revision+1 WHERE singleton=1;
END;
CREATE TRIGGER messages_revision_update AFTER UPDATE OF sender_id,receiver_id,create_time,content,msg_type,chat_id,source,source_id ON messages BEGIN
    UPDATE messages SET revision=OLD.revision+1 WHERE id=NEW.id;
    UPDATE archive_metadata SET content_revision=content_revision+1 WHERE singleton=1;
END;
CREATE TRIGGER messages_revision_delete AFTER DELETE ON messages BEGIN
    UPDATE archive_metadata SET content_revision=content_revision+1 WHERE singleton=1;
END;
CREATE TRIGGER messages_chat_receiver_insert BEFORE INSERT ON messages
WHEN NEW.chat_id IS NOT NULL AND (
    (EXISTS(SELECT 1 FROM chats WHERE id=NEW.chat_id AND kind='group') AND NEW.receiver_id IS NOT NULL)
    OR (EXISTS(SELECT 1 FROM chats WHERE id=NEW.chat_id AND kind='private') AND NEW.receiver_id IS NULL)
) BEGIN
    SELECT RAISE(ABORT,'receiver_id does not match chat kind');
END;
CREATE TRIGGER messages_chat_receiver_update BEFORE UPDATE OF chat_id,receiver_id ON messages
WHEN NEW.chat_id IS NOT NULL AND (
    (EXISTS(SELECT 1 FROM chats WHERE id=NEW.chat_id AND kind='group') AND NEW.receiver_id IS NOT NULL)
    OR (EXISTS(SELECT 1 FROM chats WHERE id=NEW.chat_id AND kind='private') AND NEW.receiver_id IS NULL)
) BEGIN
    SELECT RAISE(ABORT,'receiver_id does not match chat kind');
END;
