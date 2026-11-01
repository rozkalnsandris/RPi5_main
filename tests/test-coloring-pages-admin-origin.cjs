// Execute the actual separate Origin requests renderer with synthetic reports.
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const html=fs.readFileSync(path.join(__dirname,"../ops/admin/coloring-pages/index.html"),"utf8");
const script=html.split("<script>")[3].split("</script>")[0];
class Element{
 constructor(){this.value="";this.hidden=false;this.disabled=false;this.textContent="";this.children=[];this.listeners={};}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}
 addEventListener(event,callback){this.listeners[event]=callback;}
}
function report(days=7,count=5){
 const start=new Date(Date.UTC(2026,10,2-days+1));
 const daily=Array.from({length:days},(_,i)=>({day:new Date(start.getTime()+i*86400000).toISOString().slice(0,10),requests:i===days-1?count:0}));
 return {version:1,status:"ok",metric:"origin_detail_requests",range_days:days,timezone:"UTC",today_partial:true,generated_at:"2026-11-02T10:30:00Z",start_day:daily[0].day,end_day:daily[days-1].day,total:count,daily,pages:count?[{page_id:"0123456",requests:count}]:[]};
}
function harness(route="overview"){
 const nodes={},calls=[];for(const m of html.matchAll(/data-origin-([a-z-]+)/g))nodes[m[1]]=new Element();
 nodes.days.value="7";let response={ok:true,data:report()};
 const context={currentRoute:route,window:{},Intl,AbortController,setTimeout,clearTimeout,document:{querySelector(selector){const key=selector.slice(13,-1);assert.ok(nodes[key],selector);return nodes[key];},createElement(){return new Element();}},fetch:async(url,options)=>{calls.push({url,options});if(response.promise)return response.promise;return{ok:response.ok,json:async()=>response.data};}};
 vm.createContext(context);vm.runInContext(script,context);
 return {nodes,calls,open:page=>context.window.AdminOrigin.open(page),refresh:()=>nodes.refresh.listeners.click(),change:days=>{nodes.days.value=String(days);return nodes.days.listeners.change();},set:value=>response=value};
}
(async()=>{
 const h=harness();assert.equal(h.calls.length,0,"lazy report");await h.open("traffic");assert.equal(h.calls.length,0);
 await h.open("origin");assert.equal(h.nodes.total.textContent,"5");assert.equal(h.nodes.pages.textContent,"1");
 assert.equal(h.nodes.ranking.children[0].children[0].textContent,"0123456");
 assert.equal(h.nodes.daily.children.length,7);assert.match(h.nodes.daily.children[6].children[0].textContent,/incomplete/);
 assert.match(h.nodes.status.textContent,/UTC.*Snapshot/);assert.equal(h.nodes.content.hidden,false);
 h.set({ok:false,data:{status:"not_configured",message:"PRIVATE_UPSTREAM"}});await h.refresh();
 assert.equal(h.nodes.content.hidden,true);assert.equal(h.nodes.total.textContent,"–");assert.equal(h.nodes.ranking.children.length,0);
 assert.match(h.nodes.status.textContent,/not connected/);assert.ok(!h.nodes.status.textContent.includes("PRIVATE"));
 h.set({ok:false,data:{status:"busy"}});await h.refresh();assert.match(h.nodes.status.textContent,/shortly/);
 h.set({ok:false,data:{status:"unavailable"}});await h.refresh();assert.match(h.nodes.status.textContent,/not zero/);
 h.set({ok:true,data:report(1,0)});await h.change(1);assert.equal(h.nodes.total.textContent,"0");assert.equal(h.nodes.empty.hidden,false);assert.equal(h.nodes.content.hidden,false);
 h.set({ok:true,data:report(365,5)});await h.change(365);assert.equal(h.nodes.daily.children.length,365);
 const malformed=report(365,5);malformed.pages[0].page_id="<img onerror=evil>";
 h.set({ok:true,data:malformed});await h.refresh();assert.equal(h.nodes.content.hidden,true);assert.equal(h.nodes.ranking.children.length,0);
 const inconsistent=report(365,5);inconsistent.total=6;h.set({ok:true,data:inconsistent});await h.refresh();assert.equal(h.nodes.content.hidden,true);
 // Late results from a superseded request cannot replace the latest report.
 let resolve;h.set({promise:new Promise(r=>resolve=r)});const old=h.change(7);
 h.set({ok:true,data:report(1,2)});await h.change(1);resolve({ok:true,json:async()=>report(7,99)});await old;
 assert.equal(h.nodes.total.textContent,"2");assert.equal(h.nodes.days.disabled,false);assert.equal(h.nodes.refresh.disabled,false);
 assert.ok(h.calls.every(({url,options})=>/^\/api\/analytics\/origin\?days=(1|7|30|365)$/.test(url)&&options.method==="GET"&&options.redirect==="error"&&options.headers["X-Ausmalwiese-Admin"]==="1"));
 assert.ok(!script.includes("innerHTML"));assert.ok(!script.includes("localStorage"));
 const deep=harness("origin");for(let i=0;i<15;i++)await Promise.resolve();assert.equal(deep.nodes.total.textContent,"5");
 console.log("Origin report UI: isolated route, UTC ranges, honest empty/error states, safe DOM and stale-result rejection PASS");
})().catch(error=>{console.error(error);process.exitCode=1;});
