// #1395 source-only complete Catalog classification review regressions (extends #1341).
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const html=fs.readFileSync(path.join(__dirname,"../ops/admin/coloring-pages/index.html"),"utf8");
const mark="<!-- #1341 standalone classification audit; extended coverage review #1395 -->";
assert.equal(html.split(mark).length,2);
const source=html.split(mark)[1].split("<script>")[1].split("</script>")[0];
assert.doesNotMatch(source,/\/api\/catalog\/edit|\/api\/jobs|method:\s*["']POST/);
assert.match(html,/id="classificationReview"/);
assert.match(html,/<option value="pending">Not reviewed<\/option>/);
const ids={};
class Node{
 constructor(tag="div"){this.tag=tag;this.children=[];this.textContent="";this.value="";this.hidden=false;this.disabled=false;this.attrs={};this.open=false}
 append(...x){this.children.push(...x)}
 appendChild(x){this.append(x)}
 replaceChildren(...x){this.children=x}
 setAttribute(k,v){this.attrs[k]=v}
 click(){if(this.onclick)this.onclick()}
}
for(const x of html.matchAll(/\bid="(classification[A-Za-z]+)"/g))ids[x[1]]=new Node();
const sha=x=>x.repeat(64),c=[{id:"tiere",label:"Tiere"},{id:"lernen",label:"Lernen"},{id:"jahreszeiten",label:"Jahreszeiten & Feste"}],
 t=[{id:"hund",label:"Hund",kind:"evergreen",legacy_terms:["Hunde"]},
    {id:"baum",label:"Baum",kind:"evergreen",legacy_terms:["Bäume"]},
    {id:"weihnachten",label:"Weihnachten",kind:"seasonal",legacy_terms:["Weihnachtsmann"]}],
 l=[{category:"tiere",topic:"hund"},{category:"lernen",topic:"baum"},{category:"jahreszeiten",topic:"weihnachten"}],
 entry=(id,title,category="tiere",topics=[])=>({id,title,category,topics,thumb:"/media/test.png"}),
 entries=[entry("0000001","Hunde"),entry("0000002","Weihnachtsmann"),entry("0000003","Hund und Baum"),
          entry("0000004","Hundert Bilder"),entry("0000005","Hund","tiere",["hund"]),
          entry("0000006","Hund","tiere",["baum"]),
          {...entry("0000007","Ein Baum","lernen",["hund"]),categories:["lernen","tiere"]},
          entry("0000008","Auto"),entry("0000009","Auto")],
 snapshot={catalog:{catalog_sha256:sha("a"),count:entries.length,entries},
 taxonomy:{version:sha("b"),categories:c,topics:t.map(({id,label,kind})=>({id,label,kind}))},
 categories:{enabled:true,registry_sha256:sha("c"),categories:c},
 topics:{enabled:true,registry_sha256:sha("d"),topics:t},
 links:{enabled:true,registry_sha256:sha("e"),category_sha256:sha("c"),topic_sha256:sha("d"),links:l}};
const state={"/api/catalog":snapshot.catalog,"/api/categories":snapshot.taxonomy,"/api/categories/manage":snapshot.categories,
 "/api/topics/manage":snapshot.topics,"/api/category-topics/manage":snapshot.links};
const calls=[],downloadBytes=[],revoked=[],copy=x=>JSON.parse(JSON.stringify(x));
const ctx={window:{confirm:()=>true},document:{getElementById:k=>ids[k],createElement:k=>new Node(k)},
 Set,Map,Promise,URL:{createObjectURL(b){downloadBytes.push(b.bytes[0]);return "blob:test"},revokeObjectURL(u){revoked.push(u)}},
 Blob:class{constructor(bytes){this.bytes=bytes}},fetch:async(u,o)=>{
  calls.push({u,o});assert.equal(o.method,"GET");assert.equal(o.cache,"no-store");
  return {ok:true,json:async()=>copy(state[u])};
 },console};
vm.runInNewContext(source,ctx,{timeout:1000});
const api=ctx.window.AdminClassification,analysis=api.audit(copy(snapshot)),rows=analysis.rows;
assert.equal(rows.length,9);
assert.equal(api.totals(analysis).published,9);
assert.equal(api.totals(analysis).pending,9,"all unique IDs remain unreviewed until explicit decision");
assert.equal(rows[0].status,"proposed");assert.deepEqual(Array.from(rows[0].after.topics),["hund"]);
assert.equal(rows[1].status,"proposed");assert.deepEqual(Array.from(rows[1].after.categories),["tiere","jahreszeiten"]);
assert.equal(rows[2].status,"review","competing title phrases require human review");
assert.equal(rows[3].status,"review","no-topic/no-match is not silently treated as classified");
assert.equal(rows[4].status,"unchanged","existing linked topic stays intact");
assert.equal(rows[5].status,"review","grandfathered unlinked topic requires manual review");
assert.equal(rows[6].status,"proposed");assert.deepEqual(Array.from(rows[6].after.topics),["hund","baum"]);
assert.equal(rows[7].status,"review");assert.equal(rows[8].status,"review");
assert.ok(analysis.gaps.some(x=>x.term==="auto"&&x.count===2));
assert.equal(api.totals(analysis).unmatched,3); // "Hundert Bilder" and two Auto titles
assert.equal(api.manifest(analysis).review_decisions.length,9,"100% of IDs accounted for");
assert.equal(api.manifest(analysis).complete_review,false);
assert.equal(api.manifest(analysis).approved_changes.length,0);
assert.equal(api.manifest(analysis).mode,"DRY_RUN_ONLY");
assert.equal(api.manifest(analysis).schema,"ausmalwiese.catalog-classification-review.v2");
function bad(f){const s=copy(snapshot);f(s);assert.throws(()=>api.audit(s))}
bad(s=>s.catalog.count++);
bad(s=>s.catalog.entries.push(s.catalog.entries[0]));
bad(s=>s.catalog.entries[0].categories=["tiere","tiere"]);
bad(s=>s.links.topic_sha256=sha("f"));
bad(s=>s.links.links.push({category:"tiere",topic:"weihnachten"}));
bad(s=>s.topics.topics[0].legacy_terms="bad");
bad(s=>s.catalog.entries[0].topics=["nonexistent"]);
assert.match(api.selectionError(rows[3].after,analysis.index,true),/No relevant Topic/);
assert.match(api.selectionError(rows[5].after,analysis.index,true),/not linked/);
(async()=>{
 await api.analyze();
 assert.equal(ids.classificationWorkspace.hidden,false);
 assert.equal(ids.classificationRows.children.length,9);
 assert.ok(ids.classificationMetrics.children.some(x=>x.textContent==="pending: 9"));
 assert.equal(calls.length,10,"read-only snapshot and all five sources reread");
 // Explicit image-reviewed decision in the UI.
 const first=ids.classificationRows.children[0].children[1].children.at(-1);
 first.children[1].click();
 assert.ok(ids.classificationMetrics.children.some(x=>x.textContent==="approved: 1"));
 assert.equal(ids.classificationRows.children[0].children[1].children.at(-2).tag,"details");
 // Manual multi-topic selection never auto-removes existing values or assumes title correctness.
 api.choose(rows[2],"topics","hund",true);
 api.choose(rows[2],"categories","lernen",true);
 api.choose(rows[2],"topics","baum",true);
 assert.deepEqual(Array.from(rows[2].after.categories),["tiere","lernen"]);
 assert.deepEqual(Array.from(rows[2].after.topics),["hund","baum"]);
 assert.equal(api.selectionError(rows[2].after,analysis.index,true),"");
 assert.equal(api.decision(rows[2],"approved"),true);
 assert.equal(api.manifest(analysis).approved_changes.length,1);
 assert.equal(api.decision(rows[3],"approved"),false,"no arbitrary Topic to satisfy coverage");
 assert.equal(api.decision(rows[3],"deferred"),true);
 assert.equal(api.decision(rows[4],"approved"),true,"valid unchanged entry can be explicitly reviewed");
 assert.equal(api.manifest(analysis).approved_changes.length,1,"unchanged approval does not trigger a catalog rewrite");
 assert.equal(api.decision(rows[5],"approved"),false,"cannot accept unlinked Topic");
 api.choose(rows[5],"categories","lernen",true);
 assert.equal(api.decision(rows[5],"approved"),true);
 assert.deepEqual(Array.from(rows[5].after.topics),["baum"],"original Topic preserved");
 assert.equal(api.manifest(analysis).approved_changes.length,2);
 const coverage=api.manifest(analysis);
 assert.equal(coverage.review_decisions.length,9);
 assert.equal(coverage.review_decisions.find(x=>x.id==="0000004").decision,"deferred");
 assert.ok(coverage.review_decisions.every(x=>!Object.hasOwn(x,"title")),"export has no titles");
 await api.exportPlan();
 assert.equal(downloadBytes.length,1);assert.equal(revoked.length,1);
 const exported=JSON.parse(downloadBytes[0]);
 assert.equal(exported.mode,"DRY_RUN_ONLY");assert.equal(exported.complete_review,false);
 assert.equal(exported.approved_changes.length,1,"UI review state remains independent of synthetic API sample rows");
 assert.equal(exported.review_decisions.length,9);
 assert.ok(calls.every(x=>x.o.method==="GET"));
 state["/api/catalog"]={...snapshot.catalog,catalog_sha256:sha("9")};
 await api.exportPlan();
 assert.equal(downloadBytes.length,1);assert.equal(ids.classificationWorkspace.hidden,true);
 assert.match(ids.classificationStatus.textContent,/Export blocked/);
 console.log("Catalog classification full coverage, manual multi-topic, deferred, gap, stale and read-only export: PASS");
})().catch(e=>{console.error(e);process.exitCode=1});