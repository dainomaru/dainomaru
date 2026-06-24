# 棋譜解析実行

Fairy-Stockfish エンジンで最新棋譜を解析し、評価値コメント付き KIF と解析レポートを GitHub Releases に公開する。

## 手順

1. `mcp__github__actions_run_trigger` で `analyze_kifu.yml` をトリガー:
   - method: `run_workflow`
   - workflow_id: `analyze_kifu.yml`
   - ref: `claude/shogi-81dojo-analysis-019qha`
   - inputs: `{"movetime": "300"}`
   - owner: `dainomaru`, repo: `dainomaru`

2. 5〜10秒待ってから `mcp__github__actions_list` で最新 run_id を取得:
   - method: `list_workflow_runs`, resource_id: `analyze_kifu.yml`, per_page: 3
   - レスポンスが大きい場合はファイルに保存されるので python3 で run_id を抽出する

3. `mcp__github__actions_list` で進行状況を監視（list_workflow_jobs で run_id を指定）:
   - 解析ステップは約 40〜60 秒かかる（129手 × 300ms）
   - 60 秒ごとに ScheduleWakeup で自動確認

4. 完了後、`mcp__github__get_latest_release` でリリースアセットを確認:
   - `analyzed_game.kif` — 解析対象の棋譜1局（各手に評価値コメント付き）
   - `analysis_report.txt` — 悪手・疑問手・評価値グラフのテキストレポート

5. ダウンロード URL を案内:
   - https://github.com/dainomaru/dainomaru/releases/tag/kifu-8
   - analyzed_game.kif: https://github.com/dainomaru/dainomaru/releases/download/kifu-8/analyzed_game.kif
   - analysis_report.txt: https://github.com/dainomaru/dainomaru/releases/download/kifu-8/analysis_report.txt

## 出力ファイルの仕様

| ファイル | 内容 | エンコード |
|---------|------|-----------|
| `analyzed_game.kif` | 解析棋譜1局 + 各手に `*評価値:` コメント行 | UTF-8 with BOM |
| `analysis_report.txt` | 悪手・疑問手一覧 + 評価値グラフ | UTF-8 with BOM |
| `dainomaru_kifu.zip` | 全棋譜 ZIP（ダウンロードのみ） | — |

KIF コメント形式（ShogiDroid 等で手を進めると表示）:
```
   1 ７六歩(77)   ( 0:01/...)
*評価値: +50→+30  損失:-20
   2 ３四歩(34)
*評価値: +30→-120  損失:-150  ▲疑問手
  81 ４四角打
*評価値: +200→-300  損失:-500  ★悪手★
```

## よくある問題と対処

| 症状 | 原因 | 対処 |
|------|------|------|
| 解析ステップが数分以上 in_progress のまま | API キャッシュで stale 表示 / エンジンクラッシュ | ScheduleWakeup で継続監視。10分超えたら cancel してリトライ |
| `BrokenPipeError` で失敗 | Fairy-Stockfish が途中クラッシュ | 修正済み（eval で proc.poll() 確認、_send で BrokenPipeError キャッチ） |
| 解析ステップが無限ハング | readline() の EOF 未検出 | 修正済み（raw が空なら break） |
| 文字化け | UTF-8 未認識 | 修正済み（utf-8-sig で保存） |
| `有効な棋譜が見つかりません` | 最新10件に有効な手がない | kifu_files/ の内容を確認 |

## 解析スクリプトの仕様（analyze_kifu.py）

- エンジン: Fairy-Stockfish largeboard（UCI プロトコル、`UCI_Variant shogi`）
- 悪手閾値: 損失 300 以上（`★悪手★`）
- 疑問手閾値: 損失 100〜299（`▲疑問手`）
- KIF 候補: 最新日付順に最大10件試し、有効な手がある最初のファイルを解析
- 評価値: 常に先手（Black）視点に正規化
