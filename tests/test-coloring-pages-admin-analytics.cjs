// Exercise the actual inline renderer with synthetic aggregates; no network or tracking writes.
const assert=require("node:assert/strict"),fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const html=fs.readFileSync(path.join(__dirname,"../ops/admin/coloring-pages/index.html"),"utf8");
const script=html.split("<script>")[2].split("</script>")[0];
class Element {
  constructor(){this.value="";this.textContent="";this.children=[];this.hidden=false;this.listeners={};this.attrs={};}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=nodes;}
  setAttribute(key,value){this.attrs[key]=value;}
  addEventListener(event,callback){this.listeners[event]=callback;}
}
function harness(route="overview"){
  const nodes={},calls=[],responses={};
  for(const m of html.matchAll(/\b(data-[\w-]+)(?:="([^"]*)")?/g))nodes[`[${m[1]}${m[2]===undefined?"":`="${m[2]}"`}]`]=new Element();
  nodes['[data-stats-sort]'].value="prints";nodes['[data-traffic-sort]'].value="recentViews";
  const entries=Array.from({length:25},(_,i)=>({id:String(i).padStart(7,"0"),title:i===0?"<img onerror=evil>":"Lapa "+i,category:"tiere",thumb:i===0?"//evil.example/image":"/media/1234567/thumb.webp"}));
  const totals={print_count:76,like_count:2,recent_prints:24,view_count:283,recent_views:151};
  responses['/api/catalog']={entries};
  responses['/api/analytics/overview']={totals,pages:entries.map((e,i)=>({page_id:e.id,print_count:i,like_count:1,recent_prints:i,view_count:i*2,recent_views:i})).concat({page_id:"9999999",print_count:9})};
  responses['/api/analytics/traffic?days=7']={visits:473,crawler_requests:1342,crawlers:[{name:"<svg onload=evil>",requests:20,paths:[{path:"/detail.html",requests:20}]}],unique_visitors:3,unique_visitors_status:"available",unique_visitors_date:"2026-10-23",sampled:true};
  for(const days of [7,30]) responses['/api/analytics/campaigns?days='+days]={instagram_attribution_version:1,campaigns:[{campaign:"instagram-profile",landing_count:7},{campaign:"dortmund-01",landing_count:3,catalog_count:2,detail_count:1,print_count:1}]};
  const context={currentRoute:route,window:{},Intl,AbortController,setTimeout,clearTimeout,document:{querySelector(selector){assert.ok(nodes[selector],selector);return nodes[selector];},createElement(){return new Element();}},fetch:async(url,options)=>{calls.push({url,options});assert.ok(Object.hasOwn(responses,url),url);const data=responses[url];return {ok:data!==null,json:async()=>data};}};
  vm.createContext(context);vm.runInContext(script,context);
  const flush=async()=>{for(let i=0;i<25;i++)await Promise.resolve();};
  return {nodes,responses,calls,context,flush,open:page=>context.window.AdminAnalytics.open(page),get:name=>nodes[`[data-${name}]`],refresh:page=>nodes[`[data-${page}-refresh]`].listeners.click()};
}
(async()=>{
 const h=harness();await h.flush();assert.equal(h.calls.length,0,"lazy dashboards");
 await h.open("stats");assert.equal(h.calls.length,3);assert.equal(h.get("stats-total-prints").textContent,"76");
 assert.equal(h.get("stats-qr-total").textContent,"–","missing QR capability is not zero");
 assert.equal(h.get("stats-table").children.length,20);assert.match(h.get("stats-status").textContent,/1 stats ID/);
 h.get("stats-load-more").listeners.click();assert.equal(h.get("stats-table").children.length,25);
 h.get("stats-search").value="0000000";h.get("stats-search").listeners.input();
 const row=h.get("stats-table").children[0],link=row.children[0].children[0].children[1];
 assert.equal(link.textContent,"<img onerror=evil>");assert.equal(link.href,"https://ausmalwiese.de/detail.html?id=0000000");assert.equal(link.target,"_blank");
 assert.equal(row.children[0].children[0].children[0].src,"https://ausmalwiese.de/media/0000000/thumb.webp");
 h.get("stats-search").value="";h.get("stats-search").listeners.input();
 h.get("stats-sort").value="title";h.get("stats-sort").listeners.change();assert.equal(h.get("stats-table").children[0].children[0].children[0].children[1].textContent,"<img onerror=evil>");
 h.get("stats-search").value="missing";h.get("stats-search").listeners.input();assert.equal(h.get("stats-table").children.length,0);assert.equal(h.get("stats-table-empty").hidden,false);
 await h.open("traffic");assert.equal(h.get("stats-visits").textContent,"473");assert.equal(h.get("instagram-30").textContent,"7");
 assert.equal(h.get("stats-crawlers").children[0].children[0].textContent,"<svg onload=evil>");
 h.responses['/api/analytics/campaigns?days=30']={campaigns:[]};h.responses['/api/analytics/traffic?days=7']=null;
 await h.refresh("traffic");assert.equal(h.get("instagram-30").textContent,"–");assert.equal(h.get("stats-visits").textContent,"–");assert.equal(h.get("stats-total-views").textContent,"283");assert.match(h.get("traffic-page-status").textContent,/some data/);
 h.responses['/api/analytics/campaigns?days=30']=null;await h.refresh("stats");assert.equal(h.get("stats-kita-landing").textContent,"–");
 h.responses['/api/analytics/overview']=null;await h.refresh("stats");assert.equal(h.nodes['[data-analytics-content="stats"]'].hidden,true);assert.match(h.get("stats-status").textContent,/Could not load/);assert.equal(h.get("stats-refresh").disabled,false);
 assert.ok(h.calls.every(call=>!call.options.method || call.options.method==="GET"));assert.ok(h.calls.every(call=>call.url.startsWith("/api/")));
 const deep=harness("traffic");await deep.flush();assert.equal(deep.get("stats-visits").textContent,"473");
 console.log("Admin analytics: lazy/deep routes, counters, paging/search, safe DOM, partial failures and stale-data hiding PASS");
})().catch(error=>{console.error(error);process.exitCode=1;});
