"""Full 10-zone offline truth using pinned real 41,591-puzzle corpus."""
import json,hashlib,os,random,time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from daily_challenge_selection import daily_question_judgeable
from lord_trial_admission import question_is_lord_judgeable, select_admissible_lord_questions
from g114_zone10_alternative import zone10_admitted_alternative

source=Path(os.environ["QUESTIONS_JSON_PATH"])
expected="b7b4eedf72a87ab8fbc82ff51b658cd4dc0f08cb33426aee013e97814edae232"
assert hashlib.sha256(source.read_bytes()).hexdigest()==expected
qs=app._load_questions(); assert len(qs)==41591,len(qs)
result={"schema":"G114_REAL_CANONICAL_TEN_ZONE_PROVENANCE_V1",
"source_sha256":expected,"raw_total":len(qs),"zones":{},"failure":None}
for zone in app.ADVENTURE_ZONES:
 pool=app._questions_for_adventure_zone(qs,zone,True)
 old=sum(q.get("topic") in zone["books"] for q in pool)
 unique={q.get("id") for q in pool if type(q.get("id")) is int}
 safe=sum(daily_question_judgeable(q) for q in pool)
 lord=sum(question_is_lord_judgeable(q) for q in pool)
 denominator=app._g114_adventure_zone_denominator(zone,pool)
 z={"original_question_count":old,"actual_selected_count":len(pool),
 "safe_map_count":safe,"unsafe_map_count":len(pool)-safe,
 "safe_lord_count":lord,"gameplay_denominator":denominator,
 "alternative_count":sum(zone10_admitted_alternative(q) for q in pool)}
 assert len(unique)==len(pool),(zone["key"],"duplicate question ids")
 assert len(pool)>=20 and safe>=20 and lord>=20,(zone["key"],z)
 lord_pool=app._g114_zone10_safe_questions(zone,pool)
 selected=select_admissible_lord_questions(lord_pool,20,rng=random.Random(114))
 assert len({q["id"] for q in selected})==20
 z["lord_selected_unique"]=len(selected)
 z["pass_map"]=safe>=20;z["pass_lord"]=True
 if zone["key"]=="d7_plus":
  assert old==683 and len(pool)==1679 and denominator==1002,z
  assert z["alternative_count"]==996 and safe==1002 and lord>=996,z
 result["zones"][zone["key"]]=z
 print("G114_ZONE",zone["key"],json.dumps(z,ensure_ascii=True),flush=True)
out=Path(r"D:\g079-artifacts\g114_ten_zone_source_verified_20261026.json")
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
print("TEN_ZONE_FULL_CATALOG_PASS",len(result["zones"]),out)
