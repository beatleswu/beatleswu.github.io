"""G114 Zone 10 alternative 7d catalog, pinned to published source SGF SHA.

No inferred correctness, no SGF mutations and no lower-rank substitutes.
Every alternative passed G065 conservative terminal_verdict during manifest
creation; membership is bound to exact original question ID + content SHA.
"""
from __future__ import annotations
import hashlib,json
from functools import lru_cache
from pathlib import Path
from typing import Mapping,Any

ZONE10_ALTERNATIVE_TOPIC = "逆天改命：終焉戰場的修羅考驗"
ZONE10_SOURCE_SHA256 = "b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232"

@lru_cache(maxsize=1)
def _manifest_records():
    path=Path(__file__).with_name("g114_zone10_safe_alternative_manifest.json")
    doc=json.loads(path.read_text(encoding="utf8"))
    if (doc.get("schema")!="G114_ZONE10_ORIGINAL_CONTENT_ALTERNATIVE_PROVENANCE_V1"
            or doc.get("source_catalog_sha256")!=ZONE10_SOURCE_SHA256
            or doc.get("new_correctness_labels_created")!=0):
        raise ValueError("G114 Zone 10 source manifest mismatch")
    records={}
    for item in doc["entries"]:
        qid=item["id"]
        if type(qid) is not int or qid in records:
            raise ValueError("duplicate or invalid ID in G114 curated catalog")
        records[qid]=item["content_sha256"]
    return records

def zone10_admitted_alternative(question: Mapping[str,Any]) -> bool:
    if not isinstance(question,Mapping):
        return False
    qid=question.get("id")
    if (type(qid) is not int or question.get("enabled",True) is False
         or question.get("topic")!=ZONE10_ALTERNATIVE_TOPIC
         or question.get("rank")!="7d"
         or str(question.get("stage") or "").upper()!="LV10"):
        return False
    sgf=question.get("content")
    if not isinstance(sgf,str) or not sgf:
        return False
    expected=_manifest_records().get(qid)
    return bool(expected and hashlib.sha256(sgf.encode("utf8")).hexdigest()==expected)

def zone10_verified_player_to_move(question: Mapping[str,Any]) -> str | None:
    """Side-to-move format recovery only, NEVER answer/correctness inference.

    For whitelisted unchanged SGF only, require ALL root alternatives to open
    with the same B/W color, then recheck the actual G065 terminal authority.
    This may fill absent PL for Lord Trial; the actual verdict is still
    judged separately on exact server-owned submitted moves by G065.
    """
    if not zone10_admitted_alternative(question):
        return None
    from sgf_engine.parser.sgf_parser import parse_sgf
    from daily_challenge_selection import daily_question_judgeable
    try:
        if not daily_question_judgeable(question):
            return None
        root=parse_sgf(question["content"],strict=True)
        children=[c.move for c in root.children if c.move is not None]
        colors={m.color for m in children}
        if children and len(colors)==1:
            color=next(iter(colors))
            if color in ("B","W"):
                return color
    except (TypeError,KeyError,ValueError,AttributeError):
        return None
    return None
