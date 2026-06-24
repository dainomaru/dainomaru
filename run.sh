#!/bin/bash
# 81dojo棋譜ダウンローダー 簡単実行スクリプト
# 使い方: bash run.sh

set -e
cd "$(dirname "$0")"

echo "==================================="
echo "  81dojo 棋譜ダウンローダー"
echo "  対象: dainomaru"
echo "==================================="
echo ""

# Python確認
if ! command -v python3 &>/dev/null; then
    echo "エラー: Python3が見つかりません。インストールしてください。"
    exit 1
fi

# pip確認・ライブラリインストール
echo "[準備] 必要ライブラリを確認中..."
pip3 install -q -r requirements.txt
echo "  OK"
echo ""

# メインスクリプト実行（引数をそのまま渡す）
python3 download_81dojo_kifu.py "$@"
