# Discord-Measures-against-vandalism-BOT

荒らし対策用の Discord BOT サンプルです。`discord.py` v2 系を使い、危険ワード・危険ユーザのリストを JSON で永続化しつつ、参加/メッセージイベントで自動チェックを行います。コードは複数ファイルに分割し、最小構成で導入しやすい形にしています。

## 主要な前提
- Python 3.10+ を想定
- 使用ライブラリ: `discord.py`
- Intents: `message_content` と `members` を有効化する必要があります
- ギルド内に以下のチャンネル/ロールが存在する前提です
  - スタッフ向けアラートチャンネル: `staff-alert`
  - ログチャンネル: `anti-raid-log`
  - 警告ロール: `警告中`

## ファイル構成
```
bot.py                  # エントリーポイント
anti_raid_bot/
  __init__.py           # エクスポート
  config.py             # 定数定義（ファイル名・チャンネル名など）
  models.py             # データモデル（BannedUser）
  storage.py            # JSON 読み書きとメモリキャッシュ
  utils.py              # Discord API ヘルパー
  bot_client.py         # Bot 本体クラス・イベント・スラッシュコマンド
```

## セットアップ
1. 依存パッケージをインストールします。
   ```bash
   pip install -U discord.py
   ```
2. `bot.py` の `YOUR_TOKEN_HERE` を Bot トークンに置き換えます。
3. 必要に応じて JSON ファイルを空のまま同階層に置くか、そのまま起動して自動生成させます。

## 実行方法
```bash
python bot.py
```
起動時にスラッシュコマンドの同期が行われます。

## 実装済みスラッシュコマンド（すべて管理者権限のみ）
- `/banword_add text:<str>`: 危険ワードを追加
- `/banword_list`: 危険ワード一覧を表示（複数メッセージに分割して表示）
- `/banword_remove text:<str>`: 危険ワードを削除
- `/banuser_add user:<User> reason:<str>`: 危険ユーザを手動追加
- `/banuser_list`: 危険ユーザ一覧を表示
- `/banuser_remove user:<User>`: 危険ユーザを削除
- `/antiraid_test`: 動作確認用レスポンス
- `/alert_panel channel:<TextChannel> user:<User> reason:<str>`: 任意チャンネルに危険通知を送り、警告ロール付与/BAN/危険リスト登録のボタンを同梱

## データ保存仕様
- `banned_words.json`: 危険ワード一覧（文字列の配列）
- `banned_users.json`: 危険ユーザ情報の配列（ユーザ ID/理由/登録者/登録日時）
- ファイルが存在しない場合は起動時に空のリストで自動生成します。

## 挙動の概要
- `on_member_join`: 危険ユーザが参加した場合、警告ロール付与とスタッフ通知、必要に応じて DM 送信
- `on_message` / `on_message_edit`: 危険ユーザや危険ワード検出時にメッセージ削除・ログ送信・危険ユーザ登録を実行
- メンションに危険ユーザが含まれる場合も削除・ログを残します

## 注意点
- メッセージ削除やロール付与、BAN では権限不足の例外を握りつぶし、標準出力に簡易ログを出します。
- スラッシュコマンドの同期は Bot 起動時に自動で行われます。
