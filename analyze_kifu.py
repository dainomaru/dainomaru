#!/usr/bin/env python3
"""
将棋棋譜エンジン解析スクリプト
Fairy-Stockfish (largeboard) を使って KIF 棋譜を解析し、
ShogiDroid 形式の *解析 コメント付き KIF と解析レポートを生成する。

Usage:
    python3 analyze_kifu.py --engine ./fairy-stockfish --kif-dir kifu_files/
    python3 analyze_kifu.py --engine ./fairy-stockfish --kif game.kif
"""
import re
import copy
import subprocess
import shogi
import shogi.KIF
import sys
import argparse
from pathlib import Path


BLUNDER_THRESHOLD = 300
MISTAKE_THRESHOLD = 100
ENGINE_NAME = "Fairy-Stockfish-largeboard"


class ShogiEngine:
    """Fairy-Stockfish との USI 通信（将棋ネイティブプロトコル）"""

    def __init__(self, path: str, movetime_ms: int, multipv: int = 10):
        self.movetime = movetime_ms
        self.multipv = multipv
        self.proc = subprocess.Popen(
            [path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._send("usi")
        self._wait("usiok")
        self._send(f"setoption name MultiPV value {multipv}")
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

    def eval_full(self, sfen: str) -> list[dict]:
        """MultiPV 解析。候補手リスト (multipv id 昇順) を返す。"""
        if self.proc.poll() is not None:
            return []
        self._send(f"position sfen {sfen}")
        self._send(f"go movetime {self.movetime}")
        candidates: dict[int, dict] = {}
        while True:
            raw = self.proc.stdout.readline()
            if not raw:
                break
            line = raw.strip()
            if not line:
                continue
            p = line.split()
            if line.startswith("info") and "score" in line and "depth" in line:
                try:
                    mid = int(p[p.index("multipv") + 1]) if "multipv" in p else 1
                    depth    = int(p[p.index("depth")    + 1]) if "depth"    in p else 0
                    seldepth = int(p[p.index("seldepth") + 1]) if "seldepth" in p else depth
                    nodes    = int(p[p.index("nodes")    + 1]) if "nodes"    in p else 0
                    time_ms  = int(p[p.index("time")     + 1]) if "time"     in p else 0
                    si = p.index("score")
                    if p[si + 1] == "cp":
                        score = int(p[si + 2])
                    elif p[si + 1] == "mate":
                        n = int(p[si + 2])
                        score = 30000 if n > 0 else -30000
                    else:
                        continue
                    pv = p[p.index("pv") + 1:] if "pv" in p else []
                    candidates[mid] = {
                        "depth": depth, "seldepth": seldepth,
                        "nodes": nodes, "time_ms": time_ms,
                        "score": score, "pv": pv,
                    }
                except (ValueError, IndexError):
                    pass
            if line.startswith("bestmove"):
                parts_bm = line.split()
                if len(parts_bm) >= 2 and parts_bm[1] not in ("(none)", "0000"):
                    bm = parts_bm[1]
                    # Fairy-Stockfish shogi USI does not output pv field;
                    # use bestmove as fallback for the top candidate
                    if 1 in candidates and not candidates[1]["pv"]:
                        candidates[1]["pv"] = [bm]
                break
        return [candidates[k] for k in sorted(candidates.keys())]

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


def pv_to_kif(pv_usi: list[str], board: shogi.Board, max_moves: int = 8) -> str:
    """UCI/USI 形式の読み筋を KIF 表記文字列に変換する"""
    parts = []
    b = copy.deepcopy(board)
    for usi in pv_usi[:max_moves]:
        try:
            m = shogi.Move.from_usi(usi)
            if not m:
                break
            prefix = "▲" if b.turn == shogi.BLACK else "△"
            parts.append(f"{prefix}{shogi.KIF.move_to_kif(m, b)}")
            b.push(m)
        except Exception:
            break
    return " ".join(parts)


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


def annotate_kif(kif_text: str, move_records: list,
                 boards_before: list[shogi.Board],
                 analysis_results: list[list[dict]]) -> str:
    """KIF テキストの各指し手行の後に ShogiDroid 形式の *解析 コメントを挿入する"""
    move_re = re.compile(r'^\s*(\d+)\s+\S')

    analysis_map: dict[int, tuple] = {}
    for (num, turn, _), board, results in zip(move_records, boards_before, analysis_results):
        analysis_map[num] = (turn, board, results)

    result = []
    for line in kif_text.split("\n"):
        result.append(line)
        m = move_re.match(line)
        if not m:
            continue
        num = int(m.group(1))
        if num not in analysis_map:
            continue
        turn, board, candidates = analysis_map[num]
        if not candidates:
            continue

        result.append(f"*Engines 0 {ENGINE_NAME}")

        c0 = candidates[0]
        ts = c0["time_ms"] / 1000
        time_str = f"{int(ts // 60):02d}:{ts % 60:04.1f}"
        score0 = c0["score"] if turn == shogi.BLACK else -c0["score"]
        pv0 = pv_to_kif(c0["pv"], board)
        result.append(
            f"*解析 0  時間 {time_str} 深さ {c0['depth']}/{c0['seldepth']} "
            f"ノード数 {c0['nodes']} 評価値 {score0} 読み筋 {pv0} "
        )

        for i, cand in enumerate(candidates[1:], start=2):
            score = cand["score"] if turn == shogi.BLACK else -cand["score"]
            pv = pv_to_kif(cand["pv"], board)
            result.append(
                f"*解析 0  候補{i} 深さ {cand['depth']} 評価値 {score} 読み筋 {pv} "
            )

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
    result = shogi.KIF.Parser.parse_str(kif_text)
    if isinstance(result, list):
        return result[0] if result else {}
    return result


def extract_moves(raw_moves: list) -> list:
    valid = []
    for m in raw_moves:
        if isinstance(m, str):
            try:
                move_int = shogi.Move.from_usi(m)
                if move_int:
                    valid.append(move_int)
            except Exception:
                pass
        elif isinstance(m, int) and m > 0:
            valid.append(m)
        elif hasattr(m, "to_square"):
            valid.append(m)
    return valid


def main():
    parser = argparse.ArgumentParser(description="将棋棋譜エンジン解析")
    parser.add_argument("--engine",      required=True, help="Fairy-Stockfish のパス")
    parser.add_argument("--kif",         help="解析する KIF ファイル")
    parser.add_argument("--kif-dir",     help="KIF ディレクトリ (最新を自動選択)")
    parser.add_argument("--output",      default="analysis_report.txt")
    parser.add_argument("--output-kif",  default="analyzed_game.kif")
    parser.add_argument("--movetime",    type=int, default=300, help="1手あたり解析時間 (ms)")
    parser.add_argument("--multipv",     type=int, default=10,  help="MultiPV 候補数")
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

    kif_path = None
    kif_text = ""
    game = {}
    moves = []

    for candidate in kif_candidates[:10]:
        text = candidate.read_text(encoding="utf-8", errors="replace")
        g = parse_kif(text)
        raw = g.get("moves", [])
        m = extract_moves(raw)

        if m:
            kif_path, kif_text, game, moves = candidate, text, g, m
            print(f"最新棋譜: {candidate.name} ({len(moves)}手)", flush=True)
            break
        else:
            types_str = ", ".join(
                f"{type(x).__name__}={repr(x)[:30]}"
                for x in raw[:3]
            ) if raw else "empty"
            print(f"スキップ: {candidate.name} (raw={len(raw)}件, [{types_str}])", flush=True)

    if kif_path is None or not moves:
        sys.exit("有効な棋譜が見つかりません (10件チェック済み)")

    names = game.get("names", [])
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
    print(f"  解析時間: {args.movetime}ms/手  MultiPV: {args.multipv}  推定: {len(moves)*args.movetime//1000}秒")
    print(f"{'='*55}")

    engine = ShogiEngine(args.engine, args.movetime, multipv=args.multipv)

    board = shogi.Board()
    move_records: list[tuple] = []
    evals: list[int | None] = []
    boards_before: list[shogi.Board] = []
    analysis_results: list[list[dict]] = []

    print(f"\n[解析中 ({len(moves)}手)]")
    for i, move in enumerate(moves):
        turn = board.turn
        try:
            kif_label = shogi.KIF.move_to_kif(move, board)
        except Exception:
            kif_label = f"手{i+1}"

        board_copy = copy.deepcopy(board)

        try:
            results = engine.eval_full(board.sfen())
        except Exception as e:
            print(f"  Warning: 手{i+1}評価失敗 ({e}), 解析を途中で終了", flush=True)
            break

        score = to_black(results[0]["score"], turn) if results else None
        move_records.append((i + 1, turn, kif_label))
        evals.append(score)
        boards_before.append(board_copy)
        analysis_results.append(results)

        try:
            board.push(move)
        except Exception as e:
            print(f"  Warning: 手{i+1}適用失敗 ({e}), 解析を途中で終了", flush=True)
            break

        if (i + 1) % 20 == 0:
            pct = int((i + 1) / len(moves) * 100)
            print(f"  {i+1}/{len(moves)}手 ({pct}%)", flush=True)

    try:
        final_results = engine.eval_full(board.sfen())
        final_score = to_black(final_results[0]["score"], board.turn) if final_results else None
    except Exception:
        final_score = None
    evals.append(final_score)
    engine.close()

    losses = []
    for i, (_, turn, _) in enumerate(move_records):
        before, after = evals[i], evals[i + 1]
        if before is not None and after is not None:
            loss = (before - after) if turn == shogi.BLACK else (after - before)
        else:
            loss = None
        losses.append(loss)

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

    lines = []
    lines.append("=" * 62)
    lines.append("  将棋棋譜解析レポート")
    lines.append(f"  棋譜: {kif_path.name}")
    lines.append(f"  先手: {black_name}  後手: {white_name}")
    lines.append(f"  日付: {date_str}  手数: {len(move_records)}手")
    lines.append(f"  エンジン: {ENGINE_NAME}  解析: {args.movetime}ms/手  MultiPV: {args.multipv}")
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

    annotated = annotate_kif(kif_text, move_records, boards_before, analysis_results)
    Path(args.output_kif).write_text(annotated, encoding="utf-8-sig")

    print(f"\n解析完了 → {args.output}")
    print(f"解析棋譜  → {args.output_kif} ({kif_path.name}, ShogiDroid形式コメント付き)")
    print(f"悪手:{len(blunders)}件  疑問手:{len(mistakes)}件")

    print()
    print(report)


if __name__ == "__main__":
    main()
