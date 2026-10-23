import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import os from 'node:os';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const out = path.join(root, 'docs/handoffs/g064-evidence');
fs.mkdirSync(out, { recursive: true });
const index = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const renderer = fs.readFileSync(path.join(root, 'js/game/board_renderer.js'), 'utf8');
const fixtures = JSON.parse(fs.readFileSync(path.join(root, 'tests/fixtures/g064_sgf_annotations.json')));
const parserSource = index.slice(index.indexOf('function parseSGF(sgf)'), index.indexOf('// ─── 音效', index.indexOf('function parseSGF(sgf)')));
const context = vm.createContext({ window: {} });
vm.runInContext(renderer, context);
context.GoOdysseyBoardRenderer = context.window.GoOdysseyBoardRenderer;
vm.runInContext(parserSource, context);
const api = context.GoOdysseyBoardRenderer;
const checks = [];
function check(name, fn) { try { fn(); checks.push({ name, status: 'PASS' }); } catch (e) { checks.push({ name, status: 'FAIL', error: e.message }); } }
const plain = value => JSON.parse(JSON.stringify(value));
const transform = (p, n, t) => {
  const { x, y } = p;
  return [{ x,y },{ x:n-y,y:x },{ x:n-x,y:n-y },{ x:y,y:n-x },{ x:n-x,y },{ x,y:n-y },{ x:y,y:x },{ x:n-y,y:n-x }][t];
};
const visualCases = [];
for (const fixture of fixtures) {
  check(fixture.name + ': root and no solution markers', () => {
    const p = context.parseSGF(fixture.sgf);
    assert.ok(p);
    assert.ok(p.annotations.length);
    assert.ok(!JSON.stringify(p.annotations).includes('SECRET'));
    if (fixture.name === 'mixed-9') {
      assert.deepEqual(plain(p.annotations.filter(m => m.type === 'LB').map(m => m.text)), ['A','B','C','1','12']);
      assert.deepEqual(plain(p.tree.move), { x:3,y:4 });
      assert.equal(p.tree.children.length, 2);
    }
    if (fixture.name === 'escaped-root') {
      assert.equal(p.pl, 'B');
      assert.deepEqual(plain(p.annotations.filter(m => m.type === 'LB').map(m => m.text)), ['A]B', '1:2']);
    }
    if (fixture.name === 'range-13') assert.equal(p.black.length, 4);
    if (fixture.name === 'map-battle-69853-root') {
      const labels = p.annotations.filter(m => m.type === 'LB');
      assert.deepEqual(plain(labels.map(m => m.text)).sort(), ['1','N','Y']);
      const answerPoint = labels.find(m => m.text === 'N');
      assert.deepEqual(plain({x:answerPoint.x,y:answerPoint.y}), {x:5,y:9});
      const crop = context.calcCropSection(p);
      assert.ok(crop.displayLines >= 13);
      assert.ok(answerPoint.x >= crop.startX && answerPoint.x < crop.startX + crop.displayLines);
      assert.ok(answerPoint.y >= crop.startY && answerPoint.y < crop.startY + crop.displayLines);
    }

  });
  for (let t = 0; t < 8; t++) {
    check(`${fixture.name}: transformed geometry ${t}`, () => {
      const p = plain(context.parseSGF(fixture.sgf));
      for (const field of ['black','white','annotations']) p[field] = p[field].map(m => ({ ...m, ...transform(m, p.size-1, t) }));
      const crop = context.calcCropSection(p), objects = [];
      assert.equal(api.renderAnnotations({ addObject: o => objects.push(o) }, p, crop), p.annotations.length);
      for (let i=0; i<objects.length; i++) {
        assert.equal(objects[i].x + crop.startX, p.annotations[i].x);
        assert.equal(objects[i].y + crop.startY, p.annotations[i].y);
      }
      visualCases.push({ name: `${fixture.name} / ${t}`, problem:p, crop:plain(crop) });
    });
  }
}
check('malformed and unsupported board input fails closed', () => {
  for (const sgf of ['', '(;SZ[9]LB[aa:A)', '(;SZ[99])', '(;SZ[9:13])', null]) assert.equal(api.readSgfRoot(sgf), null);
  assert.equal(api.readSgfRoot('(;SZ[9]LB[zz:X]TR[zz])').annotations.length, 0);
});
check('literal HTML label stays text and root markup is isolated', () => {
  const p = context.parseSGF(String.raw`(;SZ[9]LB[aa:<img onerror=alert(1)>]C[LB[bb:SECRET\]];B[cc]LB[cc:SECRET])`);
  assert.equal(p.annotations.length, 1);
  assert.equal(p.annotations[0].text, '<img onerror=alert(1)>');
});
check('all five production initial/reset/replay/rebuild render sites wired', () => {
  assert.equal(index.split('GoOdysseyBoardRenderer.renderAnnotations(board, currentProblem, _cropInfo);').length-1, 5);
});
check('crop extents include distant markers and 9/13/19 windows', () => {
  const crops = Object.fromEntries(fixtures.map(f => [f.name, context.calcCropSection(context.parseSGF(f.sgf)).displayLines]));
  assert.equal(crops['corner-19'], 9);
  assert.equal(crops['crop-13-of-19'], 13);
  assert.equal(crops['distant-label-19'], 19);
});
check('production reset restores annotations without rendering solution markers', () => {
  const p = context.parseSGF(fixtures[0].sgf), objects = [];
  Object.assign(context, {
    currentProblem:p, currentQ:{}, _exploringAfterWrong:false, _cancelAutoSolution:()=>{},
    solved:true, answering:true, _altAnswerReportMode:false, _mapBattleV1Moves:[],
    _gameBootstrap:{invalidate:()=>{}}, _boardRenderer:{clear:()=>{objects.length=0;},addObject:o=>objects.push(o)},
    board:{addObject:o=>objects.push(o)}, _cropInfo:{startX:0,startY:0,displayLines:9},
    initLogicBoard:()=>{}, placeStone:()=>{}, _bx:x=>x, _by:y=>y, WGo:{B:1,W:-1},
    makeAnswerRoot:t=>t, setMsg:()=>{}, playerColor:'B', I18n:{t:k=>k}, _mapBattleV1Mode:'inactive',
  });
  vm.runInContext(index.slice(index.indexOf('function resetProblem(){'),index.indexOf('function showAnswer(){')),context);
  context.resetProblem();
  assert.equal(objects.filter(o=>o.type).length,p.annotations.length);
  assert.ok(!JSON.stringify(objects).includes('SECRET'));
  assert.equal(context.solved,false);
});
// This is static evidence, not an authenticated HTTP entitlement test.
check('G074 baseline and G075 source preserve protected question entitlement', () => {
  const baseline = spawnSync('git', ['show', 'b39b35481de43ee5de6f3dc70e215d2cf291c56b:app.py'], { cwd: root, encoding: 'utf8', maxBuffer: 8e6 });
  assert.equal(baseline.status, 0, 'G074 protected baseline must exist');
  const current = fs.readFileSync(path.join(root, 'app.py'), 'utf8').replaceAll('\r\n', '\n');
  for (const code of [baseline.stdout.replaceAll('\r\n', '\n'), current]) {
    assert.match(code, /content = q.get\('content', ''\) if \(premium or not locked\) else ''/, 'locked questions must not expose content');
    assert.match(code, /@login_required\ndef get_question\(qid\)/, 'question lookup requires authentication');
    assert.match(code, /@app.route\('\/g010_m4_quest_leaderboard\.js'\)\ndef serve_g010_m4_quest_leaderboard_js\(\)/, 'G074 public leaderboard JS route remains public');
    assert.match(code, /@app.route\('\/g010_m4_quest_leaderboard\.css'\)\ndef serve_g010_m4_quest_leaderboard_css\(\)/, 'G074 public leaderboard CSS route remains public');
  }
});
const browserScript = `
${parserSource}
const cases = ${JSON.stringify(visualCases)};
let count=0; const errors=[];
for (const item of cases) {
 try {
  const card=document.createElement('section');document.body.appendChild(card);
  const title=document.createElement('h3');title.textContent=item.name;card.appendChild(title);
  const wrap=document.createElement('div');card.appendChild(wrap);
  const p=item.problem,crop=item.crop;
  const b=new WGo.Board(wrap,{width:220,size:crop.displayLines});
  const draw=()=>{
   b.removeAllObjects();
   for(const [field,c] of [['black',WGo.B],['white',WGo.W]])for(const s of p[field])b.addObject({x:s.x-crop.startX,y:s.y-crop.startY,c});
   GoOdysseyBoardRenderer.renderAnnotations(b,p,crop);
  };
  draw(); b.setDimensions(180,180); b.setDimensions(220,220);
  const before=JSON.stringify(b.getState()); draw();
  if(before!==JSON.stringify(b.getState()))throw Error('reset changed objects');
  const objs=b.obj_arr.flat(2);
  for(const m of p.annotations)if(!objs.some(o=>o.x===m.x-crop.startX&&o.y===m.y-crop.startY&&o.type===m.type&&o.text===m.text))throw Error('missing marker');
  if(!wrap.querySelector('canvas'))throw Error('no canvas');
  card.style.transform='translate(2px, 3px) scale(.98)';
  card.dataset.markerCount=String(p.annotations.length); count++;
 }catch(e){errors.push(item.name+': '+e.message);}
}
document.documentElement.dataset.result=errors.length?'FAIL':'PASS';
document.getElementById('result').textContent=JSON.stringify({count,errors});
`;
const html = `<!doctype html><meta charset="utf-8"><style>body{background:#eee;display:flex;flex-wrap:wrap;font:12px sans-serif}section{margin:4px}h3{margin:4px}#result{width:100%}</style><pre id="result">RUNNING</pre><script src="../../../wgo/wgo.min.js"></script><script src="../../../js/game/board_renderer.js"></script><script>${browserScript}</script>`;
fs.writeFileSync(path.join(out,'browser.html'),html);
const browser = process.env.G064_CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
let browserStatus = 'SKIP';
if (fs.existsSync(browser)) {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'g064-chrome-'));
  const result = spawnSync(browser, ['--headless','--disable-gpu','--no-first-run','--no-default-browser-check','--allow-file-access-from-files',`--user-data-dir=${profile}`,'--window-size=1920,4400',`--screenshot=${path.join(out,'boards.png')}`,'--dump-dom',new URL('file:///' + path.join(out,'browser.html').replaceAll('\\','/')).href], { encoding:'utf8', timeout:45000, maxBuffer:4e6 });
  fs.writeFileSync(path.join(out,'browser-dom.html'), result.stdout || '');
  fs.writeFileSync(path.join(out,'browser-stderr.txt'), result.stderr || String(result.error || ''));
  browserStatus = /data-result="PASS"/.test(result.stdout || '') ? 'PASS' : 'FAIL';
}
const report = { source:'d0f16e6ed1f7283ea39a1826d52a464a8a981cba', checks, browser:browserStatus, browserCases:visualCases.length, liveAnonymousAndPremium:'SKIP: no isolated authenticated server/DB fixture', actualCorpusCounts:'NOT_EVALUATED', choiceButtonRuntime:'NOT_IMPLEMENTED: requires server contract', status: checks.some(c=>c.status==='FAIL') || browserStatus==='FAIL' ? 'FAIL' : 'PASS' };
fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report,null,2));
if(report.status==='FAIL')process.exitCode=1;
