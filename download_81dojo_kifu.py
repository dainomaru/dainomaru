#!/usr/bin/env python3
"""
81dojoからdainomaru選手の棋譜をダウンロードし、ShogiDroid用にKIF形式で保存するスクリプト。

使い方:
    pip install requests beautifulsoup4
    python3 download_81dojo_kifu.py

出力: kifu/ フォルダにKIFファイルが保存されます。
      そのフォルダをスマホに転送してShogiDroidで開いてください。
"""

import os
import re
import time
import zipfile
import argparse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

TARGET_USER = "dainomaru"
BASE_URL = "https://81dojo.com"
OUTPUT_DIR = Path("kifu")
DELAY = 1.0  # サーバー負荷軽減のためのウェイト(秒)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10; Mobile) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
})


def fetch(url: str, **kwargs) -> requests.Response:
    resp = SESSION.get(url, timeout=30, **kwargs)
    resp.raise_for_status()
    time.sleep(DELAY)
    return resp


def get_game_record_ids(username: str) -> list[str]:
    """ユーザーの対局IDリストを取得する。"""
    ids: list[str] = []
    page = 1

    while True:
        url = f"{BASE_URL}/members/{username}/game_records"
        params = {"page": page}
        print(f"  棋譜リスト取得中: page {page} ...")
        try:
            resp = fetch(url, params=params)
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                print(f"  ユーザー '{username}' が見つかりませんでした。")
            else:
                print(f"  HTTP エラー: {e}")
            break

        soup = BeautifulSoup(resp.text, "lxml")

        # 対局リンクを探す (例: /game_records/12345)
        links = soup.select("a[href*='/game_records/']")
        new_ids = []
        for link in links:
            href = link.get("href", "")
            m = re.search(r"/game_records/(\d+)", href)
            if m:
                gid = m.group(1)
                if gid not in ids:
                    new_ids.append(gid)

        if not new_ids:
            break

        ids.extend(new_ids)
        print(f"  {len(new_ids)} 件追加 (累計: {len(ids)} 件)")

        # 次ページが存在するか確認
        next_link = soup.select_one("a[rel='next'], .next a, a.next")
        if not next_link:
            break
        page += 1

    return ids


def download_kif(game_id: str, out_dir: Path) -> Path | None:
    """1対局のKIFファイルをダウンロードして保存する。"""
    out_path = out_dir / f"{game_id}.kif"
    if out_path.exists():
        return out_path  # スキップ(既存)

    # 81dojoのKIFダウンロードURL候補
    kif_urls = [
        f"{BASE_URL}/game_records/{game_id}.kif",
        f"{BASE_URL}/game_records/{game_id}/download.kif",
        f"{BASE_URL}/game_records/{game_id}?format=kif",
    ]

    for url in kif_urls:
        try:
            resp = fetch(url)
            content = resp.text
            # KIFファイルの簡易バリデーション
            if "手合割" in content or "▲" in content or "△" in content or "開始日時" in content:
                out_path.write_text(content, encoding="utf-8")
                return out_path
            # バイナリKIFの可能性
            if resp.content[:3] == b"\xef\xbb\xbf":  # UTF-8 BOM
                out_path.write_bytes(resp.content)
                return out_path
        except requests.HTTPError:
            continue
        except Exception as e:
            print(f"    警告: {url} -> {e}")
            continue

    # KIFが取れなかった場合はHTMLからKIF埋め込みを探す
    try:
        html_url = f"{BASE_URL}/game_records/{game_id}"
        resp = fetch(html_url)
        soup = BeautifulSoup(resp.text, "lxml")

        # pre/textarea/code タグにKIFが含まれることがある
        for tag in soup.select("pre, textarea, code"):
            text = tag.get_text()
            if "手合割" in text or "▲" in text or "△" in text:
                out_path.write_text(text, encoding="utf-8")
                return out_path

        # data属性やJSONにKIFが埋め込まれていることがある
        kif_match = re.search(r"(先手.*?(?:\n.*?){5,})", resp.text)
        if kif_match:
            out_path.write_text(kif_match.group(1), encoding="utf-8")
            return out_path

    except Exception as e:
        print(f"    警告(HTML解析): {e}")

    return None


def create_zip(out_dir: Path, zip_path: Path) -> None:
    """KIFファイル群をZIPにまとめる(スマホ転送用)。"""
    kif_files = list(out_dir.glob("*.kif"))
    if not kif_files:
        return
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in kif_files:
            zf.write(f, f.name)
    print(f"\nZIPファイル作成: {zip_path} ({len(kif_files)} 件)")


def print_shogiDroid_guide(zip_path: Path) -> None:
    print("\n" + "=" * 60)
    print("【ShogiDroidへの転送方法】")
    print("=" * 60)
    print(f"1. {zip_path} をスマホに転送します")
    print("   - USBケーブル、Google Drive、Dropbox などを使用")
    print("2. スマホでZIPを解凍し、KIFファイルをフォルダに置く")
    print("3. ShogiDroid を起動")
    print("4. メニュー → 棋譜を開く → フォルダを選択")
    print("5. 棋譜一覧からファイルを選んで解析スタート!")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="81dojo棋譜ダウンローダー")
    parser.add_argument("--user", default=TARGET_USER, help="81dojoユーザー名")
    parser.add_argument("--max", type=int, default=0, help="最大取得数 (0=全件)")
    parser.add_argument("--no-zip", action="store_true", help="ZIPを作成しない")
    args = parser.parse_args()

    username = args.user
    out_dir = OUTPUT_DIR / username
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"81dojo 棋譜ダウンローダー")
    print(f"ユーザー: {username}")
    print(f"保存先  : {out_dir}")
    print("-" * 40)

    # 1. 対局IDリストを取得
    print("[1/3] 対局リストを取得中...")
    game_ids = get_game_record_ids(username)
    if not game_ids:
        print("対局が見つかりませんでした。")
        print("ヒント: 81dojoでログインが必要な場合は --cookie オプションを検討してください。")
        return

    if args.max > 0:
        game_ids = game_ids[: args.max]
        print(f"取得上限: {args.max} 件")

    print(f"合計 {len(game_ids)} 件の対局を発見")

    # 2. KIFダウンロード
    print(f"\n[2/3] KIFファイルをダウンロード中...")
    ok, skip, fail = 0, 0, 0
    for i, gid in enumerate(game_ids, 1):
        print(f"  [{i}/{len(game_ids)}] game_id={gid}", end=" ... ", flush=True)
        result = download_kif(gid, out_dir)
        if result is None:
            print("失敗")
            fail += 1
        elif result.stat().st_size == 0:
            print("スキップ(空)")
            skip += 1
        else:
            print("OK")
            ok += 1

    print(f"\n結果: 成功={ok}, スキップ={skip}, 失敗={fail}")

    # 3. ZIP作成
    if not args.no_zip and ok > 0:
        print(f"\n[3/3] ZIPファイルを作成中...")
        zip_path = Path(f"{username}_kifu.zip")
        create_zip(out_dir, zip_path)
        print_shogiDroid_guide(zip_path)
    else:
        print(f"\nKIFファイルは {out_dir} に保存されました。")


if __name__ == "__main__":
    main()
