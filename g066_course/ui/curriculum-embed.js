/* Load only via the G/D proposal. OFF or failed summary leaves existing DOM intact. */
(async () => {
  'use strict';
  try {
    const response=await fetch('/api/course-v1/summary',{credentials:'same-origin',cache:'no-store'});
    if(!response.ok)return;
    const data=await response.json();
    if(!data.candidate || data.version!=='initiation-20261022-v1')return;
    const main=document.querySelector('main.guild-main');
    if(!main || document.getElementById('g066-tabs'))return;
    const legacy=document.createElement('section');legacy.id='g066-existing-curriculum';
    legacy.setAttribute('role','tabpanel');legacy.setAttribute('aria-labelledby','g066-legacy-tab');
    while(main.firstChild)legacy.append(main.firstChild);
    const panel=document.createElement('section');panel.id='g066-course-panel';panel.hidden=true;
    panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby','g066-course-tab');
    const frame=document.createElement('iframe');frame.title='啟蒙班 20 課';
    frame.style.cssText='width:100%;height:1050px;border:0;border-radius:14px';panel.append(frame);
    const tabs=document.createElement('div');tabs.id='g066-tabs';tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','課程與公會');
    const buttons=['任務與進度','啟蒙班 20 課'].map((text,i)=>{
      const b=document.createElement('button');b.textContent=text;b.id=i?'g066-course-tab':'g066-legacy-tab';
      b.setAttribute('role','tab');b.setAttribute('aria-controls',i?panel.id:legacy.id);
      b.style.cssText='font:inherit;padding:10px 18px;background:#1b2b50;color:#f5eddc;border:1px solid #b79554;border-radius:8px;margin:0 8px 20px 0';
      b.onclick=()=>activate(i);tabs.append(b);return b;
    });
    function activate(i){legacy.hidden=Boolean(i);panel.hidden=!i;
      buttons.forEach((b,n)=>{b.setAttribute('aria-selected',String(n===i));b.tabIndex=n===i?0:-1;});
      if(i && !frame.getAttribute('src'))frame.src='/course-v1/';}
    tabs.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();
      const i=e.key==='Home'?0:e.key==='End'?1:buttons[0].tabIndex===0?1:0;activate(i);buttons[i].focus();};
    main.append(tabs,legacy,panel);activate(0);
  } catch (_) { /* Existing quest-board remains available. */ }
})();
