"""JSON ファイルの読み書きとメモリキャッシュを扱うモジュール."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from .config import BANNED_USERS_FILE, BANNED_WORDS_FILE
from .models import BannedUser


def _ensure_file(path: Path, default_data) -> None:
    """ファイルが無ければ作成して初期データを書き込む"""
    if not path.exists():
        path.write_text(
            json.dumps(default_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class BanStorage:
    """危険ワード/ユーザ情報の読み書きとキャッシュを扱うクラス"""

    def __init__(
        self,
        words_path: Path = BANNED_WORDS_FILE,
        users_path: Path = BANNED_USERS_FILE,
    ) -> None:
        self.words_path = words_path
        self.users_path = users_path
        self.banned_words: Set[str] = set()
        self.banned_users: Dict[str, BannedUser] = {}
        self._load_all()

    def _load_all(self) -> None:
        self.banned_words = self.load_banned_words()
        self.banned_users = self.load_banned_users()

    def load_banned_words(self) -> Set[str]:
        _ensure_file(self.words_path, [])
        try:
            words: List[str] = json.loads(self.words_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            words = []
        return {w.lower() for w in words if w}

    def save_banned_words(self) -> None:
        self.words_path.write_text(
            json.dumps(sorted(self.banned_words), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_banned_word(self, word: str) -> bool:
        lower_word = word.lower().strip()
        if not lower_word or lower_word in self.banned_words:
            return False
        self.banned_words.add(lower_word)
        self.save_banned_words()
        return True

    def remove_banned_word(self, word: str) -> bool:
        lower_word = word.lower().strip()
        if lower_word not in self.banned_words:
            return False
        self.banned_words.remove(lower_word)
        self.save_banned_words()
        return True

    def load_banned_users(self) -> Dict[str, BannedUser]:
        _ensure_file(self.users_path, [])
        try:
            raw_users: List[Dict[str, str]] = json.loads(
                self.users_path.read_text(encoding="utf-8")
            )
        except json.JSONDecodeError:
            raw_users = []
        users: Dict[str, BannedUser] = {}
        for entry in raw_users:
            user = BannedUser.from_dict(entry)
            if user.user_id:
                users[user.user_id] = user
        return users

    def save_banned_users(self) -> None:
        self.users_path.write_text(
            json.dumps([u.to_dict() for u in self.banned_users.values()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_banned_user(self, user: BannedUser) -> bool:
        if user.user_id in self.banned_users:
            return False
        self.banned_users[user.user_id] = user
        self.save_banned_users()
        return True

    def remove_banned_user(self, user_id: str) -> bool:
        if user_id not in self.banned_users:
            return False
        self.banned_users.pop(user_id)
        self.save_banned_users()
        return True

    def extend_words(self, words: Iterable[str]) -> None:
        for word in words:
            self.add_banned_word(word)

    def extend_users(self, users: Iterable[BannedUser]) -> None:
        for user in users:
            self.add_banned_user(user)

    def get_banned_user(self, user_id: str) -> Optional[BannedUser]:
        return self.banned_users.get(user_id)

    def has_banned_word(self, content: str) -> Optional[str]:
        lower_content = content.lower()
        for word in self.banned_words:
            if word and word in lower_content:
                return word
        return None
