"""Discord 依存のヘルパー関数群."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import discord

from .config import LOG_CHANNEL, STAFF_ALERT_CHANNEL


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def get_text_channel(guild: discord.Guild, name: str) -> Optional[discord.TextChannel]:
    return discord.utils.get(guild.text_channels, name=name)


def get_role(guild: discord.Guild, name: str) -> Optional[discord.Role]:
    return discord.utils.get(guild.roles, name=name)


async def send_staff_alert(guild: discord.Guild, embed: discord.Embed) -> None:
    channel = get_text_channel(guild, STAFF_ALERT_CHANNEL)
    if channel:
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            print("staff-alert チャンネルへの送信に失敗しました (権限不足)")
        except discord.HTTPException as exc:
            print(f"staff-alert 送信中に HTTP 例外: {exc}")


async def send_log(
    guild: discord.Guild, content: str, embed: Optional[discord.Embed] = None
) -> None:
    channel = get_text_channel(guild, LOG_CHANNEL)
    if channel:
        try:
            await channel.send(content, embed=embed)
        except discord.Forbidden:
            print("ログチャンネルへの送信に失敗しました (権限不足)")
        except discord.HTTPException as exc:
            print(f"ログ送信中に HTTP 例外: {exc}")


async def try_delete_message(message: discord.Message) -> None:
    try:
        await message.delete()
    except discord.Forbidden:
        print("メッセージ削除に失敗しました (権限不足)")
    except discord.HTTPException as exc:
        print(f"メッセージ削除時に HTTP 例外: {exc}")


async def try_add_role(member: discord.Member, role: discord.Role) -> None:
    try:
        await member.add_roles(role, reason="危険ユーザ自動警告")
    except discord.Forbidden:
        print("ロール付与に失敗しました (権限不足)")
    except discord.HTTPException as exc:
        print(f"ロール付与中に HTTP 例外: {exc}")


async def try_ban_member(member: discord.Member, reason: str) -> None:
    """必要に応じて BAN するための関数 (現在は呼び出される箇所無し)"""
    try:
        await member.ban(reason=reason, delete_message_days=1)
    except discord.Forbidden:
        print("BAN に失敗しました (権限不足)")
    except discord.HTTPException as exc:
        print(f"BAN 実行時に HTTP 例外: {exc}")
