"""G082: actual shipped onBoardClick must reject clicks while authoritative Lord handoff is pending."""
from pathlib import Path
import subprocess
import json

ROOT=Path(__file__).resolve().parent.parent


def test_boss_transition_gate_suppresses_wgo_input_until_next_board_ready():
    html=(ROOT/"index.html").read_text(encoding="utf-8")
    start=html.index("function onBoardClick(bx,by){")
    stop=html.index("    const x=_ox(bx)",start)
    guard=html[start:stop]+"  globalThis.reachedCoordinateConversion = true;\n}\nonBoardClick(7,4);\n"
    # Execute the actual product guard prefix, not a reimplementation.
    runner=r"""
const vm=require('node:vm');
const fs=require('node:fs');
const guard=JSON.parse(fs.readFileSync(0,'utf8'));
function scenario(active,pending) {
 const observed=[];
 const context={_bossMode:active,_bossTransitionInFlightKey:pending,
   _bossIndex:7,currentQ:{id:970011},
   _e10AcceptanceTrace:(event,payload)=>observed.push({event,payload})};
 vm.runInNewContext(guard,context,{timeout:3000});
 return {reached:context.reachedCoordinateConversion===true,observed};
}
const bad=scenario(true,'attempt:7:970010');
if(bad.reached || bad.observed.length!==1
 || bad.observed[0].event!=='BOSS_TAP_IGNORED_DURING_TRANSITION') process.exit(12);
if(!scenario(true,null).reached) process.exit(13);
if(!scenario(false,'unrelated').reached) process.exit(14);
console.log('G082_LORD_PENDING_INPUT_GATE_THREE_STATES_PASS');
"""
    p=subprocess.run(["node","-e",runner],input=json.dumps(guard),text=True,capture_output=True,
                     encoding="utf-8",errors="replace",cwd=ROOT,timeout=12)
    assert p.returncode==0,(p.returncode,p.stdout,p.stderr)
    assert "THREE_STATES_PASS" in p.stdout
