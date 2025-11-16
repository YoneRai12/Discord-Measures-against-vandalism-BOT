"""データモデルを定義するモジュール."""
from dataclasses import dataclass, asdict
from typing import Dict, Optional


@dataclass
class BannedUser:
    """危険ユーザ情報を保持するデータクラス"""

    user_id: str
    reason: str
    added_by: Optional[str]
    added_at: str

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "BannedUser":
        return cls(
            user_id=str(data.get("user_id", "")),
            reason=str(data.get("reason", "")),
            added_by=data.get("added_by"),
            added_at=str(data.get("added_at", "")),
        )

    def to_dict(self) -> Dict[str, str]:
        return asdict(self)
