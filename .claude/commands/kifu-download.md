# 棋譜ダウンロード実行

81dojoから dainomaru の棋譜をダウンロードして GitHub Releases に公開する。

## 手順

1. GitHub Actions ワークフローをトリガー:
   - `mcp__github__actions_run_trigger` で `download_kifu.yml` を `claude/shogi-81dojo-analysis-019qha` ブランチで実行
   - owner: `dainomaru`, repo: `dainomaru`

2. 実行状況を `mcp__github__actions_list` で監視（list_workflow_jobs で run_id を指定）

3. 成功したら Releases URL を案内:
   https://github.com/dainomaru/dainomaru/releases

## よくあるエラーと対処

| エラー | 原因 | 対処 |
|--------|------|------|
| シークレットの確認で失敗 | DOJO_USER または DOJO_PASSWORD 未設定 | https://github.com/dainomaru/dainomaru/settings/secrets/actions で追加 |
| ログイン失敗 | パスワード間違い | DOJO_PASSWORD を更新 |
| 棋譜0件 | 検索結果が空 | 81dojoにログインして棋譜画面を確認 |

## 認証情報

- DOJO_USER: `dainomaru`
- DOJO_PASSWORD: GitHub Secrets に登録済み
