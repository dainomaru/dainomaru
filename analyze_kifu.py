#!/usr/bin/env python3
"""
将棋棋譜エンジン解析スクリプト
Fairy-Stockfish (largeboard) を使って KIF 棋譜を解析し、
評価値グラフと悪手レポートを生成する。

Usage:
    python3 analyze_kifu.py --engine ./fairy-stockfish --kif-dir kifu_files/
    python3 analyze_kifu.py --engine ./fairy-stockfish --kif game.kif
"""
import re
import subprocess
import shogi
import shogi.KIF
import sys
import argparse
from pathlib import Path


BLUNDER_THRESHOLD = 300  # 悪手: 評価値損失がこれ以上
MISTAKE_THRESHOLD = 100  # 疑問手: 評価値損失がこれ以上


class ShogiEngine:
    """Fairy-Stockfish との UCI 通信"""

    def __init__(self, path: str, movetime_ms: int):
        self.movetime = movetime_ms
        self.proc = subprocess.Popen(
            [path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._send("uci")
        self._wait("uciok")
        self._send("setoption name UCI_Variant value shogi")
        self._send("isready")
        self._wait("readyok")
        print("エンジン初期化完了", flush=True)

    def _send(self, cmd: str):
        try:
            self.proc.stdin.write(cmd + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError):
            pass

    def _wait(self, keyword: str) -> str:
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("エンジンが予期せず終了しました")
            if keyword in line:
                return line.strip()

    def eval(self, sfen: str) -> int | None:
        """局面を解析して手番側視点の評価値を返す"""
        if self.proc.poll() is not None:
            return None
        self._send(f"position fen {sfen}")
        self._send(f"go movetime {self.movetime}")
        score = None
        while True:
            raw = self.proc.stdout.readline()
            if not raw:  # EOF: エンジンが終了した
                break
            line = raw.strip()
            if not line:
                continue
            p = line.split()
            if "score cp" in line:
                try:
                    score = int(p[p.index("cp") + 1])
                except (ValueError, IndexError):
                    pass
            elif "score mate" in line:
                try:
                    n = int(p[p.index("mate") + 1])
                    score = 30000 if n > 0 else -30000
                except (ValueError, IndexError):
                    pass
            if line.startswith("bestmove"):
                break
        return score

    def close(self):
        try:
            self._send("quit")
            self.proc.wait(timeout=5)
        except Exception:
            self.proc.terminate()


def to_black(score: int | None, turn: int) -> int | None:
    """手番側評価値を先手(Black)視点に変換"""
    if score is None:
        return None
    return score if turn == shogi.BLACK else -score


def eval_bar(score: int, width: int = 30) -> str:
    """評価値を ASCII 棒グラフで表示 (中央=0, 右=先手有利)"""
    capped = max(-1000, min(1000, score))
    mid = width // 2
    pos = int(capped / 1000 * mid) + mid
    bar = [" "] * width
    bar[mid] = "│"
    if pos > mid:
        for j in range(mid + 1, min(pos + 1, width)):
            bar[j] = "█"
    elif pos < mid:
        for j in range(max(pos, 0), mid):
            bar[j] = "░"
    return "".join(bar)


def annotate_kif(kif_text: str, move_records: list, evals: list,
                 losses: list, blunder_thr: int, mistake_thr: int) -> str:
    """KIFテキストの各指し手行の後に評価値コメントを挿入する"""
    move_re = re.compile(r'^\s*(\d+)\s+\S')
    eval_map = {}
    for i, (num, turn, _) in enumerate(move_records):
        sc_before = evals[i] if i < len(evals) else None
        sc_after  = evals[i + 1] if i + 1 < len(evals) else None
        lo = losses[i] if i < len(losses) else None
        eval_map[num] = (turn, sc_before, sc_after, lo)

    result = []
    for line in kif_text.split("\n"):
        result.append(line)
        m = move_re.match(line)
        if not m:
            continue
        num = int(m.group(1))
        if num not in eval_map:
            continue
        turn, sc_before, sc_after, lo = eval_map[num]
        sb = f"{sc_before:+d}" if sc_before is not None else "?"
        sa = f"{sc_after:+d}" if sc_after is not None else "?"
        comment = f"*評価値: {sb}→{sa}"
        if lo is not None:
            comment += f"  損失:{lo:+d}"
            if lo >= blunder_thr:
                comment += "  ★悪手★"
            elif lo >= mistake_thr:
                comment += "  ▲疑問手"
        result.append(comment)
    return "\n".join(result)


def find_kif_list(kif_dir: Path) -> list[Path]:
    """日付が新しい順に KIF ファイルのリストを返す"""
    dated = []
    for kif in sorted(kif_dir.glob("*.kif")):
        content = kif.read_text(encoding="utf-8", errors="replace")
        date = ""
        for line in content.split("\n")[:15]:
            if "開始日時" in line:
                date = line.split("：", 1)[-1].strip()
                break
        dated.append((date, kif))
    dated.sort(reverse=True)
    return [kif for _, kif in dated]


def parse_kif(kif_text: str) -> dict:
    """KIF テキストを解析してゲーム情報を返す"""
    result = shogi.KIF.Parser.parse_str(kif_text)
    if isinstance(result, list):
        return result[0] if result else {}
    return result


def extract_moves(raw_moves: list) -> list:
    """raw_moves から有効な手(Move整数)のリストに変換する。
    python-shogi の KIF パーサは手を USI 形式文字列 ('7g7f' 等) で返す。
    shogi.Move.from_usi() で整数に変換し、resign 等の非手文字列は除外する。
    """
    valid = []
    for m in raw_moves:
        if isinstance(m, str):
            # USI形式文字列をMove整数に変換 ('7g7f', 'P*5e' 等)
            # 'resign', 'win' 等は from_usi で例外またはNullになりスキップ
            try:
                move_int = shogi.Move.from_usi(m)
                if move_int:
                    valid.append(move_int)
            except Exception:
                pass
        elif isinstance(m, int) and m > 0:
            valid.append(m)
        elif hasattr(m, 'to_square'):
            valid.append(m)
    return valid


def main():
    parser = argparse.ArgumentParser(description="将棋棋譜エンジン解析")
    parser.add_argument("--engine",   required=True, help="Fairy-Stockfish のパス")
    parser.add_argument("--kif",      help="解析する KIF ファイル")
    parser.add_argument("--kif-dir",  help="KIF ディレクトリ (最新を自動選択)")
    parser.add_argument("--output",     default="analysis_report.txt")
    parser.add_argument("--output-kif", default="analyzed_game.kif", help="解析対象KIFのコピー先")
    parser.add_argument("--movetime", type=int, default=300, help="1手あたり解析時間 (ms)")
    args = parser.parse_args()

    if args.kif:
        kif_candidates = [Path(args.kif)]
    elif args.kif_dir:
        kif_candidates = find_kif_list(Path(args.kif_dir))
        if not kif_candidates:
            sys.exit("KIF ファイルが見つかりません")
        print(f"候補棋譜: {len(kif_candidates)}件", flush=True)
    else:
        sys.exit("--kif または --kif-dir を指定してください")

    # 有効な手を持つKIFファイルを探す
    kif_path = None
    kif_text = ""
    game = {}
    moves = []

    for candidate in kif_candidates[:10]:  # 最大10件まで試す
        text = candidate.read_text(encoding="utf-8", errors="replace")
        g = parse_kif(text)
        raw = g.get("moves", [])
        m = extract_moves(raw)

        if m:
            kif_path, kif_text, game, moves = candidate, text, g, m
            print(f"最新棋譜: {candidate.name} ({len(moves)}手)", flush=True)
            break
        else:
            # デバッグ: なぜ手が取れないか表示
            types_str = ", ".join(
                f"{type(x).__name__}={repr(x)[:30]}"
                for x in raw[:3]
            ) if raw else "empty"
            print(f"スキップ: {candidate.name} (raw={len(raw)}件, [{types_str}])", flush=True)

    if kif_path is None or not moves:
        sys.exit("有効な棋譜が見つかりません (10件チェック済み)")

    names = game.get("names", [])

    # python-shogi は names をリスト [black_name, white_name] で返す
    if isinstance(names, list):
        black_name = names[shogi.BLACK] if len(names) > shogi.BLACK else "先手"
        white_name = names[shogi.WHITE] if len(names) > shogi.WHITE else "後手"
    else:
        black_name = names.get(shogi.BLACK, "先手")
        white_name = names.get(shogi.WHITE, "後手")

    date_str = "不明"
    for line in kif_text.split("\n")[:20]:
        if "開始日時" in line:
            date_str = line.split("：", 1)[-1].strip()
            break

    print(f"{'='*55}")
    print(f"  {black_name}(先手) vs {white_name}(後手)")
    print(f"  {date_str}  ({len(moves)}手)")
    print(f"  解析時間: {args.movetime}ms/手  推定: {len(moves)*args.movetime//1000}秒")
    print(f"{'='*55}")

    engine = ShogiEngine(args.engine, args.movetime)

    board = shogi.Board()
    move_records = []  # (move_num, turn, kif_label)
    evals = []         # 各局面の評価値 (先手視点)

    print(f"\n[解析中 ({len(moves)}手)]")
    for i, move in enumerate(moves):
        turn = board.turn
        try:
            kif_label = shogi.KIF.move_to_kif(move, board)
        except Exception:
            kif_label = f"手{i+1}"

        try:
            score = to_black(engine.eval(board.sfen()), turn)
        except Exception as e:
            print(f"  Warning: 手{i+1}評価失敗 ({e}), 解析を途中で終了", flush=True)
            break
        move_records.append((i + 1, turn, kif_label))
        evals.append(score)

        try:
            board.push(move)
        except Exception as e:
            print(f"  Warning: 手{i+1}適用失敗 ({e}), 解析を途中で終了", flush=True)
            break

        if (i + 1) % 20 == 0:
            pct = int((i + 1) / len(moves) * 100)
            print(f"  {i+1}/{len(moves)}手 ({pct}%)", flush=True)

    # 最終局面
    try:
        final_score = to_black(engine.eval(board.sfen()), board.turn)
    except Exception:
        final_score = None
    evals.append(final_score)
    engine.close()

    # 各手の評価値損失を計算
    losses = []
    for i, (_, turn, _) in enumerate(move_records):
        before, after = evals[i], evals[i + 1]
        if before is not None and after is not None:
            loss = (before - after) if turn == shogi.BLACK else (after - before)
        else:
            loss = None
        losses.append(loss)

    # 悪手・疑問手を抽出
    blunders = [
        (i, rec, lo)
        for i, (rec, lo) in enumerate(zip(move_records, losses))
        if lo is not None and lo >= BLUNDER_THRESHOLD
    ]
    mistakes = [
        (i, rec, lo)
        for i, (rec, lo) in enumerate(zip(move_records, losses))
        if lo is not None and MISTAKE_THRESHOLD <= lo < BLUNDER_THRESHOLD
    ]

    # レポート生成
    lines = []
    lines.append("=" * 62)
    lines.append("  将棋棋譜解析レポート")
    lines.append(f"  棋譜: {kif_path.name}")
    lines.append(f"  先手: {black_name}  後手: {white_name}")
    lines.append(f"  日付: {date_str}  手数: {len(move_records)}手")
    lines.append(f"  エンジン: Fairy-Stockfish  解析: {args.movetime}ms/手")
    lines.append("=" * 62)

    def fmt_move(idx, rec, lo):
        num, turn, label = rec
        player = black_name if turn == shogi.BLACK else white_name
        eb = evals[idx]
        ea = evals[idx + 1]
        sb = f"{eb:+d}" if eb is not None else "?"
        sa = f"{ea:+d}" if ea is not None else "?"
        return f"  {num:3d}手目 [{player}] {label}  {sb} → {sa}  (損失:{lo:+d})"

    lines.append("")
    lines.append(f"■ 悪手 (損失 {BLUNDER_THRESHOLD}以上): {len(blunders)}件")
    for item in sorted(blunders, key=lambda x: -x[2])[:8]:
        lines.append(fmt_move(*item))
    if not blunders:
        lines.append("  なし")

    lines.append("")
    lines.append(f"■ 疑問手 (損失 {MISTAKE_THRESHOLD}〜{BLUNDER_THRESHOLD}): {len(mistakes)}件")
    for item in sorted(mistakes, key=lambda x: -x[2])[:8]:
        lines.append(fmt_move(*item))
    if not mistakes:
        lines.append("  なし")

    lines.append("")
    lines.append("■ 評価値グラフ (▲先手 △後手  ??=悪手 ? =疑問手)")
    lines.append("   手  評価値    後手← ─────────── →先手")
    for i, (num, turn, label) in enumerate(move_records):
        sc = evals[i]
        lo = losses[i]
        if sc is None:
            continue
        mark = "??" if lo is not None and lo >= BLUNDER_THRESHOLD else \
               "? " if lo is not None and lo >= MISTAKE_THRESHOLD else "  "
        player_mark = "▲" if turn == shogi.BLACK else "△"
        sign = "+" if sc >= 0 else ""
        lines.append(
            f"   {num:3d}{player_mark} {sign}{sc:5d} {mark} {eval_bar(sc)}"
        )

    report = "\n".join(lines)
    Path(args.output).write_text(report, encoding="utf-8-sig")

    annotated = annotate_kif(
        kif_text, move_records, evals, losses,
        BLUNDER_THRESHOLD, MISTAKE_THRESHOLD
    )
    Path(args.output_kif).write_text(annotated, encoding="utf-8-sig")
    print(f"\n解析完了 → {args.output}")
    print(f"解析棋譜  → {args.output_kif} ({kif_path.name}, コメント付き)")
    print(f"悪手:{len(blunders)}件  疑問手:{len(mistakes)}件")
    print()
    print(report)


if __name__ == "__main__":
    main()
