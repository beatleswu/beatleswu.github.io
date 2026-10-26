"""Regenerate G114 same-rank 7d/LV10 zone alternatives from canonical source.

G065 content eligibility alone is not enough: an unambiguous linear SGF
may contain a repeat point/ko sequence rejected by real client answer
canonicalization. Only SGF whose entire original line settles CORRECT
and whose off-tree answer settles INCORRECT can enter final pool.
No SGF answer labeling, no source mutation.
"""
from pathlib import Path
import collections,hashlib,json,sys
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from daily_challenge_selection import daily_question_judgeable
from lord_trial_answer_service import judge_lord_trial_answer
from sgf_engine.parser.sgf_parser import parse_sgf
snapshot=Path(r"D:\g079-artifacts\g114-canonical-public-questions-20261026\questions.json")
source_sha="b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232"
raw=snapshot.read_bytes()
assert hashlib.sha256(raw).hexdigest()==source_sha
all_questions=json.loads(raw)
topic="逆天改命：終焉戰場的修羅考驗"
counts=collections.Counter(str(q.get("id")) for q in all_questions if isinstance(q,dict))
entries=[]
rejected=[]
exam={"zone_key":"d7_plus","attempt_id":"g114-audit-original-sgf"}
def original_linear_moves(question):
    root=parse_sgf(question["content"],strict=True)
    first=[c.move for c in root.children if c.move is not None]
    colors={m.color for m in first}
    if not first or len(colors)!=1:raise ValueError("unknown_player_color")
    color=next(iter(colors))
    node=root
    moves=[]
    while node.children:
        if len(node.children)!=1:raise ValueError("ambiguous_branch")
        node=node.children[0]
        m=node.move
        if m is not None and m.color==color:
            xy=m.coord
            if not isinstance(xy,str) or len(xy)!=2:raise ValueError("bad_coordinate")
            moves.append({"action":"play","x":ord(xy[0])-97,"y":ord(xy[1])-97})
    if not moves:raise ValueError("no_player_moves")
    return moves
for q in all_questions:
    if not isinstance(q,dict) or q.get("topic")!=topic:continue
    qid=q.get("id")
    basic=(type(qid) is int and counts[str(qid)]==1
         and q.get("enabled",True) is not False
         and q.get("rank")=="7d" and q.get("stage")=="LV10"
         and daily_question_judgeable(q))
    reason=None
    if basic:
        try:
            moves=original_linear_moves(q)
            _ans,result=judge_lord_trial_answer({"moves":moves},question=q,exam=exam)
            if result.result!="CORRECT" or result.authoritative_grade!=5:
                raise ValueError("not_server_correct")
            _ans,bad=judge_lord_trial_answer(
                {"moves":[{"action":"play","x":18,"y":18}]},question=q,exam=exam)
            if bad.result!="INCORRECT" or bad.authoritative_grade!=0:
                raise ValueError("unsafe_off_tree")
        except Exception as exc:
            reason=str(getattr(exc,"reason_code",type(exc).__name__))
    else:reason="not_preliminary_g065_safe"
    if reason is None:
        entries.append({"id":qid,
          "content_sha256":hashlib.sha256(q["content"].encode("utf8")).hexdigest(),
          "source":q.get("source"),"original_topic":topic,
          "rank":"7d","stage":"LV10",
          "authority":"G065_terminal_and_full_actual_Lord_CORRECT_offtree_INCORRECT",
          "side_to_move":"unique_color_across_original_root_children_not_correctness"})
    else:rejected.append({"id":qid,"reason":reason})
entries.sort(key=lambda x:x["id"])
assert len(entries)>=20 and len({x["id"] for x in entries})==len(entries)
manifest={"schema":"G114_ZONE10_ORIGINAL_CONTENT_ALTERNATIVE_PROVENANCE_V1",
"source_catalog_sha256":source_sha,"source_records":len(all_questions),
"source_topic":topic,"original_zone":"d7_plus",
"reason":"Original book unsafe; same-rank 7d verified original SGF pass unchanged G065 plus real entire Lord answer, off-tree incorrect",
"terminals_not_relabelled":True,"new_correctness_labels_created":0,
"preliminary_g065_count":sum(1 for q in all_questions if isinstance(q,dict)
   and q.get("topic")==topic and daily_question_judgeable(q)),
"eligible_count":len(entries),"rejected_count":len(rejected),
"rejected":rejected,"entries":entries}
out=root/"g114_zone10_safe_alternative_manifest.json"
out.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
print("G114_Z10_FULL_SERVER_JUDGED",len(entries),"REJECTED",len(rejected),
      "SHA256",hashlib.sha256(out.read_bytes()).hexdigest())
