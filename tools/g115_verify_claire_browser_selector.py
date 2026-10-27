"""Execute REAL headless Chrome against exact extracted G115 selector functions.
This tests the real browser JS decision path (not full logged-in player E2E).
"""
from pathlib import Path
import os
import subprocess,json,hashlib,re,html,datetime
root=Path(__file__).resolve().parents[1]
source=(root/"index.html").read_text(encoding="utf8")
start=source.index("function _nextAdventureQuestionExcludingQuarantine(qs, currentId, direction = 1) {")
end=source.index("async function _resolveMapBattleV1Resume(",start)
js=source[start:end]
# Execute the actual fallback UI functions in Chrome as well, not just static selectors.
block_start=source.index("function _blockAdventureProgression(reason) {")
block_end=source.index("function _mapBattleV1QuestionContext(",block_start)
empty_start=source.index("function _showSessionNoValidQuestion() {")
empty_end=source.index("function _publishMapBattleV1Lifecycle()",empty_start)

assert "q.locked" in js
assert source.count("const unitQs = zoneQs.filter(q => !q.locked);")==2
assert "code === 'map_battle_zone_not_unlocked'" in source
prepare_branch=source[source.index("} else if (code === 'premium_required') {"):source.index("} else if (code === 'map_battle_zone_not_unlocked') {")]
assert "_blockAdventureProgression('premium_required');" in prepare_branch
assert "setMsg(" not in prepare_branch and "I18n.t('index.premium_req')" not in prepare_branch
submit_branch=source[source.index("if (error && error.code === 'premium_required') {"):source.index("if (error && (error.code === 'upgrade_required'",source.index("if (error && error.code === 'premium_required') {"))]
assert "_blockAdventureProgression('premium_required');" in submit_branch
assert "setMsg(" not in submit_branch and "I18n.t('index.premium_req')" not in submit_branch

js += "\n" + source[block_start:block_end] + "\n" + source[empty_start:empty_end]
# Actually execute the two ORIGINAL handler branches, not just inspect text.
# Wrappers supply only the local catch parameter variables needed by the branches.
js += "\nfunction _g115PrepareCatchPremium(){ const code='premium_required'; " + prepare_branch.lstrip()[7:] + "\n}\n}\n"
js += "\nfunction _g115SubmitCatchPremium(){ const error={code:'premium_required'}; " + submit_branch + "\n}\n"


