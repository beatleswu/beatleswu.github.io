"""
katago_explain.py — KataGo JSON → 死活解說 轉換層（強化版 v3）
--------------------------------------------------------------
與 v2 完全向下相容，新增四項術語偵測：

  v2 術語引擎（保留）：
    1. 空間術語   ← ownership 格局（擴大眼位、縮小眼位、點眼、佔據要點）
    2. 手筋術語   ← board_state 棋盤（撲、倒撲、立、尖、挖、夾）
    3. 棋型術語   ← 關鍵字 + 勝率波動（假眼、劫爭、雙活）

  v3 新增術語：
    5. 接不歸（No Escape）← 對方連回後仍氣盡被提（board_state 靜態計算）
    7. 假眼（座標版）    ← 正交全己方但對角被控（board_state 幾何判定）

  優先順序（手筋鏈）：
    撲/倒撲 → 接不歸 → 立/夾/挖/尖

【典型用途】
  # CLI
  python katago_explain.py katago_output.jsonl --board-size 9

  # 作為模組（在 app.py / precompute.py 中 import）
  from katago_explain import KataGoExplainer
  explainer = KataGoExplainer(board_size=9)
  text = explainer.explain(
      katago_json,
      player_color='B',
      wrong_move={'x':2,'y':3},
      sgf_comment='黑先活',
      board_state=board_2d,          # [[int]]，1=黑,-1=白,0=空；可 None
  )

【board_state 格式】
  board_state[y][x]  ←  y=0 為棋盤最上行
  值：1 = 黑子, -1 = 白子, 0 = 空點

【KataGo JSON 格式（analysis 模式）】
{
  "rootInfo": { "winrate": 0.847, "scoreLead": 3.2, "visits": 50 },
  "moveInfos": [
    { "move": "C3", "winrate": 0.891, "visits": 42,
      "scoreLead": 4.1, "pv": ["C3","D3","E3"] },
    ...
  ],
  "ownership": [...]   # 可選，長度 board_size²，值 -1(白)~+1(黑)
}
"""

import json
import sys
import argparse
import random
import re
from typing import Optional, List, Tuple

# ══════════════════════════════════════════════════════════════════════
# 座標系統
# ══════════════════════════════════════════════════════════════════════

# KataGo 使用「跳過 I」的字母系統
_COL_LETTERS = 'ABCDEFGHJKLMNOPQRST'

_POSITION_NAMES_9 = {
    (0,0):'左上角', (8,0):'右上角', (0,8):'左下角', (8,8):'右下角',
    (4,4):'天元',
    (2,2):'左上星', (6,2):'右上星', (2,6):'左下星', (6,6):'右下星',
}
_POSITION_NAMES_13 = {
    (0,0):'左上角', (12,0):'右上角', (0,12):'左下角', (12,12):'右下角',
    (6,6):'天元',
    (3,3):'左上星', (9,3):'右上星', (3,9):'左下星', (9,9):'右下星',
}


def _katago_label(x: int, y: int, board_size: int) -> str:
    """(0-indexed x, y) → KataGo/SGF 欄行標記，例如 'C3'。"""
    if x < 0 or y < 0 or x >= board_size or y >= board_size:
        return '?'
    col = _COL_LETTERS[x] if x < len(_COL_LETTERS) else str(x)
    row = board_size - y   # KataGo row 從下往上計數
    return f"{col}{row}"


def _parse_katago_label(label: str, board_size: int) -> Optional[dict]:
    """'C3' → {'x': 2, 'y': 6, 'label': 'C3'}，解析失敗回傳 None。"""
    if not label or label.lower() == 'pass':
        return None
    label = label.upper().strip()
    col_char = label[0]
    if col_char not in _COL_LETTERS:
        return None
    x = _COL_LETTERS.index(col_char)
    try:
        row_num = int(label[1:])
        y = board_size - row_num
    except ValueError:
        return None
    if x < 0 or x >= board_size or y < 0 or y >= board_size:
        return None
    return {'x': x, 'y': y, 'label': label}


def _position_desc(x: int, y: int, board_size: int) -> str:
    """
    座標轉人類可讀位置描述。
    先查常見位置字典，否則依區域（角/邊/中腹）描述。
    """
    names = _POSITION_NAMES_9 if board_size <= 9 else _POSITION_NAMES_13
    if (x, y) in names:
        return names[(x, y)]

    label = _katago_label(x, y, board_size)
    near_left  = x <= 2
    near_right = x >= board_size - 3
    near_top   = y <= 2
    near_bot   = y >= board_size - 3

    if   near_top and near_left:   region = '左上角附近'
    elif near_top and near_right:  region = '右上角附近'
    elif near_bot and near_left:   region = '左下角附近'
    elif near_bot and near_right:  region = '右下角附近'
    elif near_top:                 region = '上邊'
    elif near_bot:                 region = '下邊'
    elif near_left:                region = '左邊'
    elif near_right:               region = '右邊'
    else:                          region = '中腹'

    return f"{label}（{region}）"


# ══════════════════════════════════════════════════════════════════════
# 數值翻譯
# ══════════════════════════════════════════════════════════════════════

def _score_desc(score_lead: float) -> str:
    """scoreLead（正=黑棋領先目數）→ 文字描述。"""
    s = abs(score_lead)
    color = '黑棋' if score_lead >= 0 else '白棋'
    if s < 1:   return '目差幾乎看不出來，誰都沒跑掉'
    elif s < 3: return f'{color}約領先 {s:.1f} 目'
    elif s < 8: return f'{color}領先 {s:.1f} 目，差距越來越明顯'
    else:       return f'{color}已是大優，領先 {s:.1f} 目'


# ══════════════════════════════════════════════════════════════════════
# 棋盤輔助工具
# ══════════════════════════════════════════════════════════════════════

def _get_neighbors(x: int, y: int, bs: int) -> List[Tuple[int, int]]:
    """回傳四方向合法鄰點列表。"""
    return [(x + dx, y + dy)
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]
            if 0 <= x + dx < bs and 0 <= y + dy < bs]


def _get_diagonals(x: int, y: int, bs: int) -> List[Tuple[int, int]]:
    """回傳四對角合法鄰點列表。"""
    return [(x + dx, y + dy)
            for dx, dy in [(-1, -1), (-1, 1), (1, -1), (1, 1)]
            if 0 <= x + dx < bs and 0 <= y + dy < bs]


def _stone(x: int, y: int, board) -> int:
    """
    取棋盤 (x,y) 的棋子值。
    board 為 None 或座標越界時回傳 0（空點）。
    """
    if board is None:
        return 0
    if y < 0 or y >= len(board) or x < 0 or x >= len(board[0]):
        return 0
    return board[y][x]


