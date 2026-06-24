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
    python3 download_81dojo_kifu.py --csa       # KIF変換せずCSAで保存

参考: https://github.com/agt-the-walker/shogi-utils
"""

import argparse
import getpass
import json
import os
import re
import sys
import time
import zipfile
from pathlib import Path

import mechanicalsoup
import requests
import shogi.CSA
import shogi.KIF

# ── 設定 ──────────────────────────────────────────────────────────────
TARGET_USER  = "dainomaru"
SYSTEM_HOST  = "system.81dojo.com"
LOGIN_URL    = f"https://{SYSTEM_HOST}/en/players/sign_in"
SEARCH_URL   = f"https://{SYSTEM_HOST}/en/kifus/search/form"
KIFU_API_URL = f"https://{SYSTEM_HOST}/api/v2/kifus/{{}}.json"
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


def get_game_ids(browser: mechanicalsoup.StatefulBrowser, target_user: str) -> list[int]:
    """検索フォームを使って全対局IDを収集する。"""
    game_ids: set[int] = set()
    oldest_date: str | None = None

    while True:
        browser.open(SEARCH_URL)
        browser.select_form()

        # 初回のみフォームフィールド名を出力（デバッグ用）
        if oldest_date is None:
            form_el = browser.get_current_form().form
            field_names = [
                el.get("name", "")
                for el in form_el.find_all(["input", "select", "textarea"])
                if el.get("name")
            ]
            print(f"  フォームフィールド: {field_names[:30]}")

        # プレイヤー名フィルタ（複数の可能なフィールド名を試みる）
        player_set = False
        for fname in ["conditions[player_name]", "conditions[black_name]",
                      "conditions[white_name]", "q[player_name_cont]", "player_name"]:
            try:
                browser[fname] = target_user
                print(f"  プレイヤー名フィールド設定: {fname}")
                player_set = True
                break
            except mechanicalsoup.utils.LinkNotFoundError:
                pass
        if not player_set:
            print("  ⚠ プレイヤー名フィールドが見つかりませんでした（全棋譜対象）")

        # 1970-01-01 から全件検索（D-Milesが必要な場合はフィールドが存在しない）
        for fname in ["conditions[search_from]", "search_from"]:
            try:
                browser[fname] = "1970-01-01"
                break
            except mechanicalsoup.utils.LinkNotFoundError:
                pass

        if oldest_date:
            print(f"  再検索 (〜{oldest_date}) ...")
            for fname in ["conditions[search_until]", "search_until"]:
                try:
                    browser[fname] = oldest_date
                    break
                except mechanicalsoup.utils.LinkNotFoundError:
                    pass
        else:
            print("  全対局を検索中...")

        browser.submit_selected()
        page  = browser.get_current_page()
        print(f"  検索後URL: {browser.url}")
        table = page.find("table", class_="list")

        if not table:
            print("  検索テーブルが見つかりません。")
            tables = page.find_all("table")
            print(f"  ページ内テーブル数: {len(tables)}")
            for t in tables[:3]:
                print(f"    class={t.get('class', [])} id={t.get('id', '')}")
            break

        rows = table.find_all("tr")
        print(f"  テーブル行数: {len(rows)}")

        # 最初の3行の構造を出力（デバッグ用）
        for i, row in enumerate(rows[:3]):
            cells = row.find_all(["td", "th"])
            for j, cell in enumerate(cells):
                links = [(a.get("href", ""), a.get_text(strip=True)[:15])
                         for a in cell.find_all("a")]
                if links:
                    print(f"  行{i}列{j}: links={links}")

        new_found = False
        row_date: str | None = None
        for row in rows:
            cells = row.find_all("td")
            if not cells:
                continue
            # 全セルの全リンクから /kifus/数字 を抽出
            for cell in cells:
                for a in cell.find_all("a"):
                    href = a.get("href", "")
                    m = re.search(r'/kifus/(\d+)', href)
                    if m:
                        gid = int(m.group(1))
                        if gid not in game_ids:
                            game_ids.add(gid)
                            new_found = True
            # 日付追跡（2列目、ページング用）
            if len(cells) > 1:
                d = cells[1].get_text(strip=True)
                if d:
                    row_date = d

        if row_date:
            oldest_date = row_date

        if not new_found:
            if not game_ids:
                print("  テーブルにゲームリンクなし。テーブルHTML(先頭800文字):")
                print(f"  {str(table)[:800]}")
            break

        # 上限に達した場合は oldest_date で再検索してページング
        if page.find(string=re.compile("Number of matching kifus reached")):
            continue

        break

    result = sorted(game_ids)
    print(f"  合計 {len(result)} 件の対局を発見")
    return result


def fetch_game_json(session: requests.Session, game_id: int) -> dict | None:
    """APIから1対局のJSONを取得する。"""
    url = KIFU_API_URL.format(game_id)
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        time.sleep(DELAY)
        return resp.json()
    except Exception as e:
        print(f"    取得失敗 ({url}): {e}")
        return None


def csa_to_kif(csa_content: str, game_id: int) -> str | None:
    """CSA文字列をKIF文字列に変換する。変換失敗時は None を返す。"""
    # 'ILLEGAL_MOVE 行と直前の2手を除去（python-shogi がエラーになるため）
    lines = []
    for line in csa_content.splitlines():
        if not line:
            continue
        if line[0] in ("I", "#"):
            continue
        if line.startswith("'ILLEGAL_MOVE"):
            if len(lines) >= 2:
                del lines[-2:]
            continue
        lines.append(line)

    clean_csa = "\n".join(lines)
    try:
        games = shogi.CSA.Parser.parse_str(clean_csa)
        if not games:
            return None
        return shogi.KIF.Exporter().kif(games[0])
    except Exception as e:
        print(f"    KIF変換失敗 (game_id={game_id}): {e}")
        return None


def save_game(data: dict, game_id: int, out_dir: Path, use_csa: bool) -> Path | None:
    """1対局を KIF または CSA ファイルとして保存する。"""
    contents: str = data.get("contents", "")
    if not contents:
        print("    contents フィールドが空です")
        return None

    if use_csa:
        # CSA をそのまま保存
        path = out_dir / f"{game_id}.csa"
        path.write_text(contents, encoding="utf-8")
        return path

    # CSA → KIF 変換
    kif_text = csa_to_kif(contents, game_id)
    if kif_text is None:
        # 変換失敗でも CSA は保持
        path = out_dir / f"{game_id}.csa"
        path.write_text(contents, encoding="utf-8")
        print(f"    (KIF変換不可 → CSAで保存: {path.name})")
        return path

    path = out_dir / f"{game_id}.kif"
    path.write_text(kif_text, encoding="utf-8")
    return path


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
    parser.add_argument("--csa",     action="store_true",  help="KIF変換せずCSA形式で保存")
    parser.add_argument("--no-zip",  action="store_true",  help="ZIPを作成しない")
    args = parser.parse_args()

    out_dir = Path("kifu") / args.user
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 50)
    print(f"  81dojo 棋譜ダウンローダー")
    print(f"  対象ユーザー : {args.user}")
    print(f"  保存形式     : {'CSA' if args.csa else 'KIF (失敗時CSA)'}")
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
    browser.close()

    if not game_ids:
        print("対局が見つかりませんでした。")
        sys.exit(1)

    if args.max > 0:
        game_ids = game_ids[-args.max:]   # 最新N件
        print(f"最新 {args.max} 件に絞り込みました")

    # 棋譜ダウンロード
    print(f"\n[2/3] 棋譜をダウンロード中 ({len(game_ids)} 件)...")
    dl_session = requests.Session()
    dl_session.headers.update({"Referer": REFERER_URL})

    ok = skip = fail = 0
    for i, gid in enumerate(game_ids, 1):
        ext   = "csa" if args.csa else "kif"
        fpath = out_dir / f"{gid}.{ext}"

        prefix = f"  [{i:4d}/{len(game_ids)}] {gid}"
        if fpath.exists():
            print(f"{prefix} ... スキップ(既存)")
            skip += 1
            continue

        data = fetch_game_json(dl_session, gid)
        if data is None:
            print(f"{prefix} ... 失敗")
            fail += 1
            continue

        saved = save_game(data, gid, out_dir, args.csa)
        if saved:
            sz = saved.stat().st_size
            print(f"{prefix} ... OK ({saved.suffix}, {sz:,} bytes)")
            ok += 1
        else:
            print(f"{prefix} ... 失敗(保存エラー)")
            fail += 1

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
