#!/usr/bin/env python3
"""GitHub Actions CI用 CSA→KIF変換テスト"""
import shogi.CSA
import shogi.KIF

# PI = 平手初期配置を使ったCSA形式（81dojoのAPIレスポンスと同構造）
SAMPLE_CSA = """V2.2
N+dainomaru
N-opponent
PI
+
+2726FU
T5
-8384FU
T4
+7776FU
T3
-3334FU
T6
%TORYO"""

games = shogi.CSA.Parser.parse_str(SAMPLE_CSA)
assert games, "CSA解析失敗"

kif = shogi.KIF.Exporter().kif(games[0])
assert "dainomaru" in kif, "先手名が含まれていない"
assert "２六歩" in kif, "手順が含まれていない"

print("CSA→KIF変換テスト: OK")
print(kif)