def _player_int(player_color: str) -> int:
    """'B' → 1,  'W' → -1"""
    return 1 if player_color == 'B' else -1


# ══════════════════════════════════════════════════════════════════════
# ❶ 手筋偵測（需要 board_state）
#    支援：撲、倒撲、立、尖、挖、夾
# ══════════════════════════════════════════════════════════════════════

def _detect_tesuji(
    x: int,
    y: int,
    player_color: str,
    board_state,          # 2D list [y][x]: 1=黑,-1=白,0=空；可 None
    bs: int,
    pv: Optional[List[dict]] = None,
) -> List[Tuple[str, str]]:
    """
    偵測落子 (x,y) 的手筋類型（需提供 board_state）。

    Parameters
    ----------
    x, y         : 落子座標（0-indexed）
    player_color : 'B' 或 'W'
    board_state  : 落子前的棋盤狀態 [y][x]；None → 回傳空列表
    bs           : 棋盤大小
    pv           : KataGo 建議的後續變化列表（用於倒撲偵測）

    Returns
    -------
    List of (術語, 解說) tuples，按重要性排序。
    """
    if board_state is None:
        return []

    pi  = _player_int(player_color)   # 己方：1 or -1
    opp = -pi                          # 對方

    nbrs  = _get_neighbors(x, y, bs)
    diags = _get_diagonals(x, y, bs)

    opp_nbr_count  = sum(1 for nx, ny in nbrs  if _stone(nx, ny, board_state) == opp)
    own_nbr_count  = sum(1 for nx, ny in nbrs  if _stone(nx, ny, board_state) == pi)
    opp_diag_count = sum(1 for dx, dy in diags if _stone(dx, dy, board_state) == opp)
    own_diag_count = sum(1 for dx, dy in diags if _stone(dx, dy, board_state) == pi)

    results = []

    # ── 撲 / 倒撲 ─────────────────────────────────────────────────────
    # 撲（Throw-in）：落入對方虎口（3個以上鄰子為對方棋子）
    is_throw_in = opp_nbr_count >= 3
    if is_throw_in:
        # 進一步判斷是否「倒撲（Snapback）」：
        #   pv[0] = 撲（即此手 best_move）
        #   pv[1] = 對方提子
        #   pv[2] = 己方在附近反提
        # 判斷標準：pv[2] 距 pv[1] 的 Manhattan 距離 ≤ 2
        is_snapback = False
        if pv and len(pv) >= 3:
            p1 = pv[1]   # 對方應手（提子）
            p2 = pv[2]   # 己方反提
            dist = abs(p2['x'] - p1['x']) + abs(p2['y'] - p1['y'])
            if dist <= 2:
                is_snapback = True

        if is_snapback:
            results.append((
                '倒撲',
                '一子飛身入虎口？別慌，這是蓄謀已久的「倒撲」！'
                '對方若手癢提了這顆棋——哈，整塊棋瞬間全進你口袋。'
                '教科書級別的釣魚手法，初中階死活的必學陷阱。'
            ))
        else:
            results.append((
                '撲',
                '直接把棋子送進對方嘴裡——「撲」！'
                '表面上是「喂，你吃！」，實際上是「吃了就中計了」。'
                '犧牲一小卒，破掉對方整個眼形，看似自殺，實為毒計。'
            ))
        # 撲/倒撲 已是最強烈的手筋特徵，通常不再疊加其他
        return results

    # ── 立（Descend） ────────────────────────────────────────────────
    # 從二路（第 2 線）向下落到一路（第 1 線）
    on_first_line = (x == 0 or x == bs - 1 or y == 0 or y == bs - 1)
    if on_first_line:
        for nx, ny in nbrs:
            if _stone(nx, ny, board_state) == pi:
                on_second = (nx == 1 or nx == bs - 2 or ny == 1 or ny == bs - 2)
                if on_second:
                    results.append((
                        '立',
                        '「立」下一子，沿邊路踩穩腳跟。別小看這一手——'
                        '氣數加了、眼形穩了，對方的活動空間也跟著縮水。'
                        '低調，但非常管用。'
                    ))
                    break

    # ── 夾（Clamp） ──────────────────────────────────────────────────
    # 在二路，新子與既有己方子夾住對方的一路棋子
    # 模式（方向向量任意）：[新子] — [對方子] — [己方子]  同直線
    on_second_line = (x == 1 or x == bs - 2 or y == 1 or y == bs - 2)
    if on_second_line:
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            ox, oy = x + dx, y + dy    # 對方棋子期望位置
            ex, ey = x + 2*dx, y + 2*dy  # 己方棋子期望位置
            if (0 <= ox < bs and 0 <= oy < bs and
                    0 <= ex < bs and 0 <= ey < bs):
                if (_stone(ox, oy, board_state) == opp and
                        _stone(ex, ey, board_state) == pi):
                    results.append((
                        '夾',
                        '「夾」！把對方的棋子夾進三明治裡——'
                        '左邊是你、右邊也是你，中間那顆對方棋子：「我逃得了嗎……逃不了。」'
                        '邊路破眼的基本功，簡單有效。'
                    ))
                    break

    # ── 挖（Wedge） ──────────────────────────────────────────────────
    # 插進對方兩顆棋子的正中間：左右兩側、或上下兩側都是對方棋子
    # （對方一間跳/尖形的中間點，強行製造斷點）
    wedge_h = (_stone(x - 1, y, board_state) == opp and
               _stone(x + 1, y, board_state) == opp)
    wedge_v = (_stone(x, y - 1, board_state) == opp and
               _stone(x, y + 1, board_state) == opp)
    if wedge_h or wedge_v:
        results.append((
            '挖',
            '像釘子一樣「挖」進對方兩顆棋子的正中間，強行製造斷點。'
            '對方：「我以為我們是連著的……」'
            '你：「不好意思，現在不是了。」氣緊從這一刻正式開始。'
        ))

    # ── 尖（Kosumi） ─────────────────────────────────────────────────
    # 與己方棋子斜向連結，且正交方向無任何鄰子（己方=非延伸；對方=非靠頂）
    # 一路上的棋另有專門手段（立/夾/撲），不稱「尖」
    if (own_diag_count >= 1 and own_nbr_count == 0
            and opp_nbr_count == 0 and not on_first_line):
        results.append((
            '尖',
            '斜向走一步「尖」，和自己的子保持切不斷的聯絡——'
            '對方從哪邊衝過來，都接得回去。'
            '看似慢一拍，其實無懈可擊，是棋盤上最堅實的步伐。'
        ))

    return results


