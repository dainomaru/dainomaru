#!/usr/bin/env python3
"""
81dojo棋譜ダウンローダー (dainomaru用)

81dojoに自分のアカウントでログインし、dainomaru の全対局棋譜を
KIF形式でダウンロードしてShogiDroid用ZIPにまとめます。

必要パッケージ:
    pip install mechanicalsoup python-shogi requests

使い方:
    python3 download_81dojo_kifu.py
    python3 download_81dojo_kifu.py --max 30   # 最新30局のみ

参考: https://github.com/agt-the-walker/shogi-utils
"""

import argparse
import getpass
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import mechanicalsoup
import requests

# ── 設定 ──────────────────────────────────────────────────────────────
TARGET_USER  = "dainomaru"
SYSTEM_HOST  = "system.81dojo.com"
LOGIN_URL    = f"https://{SYSTEM_HOST}/en/players/sign_in"
SEARCH_URL   = f"https://{SYSTEM_HOST}/en/kifus/search/form"
KIFU_DL_URL  = f"https://{SYSTEM_HOST}/kifus/{{}}/download_kif.kif"
REFERER_URL  = "https://81dojo.com"

OUTPUT_DIR   = Path("kifu") / TARGET_USER
DELAY        = 0.8   # リクエスト間隔(秒) ── サーバー負荷軽減
# ──────────────────────────────────────────────────────────────────────


def get_credentials() -> tuple[str, str]:
    """~/.netrc 優先、なければ対話入力で認証情報を取得する。"""
    import netrc as netrc_mod
    try:
        n = netrc_mod.netrc()
        info = n.authenticators(SYSTEM_HOST)
        if info:
            print(f"~/.netrc から認証情報を読み込みました (user={info[0]})")
            return info[0], info[2]
    except (FileNotFoundError, netrc_mod.NetrcParseError):
        pass

    print("81dojoのログイン情報を入力してください。")
    username = input("  ユーザー名: ").strip()
    password = getpass.getpass("  パスワード: ")
    return username, password


def login(browser: mechanicalsoup.StatefulBrowser, user: str, pw: str) -> None:
    print("ログイン中...")
    browser.open(LOGIN_URL)
    browser.select_form()
    browser["player[name]"]     = user
    browser["player[password]"] = pw
    resp = browser.submit_selected()
    if "sign_in" in resp.url or "invalid" in resp.text.lower():
        sys.exit("ログインに失敗しました。ユーザー名とパスワードを確認してください。")
    print("ログイン成功")


def get_game_ids(browser: mechanicalsoup.StatefulBrowser, target_user: str) -> list[str]:
    """検索フォームを使って全対局IDを収集する（先手・後手の両方を検索）。"""
    game_ids: set[str] = set()

    # 先手(player1)と後手(player2)で2回検索してマージ
    for player_field in ["conditions[player1]", "conditions[player2]"]:
        browser.open(SEARCH_URL)
        browser.select_form()

        try:
            browser[player_field] = target_user
        except mechanicalsoup.utils.LinkNotFoundError:
            print(f"  フィールドなし: {player_field}")
            continue

        print(f"  検索中 ({player_field}={target_user})...")
        browser.submit_selected()
        page  = browser.get_current_page()
        table = page.find("table", class_="list")

        if not table:
            print(f"  テーブルなし ({player_field})")
            continue

        rows  = table.find_all("tr")
        before = len(game_ids)
        for row in rows:
            for cell in row.find_all("td"):
                for a in cell.find_all("a"):
                    href = a.get("href", "")
                    # 英数字の対局ID を /kifus/{id} から抽出
                    m = re.search(r'/kifus/([A-Za-z0-9]+)', href)
                    if m:
                        game_ids.add(m.group(1))

        added = len(game_ids) - before
        print(f"  {player_field}: {added} 件追加 (累計 {len(game_ids)} 件)")

    result = sorted(game_ids)
    print(f"  合計 {len(result)} 件の対局を発見")
    return result


def fetch_kif(session: requests.Session, game_id: str) -> str | None:
    """認証済みセッションで KIF を直接ダウンロードする。"""
    url = KIFU_DL_URL.format(game_id)
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        text = resp.text.strip()
        if not text:
            print(f"    空の応答 ({game_id})")
            return None
        time.sleep(DELAY)
        return text
    except Exception as e:
        print(f"    取得失敗 ({url}): {e}")
        return None


