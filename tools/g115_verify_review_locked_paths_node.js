// G115 Reviewer: run exact candidate frontend selector JS, not rewritten mocks.
// Must fail on c0417ad7 and pass on corrected index.html.
'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const path=require('path');
const source=fs.readFileSync(path.resolve(__dirname,'..','index.html'),'utf8');
const start=source.indexOf('function _nextAdventureQuestionExcludingQuarantine(');
const end=source.indexOf('async function _resolveMapBattleV1Resume(',start);
assert(start>=0&&end>start);
const sandbox={
  _isSessionQuestionQuarantined:q=>q?.id===100,
  _adventureQuestionSeen:id=>id===101||id===102,
  _adventureQuestionDefeated:id=>false
};
vm.createContext(sandbox);
vm.runInContext(source.slice(start,end),sandbox,{filename:'REAL_G115_INDEX_HTML_SELECTORS'});
const pool=[{id:100,locked:false},{id:101,locked:true},{id:102,locked:false}];
const results={
  source_functions_actually_executed:true,
  seen_locked_unbeaten_question_id:101,
  seen_legal_unbeaten_question_id:102,
  first:sandbox._pickAdventureTarget(pool)?.id??null,
  after_409:sandbox._pickNextAdventureTarget(pool,100)?.id??null,
  manual_next:sandbox._nextAdventureQuestionExcludingQuarantine(pool,100,1)?.id??null,
  manual_previous:sandbox._nextAdventureQuestionExcludingQuarantine(pool,100,-1)?.id??null,
  exhausted:sandbox._pickNextAdventureTarget(pool.filter(x=>x.id!==102),100)?.id??null,
  only_locked:sandbox._nextAdventureQuestionExcludingQuarantine([{id:101,locked:true}],101,1)?.id??null
};
assert(results.first===102&&results.after_409===102&&results.manual_next===102&&results.manual_previous===102
  &&results.exhausted===null&&results.only_locked===null,JSON.stringify(results));
console.log(JSON.stringify({verdict:'PASS',...results}));
