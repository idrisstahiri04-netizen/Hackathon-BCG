'use strict';
const fs=require('fs'),path=require('path'),{spawn}=require('child_process'),http=require('http');
const {chromium}=require('playwright');
const REPO=path.resolve(__dirname,'..','..'),PORT=8880,BASE=`http://127.0.0.1:${PORT}/`;
const SC=path.join(__dirname,'screens');fs.mkdirSync(SC,{recursive:true});
const wait=(ms=8000)=>new Promise((res,rej)=>{const t0=Date.now();(function k(){http.get({host:'127.0.0.1',port:PORT,path:'/'},x=>{x.resume();res()}).on('error',()=>Date.now()-t0>ms?rej(new Error('srv')):setTimeout(k,200))})()});
const ui=p=>p.evaluate(()=>{
  const ph=[...document.querySelectorAll('#legend-items li[data-phase]')].map(li=>({ph:+li.dataset.phase,hidden:li.hidden,ct:li.querySelector('.ct')?.textContent}));
  return {clock:document.querySelector('#clock-date')?.textContent,view:document.querySelector('#horizon button.on')?.dataset.view,
   layer:document.querySelector('#layer-switch button.on')?.dataset.layer,ph,
   note:document.querySelector('#legend-note')?.hidden?null:document.querySelector('#legend-note').textContent,
   cap:document.querySelector('#view-cap')?.hidden?null:document.querySelector('#view-cap').textContent,
   title:document.querySelector('#legend .legend-title')?.textContent};});
const truth=(p)=>p.evaluate(()=>{ // decoded in place by REAL.forCountry
  const R=RISK_DATA.KEN,out={n:R.units.length,tab:{}};
  for(let t=0;t<93;t++){out.tab[t]={};for(let L=1;L<=8;L++){let c=0,pub='',sc={};for(const u of R.units){const r=u.series[t];const f=r&&r.forecast&&r.forecast[L];if(f&&f.fews_phase!=null){c++;if(f.fews_published&&f.fews_published>pub)pub=f.fews_published;sc[f.fews_scenario]=(sc[f.fews_scenario]||0)+1;}}out.tab[t][L]={c,pub,sc};}}
  return out;});
(async()=>{
  const srv=spawn('python3',['-m','http.server',String(PORT),'--bind','127.0.0.1'],{cwd:REPO,stdio:'ignore'});
  const res={js:[],cons:[],rows:[],flow:{}};
  try{await wait();
  const b=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader']});
  const mk=async()=>{const c=await b.newContext({viewport:{width:1440,height:900}});const p=await c.newPage();
    p.on('pageerror',e=>res.js.push(String(e.message)));
    p.on('console',m=>{if(m.type()==='error'){const t=m.text()+' @ '+(m.location().url||'');if(!/ERR_CONNECTION_REFUSED|net::|Failed to fetch/.test(t))res.cons.push(t)}});return p};
  // 1 flow
  for(const role of ['gov','ngo']){
    const p=await mk();const t0=Date.now();await p.goto(BASE,{waitUntil:'load'});
    const landVis=await p.evaluate(()=>!document.getElementById('landing').hidden);
    await p.screenshot({path:path.join(SC,`ken_fews_landing_${role}.png`)});
    await p.click(`[data-pick=${role}]`);
    await p.click('#search').catch(()=>{});
    await p.fill('#search','Kenya');await p.waitForTimeout(300);
    await p.locator('#results li').filter({hasText:'Kenya'}).first().click();
    await p.waitForFunction(()=>document.querySelector('#clock-date')&&/20\d\d/.test(document.querySelector('#clock-date').textContent)&&document.querySelectorAll('#legend-items li').length,{timeout:60000});
    await p.waitForTimeout(1500);
    res.flow[role]={landVis,ms:Date.now()-t0,stat:await p.evaluate(()=>document.querySelector('#stat-units')?.textContent)};
    await p.screenshot({path:path.join(SC,`ken_fews_flow_${role}.png`)});
    await p.context().close();
  }
  // 2 URL-param loads (hard refresh each = new context)
  const samples=[0,30,60,70,80,86,89,90,91,92];
  let T=null;
  for(const t of samples)for(const v of ['now','f1','f3','f6'])for(const layer of (v==='now'?['fews']:['fews','model','both'])){
    if(layer!=='fews'&&![0,60,92,80].includes(t))continue;
    const p=await mk();const t0=Date.now();
    await p.goto(`${BASE}?country=Kenya&t=${t}&view=${v}&layer=${layer}&role=gov`,{waitUntil:'load'});
    await p.waitForFunction(()=>window.APP&&document.querySelector('#clock-date')&&/20\d\d/.test(document.querySelector('#clock-date').textContent)&&document.querySelectorAll('#legend-items li[data-phase]').length>=0,{timeout:60000});
    await p.waitForTimeout(1200);
    if(!T)T=await truth(p);
    const s=await ui(p);s.ms=Date.now()-t0;s.t=t;s.req=v;s.reqLayer=layer;res.rows.push(s);
    if(layer==='fews'&&((v==='f3'&&[60,80,90].includes(t))||(v==='f1'&&t===92)||(v==='f6'&&[0,70].includes(t))))await p.screenshot({path:path.join(SC,`ken_fews_t${t}_${v}.png`)});
    await p.context().close();
  }
  res.truth=T;
  await b.close();}finally{srv.kill()}
  fs.writeFileSync('/tmp/claude-1000/-home-looooo-bcg/4f524ffb-b166-48f7-afb4-e7e249962e72/scratchpad/ken_audit.json',JSON.stringify(res));
  console.log('done',res.rows.length,res.js,res.cons.slice(0,5),JSON.stringify(res.flow));
})();
