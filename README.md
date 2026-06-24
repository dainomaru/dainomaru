# 81dojo 棋譜ダウンローダー (dainomaru用)

81dojoから **dainomaru** の全対局棋譜をダウンロードし、  
Androidアプリ **ShogiDroid** で解析するためのツールです。

## 必要環境

- Python 3.9+
- 81dojoのアカウント（自分のアカウントでログインして取得）

```bash
pip install mechanicalsoup python-shogi requests
```

## 使い方

### 基本実行

```bash
python3 download_81dojo_kifu.py
```

実行すると81dojoのユーザー名・パスワードを聞かれます。  
入力後、自動で全棋譜をダウンロードします。

### オプション

```bash
# 最新30局のみ取得
python3 download_81dojo_kifu.py --max 30

# KIF変換せずCSA形式で保存（処理が速い）
python3 download_81dojo_kifu.py --csa

# ZIPを作成しない
python3 download_81dojo_kifu.py --no-zip

# 別のユーザー名を指定
python3 download_81dojo_kifu.py --user USERNAME
```

### 認証情報を ~/.netrc に保存する方法（任意）

毎回パスワード入力を省略できます:

```
# ~/.netrc に追記
machine system.81dojo.com login dainomaru password あなたのパスワード
```

```bash
chmod 600 ~/.netrc
```

## 出力ファイル

```
kifu/
  dainomaru/
    12345678.kif   ← KIF形式 (ShogiDroid対応)
    12345679.kif
    ...
dainomaru_kifu.zip ← スマホに転送するZIPファイル
```

## ShogiDroidへの転送・解析手順

### スマホへの転送

**方法A: Google Drive（推奨）**
1. `dainomaru_kifu.zip` を Google Drive にアップロード
2. スマホの Google Drive アプリでダウンロード
3. ZIPを解凍（ファイルマネージャーアプリを使用）

**方法B: USB ケーブル**
1. PCとスマホをUSBで接続（ファイル転送モード）
2. `dainomaru_kifu.zip` をスマホの `Download/` フォルダにコピー
3. スマホのファイルマネージャーでZIPを解凍

**方法C: メール・LINE で自分に送る**
- ZIP（または個別KIFファイル）を自分に送って受信

### ShogiDroidでの解析手順

1. **ShogiDroid** を起動
2. 右上メニュー → **「棋譜を開く」**
3. ZIPを解凍したフォルダを選択
4. 一覧から解析したい棋譜をタップ
5. **「解析」ボタン**または**詰み探索ボタン**をタップ

> **エンジン設定のヒント**: ShogiDroidの設定からUSIエンジン（YaneuraOu、GPSFish等）を  
> インストールすると、より高精度な形勢評価・最善手提示が利用できます。

## 技術的な詳細

- **APIエンドポイント**: `https://system.81dojo.com/api/v2/kifus/{id}.json`
- **JSONのcontentsフィールド**: CSA形式の棋譜データ
- **変換**: CSA → KIF は `python-shogi` ライブラリを使用
- **認証**: `mechanicalsoup` によるWebログイン

参考: [shogi-utils by agt-the-walker](https://github.com/agt-the-walker/shogi-utils)

## トラブルシューティング

| 症状 | 対処法 |
|------|--------|
| 「ログインに失敗」 | ユーザー名・パスワードを再確認 |
| 棋譜が0件 | ログイン後に自分の棋譜画面を確認 |
| KIF変換失敗 → CSA保存 | CSAファイルもShogiDroidで開ける |
| 接続エラー | ネットワークとVPN設定を確認 |
