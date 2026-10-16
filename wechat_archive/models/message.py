from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Message:
    id: int
    sender_id: int
    receiver_id: int
    create_time: datetime
    content: str
    msg_type: str = "text"
    chat_id: int | None = None
    message_hash: str | None = None
    source: str | None = None
    source_id: str | None = None
    source_hash: str | None = None
    external_id: str | None = None
