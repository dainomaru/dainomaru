# dainomaru 棋譜ダウンローダー

## プロジェクト概要

81dojo（81dojo.com）から **dainomaru** の将棋対局棋譜をダウンロードし、
Android アプリ **ShogiDroid** で解析するための自動化ツール。

## ファイル構成

```
download_81dojo_kifu.py   # メインスクリプト（81dojoログイン→棋譜取得→KIF変換→ZIP）
analyze_kifu.py           # 棋譜解析スクリプト（Fairy-Stockfish→KIFコメント付き出力）
test_kifu.py              # CI用テスト（CSA→KIF変換の動作確認）
requirements.txt          # Python依存ライブラリ
run.sh                    # ローカル実行用シェルスクリプト
.github/workflows/
  download_kifu.yml       # 棋譜ダウンロードワークフロー（毎週月曜+手動）
  analyze_kifu.yml        # 棋譜解析ワークフロー（手動トリガー）
  test.yml                # CIテストワークフロー（push時自動）
```

## GitHub Secrets（必須設定）

| Secret名 | 値 |
|---|---|
| `DOJO_USER` | `dainomaru` |
| `DOJO_PASSWORD` | 81dojoのパスワード |

設定URL: https://github.com/dainomaru/dainomaru/settings/secrets/actions

## 技術的な詳細

- **認証**: mechanicalsoup でブラウザログイン → ~/.netrc から認証情報読み込み
- **棋譜取得**: `https://system.81dojo.com/api/v2/kifus/{id}.json` のJSONからCSA形式を取得
- **形式変換**: `shogi.CSA.Parser.parse_str()` → `shogi.KIF.Exporter().kif()` でCSA→KIF
- **出力**: `kifu/dainomaru/*.kif` + `dainomaru_kifu.zip`
- **ILLEGAL_MOVE対応**: 反則手の直前2手を除去してからCSA解析

## カスタムコマンド

- `/kifu-download` — ダウンロードワークフローのトリガーと結果確認
- `/kifu-analyze`  — 解析ワークフローのトリガーと結果確認（analyzed_game.kif + analysis_report.txt）
- `/kifu-status`   — 最新ワークフロー実行状況の確認

## 解析ワークフローの出力（analyze_kifu.yml）

解析実行後、GitHub Releases の最新タグに以下が追加される:

| ファイル | 内容 |
|---------|------|
| `analyzed_game.kif` | 解析対象の棋譜1局（各手に `*評価値:` コメント挿入済み） |
| `analysis_report.txt` | 悪手・疑問手一覧 + 評価値グラフ |
| `dainomaru_kifu.zip` | 全棋譜 ZIP |

- エンコード: UTF-8 with BOM（文字化け対策済み）
- エンジン: Fairy-Stockfish largeboard（UCI_Variant shogi）

## 棋譜選択オプション（analyze_kifu.yml）

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| `movetime` | 1000 | 1手あたり解析時間 (ms) |
| `kif_id` | (空) | 対局IDを直接指定（最優先） |
| `target_moves` | 0 | **手数フィルタ**。例: `130` → 130手前後の最新棋譜を選択 |
| `moves_tolerance` | 10 | `target_moves` の許容誤差（±10手） |
| `kif_skip` | 0 | 新しい順に N 件スキップ |

### 使用例

- **130手前後の棋譜を解析**: `target_moves=130`, `moves_tolerance=10`
- **特定の対局を解析**: `kif_id=XAHvdg`
- **2番目に新しい棋譜**: `kif_skip=1`
