from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class VerifyError(Exception):
    step: str
    code: str
    message: str

    def as_json(self) -> dict[str, Any]:
        return {
            "ok": False,
            "step": self.step,
            "error_code": self.code,
            "error_message": self.message,
        }
