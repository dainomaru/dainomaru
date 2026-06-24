# 棋譜解析実行

Fairy-Stockfish エンジンで最新棋譜を解析し、評価値コメント付き KIF と解析レポートを GitHub Releases に公開する。

## 手順

1. `mcp__github__actions_run_trigger` で `analyze_kifu.yml` をトリガー:
   - method: `run_workflow`
   - workflow_id: `analyze_kifu.yml`
   - ref: `claude/shogi-81dojo-analysis-019qha`
   - inputs: `{}`
   - owner: `dainomaru`, repo: `dainomaru`

2. 5〜10秒待ってから `mcp__github__actions_list` で最新 run_id を取得:
   - method: `list_workflow_runs`, resource_id: `analyze_kifu.yml`, per_page: 3
   - レスポンスが大きい場合はファイルに保存されるので python3 で run_id を抽出する

3. `mcp__github__actions_list` で進行状況を監視（list_workflow_jobs で run_id を指定）:
   - 解析ステップは約 40〜60 秒かかる（129手 × 300ms）
   - ScheduleWakeup(270s) で自動確認

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
| `analyzed_game.kif` | 解析棋譜1局 + 各手に `**解析 0` コメント挿入済み | UTF-8 with BOM |
| `analysis_report.txt` | 悪手・疑問手一覧 + 評価値グラフ | UTF-8 with BOM |
| `evaluation_graph.html` | SVG 形勢グラフ（ブラウザ表示用） | UTF-8 |
| `dainomaru_kifu.zip` | 全棋譜 ZIP（ダウンロードのみ） | — |

KIF コメント形式（ShogiDroid で開くと読み筋・形勢グラフ・悪手サークルが表示）:
```
**Engines 0 Fairy-Stockfish-largeboard
**解析 0  時間 00:00.3 深さ 11/15 ノード数 131458 評価値 30 読み筋 ▲７六歩(77) △４二金(41) ▲４八飛(28) ...
**解析 0  候補2 深さ 11 評価値 23 読み筋 ▲１六歩(17) ...
...
**解析 0  候補10 深さ 10 評価値 -23 読み筋 ▲７八銀(79) ...
1    ７六歩(77)        (0:04/0:00:04)
**解析 0  時間 00:00.3 深さ 11/12 ノード数 132706 評価値 7 読み筋 △８四歩(83) ...
**解析 0  候補2 ...
2    ８四歩(83)        (0:02/0:00:02)
```

- **解析ブロックは指し手行の前に置く**（lishogi形式）— これが赤/橙サークル表示の必須条件
- `**Engines 0 <name>` — 最初の解析ブロックの前のみ1回宣言
- `**解析 0  ...` — 各手の最善候補（ダブルアスタリスク必須）
- `**解析 0  候補2〜10` — MultiPV 10候補
- `評価値` — 常に先手（Black）視点に正規化（正=先手有利、負=後手有利）

**重要**: ShogiDroid の形勢グラフ・解析パネルは `**`（ダブルアスタリスク）形式が必要。
`*`（シングルアスタリスク）だと通常コメントとして扱われ、グラフが表示されない。

**重要**: 解析ブロックを指し手の**後**に置くと、ShogiDroid の評価値差分計算が
1手ズレて符号反転し、悪手/疑問手サークルが一切表示されなくなる。必ず**前**に置くこと。

## よくある問題と対処

| 症状 | 原因 | 対処 |
|------|------|------|
| 解析ステップが数分以上 in_progress のまま | API キャッシュで stale 表示 / エンジンクラッシュ | ScheduleWakeup で継続監視。10分超えたら cancel してリトライ |
| `BrokenPipeError` で失敗 | Fairy-Stockfish が途中クラッシュ | 修正済み（eval で proc.poll() 確認、_send で BrokenPipeError キャッチ） |
| 解析ステップが無限ハング | readline() の EOF 未検出 | 修正済み（raw が空なら break） |
| 文字化け | UTF-8 未認識 | 修正済み（utf-8-sig で保存） |
| `有効な棋譜が見つかりません` | 最新10件に有効な手がない | kifu_files/ の内容を確認 |
| 形勢グラフが表示されない | `**`（ダブルアスタリスク）が必要 | 修正済み（annotate_kif で `**解析 0` を使用） |
| 赤/橙サークルが表示されない | 解析ブロックを指し手の後に置くと評価値差分が1手ズレて符号反転する | 修正済み（解析ブロックを指し手の前に配置・lishogi形式） |

## 解析スクリプトの仕様（analyze_kifu.py）

- エンジン: Fairy-Stockfish largeboard（USI プロトコル）
- 悪手閾値: 損失 300 以上
- 疑問手閾値: 損失 100〜299
- MultiPV: 10候補（`**解析 0` + `**解析 0  候補2〜10`）
- KIF 候補: 最新日付順に最大10件試し、有効な手がある最初のファイルを解析
- 評価値: 常に先手（Black）視点に正規化
- PV変換: `shogi.KIF.Exporter.kif_move_from(usi, board)` で USI→KIF 表記に変換
- bestmove フォールバック: Fairy-Stockfish が `pv` を出力しない場合は `bestmove` 行を使用
- HTMLグラフ: `generate_eval_graph_html()` で SVG 形勢グラフを生成し `evaluation_graph.html` に出力
- 解析ブロック配置: `annotate_kif()` は指し手行の**前**に解析ブロックを挿入（lishogi形式）