# ══════════════════════════════════════════════════════════════════════
# 手筋判定統一入口（兩個解說分支共用，避免邏輯分叉）
#   優先級：人工 override → 高信心規則（撲/倒撲/立/尖/挖/夾、接不歸）
#   判不出來時回 None，由呼叫端使用不報術語的通用解說。
# ══════════════════════════════════════════════════════════════════════

def _select_tactic(
    x: int,
    y: int,
    player_color: str,
    board_state,
    bs: int,
    pv_list=None,
    override: Optional[dict] = None,
    best_label: Optional[str] = None,
) -> Optional[Tuple[str, str]]:
    """
    回傳 (術語, 解說) 或 None。

    override   : {'tactic': str, 'reason'?: str, 'move'?: str}（可選）人工權威標籤，最優先。
    best_label : 目前判定的「正解」標記（如 'O16'）。若 override 指定了 move，
                 只有在 move == best_label 時才套用，避免缺 correctMoves 時
                 best 退回成快取應手，卻把標籤貼到錯的手上。
    """
    if isinstance(override, dict) and isinstance(override.get('tactic'), str) \
            and override['tactic'].strip():
        want_move = str(override.get('move') or '').strip().upper()
        have_move = str(best_label or '').strip().upper()
        # move 必須存在且與 best 相符才套用；缺 move 或不符 → 不套用，改走幾何偵測，
        # 避免缺 correctMoves 時 best 退回快取應手，卻把標籤貼到錯的手上。
        if want_move and have_move and want_move == have_move:
            return (override['tactic'].strip(), (override.get('reason') or '').strip())

    hits = (
        _detect_tesuji(x, y, player_color, board_state, bs, pv_list)
        or _detect_no_escape(x, y, player_color, board_state, bs, pv_list)
    )
    return hits[0] if hits else None


# ══════════════════════════════════════════════════════════════════════
# ❶-c 接不歸偵測
#       落子後對方嘗試提子或接回，仍有棋子因氣數不足被提取
#       偵測方式：落點正交鄰格的對方棋子其氣數（不含落點格）≤ 1
# ══════════════════════════════════════════════════════════════════════

def _count_liberties(gx: int, gy: int, board_state, bs: int, color: int,
                     visited=None) -> int:
    """
    計算以 (gx, gy) 為起點之連通塊的氣數（BFS/flood-fill）。
    visited 為 set，避免重複計算。
    """
    if visited is None:
        visited = set()
    if (gx, gy) in visited:
        return 0
    visited.add((gx, gy))

    liberties = set()
    stack = [(gx, gy)]
    while stack:
        cx, cy = stack.pop()
        for nx, ny in _get_neighbors(cx, cy, bs):
            if (nx, ny) in visited:
                continue
            val = board_state[ny][nx]
            if val == 0:
                liberties.add((nx, ny))
            elif val == color:
                visited.add((nx, ny))
                stack.append((nx, ny))
    return len(liberties)


def _detect_no_escape(
    x: int,
    y: int,
    player_color: str,
    board_state,
    bs: int,
    pv: Optional[List[dict]] = None,
) -> List[Tuple[str, str]]:
    """
    偵測「接不歸」：
      策略 A（靜態）：
        落點鄰格中有對方棋子，其氣數（不含落點格）≤ 1，
        即使連回也無法逃脫（接不歸）。
      策略 B（PV 動態）：
        pv[1]（對方應手）後，pv[2] 能立即提取對方大塊。

    Returns
    -------
    最多一條 (術語, 解說) tuple，或空列表。
    """
    if board_state is None:
        return []

    pi  = _player_int(player_color)
    opp = -pi

    nbrs = _get_neighbors(x, y, bs)
    opp_nbrs = [(nx, ny) for nx, ny in nbrs if _stone(nx, ny, board_state) == opp]

    for (ox, oy) in opp_nbrs:
        # 計算對方連通塊氣數，但「假設落點已被我方佔據」（即不把落點算作氣）
        # 方法：把落點暫時設為己方，再算氣
        temp_board = [row[:] for row in board_state]
        temp_board[y][x] = pi  # 模擬落子
        libs = _count_liberties(ox, oy, temp_board, bs, opp)
        if libs == 0:
            return [('提子',
                '這一手直接把對方的棋提下來！氣數歸零，'
                '盤面上少掉的那幾顆子，就是最直接的戰果。'
                '先確認提完之後自己的棋形是否安全，別提了小的丟了大的。')]
        if libs == 1:
            return [('叫吃',
                '緊湊的「叫吃」！對方那塊棋只剩最後一口氣。'
                '逃？接？怎麼應都得先想清楚——'
                '很多時候不管怎麼接都是接不歸，魚已經在網裡了。')]

    return []


# ══════════════════════════════════════════════════════════════════════
# ❶-d 假眼座標偵測（board_state 版）
#       落點為空點，且對角線中有 ≥ (邊/角調整) 個對方棋子 → 判定為假眼
# ══════════════════════════════════════════════════════════════════════

def _detect_false_eye_at(
    x: int,
    y: int,
    player_color: str,
    board_state,
    bs: int,
) -> bool:
    """
    判斷 (x,y) 空點是否構成對 player_color 的「假眼」。

    真眼條件（黑棋為例）：
      - 四正交鄰點全為黑子（或棋盤邊界）
      - 對角線數：角落佔1個，邊上佔2個，中腹佔3個以上 → 需全部被黑棋控制

    假眼判定：
      正交全為己方（或邊界），但對角線中對方棋子數達上述閾值
    """
    if board_state is None:
        return False

    pi  = _player_int(player_color)
    opp = -pi

    nbrs  = _get_neighbors(x, y, bs)
    diags = _get_diagonals(x, y, bs)

    # 正交全為己方（或邊界）
    for nx, ny in nbrs:
        v = board_state[ny][nx]
        if v != pi:
            return False

    opp_diags = sum(1 for dx, dy in diags if board_state[dy][dx] == opp)

    # 閾值依位置（角/邊/中腹）決定
    on_edge = (x == 0 or x == bs-1 or y == 0 or y == bs-1)
    on_corner = ((x == 0 or x == bs-1) and (y == 0 or y == bs-1))
    if on_corner:
        threshold = 1   # 角落：1個對角被佔即成假眼
    elif on_edge:
        threshold = 2   # 邊：2個對角被佔即成假眼
    else:
        threshold = 3   # 中腹：3個對角被佔即成假眼

    return opp_diags >= threshold


# ══════════════════════════════════════════════════════════════════════
# ❷ 空間術語分析（使用 ownership 格局）
#    支援：點眼/點入、縮小眼位、佔據要點、擴大眼位
# ══════════════════════════════════════════════════════════════════════

