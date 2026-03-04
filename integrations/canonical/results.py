from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SyncResult:
    success: bool
    message: str = ""
    updated_count: int = 0
    created_count: int = 0
    errors: list[str] = field(default_factory=list)
    external_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclass
class WebhookResult:
    success: bool
    action: str = ""
    message: str = ""
    order_id: Optional[str] = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)
