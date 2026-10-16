from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class User:
    id: int
    wxid: str
    nickname: str
    avatar: str | None = None