# ownership 閾值：超過此絕對值視為「明確領地」
_OWN_THRESHOLD = 0.35


def _analyze_spatial(
    x: int,
    y: int,
    player_color: str,
    ownership_grid,   # 2D list [y][x]: +1=黑方絕對領地, -1=白方；可 None
    bs: int,
) -> List[Tuple[str, str]]:
    """
    利用 KataGo 的 ownership 格局分析落點的空間語意。

    ownership 值意義（從 player_color 視角正規化）：
      > +_OWN_THRESHOLD  → 己方領地
      < -_OWN_THRESHOLD  → 對方領地
      接近 0             → 爭議地帶 / 要點

    Returns
    -------
    List of (術語, 解說) tuples，最多一條（取最強特徵）。
    """
    if not ownership_grid:
        return []

    pi_sign = 1.0 if player_color == 'B' else -1.0
    T = _OWN_THRESHOLD

    # 落點 ownership（己方視角：正=己方）
    own_val = ownership_grid[y][x] * pi_sign

    nbrs     = _get_neighbors(x, y, bs)
    nbr_vals = [ownership_grid[ny][nx] * pi_sign for nx, ny in nbrs]

    opp_nbr_count = sum(1 for v in nbr_vals if v < -T)    # 對方強領地鄰格數
    own_nbr_count = sum(1 for v in nbr_vals if v > T)     # 己方強領地鄰格數

    # ── 點眼 / 點入 ───────────────────────────────────────────────────
    # 落點深入對方領地（own_val < -0.5）且周圍多為對方領地（≥3 鄰格）
    if own_val < -0.5 and opp_nbr_count >= 3:
        return [('點眼',
                 '直接戳進對方眼位的正中心——「點眼」！'
                 '這裡落子等於當面宣告：「你的眼是假的，你活不了。」'
                 '最直接、最殘忍、效果也最好。')]

    # ── 縮小眼位 ─────────────────────────────────────────────────────
    # 落點在對方領地邊緣，且有 2+ 對方鄰格
    if own_val < -T and opp_nbr_count >= 2:
        return [('縮小眼位',
                 '從外側一點一點擠進去——「縮小眼位」就像在幫對方的房子「裝修」：'
                 '不是在幫忙，是在把牆壁往內推。空間越來越小，對方活棋越來越難。')]

    # ── 佔據要點 ─────────────────────────────────────────────────────
    # 落點在中性地帶（接近要點），且鄰格中有對方領地
    if -T <= own_val < 0 and opp_nbr_count >= 1:
        return [('佔據要點',
                 '先搶這個點！這裡是雙方都想要的「急所」。'
                 '你拿了能防止對方做眼；對方拿了就直接破掉你的計劃。'
                 '誰慢一步，誰哭。')]

    # ── 擴大眼位 ─────────────────────────────────────────────────────
    # 落點在己方領地邊緣，且有 2+ 己方鄰格
    if own_val > T and own_nbr_count >= 2:
        return [('擴大眼位',
                 '把家的地基再打大一點——「擴大眼位」！'
                 '兩個真眼不是從天上掉下來的，先有空間、再有眼。'
                 '這是死活的基本常識，千萬別省這一步。')]

    # ── 一般中性要點 ─────────────────────────────────────────────────
    if -0.2 < own_val < 0.2 and len(nbrs) >= 3:
        return [('佔據要點',
                 '這裡是雙方都想踩的地板中央——搶到手的那方說了算，'
                 '讓出去的那方只能乖乖跟著對方的節奏走。')]

    return []


# ══════════════════════════════════════════════════════════════════════
# ❸ 棋型術語偵測（劫爭、雙活、假眼）
# ══════════════════════════════════════════════════════════════════════

def _detect_special_pattern(
    top_moves: list,
    sgf_comment: Optional[str] = None,
    best_move: Optional[dict] = None,
    player_color: str = 'B',
    board_state=None,
    bs: int = 9,
) -> List[Tuple[str, str]]:
    """
    偵測劫爭、雙活、假眼等特殊棋型。

    偵測途徑：
      1. SGF C[...] 解說關鍵字比對
      2. 前兩手勝率差值 < 5% → 可能存在劫爭
      3. board_state 座標分析 → 假眼（對方為 player_color 視角）

    Returns
    -------
    List of (術語, 解說) tuples。
    """
    results = []

    # ── 座標型假眼偵測（優先，無需 SGF 關鍵字）────────────────────────
    # 偵測「最佳手落點本身」是否為對方（即我們要攻入）的假眼
    if best_move and board_state:
        opp_color = 'W' if player_color == 'B' else 'B'
        if _detect_false_eye_at(best_move['x'], best_move['y'],
                                opp_color, board_state, bs):
            results.append(('假眼（座標偵測）',
                '⚠️ [假眼] 偵測到對方的「假眼」！四周看起來全是自己人圍著，'
                '但斜角那幾格早就被你方控制了——對方以為有眼？眼是有，活不了。'
                '打進去就是答案。'))
            return results  # 假眼確認，不再疊加其他標籤

    # ── 關鍵字比對 ────────────────────────────────────────────────────
    if sgf_comment:
        c = sgf_comment  # 保留原始大小寫（中文）
        cl = sgf_comment.lower()  # 英文關鍵字用小寫比對

        if '劫' in c or ' ko' in cl or cl.startswith('ko'):
            results.append(('劫爭',
                '🔔 [劫爭] 這局得打「劫」！死活不是直接判定，是靠劫材談判的。'
                '你有劫材、我有劫材，大家出牌看誰先撐不住。'
                '記得觀察盤面誰的劫材更多、更大。'))

        elif '雙活' in c or 'seki' in cl:
            results.append(('雙活',
                '🔔 [雙活（Seki）] 最後雙方互瞪著對方，誰也不敢下、誰也不能下——「雙活」！'
                '這叫共存，不叫輸贏。沒有眼也不死，因為動了反而死。'
                '目數也不算，接受現實就好。'))

        elif '假眼' in c:
            results.append(('假眼',
                '⚠️ [假眼] 等一下！這個「眼」是假的！'
                '對角被對方佔了關鍵位置，整個眼位就此穿幫。'
                '分清真假眼，是死活題的第一道門檻，也是最多人踩坑的地方。'))

        elif '大豬嘴' in c or '大猪嘴' in c:
            results.append(('大豬嘴',
                '🐷 [大豬嘴] 角落出現「大豬嘴」！這個棋形有個響亮的名字不是沒原因的——'
                '幾乎是死棋的代名詞。固定結論請記起來，考試很常出現，段位賽更常遇到。'))

        elif '小豬嘴' in c or '小猪嘴' in c:
            results.append(('小豬嘴',
                '🐷 [小豬嘴] 「小豬嘴」棋形現身！比大豬嘴稍有不同，'
                '但也是角落死活的常見面孔。此形有固定結論，'
                '搞清楚攻守方向再下手，別憑感覺亂猜。'))

    # ── 勝率波動偵測劫爭（無 SGF 關鍵字時） ─────────────────────────
    if not results and len(top_moves) >= 2:
        wr1 = top_moves[0]['winrate']
        wr2 = top_moves[1]['winrate']
        # 兩手勝率幾乎相同，且都不是必死 / 必活
        if abs(wr1 - wr2) < 5.0 and wr1 > 42 and wr2 > 42:
            results.append(('劫爭候選',
                '🔍 [劫爭？] 前兩個候選手的勝率差距小到可疑……'
                '這局面搞不好藏著劫爭。KataGo 也在猶豫，你也需要想一想——'
                '誰的劫材更多，誰先打劫。'))

    return results


