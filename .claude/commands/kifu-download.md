# 棋譜ダウンロード実行

81dojoから dainomaru の棋譜をダウンロードして GitHub Releases に公開する。

## 手順

1. `mcp__github__actions_run_trigger` で `download_kifu.yml` をトリガー:
   - method: `run_workflow`
   - workflow_id: `download_kifu.yml`
   - ref: `claude/shogi-81dojo-analysis-019qha`
   - inputs: `{}` （全件）または `{"max_games": "5"}` （最新5件のみ・高速）
   - owner: `dainomaru`, repo: `dainomaru`

2. 5〜10秒待ってから `mcp__github__actions_list` で最新 run_id を取得:
   - method: `list_workflow_runs`, resource_id: `download_kifu.yml`, per_page: 3

3. `mcp__github__actions_list` で進行状況を監視（list_workflow_jobs で run_id を指定）:
   - 初回: 全件ダウンロード → キャッシュ保存（時間がかかる）
   - 2回目以降: キャッシュ復元 → 新規分のみダウンロード（大幅短縮）

4. 成功したら Releases URL を案内:
   https://github.com/dainomaru/dainomaru/releases

## ワークフロー入力パラメータ

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| `max_games` | `0` | 最大取得件数 (0=全件、5=最新5件のみ) |

## キャッシュ仕様

`kifu/dainomaru/*.kif` を GitHub Actions cache で保存・復元する。

- キャッシュキー: `kifu-dainomaru-{run_id}`（毎回保存）
- 復元: 前回実行のキャッシュを自動復元 → 既存ファイルはスキップ
- **効果**: 2回目以降は新規1〜2件のみダウンロード

## ダウンロードスクリプト仕様（download_81dojo_kifu.py）

- 検索フォーム: 先手/後手の両方で検索してIDをマージ（新しい順を保持）
- `--max N`: 最新N件のみダウンロード（検索結果の先頭N件 = 最新N件）
- 既存ファイルは自動スキップ（`kifu/dainomaru/{id}.kif` が存在する場合）
- リクエスト間隔: 0.8秒/件（サーバー負荷軽減）
- 認証: `~/.netrc` から読み込み（GitHub Secrets で設定）

## よくあるエラーと対処

| エラー | 原因 | 対処 |
|--------|------|------|
| シークレットの確認で失敗 | DOJO_USER または DOJO_PASSWORD 未設定 | https://github.com/dainomaru/dainomaru/settings/secrets/actions で追加 |
| ログイン失敗 | パスワード間違い | DOJO_PASSWORD を更新 |
| 棋譜0件 | 検索結果が空 | 81dojoにログインして棋譜画面を確認 |

## 認証情報

- DOJO_USER: `dainomaru`
- DOJO_PASSWORD: GitHub Secrets に登録済み
