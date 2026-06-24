# 81dojo 棋譜ダウンローダー (dainomaru用)

81dojoから **dainomaru** の棋譜をダウンロードし、ShogiDroidで解析するためのツールです。

## 必要環境

- Python 3.9+
- インターネット接続

```bash
pip install requests beautifulsoup4 lxml
```

## 使い方

### 1. 棋譜のダウンロード

```bash
# 全棋譜をダウンロード
python3 download_81dojo_kifu.py

# 最新20局だけ取得する場合
python3 download_81dojo_kifu.py --max 20

# 別のユーザー名を指定する場合
python3 download_81dojo_kifu.py --user USERNAME
```

実行後、以下が生成されます:

```
kifu/
  dainomaru/
    12345.kif
    12346.kif
    ...
dainomaru_kifu.zip   ← スマホに転送するファイル
```

### 2. ShogiDroidへの転送と解析

#### Androidスマホへの転送方法

**方法A: Google Drive 経由**
1. `dainomaru_kifu.zip` を Google Drive にアップロード
2. スマホの Google Drive アプリで ZIPをダウンロード
3. ZIPを解凍して KIF ファイルをフォルダに配置

**方法B: USB ケーブル接続**
1. PCとスマホをUSBで接続（ファイル転送モード）
2. `dainomaru_kifu.zip` をスマホのストレージにコピー
3. スマホでZIPを解凍

**方法C: メール/LINE で自分に送る**
- ZIP ファイルをメールやLINEで自分に送信
- スマホで受信してダウンロード

#### ShogiDroidでの解析手順

1. **ShogiDroid** を起動
2. 右上メニュー → **「棋譜を開く」**
3. KIF ファイルが入ったフォルダを選択
4. 一覧から解析したい棋譜を選択
5. **詰み探索・形勢評価** のボタンで解析開始

> ShogiDroidのエンジン設定: YaneuraOu / Gikou など対応エンジンをインストールすると
> より深い解析が可能です。

## KIF ファイル形式について

- **KIF形式**: 81dojoで使われる標準形式。ShogiDroid対応済み
- **CSA形式**: 変換が必要な場合は `kif2csa` ツールを使用
- **KI2形式**: より人間が読みやすい形式（変換オプションで対応可）

## トラブルシューティング

### 棋譜が0件になる場合
81dojoはログインが必要な場合があります:
1. ブラウザで81dojoにログイン
2. DevToolsでCookieをコピー
3. スクリプトの `SESSION.cookies.update({...})` に設定

### ダウンロードに失敗する場合
- ネットワーク接続を確認
- `--max 10` で少数から試す
- 81dojoのサーバー状況を確認: https://81dojo.com
