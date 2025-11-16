import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import discord
from discord import app_commands
from discord.ext import commands

# 定数類
BANNED_WORDS_FILE = Path("banned_words.json")
BANNED_USERS_FILE = Path("banned_users.json")
STAFF_ALERT_CHANNEL = "staff-alert"
LOG_CHANNEL = "anti-raid-log"
WARNING_ROLE_NAME = "警告中"

# -------------------- データモデル --------------------
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


# -------------------- ファイル読み書き --------------------
def ensure_file(path: Path, default_data):
    """ファイルが無ければ作成して初期データを書き込む"""
    if not path.exists():
        path.write_text(json.dumps(default_data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_banned_words() -> Set[str]:
    ensure_file(BANNED_WORDS_FILE, [])
    try:
        words: List[str] = json.loads(BANNED_WORDS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        words = []
    return {w.lower() for w in words}


def save_banned_words(words: Set[str]) -> None:
    BANNED_WORDS_FILE.write_text(
        json.dumps(sorted(words), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_banned_users() -> Dict[str, BannedUser]:
    ensure_file(BANNED_USERS_FILE, [])
    try:
        raw_users: List[Dict[str, str]] = json.loads(BANNED_USERS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        raw_users = []
    users: Dict[str, BannedUser] = {}
    for entry in raw_users:
        user = BannedUser.from_dict(entry)
        if user.user_id:
            users[user.user_id] = user
    return users


def save_banned_users(users: Dict[str, BannedUser]) -> None:
    BANNED_USERS_FILE.write_text(
        json.dumps([u.to_dict() for u in users.values()], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# -------------------- ヘルパー関数 --------------------
def get_text_channel(guild: discord.Guild, name: str) -> Optional[discord.TextChannel]:
    return discord.utils.get(guild.text_channels, name=name)


def get_role(guild: discord.Guild, name: str) -> Optional[discord.Role]:
    return discord.utils.get(guild.roles, name=name)


def now_iso() -> str:
    return datetime.utcnow().isoformat()


async def send_staff_alert(guild: discord.Guild, embed: discord.Embed) -> None:
    channel = get_text_channel(guild, STAFF_ALERT_CHANNEL)
    if channel:
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            print("staff-alert チャンネルへの送信に失敗しました (権限不足)")
        except discord.HTTPException as exc:
            print(f"staff-alert 送信中に HTTP 例外: {exc}")


async def send_log(guild: discord.Guild, content: str, embed: Optional[discord.Embed] = None) -> None:
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


# -------------------- BOT 本体 --------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# メモリ上の危険リスト
banned_words: Set[str] = load_banned_words()
banned_users: Dict[str, BannedUser] = load_banned_users()


@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user} (ID: {bot.user.id})")
    # スラッシュコマンド同期
    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンド同期完了: {len(synced)} 件")
    except Exception as exc:  # noqa: BLE001
        print(f"スラッシュコマンド同期中に例外: {exc}")


@bot.event
async def on_member_join(member: discord.Member):
    user_id = str(member.id)
    if user_id not in banned_users:
        return

    info = banned_users[user_id]
    guild = member.guild
    # 警告ロール付与
    warning_role = get_role(guild, WARNING_ROLE_NAME)
    if warning_role:
        await try_add_role(member, warning_role)

    # スタッフ向けアラート
    embed = discord.Embed(title="危険ユーザが参加しました", color=discord.Color.orange())
    embed.add_field(name="ユーザ", value=f"{member.mention} ({member})", inline=False)
    embed.add_field(name="ユーザID", value=info.user_id, inline=False)
    embed.add_field(name="理由", value=info.reason, inline=False)
    embed.add_field(name="登録者", value=info.added_by or "不明", inline=False)
    embed.add_field(name="登録日時", value=info.added_at, inline=False)
    await send_staff_alert(guild, embed)

    # DM 送信 (失敗したら無視)
    try:
        await member.send(
            "サーバーへの参加が制限されています。管理者が確認するまでお待ちください。"
        )
    except discord.Forbidden:
        pass


async def log_message_action(
    message: discord.Message, reason: str, note: Optional[str] = None
) -> None:
    guild = message.guild
    if guild is None:
        return
    embed = discord.Embed(title="自動アクション", color=discord.Color.red())
    embed.add_field(name="ユーザ", value=f"{message.author.mention} ({message.author.id})", inline=False)
    embed.add_field(name="チャンネル", value=message.channel.mention, inline=False)
    content_preview = (message.content or "").strip()
    if len(content_preview) > 150:
        content_preview = content_preview[:147] + "..."
    embed.add_field(name="メッセージ", value=content_preview or "(本文なし)", inline=False)
    embed.add_field(name="理由", value=reason, inline=False)
    if note:
        embed.add_field(name="備考", value=note, inline=False)
    await send_log(guild, content="自動対処を実行しました", embed=embed)


async def add_user_to_banned(author: discord.abc.User, reason: str, added_by: Optional[str]) -> None:
    user_id = str(author.id)
    if user_id in banned_users:
        return
    info = BannedUser(user_id=user_id, reason=reason, added_by=added_by, added_at=now_iso())
    banned_users[user_id] = info
    save_banned_users(banned_users)
    print(f"危険ユーザに追加: {user_id} ({reason})")


async def check_banned_user_message(message: discord.Message) -> bool:
    user_id = str(message.author.id)
    if user_id not in banned_users:
        return False
    await try_delete_message(message)
    await log_message_action(message, reason="known banned user")
    return True


async def check_banned_words(message: discord.Message) -> bool:
    content_lower = (message.content or "").lower()
    for word in banned_words:
        if word and word in content_lower:
            await try_delete_message(message)
            await log_message_action(message, reason="banned word detected", note=f"ヒットワード: {word}")
            await add_user_to_banned(message.author, reason=f"banned word: {word}", added_by=str(bot.user.id) if bot.user else None)
            return True
    return False


async def check_mentions(message: discord.Message) -> bool:
    # メンションされたユーザに危険ユーザが含まれているか
    for user in message.mentions:
        if str(user.id) in banned_users:
            await try_delete_message(message)
            await log_message_action(
                message,
                reason="mention to banned user",
                note=f"メンション対象: {user.mention}",
            )
            return True
    return False


async def process_message(message: discord.Message) -> None:
    if message.author.bot:
        return
    if await check_banned_user_message(message):
        return
    if await check_banned_words(message):
        return
    await check_mentions(message)


@bot.event
async def on_message(message: discord.Message):
    await process_message(message)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    # 編集後の内容を検査
    await process_message(after)


# -------------------- スラッシュコマンド --------------------

def admin_only():
    return app_commands.checks.has_permissions(administrator=True)


@bot.tree.command(name="banword_add", description="危険ワードを追加")
@admin_only()
async def banword_add(interaction: discord.Interaction, text: str):
    word = text.lower().strip()
    if not word:
        await interaction.response.send_message("空文字は登録できません。", ephemeral=True)
        return
    banned_words.add(word)
    save_banned_words(banned_words)
    await interaction.response.send_message(f"危険ワードを追加しました: {word}", ephemeral=True)


@bot.tree.command(name="banword_list", description="危険ワード一覧")
@admin_only()
async def banword_list(interaction: discord.Interaction):
    if not banned_words:
        await interaction.response.send_message("登録された危険ワードはありません。", ephemeral=True)
        return
    lines = sorted(banned_words)
    chunks: List[str] = []
    buffer = ""
    for line in lines:
        candidate = buffer + f"\n- {line}" if buffer else f"- {line}"
        if len(candidate) > 1800:
            chunks.append(buffer)
            buffer = f"- {line}"
        else:
            buffer = candidate
    if buffer:
        chunks.append(buffer)

    await interaction.response.send_message(
        content="登録済み危険ワード一覧:",
        embed=discord.Embed(description="\n\n".join(f"```\n{c}\n```" for c in chunks)),
        ephemeral=True,
    )


@bot.tree.command(name="banword_remove", description="危険ワードを削除")
@admin_only()
async def banword_remove(interaction: discord.Interaction, text: str):
    word = text.lower().strip()
    if word in banned_words:
        banned_words.remove(word)
        save_banned_words(banned_words)
        await interaction.response.send_message(f"削除しました: {word}", ephemeral=True)
    else:
        await interaction.response.send_message("指定されたワードは登録されていません。", ephemeral=True)


@bot.tree.command(name="banuser_add", description="危険ユーザを追加")
@admin_only()
async def banuser_add(interaction: discord.Interaction, user: discord.User, reason: str):
    user_id = str(user.id)
    if user_id in banned_users:
        await interaction.response.send_message("既に登録済みです。", ephemeral=True)
        return
    info = BannedUser(user_id=user_id, reason=reason, added_by=str(interaction.user.id), added_at=now_iso())
    banned_users[user_id] = info
    save_banned_users(banned_users)
    await interaction.response.send_message("危険ユーザとして登録しました。", ephemeral=True)

    # スタッフ向け通知
    guild = interaction.guild
    if guild:
        embed = discord.Embed(title="手動追加: 危険ユーザ", color=discord.Color.blue())
        embed.add_field(name="ユーザ", value=f"{user.mention} ({user.id})", inline=False)
        embed.add_field(name="理由", value=reason, inline=False)
        embed.add_field(name="追加者", value=interaction.user.mention, inline=False)
        embed.add_field(name="追加日時", value=info.added_at, inline=False)
        await send_staff_alert(guild, embed)


@bot.tree.command(name="banuser_list", description="危険ユーザ一覧")
@admin_only()
async def banuser_list(interaction: discord.Interaction):
    if not banned_users:
        await interaction.response.send_message("危険ユーザは登録されていません。", ephemeral=True)
        return
    lines = [
        f"- {u.user_id} | {u.reason} | {u.added_at}" for u in banned_users.values()
    ]
    description = "\n".join(lines)
    embed = discord.Embed(title="危険ユーザ一覧", description=f"```\n{description}\n```")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="banuser_remove", description="危険ユーザを削除")
@admin_only()
async def banuser_remove(interaction: discord.Interaction, user: discord.User):
    user_id = str(user.id)
    if user_id in banned_users:
        banned_users.pop(user_id)
        save_banned_users(banned_users)
        await interaction.response.send_message("削除しました。", ephemeral=True)
    else:
        await interaction.response.send_message("登録が見つかりません。", ephemeral=True)


@bot.tree.command(name="antiraid_test", description="動作確認用コマンド")
async def antiraid_test(interaction: discord.Interaction):
    await interaction.response.send_message("AntiRaid bot is running", ephemeral=True)


@banword_add.error
@banword_list.error
@banword_remove.error
@banuser_add.error
@banuser_list.error
@banuser_remove.error
async def admin_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("管理者権限が必要です。", ephemeral=True)
    else:
        await interaction.response.send_message("コマンド実行中にエラーが発生しました。", ephemeral=True)
        print(f"スラッシュコマンドエラー: {error}")


# ---- ここにトークンを記載して実行 ----
if __name__ == "__main__":
    # 実行前に Discord BOT トークンを設定してください
    bot.run("YOUR_TOKEN_HERE")
