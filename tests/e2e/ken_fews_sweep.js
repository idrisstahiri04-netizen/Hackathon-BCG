'use strict';
const fs=require('fs'),path=require('path'),{spawn}=require('child_process'),http=require('http');
const {chromium}=require('playwright');
const REPO=path.resolve(__dirname,'..','..'),PORT=8880;
const wait=()=>new Promise((res,rej)=>{const t0=Date.now();(function k(){http.get({host:'127.0.0.1',port:PORT,path:'/'},x=>{x.resume();res()}).on('error',()=>Date.now()-t0>8000?rej():setTimeout(k,200))})()});
(async()=>{
 const srv=spawn('python3',['-m','http.server',String(PORT),'--bind','127.0.0.1'],{cwd:REPO,stdio:'ignore'});
 try{await wait();
 const out=[];const js=[];let fails=0;
 for(let c0=0;c0<=92;c0+=3){
 let b;try{b=await chromium.launch({channel:'chrome',headless:true,args:['--enable-unsafe-swiftshader']});
 const ctx=await b.newContext({viewport:{width:1100,height:700}});const p=await ctx.newPage();
 p.on('pageerror',e=>js.push(String(e.message)));
 await p.goto(`http://127.0.0.1:${PORT}/?country=Kenya&t=${c0}&view=f1&layer=fews&role=gov`,{waitUntil:'load'});
 await p.waitForFunction(()=>window.APP&&/20\d\d/.test(document.querySelector('#clock-date')?.textContent||''),{timeout:60000});
 await p.waitForTimeout(1500);
 for(let t=c0;t<=Math.min(92,c0+2);t++){
  await p.evaluate(t=>{const s=document.querySelector('#scrub');s.max=Math.max(+s.max,92);s.value=t;s.dispatchEvent(new Event('input',{bubbles:true}));s.dispatchEvent(new Event('change',{bubbles:true}));},t);
  for(const v of [1,3,6]){
   await p.click(`#horizon button[data-view=f${v}]`);
   const s=await p.evaluate(()=>{const ph=[...document.querySelectorAll('#legend-items li[data-phase]')].map(li=>+li.dataset.phase>0?+(li.querySelector('.ct')?.textContent)||0:0);
     return {clock:document.querySelector('#clock-date').textContent,n:ph.reduce((a,b)=>a+b,0),note:document.querySelector('#legend-note')?.hidden?null:document.querySelector('#legend-note').textContent,title:document.querySelector('#legend .legend-title').textContent}});
   out.push({t,v,...s});
  }
 }
 }catch(e){console.log('chunk fail',c0,e.message.slice(0,80));c0-=3;fails++;if(fails>25)break}finally{if(b)await b.close().catch(()=>{})}}
 fs.writeFileSync('/tmp/claude-1000/-home-looooo-bcg/4f524ffb-b166-48f7-afb4-e7e249962e72/scratchpad/ken_sweep.json',JSON.stringify({out,js}));
}finally{srv.kill()}
 console.log('ok');
})();
