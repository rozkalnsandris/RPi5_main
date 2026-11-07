// Execute the actual separate GoatCounter visits renderer with synthetic reports and Catalog/Archive titles.
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const html=fs.readFileSync(path.join(__dirname,"../ops/admin/coloring-pages/index.html"),"utf8");
const script=html.split("<script>")[3].split("</script>")[0];
class Element{
 constructor(){this.value="";this.hidden=false;this.disabled=false;this.textContent="";this.children=[];this.listeners={};this.attributes={};this.style={};this.title="";}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this.children=nodes;}
 addEventListener(event,callback){this.listeners[event]=callback;}
 setAttribute(name,value){this.attributes[name]=String(value);}
}
function report(days=7,coloring=5,home=1,pageId="0123456"){
 const start=new Date(Date.UTC(2026,10,2-days+1)),total=coloring+home;
 const daily=Array.from({length:days},(_,i)=>({day:new Date(start.getTime()+i*86400000).toISOString().slice(0,10),visits:i===days-1?total:0}));
 return {version:3,status:"ok",metric:"goatcounter_visits",range_days:days,timezone:"UTC",today_partial:true,cache_seconds:60,generated_at:"2026-11-02T10:30:00Z",start_day:daily[0].day,end_day:daily[days-1].day,total,homepage_visits:home,ausmalbild_visits:coloring,daily,pages:coloring?[{page_id:pageId,visits:coloring}]:[],
  referrers:[{label:"Google",visits:3}],campaigns:[{label:"profile",visits:2}],locations:[{label:"Germany",visits:4}],browsers:[{label:"Firefox",visits:3}],systems:[{label:"Android",visits:3}],sizes:[{label:"390",visits:2}]};
}
function harness(route="overview"){
 const nodes={},calls=[];for(const m of html.matchAll(/data-origin-([a-z-]+)/g))nodes[m[1]]=new Element();
 nodes.days.value="7";
 let response={ok:true,data:report()};
 let catalog={ok:true,data:{count:1,entries:[{id:"0123456",title:"Kleiner Traktor"}]}};
 let archive={ok:true,data:{count:1,entries:[{state:"archived",entry:{id:"7654321",title:"Alter Schneemann"}}]}};
 const context={currentRoute:route,window:{},Intl,AbortController,setTimeout,clearTimeout,Map,document:{querySelector(selector){const key=selector.slice(13,-1);assert.ok(nodes[key],selector);return nodes[key];},createElement(){return new Element();},createElementNS(){return new Element();}},fetch:async(url,options)=>{
   calls.push({url,options});
   if(/^\/api\/analytics\/origin\?days=/.test(url)){if(response.promise)return response.promise;return{ok:response.ok,json:async()=>response.data};}
   if(url==="/api/catalog")return{ok:catalog.ok,json:async()=>catalog.data};
   if(url==="/api/archive")return{ok:archive.ok,json:async()=>archive.data};
   throw new Error("unexpected URL "+url);
 }};
 vm.createContext(context);vm.runInContext(script,context);
 return {nodes,calls,open:page=>context.window.AdminOrigin.open(page),refresh:()=>nodes.refresh.listeners.click(),change:days=>{nodes.days.value=String(days);return nodes.days.listeners.change();},set:value=>response=value,setCatalog:value=>catalog=value,setArchive:value=>archive=value};
}
function pageCells(h){
 const tr=h.nodes.ranking.children[0],page=tr.children[0],wrap=page.children[0],copy=wrap.children[wrap.children.length-1];
 return {title:copy.children[0].textContent,id:copy.children[1].textContent,visits:tr.children[1].textContent,share:tr.children[2].textContent};
}
(async()=>{
 const h=harness();assert.equal(h.calls.length,0,"lazy report");await h.open("stats");assert.equal(h.calls.length,0);
 await h.open("traffic");assert.equal(h.nodes.total.textContent,"6");assert.equal(h.nodes.home.textContent,"1");assert.equal(h.nodes.coloring.textContent,"5");assert.equal(h.nodes.pages.textContent,"1");
 assert.deepEqual(pageCells(h),{title:"Kleiner Traktor",id:"ID: 0123456",visits:"5",share:"100%"});
 assert.ok(h.nodes.trend.children.length>=2);const shortLabels=h.nodes.trend.children.filter(child=>child.attributes.class==="traffic-trend-label");assert.equal(shortLabels.length,1);assert.deepEqual(shortLabels.map(label=>label.textContent),["6"]);assert.equal(h.nodes.referrers.children.length,1);assert.equal(h.nodes.campaigns.children.length,1);
 assert.equal(h.nodes.locations.children.length,1);assert.equal(h.nodes.browsers.children.length,1);assert.equal(h.nodes.systems.children.length,1);assert.equal(h.nodes.sizes.children.length,1);
 assert.equal(h.nodes.daily.children.length,7);assert.match(h.nodes.daily.children[6].children[0].textContent,/incomplete/);
 assert.match(h.nodes.status.textContent,/UTC.*Snapshot/);assert.equal(h.nodes.content.hidden,false);

 h.set({ok:true,data:report(7,4,1,"7654321")});await h.refresh();
 assert.deepEqual(pageCells(h),{title:"Alter Schneemann",id:"ID: 7654321",visits:"4",share:"100%"},"archive title");

 h.set({ok:true,data:report(7,2,1,"1111111")});await h.refresh();
 assert.deepEqual(pageCells(h),{title:"Unknown historical page",id:"ID: 1111111",visits:"2",share:"100%"},"unknown historical ID fallback");

 h.set({ok:false,data:{status:"not_configured",message:"PRIVATE_UPSTREAM"}});await h.refresh();
 assert.equal(h.nodes.content.hidden,true);assert.equal(h.nodes.total.textContent,"–");assert.equal(h.nodes.ranking.children.length,0);
 assert.match(h.nodes.status.textContent,/not connected/);assert.ok(!h.nodes.status.textContent.includes("PRIVATE"));
 h.set({ok:false,data:{status:"busy"}});await h.refresh();assert.match(h.nodes.status.textContent,/shortly/);
 h.set({ok:false,data:{status:"unavailable"}});await h.refresh();assert.match(h.nodes.status.textContent,/not zero/);
 h.set({ok:true,data:report(1,0,0)});await h.change(1);assert.equal(h.nodes.total.textContent,"0");assert.equal(h.nodes.empty.hidden,false);assert.equal(h.nodes.content.hidden,false);assert.equal(h.nodes.trend.children.filter(child=>child.attributes.class==="traffic-trend-label").length,0);
 h.set({ok:true,data:report(365,5)});await h.change(365);assert.equal(h.nodes.daily.children.length,365);const longLabels=h.nodes.trend.children.filter(child=>child.attributes.class==="traffic-trend-label");assert.equal(longLabels.length,1);assert.equal(longLabels[0].textContent,"6");
 const malformed=report(365,5);malformed.pages[0].page_id="<img onerror=evil>";
 h.set({ok:true,data:malformed});await h.refresh();assert.equal(h.nodes.content.hidden,true);assert.equal(h.nodes.ranking.children.length,0);
 const inconsistent=report(365,5);inconsistent.total=7;h.set({ok:true,data:inconsistent});await h.refresh();assert.equal(h.nodes.content.hidden,true);
 let resolve;h.set({promise:new Promise(r=>resolve=r)});const old=h.change(7);
 h.set({ok:true,data:report(1,2,1)});await h.change(1);resolve({ok:true,json:async()=>report(7,99,1)});await old;
 assert.equal(h.nodes.total.textContent,"3");assert.equal(h.nodes.days.disabled,false);assert.equal(h.nodes.refresh.disabled,false);
 assert.ok(h.calls.every(({url,options})=>(/^\/api\/analytics\/origin\?days=(1|7|30|365)$/.test(url)||url==="/api/catalog"||url==="/api/archive")&&options.method==="GET"&&options.redirect==="error"&&options.headers["X-Ausmalwiese-Admin"]==="1"));
 assert.ok(!script.includes("innerHTML"));assert.ok(!script.includes("localStorage"));
 const deep=harness("traffic");for(let i=0;i<25;i++)await Promise.resolve();assert.equal(deep.nodes.total.textContent,"6");assert.equal(pageCells(deep).title,"Kleiner Traktor");
 assert.ok(!html.includes('data-page="origin"'),"no separate GoatCounter route");
 assert.ok(!html.includes('data-nav="origin"'),"no separate GoatCounter navigation");
 assert.ok(!html.includes("/api/analytics/traffic?days=7"),"Traffic has no Cloudflare analytics call");
 assert.match(html,/Recognizable bots and crawlers are filtered/);
 assert.match(html,/Documented GoatCounter aggregate dimensions/);
 assert.ok(!html.includes("HTTP requests in the last 7 days"));
 console.log("GoatCounter Traffic UI: documented API dimensions, trend, titles, safe aggregates and stale-result rejection PASS");
})().catch(error=>{console.error(error);process.exitCode=1;});
