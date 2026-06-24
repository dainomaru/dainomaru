# dainomaru 棋譜ダウンローダー

## プロジェクト概要

81dojo（81dojo.com）から **dainomaru** の将棋対局棋譜をダウンロードし、
Android アプリ **ShogiDroid** で解析するための自動化ツール。

## ファイル構成

```
download_81dojo_kifu.py   # メインスクリプト（81dojoログイン→棋譜取得→KIF変換→ZIP）
test_kifu.py              # CI用テスト（CSA→KIF変換の動作確認）
requirements.txt          # Python依存ライブラリ
run.sh                    # ローカル実行用シェルスクリプト
.github/workflows/
  download_kifu.yml       # 棋譜ダウンロードワークフロー（毎週月曜+手動）
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
- `/kifu-status`  — 最新ワークフロー実行状況の確認