def create_zip(out_dir: Path, zip_path: Path) -> int:
    """KIF/CSAファイルをZIPにまとめてスマホ転送用に出力する。"""
    files = list(out_dir.glob("*.kif")) + list(out_dir.glob("*.csa"))
    if not files:
        return 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(files):
            zf.write(f, f.name)
    return len(files)


def print_guide(zip_path: Path) -> None:
    print()
    print("=" * 62)
    print("  ShogiDroid で解析する手順")
    print("=" * 62)
    print(f"  1. {zip_path}  をスマホに転送")
    print("       USBケーブル / Google Drive / Dropbox / LINE など")
    print("  2. スマホでZIPを解凍 → KIFファイルを任意フォルダへ")
    print("  3. ShogiDroid を起動")
    print("  4. 右上メニュー → 「棋譜を開く」→ フォルダを選択")
    print("  5. 棋譜リストからファイルをタップ → 「解析」ボタン")
    print()
    print("  ヒント: エンジン(YaneuraOuなど)を入れると詳細解析できます")
    print("=" * 62)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="81dojo棋譜ダウンローダー (ShogiDroid用)"
    )
    parser.add_argument("--user",    default=TARGET_USER, help="81dojoのターゲットユーザー名")
    parser.add_argument("--max",     type=int, default=0, help="最大取得件数 (0=全件)")
    parser.add_argument("--no-zip",  action="store_true",  help="ZIPを作成しない")
    args = parser.parse_args()

    out_dir = Path("kifu") / args.user
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print(f"  81dojo 棋譜ダウンローダー")
    print(f"  対象ユーザー : {args.user}")
    print(f"  保存先       : {out_dir}")
    print("=" * 50)

    # ログイン
    login_user, login_pw = get_credentials()
    browser = mechanicalsoup.StatefulBrowser(
        soup_config={"features": "lxml"},
    )
    browser.session.headers.update({"Referer": REFERER_URL})
    login(browser, login_user, login_pw)

    # 対局ID収集
    print("\n[1/3] 対局IDを収集中...")
    game_ids = get_game_ids(browser, args.user)
    # 認証クッキーをダウンロードセッションに引き継ぐ
    auth_cookies = dict(browser.session.cookies)
    browser.close()

    if not game_ids:
        print("対局が見つかりませんでした。")
        sys.exit(1)

    if args.max > 0:
        game_ids = game_ids[-args.max:]   # 最新N件
        print(f"最新 {args.max} 件に絞り込みました")

    # 棋譜ダウンロード（認証済みセッションで直接KIFを取得）
    print(f"\n[2/3] 棋譜をダウンロード中 ({len(game_ids)} 件)...")
    dl_session = requests.Session()
    dl_session.cookies.update(auth_cookies)
    dl_session.headers.update({"Referer": REFERER_URL})

    ok = skip = fail = 0
    for i, gid in enumerate(game_ids, 1):
        fpath = out_dir / f"{gid}.kif"

        prefix = f"  [{i:4d}/{len(game_ids)}] {gid}"
        if fpath.exists():
            print(f"{prefix} ... スキップ(既存)")
            skip += 1
            continue

        kif_text = fetch_kif(dl_session, gid)
        if kif_text is None:
            print(f"{prefix} ... 失敗")
            fail += 1
            continue

        fpath.write_text(kif_text, encoding="utf-8")
        sz = fpath.stat().st_size
        print(f"{prefix} ... OK ({sz:,} bytes)")
        ok += 1

    print(f"\n  結果: 成功={ok}  スキップ={skip}  失敗={fail}")

    # ZIP作成
    if not args.no_zip and ok > 0:
        print("\n[3/3] ZIPを作成中...")
        zip_path = Path(f"{args.user}_kifu.zip")
        count = create_zip(out_dir, zip_path)
        print(f"  作成完了: {zip_path} ({count} ファイル)")
        print_guide(zip_path)
    else:
        print(f"\n  棋譜ファイルは {out_dir} に保存されました。")


if __name__ == "__main__":
    main()
