// #1341 synthetic, read-only Catalog classification regressions.
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const html=fs.readFileSync(path.join(__dirname,"../ops/admin/coloring-pages/index.html"),"utf8");
const mark="<!-- #1341 standalone classification audit -->";
assert.equal(html.split(mark).length,2);
const source=html.split(mark)[1].split("<script>")[1].split("</script>")[0];
assert.doesNotMatch(source,/\/api\/catalog\/edit|\/api\/jobs|method:\s*["']POST/);
const ids={};
class Node{constructor(tag="div"){this.tag=tag;this.children=[];this.textContent="";this.value="";this.hidden=false;this.disabled=false;this.attrs={};}
 append(...x){this.children.push(...x)}appendChild(x){this.append(x)}replaceChildren(...x){this.children=x}
 setAttribute(k,v){this.attrs[k]=v}click(){if(this.onclick)this.onclick()}}
for(const x of html.matchAll(/\bid="(classification[A-Za-z]+)"/g))ids[x[1]]=new Node();
const sha=x=>x.repeat(64),c=[{id:"tiere",label:"Tiere"},{id:"lernen",label:"Lernen"},{id:"jahreszeiten",label:"Jahreszeiten & Feste"}],
 t=[{id:"hund",label:"Hund",kind:"evergreen",legacy_terms:["Hunde"]},
    {id:"baum",label:"Baum",kind:"evergreen",legacy_terms:["Bäume"]},
    {id:"weihnachten",label:"Weihnachten",kind:"seasonal",legacy_terms:["Weihnachtsmann"]}],
 l=[{category:"tiere",topic:"hund"},{category:"lernen",topic:"baum"},{category:"jahreszeiten",topic:"weihnachten"}],
 entry=(id,title,category="tiere",topics=[])=>({id,title,category,topics,thumb:"/media/test.png"}),
 entries=[entry("0000001","Hunde"),entry("0000002","Weihnachtsmann"),entry("0000003","Hund und Baum"),
          entry("0000004","Hundert Bilder"),entry("0000005","Hund","tiere",["hund"]),
          entry("0000006","Hund","tiere",["baum"]),{...entry("0000007","Ein Baum","lernen",["hund"]),categories:["lernen","tiere"]}],
 snapshot={catalog:{catalog_sha256:sha("a"),count:entries.length,entries},
 taxonomy:{version:sha("b"),categories:c,topics:t.map(({id,label,kind})=>({id,label,kind}))},
 categories:{enabled:true,registry_sha256:sha("c"),categories:c},
 topics:{enabled:true,registry_sha256:sha("d"),topics:t},
 links:{enabled:true,registry_sha256:sha("e"),category_sha256:sha("c"),topic_sha256:sha("d"),links:l}};
const state={"/api/catalog":snapshot.catalog,"/api/categories":snapshot.taxonomy,"/api/categories/manage":snapshot.categories,
 "/api/topics/manage":snapshot.topics,"/api/category-topics/manage":snapshot.links};
const calls=[],exports=[],revoked=[],copy=x=>JSON.parse(JSON.stringify(x));
const ctx={window:{confirm:()=>true},document:{getElementById:k=>ids[k],createElement:k=>new Node(k)},
 Set,Map,Promise,URL:{createObjectURL(b){exports.push(b.bytes[0]);return "blob:test"},revokeObjectURL(u){revoked.push(u)}},
 Blob:class{constructor(bytes){this.bytes=bytes}},
 fetch:async(u,o)=>{calls.push({u,o});assert.equal(o.method,"GET");assert.equal(o.cache,"no-store");return {ok:true,json:async()=>copy(state[u])}},
 console};
vm.runInNewContext(source,ctx,{timeout:1000});
const api=ctx.window.AdminClassification,analysis=api.audit(copy(snapshot)),rows=analysis.rows;
assert.equal(rows.length,7);assert.equal(rows[0].status,"proposed");assert.deepEqual(Array.from(rows[0].after.topics),["hund"]);
assert.equal(rows[1].status,"proposed");assert.deepEqual(Array.from(rows[1].after.categories),["tiere","jahreszeiten"]);
assert.equal(rows[2].status,"review");assert.equal(rows[3].status,"unchanged");assert.equal(rows[4].status,"unchanged");
assert.equal(rows[5].status,"review");assert.equal(rows[6].status,"unchanged");
assert.deepEqual(Array.from(rows[6].after.categories),["lernen","tiere"]);
rows[0].decision="approved";rows[1].decision="rejected";
assert.equal(api.manifest(analysis).approved_changes.length,1);
assert.equal(api.manifest(analysis).mode,"DRY_RUN_ONLY");
assert.ok(!JSON.stringify(api.manifest(analysis)).includes("Hunde"),"export has no titles");
function bad(f){const s=copy(snapshot);f(s);assert.throws(()=>api.audit(s))}
bad(s=>s.catalog.count++);
bad(s=>s.catalog.entries.push(s.catalog.entries[0]));
bad(s=>s.catalog.entries[0].categories=["tiere","tiere"]);
bad(s=>s.links.topic_sha256=sha("f"));
bad(s=>s.links.links.push({category:"tiere",topic:"weihnachten"}));
bad(s=>s.topics.topics[0].legacy_terms="bad");
(async()=>{
 await api.analyze();assert.equal(ids.classificationWorkspace.hidden,false);
 assert.equal(ids.classificationRows.children.length,7);
 const first=ids.classificationRows.children[0].children[1].children.at(-1);
 first.children[1].click();
 assert.ok(ids.classificationMetrics.children.some(x=>x.textContent==="approved: 1"));
 await api.exportPlan();assert.equal(exports.length,1);assert.equal(revoked.length,1);
 assert.equal(JSON.parse(exports[0]).approved_changes.length,1);
 state["/api/catalog"]={...snapshot.catalog,catalog_sha256:sha("9")};
 await api.exportPlan();assert.equal(exports.length,1);assert.equal(ids.classificationWorkspace.hidden,true);
 assert.match(ids.classificationStatus.textContent,/Export blocked/);
 assert.ok(calls.every(x=>x.o.method==="GET"));
 console.log("Catalog classification read-only, review, stale, and export: PASS");
})().catch(e=>{console.error(e);process.exitCode=1});
