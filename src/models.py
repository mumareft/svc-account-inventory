from dataclasses import dataclass
from typing import Any, Literal

Source = Literal["AD", "ENTRA", "SILVERFORT"]


@dataclass
class RawAccount:
    source: Source
    source_object_id: str
    name: str | None
    display_name: str | None
    enabled: bool | None
    account_type: str | None
    last_seen: str | None
    raw: dict[str, Any]