tests=r"""
const outcomes=[];
const seen = new Set();
const defeated = new Set();
const quarantine = new Set();
function _isSessionQuestionQuarantined(q) { return quarantine.has(q?.id); }
function _adventureQuestionSeen(id) { return seen.has(id); }
function _adventureQuestionDefeated(id) { return defeated.has(id); }
function confirm(name,result){outcomes.push({name,pass:result===true});}
const bad={id:100,locked:false};
const locked={id:101,locked:true};
const good={id:102,locked:false};
const candidates=[bad,locked,good];
confirm('first eligible target prefers bad before SGF rejection', _pickAdventureTarget(candidates)?.id===100);
quarantine.add(100);
confirm('after 409, selects permitted legal candidate not locked', _pickNextAdventureTarget(candidates,100)?.id===102);
confirm('manual selection excludes locked candidate', _pickAdventureTarget(candidates)?.id===102);
confirm('locked candidate is never offered even if all remaining',_pickNextAdventureTarget([bad,locked],100)===null);
quarantine.add(102);
confirm('no infinite recursion when all legal candidates exhausted',_pickNextAdventureTarget(candidates,100)===null);
const filtered=[bad,locked,good].filter(q=>!q.locked);
confirm('zone pool excludes locked records',filtered.length===2&&!filtered.includes(locked));
const onlyLocked=[locked].filter(q=>!q.locked);
confirm('all locked -> explicit empty eligible pool',onlyLocked.length===0);

// G115 independent Reviewer c0417 regression: the locked candidate is
// ALREADY SEEN but NOT DEFEATED. It precedes a permitted SEEN candidate.
seen.add(101);
seen.add(102);
quarantine.clear();
quarantine.add(100);
confirm('Reviewer: seen locked q101 never beats seen legal q102 in first selector',
    _pickAdventureTarget(candidates)?.id === 102);
confirm('Reviewer: seen locked q101 never wins 409-next selector',
    _pickNextAdventureTarget(candidates,100)?.id === 102);
confirm('Reviewer: seen locked q101 never wins manual Next',
    _nextAdventureQuestionExcludingQuarantine(candidates,100,1)?.id === 102);
confirm('Reviewer: seen locked q101 never wins manual Previous',
    _nextAdventureQuestionExcludingQuarantine(candidates,100,-1)?.id === 102);
quarantine.add(102);
confirm('Reviewer: all eligible previously-seen excluded -> next returns null',
    _pickNextAdventureTarget(candidates,100) === null);
confirm('Reviewer: all eligible previously-seen excluded -> manual returns null',
    _nextAdventureQuestionExcludingQuarantine(candidates,100,1) === null);
confirm('Reviewer: locked only never returned on manual Next',
    _nextAdventureQuestionExcludingQuarantine([locked],101,1) === null);

// The real G115 error UI must preserve the typed reason and hide blank boards.
const ADVENTURE_UNAVAILABLE_SOURCE_CONTEXT='synthetic-chrome-only';
let _mapBattleV1Mode='active',_mapBattleV1State={active:true};
let _bossMode=false,solved=false,answering=true,lastMessage='',lastReason='';
function _syncE10BattleActions() {}
function setMsg(msg){lastMessage=msg;}
function notifyAdventureQuestionRuntimeError(reason){lastReason=reason;}
function _e10AcceptanceTrace() {}
function _publishMapBattleV1Lifecycle() {}
function _isAdventureZonePractice(){return true;}
const board=document.getElementById('board-canvas-wrap');
_blockAdventureProgression('map_battle_zone_not_unlocked');
confirm('locked zone gives explanatory Chinese not generic English', lastMessage.includes('解鎖驗證')&&lastReason==='map_battle_zone_not_unlocked');
confirm('locked zone hides blank board',board.classList.contains('hidden'));
const oldMessage=lastMessage;
_blockAdventureProgression('map_battle_blocked');
confirm('secondary generic error cannot overwrite real 403 reason',lastMessage===oldMessage);
_mapBattleV1Mode='active';board.classList.remove('hidden');
_blockAdventureProgression('premium_required');
confirm('Premium mismatch does not advise repurchase',lastMessage.includes('請勿重新購買會員'));
_mapBattleV1Mode='active';lastMessage='';
_g115PrepareCatchPremium();
confirm('real prepare 403 premium handler preserves typed no-repurchase message',
lastMessage.includes('請勿重新購買會員')&&!lastMessage.includes('升級'));
_mapBattleV1Mode='active';lastMessage='';
_g115SubmitCatchPremium();
confirm('real submit 403 premium handler preserves typed no-repurchase message',
lastMessage.includes('請勿重新購買會員')&&!lastMessage.includes('升級'));

board.classList.remove('hidden');lastMessage='';
_showSessionNoValidQuestion();
confirm('exhausted legal pool guides player back and hides blank board',
lastMessage.includes('返回地圖')&&board.classList.contains('hidden')&&solved&&!answering);
document.getElementById('report').textContent=JSON.stringify({pass:outcomes.every(x=>x.pass),tests:outcomes});
"""
page="<!doctype html><html><head><meta charset=\"utf-8\"></head><body><div id=\"board-canvas-wrap\"></div><pre id=\"report\">NOT_RUN</pre><script>"+js+"\n"+tests+"</script></body></html>"
path=Path(os.environ.get("G115_BROWSER_ARTIFACT_DIR",str(Path.cwd()))) / "g115-claire-real-chrome-selector-fixture.html"
path.write_text(page,encoding="utf8")
chrome=Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
assert chrome.exists()
cmd=[str(chrome),"--headless=new","--disable-gpu","--no-first-run","--no-default-browser-check",
"--disable-background-networking","--disable-extensions","--user-data-dir="+str(Path(os.environ.get("G115_BROWSER_ARTIFACT_DIR",str(Path.cwd()))) / "g115-chrome-profile"),
"--virtual-time-budget=5000","--dump-dom",path.as_uri()]
p=subprocess.run(cmd,capture_output=True,text=True,encoding="utf8",errors="replace",timeout=60)
matched=re.search(r'<pre id="report">([^<]+)</pre>',p.stdout)
if not matched:raise RuntimeError("REAL_CHROME_DID_NOT_RENDER_JS_TEST_RESULTS "+str(p.returncode)+" "+p.stderr[-450:])
obj=json.loads(html.unescape(matched.group(1)))
assert p.returncode==0 and obj["pass"] and len(obj["tests"])==21,obj
receipt={"schema":"G115_REAL_CHROME_SELECTOR_P1_REVIEWER_NEGATIVE_V2",
"observed_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
"browser":"Google Chrome --headless=new","source_git_index_sha256":hashlib.sha256(source.encode()).hexdigest(),
"browser_real_dom_execution":True,"full_authenticated_player_e2e":False,
"tests":obj["tests"],"all_pass":True}
target=Path(os.environ.get("G115_BROWSER_ARTIFACT_DIR",str(Path.cwd()))) / "g115-claire-real-chrome-selector-test-receipt.json"
target.write_text(json.dumps(receipt,indent=2)+"\n",encoding="utf8")
print(json.dumps({"real_chrome":"PASS","count":len(obj["tests"]),"receipt_path":str(target),"sha256":hashlib.sha256(target.read_bytes()).hexdigest()}))