# ══════════════════════════════════════════════════════════════════════
# 主類別：KataGoExplainer
# ══════════════════════════════════════════════════════════════════════

class KataGoExplainer:
    """
    將 KataGo 的 JSON 輸出解析為可讀的圍棋死活解說。

    Parameters
    ----------
    board_size : int
        棋盤大小（通常 9、13、19）
    """

    def __init__(self, board_size: int = 9):
        self.board_size = board_size

    # ── 解析 KataGo JSON ──────────────────────────────────────────────

    def parse(self, katago_json: dict) -> dict:
        """
        解析 KataGo analysis JSON，回傳結構化資料（與 v1 相容）。

        Returns
        -------
        {
          'winrate'        : float,          # 0–100，當前走棋方勝率
          'score_lead'     : float,          # 正=黑方領先目數
          'best_move'      : {x,y,label} | None,
          'top_moves'      : [...],          # 最多 3 個推薦手
          'ownership_grid' : [[float]] | None,
        }
        """
        root_info  = katago_json.get('rootInfo', {})
        move_infos = katago_json.get('moveInfos', [])
        ownership  = katago_json.get('ownership', [])
        bs = self.board_size

        top_moves = []
        for mi in move_infos[:3]:
            mv = _parse_katago_label(mi.get('move', ''), bs)
            if not mv:
                continue
            pv_parsed = []
            for pv_label in mi.get('pv', [])[:6]:
                p = _parse_katago_label(pv_label, bs)
                if p:
                    pv_parsed.append(p)
            top_moves.append({
                'move':    mv,
                'winrate': round(mi.get('winrate', 0) * 100, 1),
                'visits':  mi.get('visits', 0),
                'pv':      pv_parsed,
            })

        ownership_grid = None
        if ownership and len(ownership) == bs * bs:
            ownership_grid = [
                [round(ownership[y * bs + x], 2) for x in range(bs)]
                for y in range(bs)
            ]

        return {
            'winrate':        round(root_info.get('winrate', 0.5) * 100, 1),
            'score_lead':     round(root_info.get('scoreLead', 0), 1),
            'top_moves':      top_moves,
            'best_move':      top_moves[0]['move'] if top_moves else None,
            'ownership_grid': ownership_grid,
        }

    # ── 生成解說文字 ──────────────────────────────────────────────────

    def _explain_english(
        self,
        *,
        player_color: str,
        wrong_move: Optional[dict],
        sgf_comment: Optional[str],
        q_info: Optional[dict],
        board_state,
        correct_moves: Optional[List[dict]],
        override: Optional[dict],
        best: Optional[dict],
        top_moves: list,
        best_is_authoritative: bool,
    ) -> str:
        """Build a conservative English explanation from verified board data."""
        parts = []

        def english_only(value):
            value = str(value or '').strip()
            return '' if re.search(r'[\u3400-\u9fff]', value) else value

        if q_info:
            topic = english_only(q_info.get('topic_en'))
            level = english_only(q_info.get('level_en'))
            display = english_only(q_info.get('display_name_en'))
            diff = english_only(q_info.get('difficulty'))
            labels = []
            for value in (topic, level):
                if value and value.lower() != 'unknown' and value not in labels:
                    labels.append(value)
            if not labels and display:
                labels.append(display)
            if not labels and q_info.get('id') is not None:
                labels.append(f"Problem {q_info['id']}")
            if diff:
                labels.append(f'({diff})')
            if labels:
                parts.append('📌 ' + ' · '.join(labels))

        wrong_label = None
        if wrong_move:
            wrong_label = _katago_label(wrong_move['x'], wrong_move['y'], self.board_size)
            if best and best_is_authoritative:
                parts.append(
                    f'{wrong_label} is close, but it misses the key point. '
                    f'The correct move is {best["label"]}.'
                )
            elif best:
                parts.append(
                    f'After {wrong_label}, the system suggests {best["label"]} as the best response. '
                    'This is a KataGo reference, not a stored problem answer.'
                )
            else:
                parts.append(
                    f'{wrong_label} does not solve the position. Recount the liberties and inspect '
                    'the cutting and connection points before trying again.'
                )

        if best and best_is_authoritative:
            best_label = best['label']
            lead = (f'✅ The correct move is {best_label}.' if wrong_move
                    else f'✅ Correct — {best_label} is the key point.')
            detail_lines = [lead]
            pv_list = top_moves[0]['pv'] if top_moves else None
            tactic = _select_tactic(
                best['x'], best['y'], player_color, board_state, self.board_size,
                pv_list, override=override, best_label=best_label)
            if tactic:
                tag_zh, _ = tactic
                tactic_names = {
                    '倒撲': 'Snapback', '撲': 'Throw-in', '立': 'Descend',
                    '夾': 'Clamp', '挖': 'Wedge', '尖': 'Kosumi',
                    '提子': 'Capture', '叫吃': 'Atari', '接不歸': 'Net',
                    '切斷': 'Cut',
                }
                tag_en = english_only((override or {}).get('tactic_en')) or tactic_names.get(tag_zh)
                reason_en = english_only((override or {}).get('reason_en'))
                if tag_en:
                    detail_lines.append(f'Tesuji: {tag_en}.')
                if reason_en:
                    detail_lines.append(reason_en)
                elif tag_en:
                    detail_lines.append(
                        'Compare the liberties and connections after this move; its purpose is '
                        'more important than the name of the pattern.'
                    )
            else:
                detail_lines.append(
                    'Compare this move with your choice: check liberties, eye space, and whether '
                    'either side can connect or be cut.'
                )

            if correct_moves and len(correct_moves) > 1:
                alternatives = []
                for move in correct_moves[1:4]:
                    col = _COL_LETTERS[move['x']] if move['x'] < len(_COL_LETTERS) else '?'
                    alternatives.append(f'{col}{self.board_size - move["y"]}')
                if alternatives:
                    detail_lines.append('Other accepted first moves: ' + ', '.join(alternatives) + '.')
            parts.append('\n'.join(detail_lines))
        elif best and not best_is_authoritative and not wrong_move:
            parts.append(
                f'💡 This problem has no stored answer. KataGo suggests {best["label"]} '
                'as a reference move.'
            )

        if wrong_move and top_moves and top_moves[0].get('move'):
            reply = top_moves[0]['move']['label']
            parts.append(
                f'After {wrong_label}, the opponent can answer at {reply}. '
                'Replay that exchange and compare the resulting liberties and eye space.'
            )

        safe_comment = english_only(sgf_comment)
        if safe_comment:
            parts.append('📖 Study note: ' + safe_comment)

        if not parts:
            color = 'Black' if player_color == 'B' else 'White'
            opponent = 'White' if player_color == 'B' else 'Black'
            parts.append(
                f'💡 {color} to play. Count liberties first, then inspect eye space and the '
                f'connection points between {opponent} stones. The key move usually changes '
                'more than one of those features at once.'
            )
        return '\n\n'.join(parts)

    def explain(
        self,
        katago_json: Optional[dict],
        player_color: str = 'B',
        wrong_move: Optional[dict] = None,
        sgf_comment: Optional[str] = None,
        q_info: Optional[dict] = None,
        board_state=None,
        correct_moves: Optional[List[dict]] = None,   # ← 新增：SGF 正確答案 [{x,y},...]
        override: Optional[dict] = None,              # ← 新增：人工權威手筋標籤 {tactic,reason}
        language: str = 'zh',                         # 'zh' | 'en'
    ) -> str:
        """
        組合完整解說文字。

        Parameters（v1 相容，v2 擴充）
        --------------------------------
        katago_json          : KataGo 原始 JSON；None → 僅用 SGF 解說
        player_color         : 'B' 或 'W'
        wrong_move           : {'x':int,'y':int}，玩家的錯誤落子；None 表示答對
        sgf_comment          : SGF C[...] 原始解說文字
        q_info               : 題目 dict（含 topic/level/difficulty）
        board_state          : 題目初始棋盤 [y][x]；1=黑,-1=白,0=空；
                               提供後啟用手筋偵測（撲/倒撲/立/尖/挖/夾）
        Returns
        -------
        str : 組裝完成的解說段落（各段以空行分隔）
        """
        bs    = self.board_size
        color = '黑棋' if player_color == 'B' else '白棋'
        opp   = '白棋' if player_color == 'B' else '黑棋'
        parts = []

        # ── 解析 KataGo ────────────────────────────────────────────────
        parsed       = self.parse(katago_json) if katago_json else None

        best       = parsed['best_move']      if parsed else None
        top_moves  = parsed['top_moves']      if parsed else []
        winrate    = parsed['winrate']        if parsed else None
        score_lead = parsed['score_lead']     if parsed else None
        own_grid   = parsed['ownership_grid'] if parsed else None


        # ── 用 SGF 正確答案覆蓋 KataGo 的 best_move ──────────────────
        # KataGo 的 best 是「對手懲罰錯誤落子的手」，不是 SGF 題目答案。
        # 若前端傳來 correct_moves，優先以此作為「正確答案」顯示。
        if correct_moves:
            sgf_best = correct_moves[0]   # 取第一個正解
            col = _COL_LETTERS[sgf_best['x']] if sgf_best['x'] < len(_COL_LETTERS) else '?'
            row = self.board_size - sgf_best['y']
            best = {'x': sgf_best['x'], 'y': sgf_best['y'], 'label': f'{col}{row}'}
            # 若有多個正解，也組成 label 列表備用
            _extra_corrects = []
            for cm in correct_moves[1:3]:
                c2 = _COL_LETTERS[cm['x']] if cm['x'] < len(_COL_LETTERS) else '?'
                r2 = self.board_size - cm['y']
                _extra_corrects.append(f'{c2}{r2}')
        else:
            _extra_corrects = []

        # best 是否為「權威正解」：有 correct_moves（前端傳入或後端從 SGF 自產）時，
        # best 取自 SGF 答案樹，可稱正解；否則 best 只是 KataGo 的推薦應手，
        # 此題未收錄標準答案，文案必須降級為「推薦應手（僅供參考）」，不得謊稱正解。
        best_is_authoritative = bool(correct_moves)

        if language == 'en':
            return self._explain_english(
                player_color=player_color,
                wrong_move=wrong_move,
                sgf_comment=sgf_comment,
                q_info=q_info,
                board_state=board_state,
                correct_moves=correct_moves,
                override=override,
                best=best,
                top_moves=top_moves,
                best_is_authoritative=best_is_authoritative,
            )

        # ── 段落 1：題目基本資訊 ──────────────────────────────────────
        if q_info:
            topic = q_info.get('topic', '')
            level = q_info.get('level', '')
            diff  = q_info.get('difficulty', '')
            title_parts = [x for x in [topic, level] if x and x != 'Unknown']
            if diff:
                title_parts.append(f'（{diff}）')
            if title_parts:
                parts.append('📌 ' + '・'.join(title_parts))

        # ══════════════════════════════════════════════════════════════
        # 幽默圍棋老師解說：死活題視角，輕鬆但有料
        # ══════════════════════════════════════════════════════════════

        # ── 段落 2：答錯時的分析 ──────────────────────────────────────
        if wrong_move:
            wlabel = _katago_label(wrong_move['x'], wrong_move['y'], bs)

            # ── 改善③：判斷「差一點」——錯誤落點與正解的 Manhattan 距離 ──
            _close_to_correct = False
            if correct_moves:
                wdist_min = min(
                    abs(wrong_move['x'] - cm['x']) + abs(wrong_move['y'] - cm['y'])
                    for cm in correct_moves
                )
                _close_to_correct = (wdist_min == 1)   # 正交緊鄰算「差一點」

            if _close_to_correct:
                wrong_openers = [
                    f'哇，{wlabel}……就差那麼一點點！方向對了，位置偏了一格。',
                    f'嗯！{wlabel} 感覺到了嗎？就差一步，再想想！',
                    f'快了快了！{wlabel} 的感覺是對的，但急所不在這一格。',
                    f'咦，{wlabel}？鼻子都碰到了，就是沒進去。再仔細看看！',
                ]
            else:
                wrong_openers = [
                    f'哎呀！{wlabel} 那邊下不得哇！',
                    f'唉～{wlabel}？老師我看了都替你捏把冷汗。',
                    f'嗯……{wlabel} 嘛……（老師沉默三秒）不行啦。',
                    f'好大膽！敢下 {wlabel}！可惜膽大不等於棋好。',
                    f'學生啊，{wlabel} 這步棋，對手看了會偷笑的。',
                    f'{wlabel}？老師的眉頭皺起來了。',
                    f'嘿，{wlabel} 這手……怎麼說呢，看起來很兇，其實很空。',
                ]
            wrong_lines = [random.choice(wrong_openers)]

            if best and not best_is_authoritative:
                # 無 SGF 正解：best 只是 KataGo 推薦手 → 降級，不謊稱正解、不報手筋
                blabel = best['label']
                wrong_lines.append(
                    f'這題沒有收錄標準答案；系統推薦的最佳應手是 {blabel}（僅供參考）。')
            elif best:
                blabel = best['label']
                pv_list = top_moves[0]['pv'] if top_moves else None
                tactic = _select_tactic(best['x'], best['y'], player_color,
                                        board_state, bs, pv_list,
                                        override=override, best_label=blabel)
                if tactic:
                    _ttag, _tdesc = tactic
                    correct_hints = [
                        f'急所在 {blabel}，這叫「{_ttag}」——老師教過的！',
                        f'{blabel} 才是要點，用的是「{_ttag}」，記住了嗎？',
                        f'看好了，{blabel}！「{_ttag}」就是這樣用的。',
                        f'這題關鍵是 {blabel}，「{_ttag}」手筋——經典！',
                    ]
                else:
                    correct_hints = [
                        f'正確的急所是 {blabel}，那才是真正的痛點。',
                        f'{blabel}！就是這裡！對手最不想你下的地方。',
                        f'記住 {blabel}，這個位置老師劃重點。',
                        f'答案是 {blabel}——下次看到這個形要反射動作喔。',
                        f'{blabel} 才是命門，{wlabel} 打偏了。',
                    ]
                wrong_lines.append(random.choice(correct_hints))

            # ── 顯示錯誤後果：你下了 wlabel，對手會這樣應 ──────────
            if top_moves and top_moves[0].get('move'):
                opp_label = top_moves[0]['move']['label']
                opp_replies = [
                    f'你下了 {wlabel}，對手馬上 {opp_label}，棋就活不成了。',
                    f'下完 {wlabel}，對手 {opp_label} 一夾，你的棋就麻煩大了。',
                    f'對手會趁機下 {opp_label}——這就是你的棋死在哪裡。',
                    f'結果是：對手 {opp_label}，你的眼位沒了。',
                    f'{wlabel} 之後對手 {opp_label}，這個形就崩了。',
                    f'對手巴不得你下 {wlabel}，接著走 {opp_label} 來應對，你就不好處理了。',
                ]
                wrong_lines.append(random.choice(opp_replies))

            parts.append('\n'.join(wrong_lines))

        # ── 段落 3：正確手的死活解說 ──────────────────────────────────
        if best:
            blabel = best['label']

            # ── 改善②：顯示完整正解手順 ─────────────────────────────
            # correct_moves 是前端從 SGF 樹抽出的正解第一手；
            # 若有多個正解，一併列出。
            _seq_label = None
            if correct_moves and len(correct_moves) >= 2:
                _cm_labels = []
                for cm in correct_moves[:4]:
                    c = _COL_LETTERS[cm['x']] if cm['x'] < len(_COL_LETTERS) else '?'
                    r = bs - cm['y']
                    _cm_labels.append(f'{c}{r}')
                _seq_label = ' → '.join(_cm_labels)

            if not best_is_authoritative:
                # 無 SGF 正解：best 來自 KataGo 推薦手 → 只給降級提示，
                # 不謊稱正解、不報手筋、不列「正解手順」。保留 best 供特殊棋型偵測。
                downgrade_openers = [
                    f'💡 此題未收錄標準答案；系統推薦的最佳應手是 {blabel}（僅供參考）。',
                    f'💡 這題沒有標準解，KataGo 推薦的應手是 {blabel}，可作思路參考。',
                ]
                parts.append(random.choice(downgrade_openers))
            else:
                correct_openers = [
                    f'✅ 答對！{blabel} 就是急所，孺子可教也！',
                    f'✅ {blabel}！這步棋老師給滿分！',
                    f'✅ 沒錯，就是 {blabel}！你真的學進去了。',
                    f'✅ {blabel}，漂亮！今晚可以多吃一碗飯了。',
                    f'✅ {blabel}！正確！老師點頭了。',
                    f'✅ 就是 {blabel}！記住這個感覺，下次要更快找到。',
                ] if not wrong_move else [
                    f'✅ 告訴你，正確手是 {blabel}。',
                    f'✅ {blabel} 才是這題的靈魂所在。',
                    f'✅ 來，老師示範：{blabel}，記住了嗎？',
                    f'✅ 正解是 {blabel}——再練一次，直到反射動作為止。',
                    f'✅ 答案揭曉：{blabel}。想清楚為什麼了嗎？',
                ]
                correct_lines = [random.choice(correct_openers)]

                # ① 手筋偵測（人工 override → 高信心規則；低信心不報術語）
                pv_list = top_moves[0]['pv'] if top_moves else None
                tactic = _select_tactic(best['x'], best['y'], player_color,
                                        board_state, bs, pv_list,
                                        override=override, best_label=blabel)
                if tactic:
                    _ttag, _tdesc = tactic
                    tesuji_intros = [
                        f'這招叫「{_ttag}」——',
                        f'用的是「{_ttag}」手筋，厲害的地方在於：',
                        f'「{_ttag}」！老師最愛看學生用這個——',
                        f'注意，這是「{_ttag}」的典型形：',
                    ]
                    correct_lines.append(random.choice(tesuji_intros) + _tdesc)

                # ② 眼位格局
                spatial = _analyze_spatial(best['x'], best['y'], player_color, own_grid, bs)
                if spatial:
                    _stag, _sdesc = spatial[0]
                    if any(k in _stag for k in ('眼', '要點', '緊氣')):
                        eye_intros = [
                            f'眼位的關鍵：{_sdesc}',
                            f'你看這眼位——{_sdesc}',
                            f'死活的核心在這：{_sdesc}',
                            f'從眼位來看：{_sdesc}',
                        ]
                        correct_lines.append(random.choice(eye_intros))

                # ③ 正解手順（來自 correct_moves，比 KataGo PV 更可靠）
                if _seq_label:
                    seq_intros = [
                        f'正解手順：{_seq_label}——背起來！',
                        f'標準手順是 {_seq_label}，理解比死背更重要。',
                        f'完整答案：{_seq_label}，這個形要記住。',
                    ]
                    correct_lines.append(random.choice(seq_intros))

                # ④ 多個正解時補充提示
                if _extra_corrects:
                    correct_lines.append(f'（{" 或 ".join(_extra_corrects)} 也是正解）')

                parts.append('\n'.join(correct_lines))

        elif sgf_comment and not wrong_move:
            # 無 best_move 但有 SGF 解說時，直接顯示
            sgf_intros = [
                f'✅ {sgf_comment}',
                f'✅ 教材說：{sgf_comment}',
                f'✅ 記住這個結論：{sgf_comment}',
            ]
            parts.append(random.choice(sgf_intros))

        # ── 段落 4：特殊棋型（劫爭 / 雙活 / 假眼）──────────────────
        specials = _detect_special_pattern(
            top_moves, sgf_comment,
            best_move=best,
            player_color=player_color,
            board_state=board_state,
            bs=bs,
        )
        for _stag, _sdesc in specials:
            # 在特殊棋型前加老師的驚嘆
            special_intros = {
                '劫': '⚡ 注意！這是劫爭——',
                '雙活': '🤝 有意思！雙活的形——',
                '假眼': '👁️ 看清楚！這是假眼——',
            }
            prefix = next((v for k, v in special_intros.items() if k in _stag), '⚠️ 特殊棋型——')
            parts.append(prefix + _sdesc)

        # ── 段落 5：SGF 教材解說 ──────────────────────────────────────
        if sgf_comment and best:
            book_intros = [
                f'📖 書上說：{sgf_comment}',
                f'📖 教材的解說是：{sgf_comment}',
                f'📖 老師的參考書這樣寫：{sgf_comment}',
            ]
            parts.append(random.choice(book_intros))

        # ── 段落 6：完全無資料時的基本提示 ───────────────────────────
        if not parts or (not best and not sgf_comment):
            fallbacks = [
                (f'💡 好啦，老師給你個線索：{color}的任務，'
                 f'不是「活著」就是「殺掉{opp}」，二選一。\n'
                 '找到那個下了之後對方最頭痛的點，那就是急所。加油！'),
                (f'💡 死活題只有一個核心：眼。\n'
                 f'{color}要活，就得做出兩個真眼；要殺，就得讓{opp}一個眼都沒有。\n'
                 '這題的急所就藏在眼位裡，找找看！'),
                (f'💡 老師問你：{color}現在幾隻眼？\n'
                 '想清楚了再下，圍棋從來不是靠感覺的。'),
                (f'💡 提示：先數氣，再找眼。\n'
                 f'{color}的棋還差幾口氣？{opp}有幾個真眼？\n'
                 '把這兩個問題回答清楚，答案自然浮現。'),
                (f'💡 老師不直接說答案，但給你方向：\n'
                 f'找到{opp}兩塊棋之間的「公共要點」——那個點，誰先佔誰贏。'),
                (f'💡 這題考的是「急所感」。\n'
                 '試著換個角度：如果你是對手，你最不希望對方下哪裡？\n'
                 '那裡，就是答案。'),
            ]
            parts.append(random.choice(fallbacks))

        return '\n\n'.join(parts)

    # ── 格式化輸出（CLI 用） ──────────────────────────────────────────

    def format_analysis(self, katago_json: dict) -> str:
        """將 KataGo JSON 格式化為人類可讀的分析報告（不含解說段落）。"""
        parsed = self.parse(katago_json)
        bs = self.board_size
        lines = []

        lines.append(f'=== KataGo 分析結果（{bs} 路）===')
        lines.append(f'當前走棋方勝率：{parsed["winrate"]:.1f}%')
        lines.append(f'目數優勢：{_score_desc(parsed["score_lead"])}')
        lines.append('')

        if parsed['top_moves']:
            lines.append('推薦手順：')
            for i, tm in enumerate(parsed['top_moves'], 1):
                mv    = tm['move']
                mpos  = _position_desc(mv['x'], mv['y'], bs)
                pvlbs = ' → '.join(p['label'] for p in tm['pv'][:4])
                lines.append(
                    f"  {i}. {mv['label']}（{mpos}）"
                    f"  勝率 {tm['winrate']:.1f}%  搜尋 {tm['visits']} 次"
                    + (f"\n     後續：{pvlbs}" if pvlbs else '')
                )
        else:
            lines.append('  （無推薦手資料）')

        return '\n'.join(lines)


