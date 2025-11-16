"""Bot 本体のクラス定義."""
from __future__ import annotations

from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, button

from .config import WARNING_ROLE_NAME
from .models import BannedUser
from .storage import BanStorage
from .utils import (
    get_role,
    now_iso,
    send_log,
    send_staff_alert,
    try_add_role,
    try_delete_message,
)


class AntiRaidBot(commands.Bot):
    """荒らし対策機能をまとめた Bot クラス"""

    def __init__(self, storage: BanStorage) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.storage = storage

    async def setup_hook(self) -> None:
        """Bot の初期セットアップ"""
        self._register_commands()
        try:
            synced = await self.tree.sync()
            print(f"スラッシュコマンド同期完了: {len(synced)} 件")
        except Exception as exc:  # noqa: BLE001
            print(f"スラッシュコマンド同期中に例外: {exc}")

    def _register_commands(self) -> None:
        self.tree.add_command(self.banword_add)
        self.tree.add_command(self.banword_list)
        self.tree.add_command(self.banword_remove)
        self.tree.add_command(self.banuser_add)
        self.tree.add_command(self.banuser_list)
        self.tree.add_command(self.banuser_remove)
        self.tree.add_command(self.alert_panel)
        self.tree.add_command(self.antiraid_test)
        self.tree.on_error = self.on_app_command_error

    # -------------------- イベント --------------------
    async def on_ready(self) -> None:
        print(f"Bot logged in as {self.user} (ID: {self.user.id if self.user else 'N/A'})")

    async def on_member_join(self, member: discord.Member) -> None:
        user_id = str(member.id)
        info = self.storage.get_banned_user(user_id)
        if not info:
            return

        guild = member.guild
        warning_role = get_role(guild, WARNING_ROLE_NAME)
        if warning_role:
            await try_add_role(member, warning_role)

        embed = discord.Embed(title="危険ユーザが参加しました", color=discord.Color.orange())
        embed.add_field(name="ユーザ", value=f"{member.mention} ({member})", inline=False)
        embed.add_field(name="ユーザID", value=info.user_id, inline=False)
        embed.add_field(name="理由", value=info.reason, inline=False)
        embed.add_field(name="登録者", value=info.added_by or "不明", inline=False)
        embed.add_field(name="登録日時", value=info.added_at, inline=False)
        await send_staff_alert(guild, embed)

        try:
            await member.send("サーバーへの参加が制限されています。管理者が確認するまでお待ちください。")
        except discord.Forbidden:
            pass

    async def on_message(self, message: discord.Message) -> None:
        await self.process_message(message)

    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        await self.process_message(after)

    # -------------------- メッセージ処理 --------------------
    async def process_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if await self._check_banned_user_message(message):
            return
        if await self._check_banned_words(message):
            return
        await self._check_mentions(message)

    async def _check_banned_user_message(self, message: discord.Message) -> bool:
        user_id = str(message.author.id)
        if not self.storage.get_banned_user(user_id):
            return False
        await try_delete_message(message)
        await self._log_message_action(message, reason="known banned user")
        return True

    async def _check_banned_words(self, message: discord.Message) -> bool:
        if not message.content:
            return False
        hit_word = self.storage.has_banned_word(message.content)
        if not hit_word:
            return False
        await try_delete_message(message)
        await self._log_message_action(
            message, reason="banned word detected", note=f"ヒットワード: {hit_word}"
        )
        await self._add_user_to_banned(
            message.author,
            reason=f"banned word: {hit_word}",
            added_by=str(self.user.id) if self.user else None,
        )
        return True

    async def _check_mentions(self, message: discord.Message) -> bool:
        for user in message.mentions:
            if self.storage.get_banned_user(str(user.id)):
                await try_delete_message(message)
                await self._log_message_action(
                    message,
                    reason="mention to banned user",
                    note=f"メンション対象: {user.mention}",
                )
                return True
        return False

    async def _add_user_to_banned(
        self, author: discord.abc.User, reason: str, added_by: Optional[str]
    ) -> None:
        user_id = str(author.id)
        if user_id in self.storage.banned_users:
            return
        info = BannedUser(user_id=user_id, reason=reason, added_by=added_by, added_at=now_iso())
        self.storage.add_banned_user(info)
        print(f"危険ユーザに追加: {user_id} ({reason})")

    async def _log_message_action(
        self, message: discord.Message, reason: str, note: Optional[str] = None
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

    # -------------------- スラッシュコマンド --------------------
    @app_commands.command(name="banword_add", description="危険ワードを追加")
    @app_commands.checks.has_permissions(administrator=True)
    async def banword_add(self, interaction: discord.Interaction, text: str) -> None:
        word = text.lower().strip()
        if not word:
            await interaction.response.send_message("空文字は登録できません。", ephemeral=True)
            return
        created = self.storage.add_banned_word(word)
        if created:
            await interaction.response.send_message(
                f"危険ワードを追加しました: {word}", ephemeral=True
            )
        else:
            await interaction.response.send_message("既に登録済みです。", ephemeral=True)

    @app_commands.command(name="banword_list", description="危険ワード一覧")
    @app_commands.checks.has_permissions(administrator=True)
    async def banword_list(self, interaction: discord.Interaction) -> None:
        if not self.storage.banned_words:
            await interaction.response.send_message("登録された危険ワードはありません。", ephemeral=True)
            return
        lines = sorted(self.storage.banned_words)
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

    @app_commands.command(name="banword_remove", description="危険ワードを削除")
    @app_commands.checks.has_permissions(administrator=True)
    async def banword_remove(self, interaction: discord.Interaction, text: str) -> None:
        word = text.lower().strip()
        if self.storage.remove_banned_word(word):
            await interaction.response.send_message(f"削除しました: {word}", ephemeral=True)
        else:
            await interaction.response.send_message(
                "指定されたワードは登録されていません。", ephemeral=True
            )

    @app_commands.command(name="banuser_add", description="危険ユーザを追加")
    @app_commands.checks.has_permissions(administrator=True)
    async def banuser_add(
        self, interaction: discord.Interaction, user: discord.User, reason: str
    ) -> None:
        user_id = str(user.id)
        if user_id in self.storage.banned_users:
            await interaction.response.send_message("既に登録済みです。", ephemeral=True)
            return
        info = BannedUser(
            user_id=user_id,
            reason=reason,
            added_by=str(interaction.user.id),
            added_at=now_iso(),
        )
        self.storage.add_banned_user(info)
        await interaction.response.send_message("危険ユーザとして登録しました。", ephemeral=True)

        guild = interaction.guild
        if guild:
            embed = discord.Embed(title="手動追加: 危険ユーザ", color=discord.Color.blue())
            embed.add_field(name="ユーザ", value=f"{user.mention} ({user.id})", inline=False)
            embed.add_field(name="理由", value=reason, inline=False)
            embed.add_field(name="追加者", value=interaction.user.mention, inline=False)
            embed.add_field(name="追加日時", value=info.added_at, inline=False)
            await send_staff_alert(guild, embed)

    @app_commands.command(name="banuser_list", description="危険ユーザ一覧")
    @app_commands.checks.has_permissions(administrator=True)
    async def banuser_list(self, interaction: discord.Interaction) -> None:
        if not self.storage.banned_users:
            await interaction.response.send_message("危険ユーザは登録されていません。", ephemeral=True)
            return
        lines = [
            f"- {u.user_id} | {u.reason} | {u.added_at}" for u in self.storage.banned_users.values()
        ]
        description = "\n".join(lines)
        embed = discord.Embed(title="危険ユーザ一覧", description=f"```\n{description}\n```")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="banuser_remove", description="危険ユーザを削除")
    @app_commands.checks.has_permissions(administrator=True)
    async def banuser_remove(self, interaction: discord.Interaction, user: discord.User) -> None:
        user_id = str(user.id)
        if self.storage.remove_banned_user(user_id):
            await interaction.response.send_message("削除しました。", ephemeral=True)
        else:
            await interaction.response.send_message("登録が見つかりません。", ephemeral=True)

    @app_commands.command(name="antiraid_test", description="動作確認用コマンド")
    async def antiraid_test(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message("AntiRaid bot is running", ephemeral=True)

    @app_commands.command(
        name="alert_panel", description="任意チャンネルに危険通知と操作ボタンを送信"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def alert_panel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        user: discord.User,
        reason: str,
    ) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message(
                "ギルド内でのみ使用できます。", ephemeral=True
            )
            return

        embed = discord.Embed(title="危険通知", color=discord.Color.orange())
        embed.add_field(name="ユーザ", value=f"{user.mention} ({user.id})", inline=False)
        embed.add_field(name="理由", value=reason, inline=False)
        embed.set_footer(text="ボタンから迅速に対応できます")

        view = ManageUserView(bot=self, target_user_id=user.id, reason=reason)
        try:
            await channel.send(content="危険ユーザ通知", embed=embed, view=view)
        except discord.Forbidden:
            await interaction.response.send_message(
                "指定チャンネルへ送信できません (権限不足)", ephemeral=True
            )
            return
        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"送信中にエラーが発生しました: {exc}", ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"{channel.mention} に危険通知を送信しました。", ephemeral=True
        )

    # -------------------- エラーハンドリング --------------------
    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message("管理者権限が必要です。", ephemeral=True)
        else:
            await interaction.response.send_message(
                "コマンド実行中にエラーが発生しました。", ephemeral=True
            )
            print(f"スラッシュコマンドエラー: {error}")


