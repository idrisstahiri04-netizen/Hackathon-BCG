'use strict';
const fs=require('fs'),path=require('path'),http=require('http');
const {spawn}=require('child_process');
const {chromium}=require('playwright');
const PORT=8801,BASE=`http://127.0.0.1:${PORT}/`,REPO=path.resolve(__dirname,'..','..');
const SC=path.join(__dirname,'screens');fs.mkdirSync(SC,{recursive:true});
const MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const lab=t=>`${MON[t%12]} ${2019+Math.floor(t/12)}`;
const load=iso=>{const src=fs.readFileSync(path.join(REPO,'data','risk',iso+'.js'),'utf8');const tag=`RISK_DATA["${iso}"] = `;let s=src.slice(src.indexOf(tag)+tag.length).trim();if(s.endsWith(';'))s=s.slice(0,-1);return JSON.parse(s);};
const waitPort=(p,ms=8000)=>new Promise((res,rej)=>{const t0=Date.now();(function k(){const r=http.get({host:'127.0.0.1',port:p,path:'/'},x=>{x.resume();res()});r.on('error',()=>Date.now()-t0>ms?rej(new Error('no server')):setTimeout(k,150));})();});
const C=[['Zimbabwe','ZWE'],['Kenya','KEN'],['Malawi','MWI'],['Zambia','ZMB'],['Mozambique','MOZ'],['Tanzania','TZA'],['Ethiopia','ETH'],['Somalia','SOM'],['Namibia','NAM'],['Botswana','BWA'],['South Africa','ZAF'],['Madagascar','MDG'],['Angola','AGO'],['Uganda','UGA']];
(async()=>{
  const server=spawn('python3',['-m','http.server',String(PORT),'--bind','127.0.0.1'],{cwd:REPO,stdio:'ignore'});
  const out={checks:{},js:[],con:[]};const ck=(n,ok,i)=>out.checks[n]={pass:!!ok,info:i};
  let b;
  try{
    await waitPort(PORT);
    b=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader']});
    const mk=async(w,h)=>{const c=await b.newContext({viewport:{width:w,height:h}});const p=await c.newPage();
      p.on('pageerror',e=>out.js.push(String(e.message)));
      p.on('console',m=>{if(m.type()==='error'){const t=m.text()+' @ '+(m.location().url||'');if(!/ERR_CONNECTION_REFUSED|Failed to load resource|net::|Failed to fetch/.test(t))out.con.push(t);}});
      await p.route('**/js/config.local.js',r=>r.fulfill({status:200,contentType:'application/javascript',body:'window.SMS_API_BASE="http://127.0.0.1:8603";'}));
      return p;};
    const go=async(p,q)=>{await p.goto(BASE+q,{waitUntil:'load'});await p.waitForFunction(()=>window.RISK_DATA&&window.GEO_DATA&&document.querySelector('#clock-date')&&window.APP);await p.waitForTimeout(1800);};
    const st=p=>p.evaluate(()=>({clock:document.querySelector('#clock-date').textContent,on:document.querySelector('#horizon button.on')?.dataset.view,layer:document.querySelector('#layer-switch button.on')?.dataset.layer,
      title:document.querySelector('#legend .legend-title').textContent,
      legend:[...document.querySelectorAll('#legend-items li')].filter(li=>!li.hidden&&!li.classList.contains('lg-group')).map(li=>li.textContent.trim().replace(/\s+/g,' ')),
      stat:document.querySelector('#stat-units').textContent,statLab:document.querySelector('#stat-units + .stat-lab').textContent,
      note:document.querySelector('#legend-note').hidden?null:document.querySelector('#legend-note').textContent,
      cap:document.querySelector('#view-cap').hidden?null:document.querySelector('#view-cap').textContent,
      conf:[...document.querySelectorAll('#horizon .vs-conf')].map(x=>x.textContent),goToday:document.querySelector('#go-today').hidden,
      top10note:document.querySelector('#top10-note').textContent}));
    // 1. countries
    let p=await mk(1440,900);
    await go(p,'');await p.click('#search');await p.waitForTimeout(300);
    const list=[];const missing=[];
    for(const [n] of C){await p.fill('#search',n);await p.waitForTimeout(150);const t=(await p.locator('#results li').allInnerTexts()).find(x=>x.includes(n));if(!t)missing.push(n);else list.push(t.replace(/\s+/g,' '));}
    await p.fill('#search','');
    ck('search_lists_14',missing.length===0,{missing,list:list.map(x=>x.replace(/\s+/g,' '))});
    const per={};
    for(const [n,iso] of C){
      let R;try{R=load(iso)}catch(e){per[iso]={pass:false,why:'no risk file'};continue;}
      await go(p,`?country=${encodeURIComponent(n)}`);
      const r=await p.evaluate(iso=>({geoN:GEO_DATA[iso]?.features.length,riskN:RISK_DATA[iso]?.units.length,hud:document.querySelector('#hud-sub').textContent,
        legendN:[...document.querySelectorAll('#legend-items li')].map(li=>+li.innerText.trim().split('\n').pop()||0).reduce((a,b)=>a+b,0),
        mv:RISK_DATA[iso]?.meta.model_version}),iso);
      await p.click('#search');await p.waitForTimeout(150);
      const live=(await p.locator('#results li').allInnerTexts()).find(x=>x.includes(n))||'';
      per[iso]={pass:/LIVE/i.test(live)&&r.geoN===r.riskN&&r.riskN===R.units.length&&r.legendN===r.riskN,live:live.replace(/\s+/g,' '),...r};
    }
    ck('countries_live_render',Object.values(per).every(v=>v.pass),per);
    await p.context().close();

    // 2/3. ZWE forecast
    const R=load('ZWE');const NU=R.units.length,LT=R.meta.live_t,thr=R.meta.metrics?.p_crisis?.watch_threshold||0.57;
    const mb=R.units.find(u=>u.name==='Mbire');const F=mb.series[57].forecast;
    const phOK=[1,2,3].every(L=>F[L].fews_phase===2)&&[4,5,6,7].every(L=>F[L].fews_phase===3)&&F[8].fews_phase==null;
    ck('data_mbire_phases',phOK,Object.fromEntries(Object.entries(F).map(([k,v])=>[k,[v.fews_phase,v.fews_scenario,v.p_crisis]])));
    p=await mk(1440,900);
    await go(p,'?country=Zimbabwe&t=57&view=f1&layer=fews&county=Mbire');
    const fewsUI={};
    for(let L=1;L<=8;L++){await p.keyboard.press(String(L));await p.waitForTimeout(300);
      fewsUI[L]=await p.evaluate(()=>({legend:[...document.querySelectorAll('#legend-items li')].filter(li=>!li.hidden).map(li=>li.textContent.trim().replace(/\s+/g,' ')),
        fews:document.querySelector('#detail .fc-fews-line, #detail .fc-fews-head')?.textContent,cap:document.querySelector('#view-cap')?.textContent}));
    }
    ck('oct2023_fews_phase_mbire',[1,2,3].every(L=>/Phase 2/.test(fewsUI[L].fews||''))&&[4,5,6,7].every(L=>/Phase 3/.test(fewsUI[L].fews||'')),Object.fromEntries(Object.entries(fewsUI).map(([k,v])=>[k,v.fews])));
    ck('oct2023_f8_honest',/no (model )?forecast|pending|no outlook/i.test(fewsUI[8].cap+fewsUI[8].legend.join('|')+(fewsUI[8].fews||'')),{cap:fewsUI[8].cap,fews:fewsUI[8].fews,legend:fewsUI[8].legend});
    await p.screenshot({path:path.join(SC,'final_1440_oct2023_fews_f8.png')});
    await go(p,'?country=Zimbabwe&t=57&view=f3&county=Mbire');
    let s=await st(p);
    ck('oct2023_model_layer',s.on==='f3'&&s.layer==='model'&&/chance of Crisis/.test(s.statLab)&&s.conf.length===8&&s.conf.slice(0,3).every(x=>x),{...s,legend:undefined});
    const pan=await p.evaluate(()=>{const d=document.querySelector('#detail');return{hidden:d.hidden,big:d.querySelector('.fc-big')?.textContent,chip:d.querySelector('.fc-conf-chip')?.textContent,confs:d.querySelector('.fc-confs')?.textContent,
      braces:[...d.querySelectorAll('.fc-brace-lab')].map(x=>x.textContent),pub:d.querySelector('.fc-pub')?.textContent,steps:d.querySelectorAll('.fc-step').length,stepsNone:d.querySelectorAll('.fc-step.none').length,chart:!!d.querySelector('svg.fc-chart'),
      notes:[...d.querySelectorAll('.fc-note')].map(x=>x.textContent)}});
    ck('oct2023_chart_ml_step_pub',pan.chart&&pan.braces.join('|')==='ML1|ML2'&&/published (Oct 2023|2023-10)/.test(pan.pub||'')&&!!pan.chip&&!!pan.confs,pan);
    await p.screenshot({path:path.join(SC,'final_1440_oct2023_f3_mbire.png')});
    for(const L of [4,8]){await p.keyboard.press(String(L));await p.waitForTimeout(300);}
    s=await st(p);ck('oct2023_model_f8_pending',/no model forecast/i.test(s.cap||''),s.cap);
    // Feb 2024
    const hot=(t,L)=>R.units.filter(u=>{const f=u.series[t].forecast?.[L];const v=f?(f.p_crisis??f.p):null;return v!=null&&v>=thr}).length;
    const feb={};
    for(const L of [2,3]){await go(p,`?country=Zimbabwe&t=61&view=f${L}`);s=await st(p);feb[L]={ui:s.stat,data:hot(61,L),of:NU,lab:s.statLab};
      await p.screenshot({path:path.join(SC,`final_1440_feb2024_f${L}.png`)});}
    ck('feb2024_counts',[2,3].every(L=>+feb[L].ui===feb[L].data&&feb[L].data>0),feb);
    // go today
    await go(p,'?country=Zimbabwe&t=61&view=f3');
    ck('go_today_visible',!(await st(p)).goToday,null);
    await p.click('#go-today');await p.waitForTimeout(500);
    s=await st(p);ck('go_today_clock',s.clock===lab(LT)&&s.clock==='Sep 2026',s.clock);
    const live={};
    for(let L=1;L<=8;L++){await p.keyboard.press(String(L));await p.waitForTimeout(250);s=await st(p);
      const nul=R.units.filter(u=>{const f=u.series[LT].forecast?.[L];return !f||(f.p_crisis??f.p)==null}).length;
      live[L]={on:s.on,title:s.title,stat:s.stat,nullUnits:nul,cap:s.cap,note:s.note,legend:s.legend.slice(-2)};}
    await p.screenshot({path:path.join(SC,'final_1440_live_sep2026_f8.png')});
    ck('live_f1_f8_render_and_notes',Object.entries(live).every(([L,v])=>v.on===`f${L}`&&v.title.includes(lab(LT+ +L)))&&/some inputs missing/.test(live[1].cap+live[1].note),live);
    await p.context().close();
    // 4. 390
    p=await mk(390,844);
    for(const [nm,q] of [['oct2023_f3','?country=Zimbabwe&t=57&view=f3&county=Mbire'],['feb2024_f3','?country=Zimbabwe&t=61&view=f3'],['live_f2',`?country=Zimbabwe&t=${LT}&view=f2`],['uganda','?country=Uganda']]){
      await go(p,q);const ov=await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
      ck('mobile_no_hscroll_'+nm,!ov,ov);await p.screenshot({path:path.join(SC,`final_390_${nm}.png`)});}
    await p.context().close();
    // 1440 new countries
    p=await mk(1440,900);
    for(const [n] of [['Madagascar'],['Angola'],['Uganda']]){await go(p,`?country=${n}`);await p.screenshot({path:path.join(SC,`final_1440_${n}.png`)});}
    await p.context().close();
    ck('zero_js_errors',out.js.length===0,out.js);ck('zero_console_errors',out.con.length===0,out.con);
  }catch(e){out.fatal=String(e.stack||e);}
  finally{if(b)await b.close().catch(()=>{});server.kill();}
  fs.writeFileSync(path.join(__dirname,'final_results.json'),JSON.stringify(out,null,2));
  console.log(JSON.stringify(Object.fromEntries(Object.entries(out.checks).map(([k,v])=>[k,v.pass])),null,1),out.fatal||'',out.js,out.con);
})();
