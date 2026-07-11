# -*- coding: utf-8 -*-
"""
AI 解說的人工權威手筋標籤載入器（Flask-free，方便單元測試）。

以穩定的 SGF 相對路徑 source 為主鍵（question_id 在 --force-rebuild 會重配，
不可當主鍵）。精確比對、不支援萬用字元；key 與 source 一律正規化斜線後比對。

每筆 override 格式：
    { "move": "O16", "tactic": "切斷", "reason": "...",
      "tactic_en": "Cut", "reason_en": "..." }
  - move   : 必填，正解座標標記（如 "O16"），載入時轉大寫並驗證格式。呼叫端用它與
             best 核對，相符才套用——避免缺 correctMoves 時 best 退回快取應手，卻把
             標籤貼到錯的手上。缺 move 或格式錯的條目一律丟棄。
  - tactic : 必填，非空字串
  - reason / tactic_en / reason_en : 選填字串
壞掉的條目（非 dict、tactic 非字串、缺/錯 move）會被丟棄，不致讓 API 500。
"""
import os
import re
import json

# 圍棋座標標記：直線 A-T（略過 I），數字 1-25。用於驗證 override 的 move 欄。
_MOVE_RE = re.compile(r'^[A-HJ-T](?:[1-9]|1[0-9]|2[0-5])$')

OVERRIDES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              'explain_overrides.json')

_cache = None
_mtime = None
_cache_path = None


def norm_src(s):
    """統一斜線並去除前後空白，讓 \\ 與 / 的 source 都能精確對上。"""
    return str(s or '').replace('\\', '/').strip()


def _clean_entry(v):
    """
    驗證並正規化單筆 override；不合法回 None。

    必填：
      tactic : 非空字串
      move   : 正解座標標記（如 'O16'），轉大寫後須符合 _MOVE_RE。
               必填的理由：呼叫端用 move 與 best 核對，缺 move 會繞過 F2 防護，
               讓「標籤貼到錯的手」的問題復發，故缺 move / 格式錯的條目一律丟棄。
    選填：
      reason / tactic_en / reason_en : 字串
    """
    if not isinstance(v, dict):
        return None
    tactic = v.get('tactic')
    if not isinstance(tactic, str) or not tactic.strip():
        return None
    move = v.get('move')
    if not isinstance(move, str):
        return None
    move = move.strip().upper()
    if not _MOVE_RE.match(move):
        return None
    out = {'tactic': tactic.strip(), 'move': move}
    for key in ('reason', 'tactic_en', 'reason_en'):
        value = v.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    return out


def load_overrides(path=OVERRIDES_FILE):
    """載入並快取（依 mtime 自動重載）。回傳 {normsrc: {tactic[,reason][,move]}}。"""
    global _cache, _mtime, _cache_path
    if not os.path.exists(path):
        _cache, _mtime, _cache_path = {}, None, path
        return _cache
    mtime = os.path.getmtime(path)
    if _cache is not None and path == _cache_path and mtime == _mtime:
        return _cache
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception as e:
        print(f'[explain_overrides] 載入 {path} 失敗：{e}')
        if _cache is None:
            _cache = {}
        return _cache
    result = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            entry = _clean_entry(v)
            if entry:
                result[norm_src(k)] = entry
    _cache, _mtime, _cache_path = result, mtime, path
    return _cache


def get_override(source, path=OVERRIDES_FILE):
    """依 source 精確查表（已正規化）。查無回 None。"""
    return load_overrides(path).get(norm_src(source))