# ══════════════════════════════════════════════════════════════════════
# CLI 入口
# ══════════════════════════════════════════════════════════════════════

def _main():
    parser = argparse.ArgumentParser(
        description='將 KataGo analysis 輸出轉換為人類可讀的圍棋死活解說（v2）'
    )
    parser.add_argument(
        'input', nargs='?', default='-',
        help='KataGo JSONL 輸出檔案路徑（預設從 stdin 讀取）'
    )
    parser.add_argument('--board-size', type=int, default=9, metavar='N',
                        help='棋盤大小（預設 9）')
    parser.add_argument('--player', default='B', choices=['B', 'W'],
                        help='當前走棋方（預設 B=黑）')
    parser.add_argument('--wrong-x', type=int, default=None,
                        help='錯誤落子的 x 座標（0-indexed）')
    parser.add_argument('--wrong-y', type=int, default=None,
                        help='錯誤落子的 y 座標（0-indexed）')
    parser.add_argument('--sgf-comment', default=None,
                        help='SGF C[...] 原始解說文字')
    parser.add_argument('--raw', action='store_true',
                        help='只輸出結構化分析，不生成解說段落')
    args = parser.parse_args()

    # 讀取輸入
    if args.input == '-':
        text = sys.stdin.read().strip()
    else:
        with open(args.input, encoding='utf-8') as f:
            text = f.read().strip()

    # 支援 JSONL（取最後一行有效 JSON）或單一 JSON
    katago_json = None
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            katago_json = json.loads(line)
            break
        except json.JSONDecodeError:
            continue

    if katago_json is None:
        print('[錯誤] 找不到有效的 JSON 資料', file=sys.stderr)
        sys.exit(1)

    explainer  = KataGoExplainer(board_size=args.board_size)
    wrong_move = None
    if args.wrong_x is not None and args.wrong_y is not None:
        wrong_move = {'x': args.wrong_x, 'y': args.wrong_y}

    print(explainer.format_analysis(katago_json))

    if not args.raw:
        print()
        print('── 解說 ─────────────────────────────────────────')
        print(explainer.explain(
            katago_json,
            player_color=args.player,
            wrong_move=wrong_move,
            sgf_comment=args.sgf_comment,
        ))


if __name__ == '__main__':
    _main()
