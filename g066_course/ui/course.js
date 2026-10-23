/* All progress and verdicts come from the server. No localStorage authority. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  let number, run, slot = 0, retryId, moves = [], answered = [], retrySlot;
  const status = text => { $('course-status').textContent = text; };
  const errors = {course_feature_off:'課程尚未開放（功能旗標 OFF）',login_required:'請先登入',verified_video_required:'影片學習紀錄尚未通過伺服器驗證',media_owner_review_required:'本課影片待 Owner 驗收',katago_review_required:'題目仍待 KataGo 覆核',previous_lesson_required:'請先完成前一課',daily_retry_limit:'今日重試已達候選規則上限',daily_new_lesson_limit:'今日新課已達候選規則上限'};
  async function api(path, body) {
    const options = {credentials:'same-origin',cache:'no-store'};
    if (body) Object.assign(options,{method:'POST',headers:{'Content-Type':'application/json','X-Course-CSRF':document.querySelector('meta[name="course-csrf"]')?.content || ''},body:JSON.stringify({...body,request_id:crypto.randomUUID()})});
    const response = await fetch('/api/course-v1/' + path, options);
    const data = await response.json();
    if (!response.ok) throw Error(errors[data.error] || data.error || '暫時無法讀取');
    return data;
  }
  const safe = fn => async () => { try { await fn(); } catch(error) { status(error.message); } };
  async function refresh() {
    const data = await api('summary'); $('lessons').replaceChildren();
    for (let week=1;week<=4;week++) {
      const title=document.createElement('h2');title.textContent=`第 ${week} 週`;$('lessons').append(title);
      for (const lesson of data.lessons.filter(l=>l.week===week)) {
        const button=document.createElement('button');button.textContent=`${lesson.complete?'✓ ':''}${lesson.number}. ${lesson.title}`;
        button.disabled=!lesson.unlocked;button.dataset.lesson=lesson.number;
        button.setAttribute('aria-current',String(number===lesson.number));
        button.onclick=safe(()=>select(lesson));$('lessons').append(button);
      }
    }
    status('課程候選 · 進度由伺服器驗證');
  }
  async function select(lesson) {
    number=lesson.number; run=null; retryId=null; $('practice').hidden=true; $('start').disabled=false;
    $('lesson-title').textContent=`第 ${number} 課 · ${lesson.title}`;
    document.querySelectorAll('[data-lesson]').forEach(b=>b.setAttribute('aria-current',String(Number(b.dataset.lesson)===number)));
    const video=$('video');video.pause();video.removeAttribute('src');video.hidden=true;video.replaceChildren();
    try {
      const media=await api(`media/${number}`);
      const url=new URL(media.external_url,location.href);
      if(url.protocol!=='https:') throw Error('媒體外部網址尚未核准');
      video.src=url.href;video.hidden=false;$('media-status').textContent='觀看後由伺服器驗證學習紀錄';
    } catch(error) {$('media-status').textContent=error.message;}
  }
  async function question() {
    moves=[];$('moves').textContent='請選擇落點'; $('retry').hidden=true;$('replace').hidden=true;$('next').hidden=true;
    $('submit').disabled=false;$('clear').disabled=false;
    const data=await api(`question?run_id=${encodeURIComponent(run)}&slot=${slot}${retryId?'&retry_id='+encodeURIComponent(retryId):''}`);
    $('question-title').textContent=`練習 ${slot+1} / 8${retryId?' · 錯題複習（不改首次分數）':''}`;
    const board=$('board');board.replaceChildren();board.style.gridTemplateColumns=`repeat(${data.board_size},1fr)`;
    for(let y=0;y<data.board_size;y++) for(let x=0;x<data.board_size;x++) {
      const cell=document.createElement('button'),stone=data.stones.find(s=>s.x===x&&s.y===y);
      cell.setAttribute('aria-label',`${x+1},${y+1}${stone?' '+stone.color:''}`);cell.dataset.stone=stone?.color || '';
      cell.textContent=stone?'●': '+';cell.disabled=Boolean(stone);
      cell.onclick=()=>{moves.push({x,y});$('moves').textContent=moves.map(m=>`(${m.x+1},${m.y+1})`).join(' → ');};board.append(cell);
    }
    $('practice').hidden=false;
  }
  $('start').onclick=safe(async()=>{
    const data=await api('start',{lesson:number});run=data.run_id;answered=data.answers;
    $('review-label').hidden=true;
    slot=Array.from({length:8},(_,i)=>i).find(i=>!answered.some(a=>a.slot===i));retryId=null;
    if(slot===undefined){status(data.complete?'本課已完成':'本課首次測驗未達 6 題；可複習錯題，補考規則待 Owner 決定');
      const wrong=answered.filter(a=>!a.first_correct);
      if(!wrong.length){$('practice').hidden=true;return;}
      $('review-slot').replaceChildren();
      for(const a of wrong){const option=document.createElement('option');option.value=a.slot;option.textContent=`練習 ${a.slot+1}`;$('review-slot').append(option);}
      $('review-label').hidden=false;slot=wrong[0].slot;await question();$('submit').disabled=true;showRetry();return;}
    await question();
  });
  function showRetry(){ $('retry').hidden=false;$('replace').hidden=false;retrySlot=slot; }
  $('review-slot').onchange=safe(async()=>{slot=Number($('review-slot').value);retryId=null;await question();$('submit').disabled=true;showRetry();});
  $('submit').onclick=safe(async()=>{
    $('submit').disabled=true;
    try {
      const data=await api('answer',{run_id:run,slot,moves,...(retryId?{retry_id:retryId}:{})});
      $('score').textContent=`${data.outcome==='CORRECT'?'答對了':'再想一想'} · 首次答對 ${data.first_correct}/8 · 已作答 ${data.answered}/8${data.complete?' · 已解鎖下一課':''}`;
      if(!retryId) answered.push({slot,first_correct:data.outcome==='CORRECT'?1:0});
      if(data.outcome==='INCORRECT')showRetry();
      $('next').hidden=false;await refresh();
    } catch(e){$('submit').disabled=false;throw e;}
  });
  for(const [id,replace] of [['retry',false],['replace',true]]) $(id).onclick=safe(async()=>{
    slot=retrySlot;const data=await api('retry',{run_id:run,slot,replace});retryId=data.retry_id;await question();
  });
  $('clear').onclick=()=>{moves=[];$('moves').textContent='請選擇落點';};
  $('next').onclick=safe(async()=>{retryId=null;const pending=Array.from({length:8},(_,i)=>i).find(i=>!answered.some(a=>a.slot===i));
    if(pending===undefined){$('practice').hidden=true;status('本課作答結束，可繼續下一課或回到本課複習');return;}slot=pending;await question();});
  safe(refresh)();
})();
