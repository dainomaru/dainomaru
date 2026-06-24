# 棋譜ダウンロード状況確認

最新のワークフロー実行結果を確認する。

## 手順

1. `mcp__github__actions_list` で `download_kifu.yml` の最新実行を取得
   - method: `list_workflow_runs`, per_page: 1
   - owner: `dainomaru`, repo: `dainomaru`

2. status が `completed` かつ conclusion が `success` なら成功

3. 失敗していたら `mcp__github__get_job_logs` でログを確認して原因を特定

4. 成功していたら Releases を確認:
   https://github.com/dainomaru/dainomaru/releases
