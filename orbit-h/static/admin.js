'use strict';
const $=id=>document.getElementById(id),fa=n=>Number(n).toLocaleString('fa-IR'), phases={idle:'آمادهٔ تیم‌یابی',forming:'تیم‌یابی باز است',playing:'مأموریت در جریان',paused:'زمان متوقف شده',ended:'پایان عملیات'}, actions={form:'باز کردن تیم‌یابی',start:'شروع فوری مأموریت',pause:'توقف زمان',resume:'ادامهٔ زمان',end:'پایان رویداد'};
let data=null,serial=0,at=0,dirty=false,busy=false,logged=false,msgTimer=0,teamsKey='',actionsKey='';
function status(t){clearTimeout(msgTimer);$('status').textContent=t;if(t)msgTimer=setTimeout(()=>{$('status').textContent=''},6500)}
function el(tag,text,cls){const e=document.createElement(tag);e.textContent=text||'';if(cls)e.className=cls;return e}
async function api(path,body){const r=await fetch('/api/admin/'+path,{cache:'no-store',...(body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})});let j=await r.json();if(!r.ok||j.error){const e=new Error(j.error||'ارتباط برقرار نشد.');e.code=r.status;throw e}return j}
function mode(on){$('login').hidden=on;$('dash').hidden=!on;logged=on;if(!on){$('teams').replaceChildren();data=null;dirty=false;teamsKey='';actionsKey=''}}
function clock(){if(!data)return;let s=Math.max(0,Math.ceil(data.remaining-(['forming','playing'].includes(data.phase)?(Date.now()-at)/1000:0)));$('clock').textContent=['idle','ended'].includes(data.phase)?'—':[Math.floor(s/60),s%60].map(v=>String(v).padStart(2,'0')).join(':')}
function btn(text,fn,cls){const b=el('button',text,cls);b.type='button';b.onclick=fn;return b}
function answerKey(id){
  const wrap=el('div','','answer-key'), panel=el('div','','answer-key-panel');
  const show='نمایش پاسخ‌نامه', hide='بستن پاسخ‌نامه';
  let version=0;
  const toggle=btn(show,async()=>{
    const token=++version, opening=panel.hidden;
    toggle.setAttribute('aria-expanded',String(opening));
    toggle.textContent=opening?hide:show;
    panel.hidden=!opening;
    panel.replaceChildren();
    if(!opening)return;
    panel.textContent='در حال دریافت پاسخ‌ها…';
    try{
      const {stages}=await api(`teams/${id}/answer-key`);
      if(token!==version || !panel.isConnected)return;
      const list=el('ol');
      for(const {stage,title,answer} of stages){
        const row=el('li'), value=el('bdi',answer);
        value.dir='ltr';
        row.append(el('strong',`مرحلهٔ ${fa(stage)}: ${title} — `),value);
        list.append(row);
      }
      panel.replaceChildren(list);
    }catch(e){
      if(token!==version || !panel.isConnected)return;
      if(e.code===401 || e.code===403){++serial;mode(false)}else panel.textContent=e.message;
    }
  },'secondary');
  panel.id=`answer-key-${id}`;panel.hidden=true;
  toggle.setAttribute('aria-controls',panel.id);toggle.setAttribute('aria-expanded','false');
  wrap.dataset.team=id;wrap.append(toggle,panel);return wrap;
}
function teams(){const query=$('filter').value.trim(), key=JSON.stringify([data.teams,query]);if(key===teamsKey)return;teamsKey=key;const dest=$('teams'),opened=new Set([...dest.querySelectorAll('details[open]')].map(d=>d.dataset.id));const keys=new Map([...dest.querySelectorAll('.answer-key')].map(k=>[k.dataset.team,k]));const next=document.createDocumentFragment();for(const t of data.teams.filter(t=>[t.name,t.code,...t.members.map(m=>m.name)].some(n=>n.includes(query)))){const box=el('div','','crew'), row=el('div','','top'), b=el('div','','buttons');row.append(el('strong',t.name),el('bdi',t.code));box.append(row,el('p',`${fa(t.members.length)} عضو · ${fa(t.stage)} از ۴ مرحله · ${fa(t.score)} امتیاز`));b.append(btn('اصلاح امتیاز',()=>{const val=prompt('تغییر امتیاز با عدد مثبت یا منفی (مثلاً ‎-۱۰)');if(val===null)return;const num=val.trim().replace(/[۰-۹]/g,x=>'۰۱۲۳۴۵۶۷۸۹'.indexOf(x));if(!/^-?\d+$/.test(num))return status('یک عدد صحیح وارد کنید.');run('score',{teamId:t.id,delta:Number(num)})},'secondary'));box.append(b);const d=el('details');d.dataset.id=t.id;d.open=opened.has(String(t.id));d.append(el('summary','اعضای تیم'));const list=el('ul');for(const m of t.members){let li=el('li',m.name);li.append(btn('حذف عضو',()=>{if(confirm(`«${m.name}» از تیم «${t.name}» حذف شود؟`))run('kick',{memberId:m.id,teamId:t.id})},'danger'));list.append(li)}d.append(list);box.append(d,keys.get(String(t.id))||answerKey(t.id));next.append(box)}if(!next.children.length)next.append(el('p',query?'نتیجه‌ای پیدا نشد.':'هنوز تیمی ساخته نشده است.'));dest.replaceChildren(next)}
function render(){mode(true);$('phase').textContent=phases[data.phase];$('counts').textContent=`${fa(data.teams.length)} تیم  /  ${fa(data.teams.reduce((s,t)=>s+t.members.length,0))} شرکت‌کننده`;for(const field of $('settings').elements)field.disabled=data.phase!=='idle';if(!dirty)for(const k of ['formingMinutes','playMinutes','capacity'])$('settings').elements[k].value=data[k];$('currentMsg').textContent=data.announcement?'پیام فعلی: '+data.announcement:'پیام فعالی نیست.';if(actionsKey!==data.phase){actionsKey=data.phase;const controls=$('controls');controls.replaceChildren();for(const a of ({idle:['form'],forming:['start','pause','end'],playing:['pause','end'],paused:['resume','end'],ended:[]}[data.phase]||[]))controls.append(btn(actions[a],()=>{if(['end','start'].includes(a)&&!confirm(actions[a]+'؟'))return;run(a)},a==='end'?'danger':''));if(!controls.children.length)controls.append(el('span','برای اجرای بعدی، خروجی بگیرید و رویداد را بازنشانی کنید.'))}teams();clock();$('log').replaceChildren(...data.log.map(x=>el('li',x)))}
async function sync(){const n=++serial;try{let d=await api('state');if(n!==serial)return;data=d;at=Date.now();render()}catch(e){if(n!==serial)return;if([401,403].includes(e.code)){mode(false)}else status('وضعیت تازه نشد؛ اتصال را بررسی کنید.')}}
async function run(action,extra={}){if(busy)return;busy=true;try{await api('action',{action,...extra});if(action==='settings'||action==='reset')dirty=false;if(action==='announce')$('announce').reset();status('تغییر ثبت شد.')}catch(e){status(e.message)}finally{busy=false;await sync()}}
$('loginForm').onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;try{await api('login',{password:e.target.password.value});e.target.reset();status('ورود موفق.');await sync()}catch(err){status(err.message)}finally{busy=false}};
$('logout').onclick=async()=>{try{await api('logout',{});++serial;mode(false);status('از پنل خارج شدید.')}catch(e){status(e.message)}};
$('settings').oninput=()=>{dirty=true};$('settings').onsubmit=e=>{e.preventDefault();run('settings',Object.fromEntries([...new FormData(e.target)].map(([k,v])=>[k,Number(v)])))};$('announce').onsubmit=e=>{e.preventDefault();run('announce',{text:e.target.elements.text.value.trim()})};$('reset').onclick=()=>{if(prompt('همهٔ تیم‌ها و نتایج پاک می‌شوند. برای تأیید کلمهٔ «پاک» را بنویسید.')==='پاک')run('reset')};$('filter').oninput=teams;
sync().finally(()=>{if($('status').textContent==='در حال دریافت وضعیت…')status('')});setInterval(()=>{if(logged&&!busy&&!document.hidden)sync()},3500);setInterval(clock,300);