class ManageUserView(View):
    """危険通知から即応できる操作ボタン付きビュー"""

    def __init__(self, bot: AntiRaidBot, target_user_id: int, reason: str) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.target_user_id = target_user_id
        self.reason = reason

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "管理者のみ操作できます。", ephemeral=True
            )
            return False
        return True

    async def _fetch_member(self, guild: discord.Guild) -> Optional[discord.Member]:
        member = guild.get_member(self.target_user_id)
        if member:
            return member
        try:
            return await guild.fetch_member(self.target_user_id)
        except discord.NotFound:
            return None
        except discord.HTTPException:
            return None

    @button(label="警告ロール付与", style=discord.ButtonStyle.secondary)
    async def warn_button(
        self, interaction: discord.Interaction, _: discord.ui.Button["ManageUserView"]
    ) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("ギルドでのみ操作できます。", ephemeral=True)
            return

        member = await self._fetch_member(guild)
        if not member:
            await interaction.response.send_message("メンバーが見つかりません。", ephemeral=True)
            return

        role = get_role(guild, WARNING_ROLE_NAME)
        if not role:
            await interaction.response.send_message(
                "警告ロールが見つかりません。", ephemeral=True
            )
            return

        await try_add_role(member, role)
        await interaction.response.send_message("警告ロールを付与しました。", ephemeral=True)

    @button(label="BAN する", style=discord.ButtonStyle.danger)
    async def ban_button(
        self, interaction: discord.Interaction, _: discord.ui.Button["ManageUserView"]
    ) -> None:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("ギルドでのみ操作できます。", ephemeral=True)
            return

        member = await self._fetch_member(guild)
        if not member:
            await interaction.response.send_message(
                "対象メンバーを取得できませんでした。", ephemeral=True
            )
            return

        try:
            await member.ban(reason=f"Alert panel action: {self.reason}")
        except discord.Forbidden:
            await interaction.response.send_message(
                "BAN に失敗しました (権限不足)", ephemeral=True
            )
            return
        except discord.HTTPException as exc:
            await interaction.response.send_message(
                f"BAN 実行中にエラーが発生しました: {exc}", ephemeral=True
            )
            return

        await interaction.response.send_message("BAN を実行しました。", ephemeral=True)

    @button(label="危険リストへ追加", style=discord.ButtonStyle.primary)
    async def add_banlist_button(
        self, interaction: discord.Interaction, _: discord.ui.Button["ManageUserView"]
    ) -> None:
        user_id = str(self.target_user_id)
        if user_id in self.bot.storage.banned_users:
            await interaction.response.send_message("既に登録済みです。", ephemeral=True)
            return
        info = BannedUser(
            user_id=user_id,
            reason=self.reason,
            added_by=str(interaction.user.id),
            added_at=now_iso(),
        )
        self.bot.storage.add_banned_user(info)
        await interaction.response.send_message("危険ユーザリストに追加しました。", ephemeral=True)
