# 棋譜ワークフロー状況確認

ダウンロードワークフローと解析ワークフローの最新実行結果を確認する。

## 手順

1. `mcp__github__actions_list` で両ワークフローの最新実行を取得:
   - method: `list_workflow_runs`, per_page: 1
   - `download_kifu.yml` と `analyze_kifu.yml` をそれぞれ確認
   - owner: `dainomaru`, repo: `dainomaru`

2. 各ワークフローの状態を報告:
   - `in_progress` → 実行中（ScheduleWakeup で60秒後に再確認）
   - `completed / success` → 成功
   - `completed / failure` → 失敗（ログを確認）
   - `completed / cancelled` → キャンセル済み

3. 失敗していたら `mcp__github__get_job_logs` でログを確認して原因を特定:
   - job_id を `list_workflow_jobs` で取得してから呼ぶ
   - return_content: true, tail_lines: 100

4. リリースの最新状態を `mcp__github__get_latest_release` で確認:
   - 期待するアセット: `dainomaru_kifu.zip`, `analyzed_game.kif`, `analysis_report.txt`

5. 結果を案内:
   - リリースページ: https://github.com/dainomaru/dainomaru/releases
