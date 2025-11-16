"""荒らし対策 Discord BOT のエントリーポイント."""
from anti_raid_bot import AntiRaidBot, BanStorage


# ---- ここにトークンを記載して実行 ----
def main() -> None:
    """Bot を起動するエントリーポイント"""
    storage = BanStorage()
    bot = AntiRaidBot(storage)
    bot.run("YOUR_TOKEN_HERE")


if __name__ == "__main__":
    main()
