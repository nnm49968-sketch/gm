'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const show = (id, yes) => { $(id).hidden = !yes; };
  const text = (id, value = '') => { const s=String(value ?? ''); if ($(id).textContent !== s) $(id).textContent=s; };
  const fa = n => Number(n).toLocaleString('fa-IR');
  const phases = {idle:'پیش از شروع',forming:'تیم‌سازی',playing:'در حال بازی',paused:'توقف موقت',ended:'پایان بازی'};
  const keyCache = new Map();
  let state, connected=false, joining=false, pending=false, serial=0, reading=false, sampledAt=0, lastStage;
  function list(id, data, build) {
    const sig=JSON.stringify(data); if(keyCache.get(id)===sig) return;
    const el=$(id), atBottom=el.scrollHeight-el.scrollTop-el.clientHeight<24;
    el.replaceChildren(...data.map(build)); keyCache.set(id,sig);
    if(id==='messages' && atBottom) el.scrollTop=el.scrollHeight;
  }
  function node(tag,value) { const el=document.createElement(tag); el.textContent=value; return el; }
  function tick() {
    if(!state || !connected || state.phase==='idle') {text('timer','--:--'); return;}
    const elapsed=['forming','playing'].includes(state.phase)? Math.floor((performance.now()-sampledAt)/1000):0;
    const n=Math.max(0,Math.ceil(state.remaining||0)-elapsed);
    text('timer',[Math.floor(n/60),n%60].map(v=>String(v).padStart(2,'0').replace(/\d/g,c=>'۰۱۲۳۴۵۶۷۸۹'[c])).join(':'));
  }
  $('scratch').oninput=()=>{try{sessionStorage.setItem('hard-notes:'+lastStage,$('scratch').value)}catch{}};
  function controls(){document.querySelectorAll('.primary,#leave,#hint').forEach(b=>b.disabled=pending || !connected);}
  function render(s) {
    const {phase,team,puzzle,leaders=[]}=s, forming=phase==='forming', play=phase==='playing', paused=phase==='paused';
    const stageKey=JSON.stringify([team?.code,s.me?.id,team?.stage]);
    if(lastStage!==stageKey){$('answer').value='';$('clueBox').open=true;lastStage=stageKey;try{$('scratch').value=sessionStorage.getItem('hard-notes:'+stageKey)||''}catch{$('scratch').value=''}}
    if(state?.team?.id!==team?.id){$('message').value='';text('chatFeedback');}
    state=s; connected=true; sampledAt=performance.now(); tick();
    text('link','ارتباط زنده');$('link').classList.add('live');show('connection',false);
    text('phase',phases[phase]);text('code',team?.code||'—');$('code').dir='auto';text('announcement',s.announcement);show('announcement',!!s.announcement);
    show('boarding',forming&&!team);show('teamInfo',!!team);show('leave',forming&&team);show('radio',!!team);
    show('chat',!!team&&['forming','playing'].includes(phase));
    const complete=team?.stage>=4;
    text('deskTitle',team ? (complete?'هر چهار معما حل شد':'میز بازی تیم') : forming?'ورود بازیکن':'میز بازی');
    const summaries={idle:'وقتی تیم‌سازی شروع شود، همین‌جا می‌توانی تیم بسازی یا به تیم دوستانت بپیوندی. نیازی به تازه‌کردن صفحه نیست.',forming:team?'کد تیم را برای دوستانت بفرست. با شروع بازی، سرنخت را اینجا می‌بینی.':`نامت را بنویس. برای پیوستن به تیم دوستانت، کد تیم را از آن‌ها بگیر.${s.capacity?' ظرفیت هر تیم: '+fa(s.capacity)+' نفر.':''}`,playing:team?(complete?'همهٔ مراحل را حل کردید. جایگاه تیم را در جدول ببینید.':'سرنخ‌ها را بررسی کنید و با هم پاسخ مرحله را بیابید.'):'تیم‌سازی به پایان رسیده است. می‌توانید جدول تیم‌ها را دنبال کنید.',paused:'بازی مکث کرده است. با ادامهٔ بازی می‌توانید پاسخ بفرستید.',ended:'بازی تمام شد. نتیجهٔ تیم‌ها را در جدول ببینید.'};
    text('summary',summaries[phase]);
    text('teamLabel',team?.name);text('score',team?`${fa(team.score)} امتیاز`:'');
    list('members',team?.members||[],m=>node('li',m.name+(m.id===s.me?.id?' (شما)':'')));
    list('messages',team?.messages||[],m=>{const li=node('li','');li.append(node('b',m.name),node('span',m.text));return li;});
    const challenge=!!team&&!complete&&(play||paused)&&!!puzzle;
    show('challenge',challenge);text('stage',challenge?`مرحلهٔ ${fa(team.stage+1)} از ۴`:'');text('pTitle',challenge?puzzle.title:'');text('prompt',challenge?puzzle.prompt:'');
    list('clues',challenge?puzzle.clues||[]:[],c=>node('li',c));text('format',challenge?puzzle.format:'');
    text('hintText',challenge?puzzle.hint:'');show('hintText',challenge&&!!puzzle.hint);show('hint',challenge&&play&&!team.hintUsed&&!puzzle.hint);show('solve',challenge&&play);
    document.querySelectorAll('.track li').forEach((el,i)=>{el.classList.toggle('done',i<team?.stage); const active=challenge&&i===team.stage;el.classList.toggle('active',active);el.setAttribute('aria-current',active?'step':'false');el.setAttribute('aria-label',`مرحلهٔ ${fa(i+1)}${i<team?.stage?'، حل شده':''}`);});
    show('rankTable',leaders.length>0);show('noRanks',!leaders.length);list('ranks',leaders,(row,i)=>{const tr=node('tr','');[fa(i+1),row.name,fa(row.stage),fa(row.score)].forEach(v=>tr.append(node('td',v)));return tr;});controls();
  }
  async function refresh(force=false){
    if(!force&&(reading||pending||document.hidden))return;
    const seq=++serial; reading=true;
    try{const r=await fetch('/api/state',{cache:'no-store',signal:AbortSignal.timeout(9000)});if(!r.ok) throw Error();const s=await r.json();if(!(s.phase in phases))throw Error();if(seq===serial)render(s);}
    catch{if(seq!==serial)return;connected=false;controls();tick();text('link','ارتباط قطع است');$('link').classList.remove('live');text('connection','اتصال به بازی قطع شده است. صفحه خودش دوباره تلاش می‌کند.');show('connection',true);if(!state)text('summary','در انتظار اتصال به بازی…');}
    finally{if(seq===serial)reading=false;}
  }
  async function send(action,body,resultId='feedback',onSuccess){
    if(pending||!connected)return; pending=true; ++serial; reading=false; controls();text(resultId,'در حال ارسال…');
    try{const r=await fetch('/api/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(10000)});const d=await r.json();
      if(!r.ok||!d.ok)text(resultId,d.error||'درخواست پذیرفته نشد.');else{onSuccess?.();text(resultId,d.message||'درخواست ثبت شد.');}
    }catch{text(resultId,'تأیید دریافت نشد. پیش از ارسال دوباره، وضعیت را بررسی کنید.');}
    finally{await refresh(true);pending=false;controls();}
  }
  function mode(join){joining=join;show('teamField',!join);show('joinField',join);$('joinCode').disabled=!join;$('joinCode').required=join;$('teamName').disabled=join;$('teamName').required=!join;$('createTab').setAttribute('aria-pressed',String(!join));$('joinTab').setAttribute('aria-pressed',String(join));text('enter',join?'پیوستن به تیم':'ساخت تیم');}
  $('createTab').onclick=()=>mode(false);$('joinTab').onclick=()=>mode(true);
  function value(id){return $(id).value.trim();}
  $('entry').onsubmit=e=>{e.preventDefault();const name=value('name'),target=value(joining?'joinCode':'teamName');if(!name||!target){text('feedback','لطفاً هر دو فیلد را کامل کنید.');return;}send(joining?'join':'create',joining?{name,code:target}:{name,team:target});};
  $('leave').onclick=()=>{if(confirm('از این تیم خارج می‌شوید؟'))send('leave',{});};
  $('hint').onclick=()=>{if(confirm('با راهنما، امتیاز حل این مرحله از ۱۰۰ به ۸۰ می‌رسد. راهنما برای کل تیم باز شود؟'))send('hint',{stage:state.team.stage});};
  $('solve').onsubmit=e=>{e.preventDefault();if(value('answer'))send('answer',{stage:state.team.stage,answer:value('answer')});else text('feedback','پاسخ را وارد کنید.');};
  $('chat').onsubmit=e=>{e.preventDefault();const msg=value('message');if(msg)send('chat',{text:msg},'chatFeedback',()=>{if(value('message')===msg)$('message').value='';});else text('chatFeedback','پیامی بنویسید.');};
  setInterval(refresh,2500);setInterval(tick,500);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});window.addEventListener('online',()=>refresh());refresh();
})();
