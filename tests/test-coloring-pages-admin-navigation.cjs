// Offline behavioral regressions for the protected admin UI. No browser/network dependencies.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const html = fs.readFileSync(path.join(__dirname, "../ops/admin/coloring-pages/index.html"), "utf8");
const script = html.split("<script>")[1].split("</script>")[0];
const categoryPage = html.slice(html.indexOf('data-page="categories"'), html.indexOf('data-page="activity"'));
assert.equal((categoryPage.match(/class="admin-panel categories-panel"/g)||[]).length,1,"Categories and Topics use exactly one management card");
assert.equal((categoryPage.match(/class="container categories-shell"/g)||[]).length,1,"no second Topics container");
assert.equal((categoryPage.slice(0,categoryPage.indexOf('<dialog id="topicsDialog"')).match(/<h2\b/g)||[]).length,1,"one top-level management heading; edit dialog has its own title");
assert.match(categoryPage,/<section class="topics-inline" id="managedTopicsPanel" aria-labelledby="managedTopicsHeading">/,"topic tools are nested inside Categories");
assert.match(categoryPage,/<h3 id="managedTopicsHeading" tabindex="-1">Topic tools<\/h3>/,"legacy #topics bookmark focus target retained");
assert.ok(categoryPage.indexOf('id="categoriesRows"')<categoryPage.indexOf('id="topicsOtherDetails"'),"unlinked topics follow category rows");
assert.ok(categoryPage.indexOf('id="topicsOtherDetails"')<categoryPage.indexOf('id="topicsCreate"'),"Add topic remains within the same card");
assert.match(categoryPage,/id="categoriesRows"[^>]*aria-label="Categories and linked topics"/,"category rows explain linked topics");
assert.match(html,/@media\(max-width:700px\).*category-topics-list/,"existing narrow-screen disclosure preserved");
class Element {
  constructor(tag="div") { this.tag=tag;this.value="";this.textContent="";this.style={};this.dataset={};this.attrs={};this.children=[];this.hidden=false;this.disabled=false;this.classList={add(){},remove(){}}; }
  get options(){return this.children.filter(x=>x.tag==="option")}
  remove(i){this.children.splice(i,1)}
  replaceChildren(...items){this.children=items}
  querySelector(q){if(q==="summary"){if(!this.summary)this.summary=new Element("summary");return this.summary}return null}
  querySelectorAll(q){if(q==="option")return this.children.flatMap(x=>x.tag==="option"?[x]:x.children);if(q==="input")return this.children.flatMap(x=>x.children.filter(y=>y.tag==="input"));return []}
  set innerHTML(value) { this.markup=value;this.children=[]; }
  get innerHTML() { return this.markup||""; }
  append(...items) { this.children.push(...items); }
  appendChild(item) { this.append(item); }
  setAttribute(name,value) { this.attrs[name]=value; }
  removeAttribute(name) { delete this.attrs[name]; }
  focus() { this.focused=true; }
  scrollIntoView() {}
  showModal() { this.open=true; }
  close() { this.open=false; }
  reportValidity() { return true; }
}
function harness() {
  const ids={};
  for (const match of html.matchAll(/\bid="([^"]+)"/g)) ids[match[1]]=new Element();
  const pages=[...html.matchAll(/\bdata-page="([^"]+)"/g)].map(m=>Object.assign(new Element(),{dataset:{page:m[1]}}));
  const navs=[...html.matchAll(/\bdata-nav="([^"]+)"/g)].map(m=>Object.assign(new Element(),{dataset:{nav:m[1]}}));
  ids.catalogFilter.children=[new Element("option")];
  const layout=new Element(),skip=new Element(),listeners={},calls=[];
  const location={hash:""};
  const entries=Array.from({length:53},(_,i)=>({id:String(i).padStart(7,"0"),title:"Page "+i,category:i%2?"tiere":"lernen",age:"3-6",difficulty:"easy",thumb:"/media/test/thumb.webp"}));
  const state={entries,etag:'W/"edge-weakened"',catalogSha:"a".repeat(64),status:200,confirm:false,prompts:[],answers:[],
    usageHold:false,pendingUsage:[],
    taxonomy:{version:"b".repeat(64),categories:[{id:"tiere",label:"Tiere"},{id:"lernen",label:"Lernen"},{id:"jahreszeiten",label:"Jahreszeiten & Feste"}],
    topics:[{id:"weihnachten",label:"Weihnachten",kind:"seasonal"},{id:"obst",label:"Obst",kind:"evergreen"}]},
    links:{enabled:true,revision:1,registry_sha256:"d".repeat(64),category_sha256:"f".repeat(64),topic_sha256:"e".repeat(64),
      links:[{category:"jahreszeiten",topic:"weihnachten"},{category:"tiere",topic:"obst"},{category:"lernen",topic:"obst"}]}};
  const sandbox={
    document:{
      title:"",
      getElementById:id=>ids[id],
      querySelectorAll:selector=>selector==="[data-page]"?pages:navs,
      querySelector:selector=>selector===".edit-layout"?layout:skip,
      createElement:tag=>new Element(tag)
    }, location,
    history:{replaceState(_a,_b,url){location.hash=url}},
    window:{addEventListener(name,callback){listeners[name]=callback},scrollTo(){},confirm(message){state.confirmText=message;return state.confirm},prompt(message){state.prompts.push(message);return state.answers.length?state.answers.shift():null}},
    sessionStorage:{getItem(){return null},setItem(){},removeItem(){}},
    setTimeout(){return 1},clearTimeout(){},setInterval(){return 1},clearInterval(){},
    console,
    fetch:async(url,options={})=>{
      calls.push({url,options});
      if(["/api/catalog/edit","/api/catalog/archive","/api/catalog/restore","/api/archive/delete"].includes(url))return {ok:state.status===200,status:state.status,json:async()=>state.status===200?({status:"ok",deleted_file_count:1}):({error:"stale"})};
      if(url==="/api/catalog"){
        const fails=!!state.usageReadFails;
        if(state.usageHold&&options.cache!=="no-store")await new Promise(resolve=>state.pendingUsage.push(resolve));
        return {ok:!fails,status:fails?503:200,headers:{get:()=>state.etag},json:async()=>({entries:state.entries,count:state.entries.length,catalog_sha256:state.catalogSha})};
      }
      if(url==="/api/archive")return {ok:true,json:async()=>({entries:state.archiveEntries||[],count:(state.archiveEntries||[]).length,catalog_sha256:state.archiveSha||state.catalogSha})};
      if(url==="/api/activity")return {ok:true,json:async()=>({events:[],count:0})};
      if(url==="/api/categories")return {ok:true,json:async()=>state.taxonomy};
      if(url==="/api/categories/manage")return {ok:true,json:async()=>state.managed||({enabled:false,reason:"Not activated",categories:[],revision:null,registry_sha256:null,counts:{}})};
      if(url==="/api/topics/manage")return {ok:true,json:async()=>state.managedTopics||({enabled:false,reason:"Not activated",topics:[],revision:null,registry_sha256:null,counts:{}})};
      if(url==="/api/category-topics/manage"){
        if(options.method==="POST"){
          if(state.linkWriteStatus===412)return {ok:false,status:412,json:async()=>({error:"Stale assignment"})};
          const data=JSON.parse(options.body);
          if(data.action==="link")state.links.links.push({category:data.category,topic:data.topic});
          if(data.action==="unlink")state.links.links=state.links.links.filter(x=>x.category!==data.category||x.topic!==data.topic);
          state.links.registry_sha256="c".repeat(64);state.links.revision++;
        }
        return {ok:true,status:200,json:async()=>state.links};
      }
      if(url==="/api/uploads")return {ok:true,json:async()=>({upload_id:"c".repeat(32),count:1,files:[{title:"Weihnachtsstern"}]})};
      if(url==="/api/jobs")return {ok:true,json:async()=>({job_id:"d".repeat(32),status:"queued",steps:[],results:[]})};
      if(url==="/api/session")return {ok:true,json:async()=>({csrf_token:"fixture"})};
      if(url==="/api/jobs/active")return {ok:true,json:async()=>({active:false})};
      throw Error("Unexpected test request: "+url);
    }
  };
  vm.createContext(sandbox);
  vm.runInContext(script,sandbox);
  return {s:sandbox,ids,pages,navs,state,calls,listeners,layout,skip,go(route){location.hash="#"+route;sandbox.routePage()}};
}
async function ready(h){for(let i=0;i<40;i++)await Promise.resolve();h.s.categoriesReady=true;}
async function managerReady(h){await h.s.refreshTaxonomyManagers();await h.s.categoryTopicUsagePending;}
(async()=>{
  const h=harness();await ready(h);
  assert.equal(h.s.taxonomyVersion,"b".repeat(64));
  assert.equal(h.s.topicReady,true);
  assert.equal(Object.keys(h.s.categoryInputs).length,3);
  assert.equal(h.s.categoryInputs.jahreszeiten.value,"jahreszeiten");
  assert.equal(h.ids.categoryChoices.children[0].children.length,4,"fieldset has legend and categories");
  assert.equal(Object.keys(h.s.topicInputs).length,0,"topics are hidden until a category is chosen");
  h.s.categoryInputs.jahreszeiten.checked=true;h.s.categoryInputs.jahreszeiten.onchange();
  assert.equal(h.ids.categorySummary.textContent,"Choose categories… (1 selected)");
  assert.equal(h.s.topicInputs.weihnachten.disabled,false);
  assert.equal(h.s.topicInputs.obst,undefined,"unlinked topics are not offered");
  h.s.topicInputs.weihnachten.checked=true;h.s.topicInputs.weihnachten.onchange();
  assert.deepEqual(Array.from(h.s.selectedTopics),["weihnachten"]);
  assert.equal(h.ids.chosenTopic.children.length,1,"selected topic has a chip");
  assert.equal(h.ids.chosenTopic.children[0].children[0].textContent,"Weihnachten");
  assert.equal(h.ids.chosenTopic.children[0].children[1].attrs["aria-label"],"Remove Weihnachten topic");
  h.ids.chosenTopic.children[0].children[1].onclick();
  assert.equal(h.s.selectedTopics.length,0);
  assert.equal(h.ids.topicPicker.querySelector("summary").focused,true,"removal focuses disclosure");
  h.s.topicInputs.weihnachten.checked=true;h.s.topicInputs.weihnachten.onchange();
  assert.deepEqual(Array.from(h.s.selectedCategories),["jahreszeiten"]);
  assert.equal(h.ids.chosenCategories.children.length,1);
  assert.equal(h.s.categoryInputs.jahreszeiten.checked,true);
  assert.equal(h.ids.chosenCategories.children[0].children[0].textContent,"Jahreszeiten & Feste (primary)");
  await h.s.sendZip({name:"weihnachten.zip"});
  await h.ids.publish.onclick();
  const pub=h.calls.find(x=>x.url==="/api/jobs");
  assert.equal(JSON.parse(pub.options.body).topic,"weihnachten");
  assert.deepEqual(JSON.parse(pub.options.body).topics,["weihnachten"]);
  assert.deepEqual(JSON.parse(pub.options.body).categories,["jahreszeiten"]);
  assert.equal(JSON.parse(pub.options.body).category,"jahreszeiten");
  assert.equal(JSON.parse(pub.options.body).taxonomy_sha256,"b".repeat(64));
  h.state.taxonomy.topics.push({id:"laterne",label:"Laterne",kind:"seasonal"});
  h.state.links.links.push({category:"jahreszeiten",topic:"laterne"});
  await h.s.loadCategories();
  assert.equal(Object.keys(h.s.topicInputs).includes("laterne"),true);
  assert.equal(h.s.categoryInputs.jahreszeiten.checked,true,"taxonomy reload preserves category checkboxes");
  const multi=harness();await ready(multi);
  const add=id=>{multi.s.categoryInputs[id].checked=true;multi.s.categoryInputs[id].onchange()};
  add("tiere");add("jahreszeiten");add("lernen");add("lernen");
  assert.deepEqual(Array.from(multi.s.selectedCategories),["tiere","jahreszeiten","lernen"],"duplicate category ignored");
  assert.equal(multi.ids.chosenCategories.children.length,3);
  assert.equal(multi.s.categoryInputs.lernen.checked,true);
  assert.equal(multi.ids.categorySummary.textContent,"Choose categories… (3 selected)");
  multi.s.topicInputs.weihnachten.checked=true;multi.s.topicInputs.weihnachten.onchange();
  multi.s.topicInputs.obst.checked=true;multi.s.topicInputs.obst.onchange();
  assert.deepEqual(Array.from(multi.s.selectedTopics),["weihnachten","obst"]);
  assert.equal(multi.ids.chosenTopic.children.length,2);
  multi.ids.chosenCategories.children[1].children[1].onclick();
  assert.deepEqual(Array.from(multi.s.selectedTopics),["weihnachten","obst"],"category change never silently discards a topic");
  assert.equal(multi.ids.chosenTopic.children.length,2,"invalid selection remains visible");
  assert.match(multi.ids.topicSelectionStatus.textContent,/unlinked/);
  assert.equal(multi.ids.categoryPicker.querySelector("summary").focused,true,"chip removal focuses category disclosure");
  assert.equal(multi.s.categoryInputs.jahreszeiten.checked,false,"removed chip unchecks category");
  multi.ids.chosenCategories.children[0].children[1].onclick();
  assert.deepEqual(Array.from(multi.s.selectedCategories),["lernen"],"next chip becomes primary");
  add("jahreszeiten");
  await multi.s.sendZip({name:"multi.zip"});
  await multi.ids.publish.onclick();
  const multiJob=multi.calls.find(x=>x.url==="/api/jobs");
  assert.deepEqual(JSON.parse(multiJob.options.body).categories,["lernen","jahreszeiten"]);
  assert.equal(JSON.parse(multiJob.options.body).category,"lernen");
  multi.state.entries[0].categories=["lernen","tiere"];
  multi.state.entries[1].categories=["tiere","jahreszeiten"];
  multi.state.entries[1].topics=["obst","weihnachten"];
  await multi.s.loadCatalog();
  multi.ids.catalogFilter.value="tiere";
  assert.equal(multi.s.filteredCatalog().some(x=>x.id==="0000000"),true,"any-category catalog filter");
  multi.go("edit/0000000");
  assert.deepEqual(Array.from(multi.s.editSelectedCategories),["lernen","tiere"]);
  assert.equal(multi.ids.editChosenCategories.children.length,2);
  multi.ids.editChosenCategories.children[0].children[1].onclick();
  assert.equal(multi.s.editValues().category,"tiere");
  assert.deepEqual(Array.from(multi.s.editValues().categories),["tiere"]);
  multi.ids.editChosenCategories.children[0].children[1].onclick();
  assert.equal(multi.ids.editSave.disabled,true,"zero-category edit is blocked");
  multi.s.editCategoryInputs.tiere.checked=true;multi.s.editCategoryInputs.tiere.onchange();
  assert.deepEqual(Array.from(multi.s.editValues().categories),["tiere"],"edit checkbox restores category");
  multi.state.confirm=true; // Allow leaving the deliberately modified first edit.
  multi.go("edit/0000001");
  assert.equal(multi.s.editCategoryInputs.tiere.checked,true);
  assert.equal(multi.s.editCategoryInputs.jahreszeiten.checked,true);
  multi.s.editCategoryInputs.lernen.checked=true;multi.s.editCategoryInputs.lernen.onchange();
  assert.deepEqual(Array.from(multi.s.editValues().categories),["tiere","jahreszeiten","lernen"],"edit category toggle updates payload");
  multi.s.editCategoryInputs.lernen.checked=false;multi.s.editCategoryInputs.lernen.onchange();
  assert.deepEqual(Array.from(multi.s.editValues().categories),["tiere","jahreszeiten"],"edit checkbox untoggle restores original");
  assert.deepEqual(Array.from(multi.s.editSelectedTopics),["obst","weihnachten"],"all edited topics loaded");
  assert.deepEqual(Array.from(multi.s.editValues().topics),["obst","weihnachten"],"catalog edit preserves both topics");
  // Edit checkboxes must mutate the same selectedTopics array that editValues() saves.
  multi.s.editTopicInputs.obst.checked=false;multi.s.editTopicInputs.obst.onchange();
  assert.deepEqual(Array.from(multi.s.editValues().topics),["weihnachten"],"unchecking existing topic updates edit payload");
  assert.equal(multi.ids.editChosenTopics.children.length,1,"unchecking removes the corresponding chip");
  multi.s.editTopicInputs.obst.checked=true;multi.s.editTopicInputs.obst.onchange();
  assert.deepEqual(Array.from(multi.s.editValues().topics),["weihnachten","obst"],"checking adds the topic to edit payload");
  assert.equal(multi.ids.editChosenTopics.children.length,2,"checking restores the chosen topic chip");
  multi.ids.editChosenTopics.children[1].children[1].onclick();
  assert.deepEqual(Array.from(multi.s.editSelectedTopics),["weihnachten"]);
  assert.equal(multi.ids.editTopicPicker.querySelector("summary").focused,true);
  multi.ids.editChosenCategories.children[1].children[1].onclick();
  assert.deepEqual(Array.from(multi.s.editSelectedTopics),["weihnachten"],"edit preserves invalid topic until deliberate correction");
  assert.equal(multi.ids.editSave.disabled,true,"invalid edit selection blocks save");
  multi.ids.editChosenTopics.children[0].children[1].onclick();
  multi.s.editTopicInputs.obst.checked=true;multi.s.editTopicInputs.obst.onchange();
  assert.deepEqual(Array.from(multi.s.editValues().topics),["obst"],"checkbox selection survives category changes");
  await multi.ids.editForm.onsubmit({preventDefault(){}});
  const edited=multi.calls.find(x=>x.url==="/api/catalog/edit");
  assert.equal(JSON.parse(edited.options.body).topic,"obst","primary edited topic submitted");
  assert.deepEqual(JSON.parse(edited.options.body).topics,["obst"],"edited checkbox topic transmitted to API");
  assert.deepEqual(JSON.parse(edited.options.body).categories,["tiere"],"edited categories transmitted to API");
  assert.equal(JSON.parse(edited.options.body).category,"tiere","first selected category stays primary");
  const managed=harness();await ready(managed);
  managed.state.managed={
    enabled:true,revision:1,registry_sha256:"f".repeat(64),
    categories:[{id:"tiere",label:"Tiere"},{id:"berufe",label:"Berufe"},{id:"autos",label:"Autos"}],
    counts:{tiere:{catalog:91,archive:0},berufe:{catalog:0,archive:0},autos:{catalog:2,archive:1}}
  };
  await managed.s.loadManagedCategories();
  assert.equal(managed.ids.categoriesRows.hidden,false,"active categories list is visible");
  assert.equal(managed.ids.categoriesCreate.hidden,false,"creation disclosure is available");
  assert.equal(managed.ids.categoriesRows.children.length,3,"one compact row per category");
  assert.equal(managed.ids.categoriesRows.children[0].tag,"li","native list semantics");
  assert.equal(managed.ids.categoriesRows.children[0].children[0].children[0].textContent,"Tiere");
  assert.equal(managed.ids.categoriesRows.children[0].children[1].textContent,"91 catalog · 0 archive");
  assert.equal(managed.ids.categoriesRows.children[0].children[2].children.length,1,"built-in categories have no delete");
  assert.equal(managed.ids.categoriesRows.children[1].children[2].children[1].disabled,false,"unused custom category can be deleted");
  assert.equal(managed.ids.categoriesRows.children[2].children[2].children[1].disabled,true,"referenced custom category cannot be deleted");
  assert.equal(managed.ids.categoriesRows.children[2].children[2].children[1].attrs["aria-label"],"Delete Autos (in use)");
  managed.state.answers=[null];
  await managed.ids.categoriesRows.children[0].children[2].children[0].onclick();
  assert.equal(managed.calls.filter(c=>c.url==="/api/categories/manage"&&c.options.method==="POST").length,0,"cancelled rename performs no write");
  const grouped=harness();await ready(grouped);
  grouped.state.entries=[
    {id:"0000001",category:"tiere",categories:["tiere","autos","autos"],topics:["bauernhof","bauernhof","obst"]},
    {id:"0000002",category:"tiere",categories:["tiere"],topics:["bauernhof"]},
    {id:"0000003",category:"berufe",topics:[]}
  ];
  grouped.state.archiveEntries=[
    {state:"archived",entry:{id:"0000004",category:"autos",topics:["bauernhof"]}},
    {state:"archived",entry:{id:"0000005",category:"berufe",topics:["obst"]}}
  ];
  grouped.state.managed={enabled:true,revision:1,registry_sha256:"f".repeat(64),
    categories:[{id:"tiere",label:"Tiere"},{id:"autos",label:"Autos"},{id:"berufe",label:"Berufe"}],
    counts:{tiere:{catalog:2,archive:0},autos:{catalog:1,archive:1},berufe:{catalog:1,archive:1}}};
  grouped.state.managedTopics={enabled:true,revision:1,registry_sha256:"e".repeat(64),
    topics:[{id:"bauernhof",label:"Bauernhof",icon:"🚜",kind:"evergreen",legacy_terms:[]},
      {id:"obst",label:"Obst",icon:"🍎",kind:"evergreen",legacy_terms:[]},
      {id:"weihnachten",label:"Weihnachten",icon:"🎄",kind:"seasonal",legacy_terms:[]}],
    counts:{bauernhof:{catalog:2,archive:1},obst:{catalog:1,archive:1},weihnachten:{catalog:0,archive:0}}};
  grouped.state.links.links=[
    {category:"tiere",topic:"bauernhof"},{category:"tiere",topic:"obst"},
    {category:"autos",topic:"bauernhof"},{category:"autos",topic:"obst"},
    {category:"berufe",topic:"obst"}
  ];
  // An intentionally blocked usage read must not block functional Category/Topic links.
  grouped.state.usageHold=true;
  await grouped.s.refreshTaxonomyManagers();
  assert.equal(grouped.ids.categoriesRows.children.length,3,"manager renders before page usage");
  assert.equal(grouped.ids.categoriesRows.children[0].children[3].children[1].children.length,2,"links render while usage is pending");
  assert.equal(grouped.ids.categoriesRows.children[0].children[3].children[1].children[0].children[1].textContent,"Page usage loading…","no invented zero count");
  assert.match(grouped.ids.topicGroupsStatus.textContent,/Loading page usage/);
  assert.equal(grouped.state.pendingUsage.length,1,"catalog usage request remains pending");
  grouped.state.pendingUsage.shift()();
  await grouped.s.categoryTopicUsagePending;
  assert.equal(grouped.ids.categoriesRows.children[0].children[3].children[1].children[0].children[1].textContent,"2 catalog · 0 archive","counts update in place");
  grouped.state.usageHold=false;
  await managerReady(grouped);
  assert.equal(grouped.ids.categoriesRows.children.length,3);
  // A slower older error must not overwrite the more recent successful refresh.
  grouped.state.usageHold=true;grouped.state.usageReadFails=true;
  await grouped.s.refreshTaxonomyManagers();
  const staleUsage=grouped.s.categoryTopicUsagePending;
  grouped.state.usageReadFails=false;
  await grouped.s.refreshTaxonomyManagers();
  const freshUsage=grouped.s.categoryTopicUsagePending;
  assert.equal(grouped.state.pendingUsage.length,2);
  grouped.state.pendingUsage.pop()();await freshUsage;
  assert.match(grouped.ids.topicGroupsStatus.textContent,/Assignments are saved independently/);
  grouped.state.pendingUsage.shift()();await staleUsage;
  assert.doesNotMatch(grouped.ids.topicGroupsStatus.textContent,/Usage unavailable/,"late older errors are ignored");
  grouped.state.usageHold=false;
  const tiereDetails=grouped.ids.categoriesRows.children[0].children[3];
  assert.equal(tiereDetails.tag,"details","category uses native disclosure");
  assert.equal(tiereDetails.children[0].textContent,"2 linked topics — show / hide");
  assert.equal(tiereDetails.children[1].children.length,2,"linked topics deduplicated");
  assert.equal(tiereDetails.children[1].children[0].children[0].children[0].textContent,"🚜 Bauernhof");
  assert.equal(tiereDetails.children[1].children[0].children[1].textContent,"2 catalog · 0 archive");
  assert.equal(tiereDetails.children[1].children[0].children[2].children[1].textContent,"Unlink","unlink differs from global delete");
  assert.equal(tiereDetails.children[1].children[0].children[2].children[1].disabled,false);
  assert.equal(grouped.ids.categoriesRows.children[1].children[3].children[1].children.length,2,"many-to-many links");
  assert.equal(grouped.ids.categoriesRows.children[2].children[3].children[1].children.length,1);
  assert.equal(grouped.ids.categoriesRows.children[2].children[3].children[1].children[0].children[1].textContent,"0 catalog · 1 archive");
  assert.equal(grouped.ids.topicsOtherSummary.textContent,"Unlinked topics (1)");
  assert.equal(grouped.ids.topicsRows.children.length,1);
  assert.equal(grouped.ids.topicsRows.children[0].children[0].children[0].textContent,"🎄 Weihnachten");
  assert.equal(grouped.ids.topicsRows.children[0].children[2].children[1].disabled,false);
  assert.ok(html.includes('<details id="topicsOtherDetails"'),"unlinked topics collapsed in native disclosure");
  tiereDetails.open=true;tiereDetails.ontoggle();grouped.ids.topicsOtherDetails.open=true;
  await managerReady(grouped);
  assert.equal(grouped.ids.categoriesRows.children[0].children[3].open,true);
  assert.equal(grouped.ids.topicsOtherDetails.open,true);
  grouped.ids.categoriesRows.children[0].children[3].children[1].children[0].children[2].children[0].onclick();
  assert.equal(grouped.ids.topicEditId.value,"bauernhof","edit works within Category");
  grouped.state.usageReadFails=true;
  await managerReady(grouped);
  assert.equal(grouped.ids.categoriesRows.children[0].children[3].children[1].children.length,2,"read failure does not erase saved links");
  assert.match(grouped.ids.topicGroupsStatus.textContent,/Usage unavailable/);
  grouped.state.usageReadFails=false;grouped.state.archiveSha="b".repeat(64);
  await managerReady(grouped);
  assert.equal(grouped.ids.categoriesRows.children[0].children[3].children[1].children.length,2,"usage mismatch does not fabricate or erase links");
  grouped.state.archiveSha=null;grouped.state.entries=[{id:"0000007",category:"tiere",topics:[]}];grouped.state.archiveEntries=[];
  await managerReady(grouped);
  assert.equal(grouped.ids.categoriesRows.children[0].children[3].children[1].children[0].children[1].textContent,"0 catalog · 0 archive","zero-use linked topic shown");
  assert.equal(grouped.ids.topicsOtherSummary.textContent,"Unlinked topics (1)");
  grouped.state.links.links=[];
  await managerReady(grouped);
  assert.equal(grouped.ids.categoriesRows.children[0].children[3].children[0].textContent,"No linked topics — open to link");
   assert.equal(grouped.ids.categoriesRows.children[0].children[3].children[2].textContent,"No topics linked to this category. Choose one below to link it.","empty category explains explicit linking");
  assert.equal(grouped.ids.topicsRows.children.length,3,"usage never fabricates links");
  const select=grouped.ids.categoriesRows.children[0].children[3].children.at(-1).children[0];
  select.value="bauernhof";
  await grouped.ids.categoriesRows.children[0].children[3].children.at(-1).children[1].onclick();
  const linkWrite=grouped.calls.find(x=>x.url==="/api/category-topics/manage"&&x.options.method==="POST");
  assert.equal(linkWrite.options.headers["If-Match"],'"'+("d".repeat(64))+'"',"strong If-Match guards link");
  assert.equal(linkWrite.options.headers["X-Ausmalwiese-CSRF"],"fixture");
  assert.deepEqual(JSON.parse(linkWrite.options.body),{action:"link",category:"tiere",topic:"bauernhof",category_sha256:"f".repeat(64),topic_sha256:"e".repeat(64)});
  assert.equal(grouped.ids.categoriesRows.children[0].children[3].children[1].children.length,1,"explicit link persists");
  grouped.state.links.enabled=false;grouped.state.links.reason="Owner seed required";
  await managerReady(grouped);
  assert.match(grouped.ids.topicGroupsStatus.textContent,/Owner seed required/);
  assert.equal(grouped.ids.categoriesRows.children[0].children[3].children[1].children.length,0,"disabled assignments never guessed");
  assert.equal(grouped.ids.categoriesRows.children[0].children[3].children.at(-1).tag,"p","no write controls while disabled");

  const inactive=harness();await ready(inactive);await inactive.s.loadManagedCategories();
  assert.equal(inactive.ids.categoriesRows.hidden,true,"unavailable categories hide list");
  assert.equal(inactive.ids.categoriesCreate.hidden,true,"unavailable categories hide creation");
  h.ids.navToggle.onclick();assert.equal(h.ids.primaryNav.dataset.open,"true");assert.equal(h.ids.navToggle.attrs["aria-expanded"],"true");
  h.listeners.keydown({key:"Escape"});assert.equal(h.ids.primaryNav.dataset.open,"false");assert.equal(h.ids.navToggle.focused,true);
  h.ids.navToggle.onclick();h.ids.primaryNav.onclick({target:{closest:()=>({})}});
  assert.equal(h.ids.navToggle.attrs["aria-expanded"],"false");
  h.ids.navToggle.onclick();h.go("catalog");assert.equal(h.ids.primaryNav.dataset.open,"false");
  const opened=[];h.s.window.AdminAnalytics={open:page=>opened.push(page)};
  for(const page of ["overview","upload","catalog","categories","archive","activity","stats","traffic"]){
    h.go(page);assert.deepEqual(h.pages.filter(x=>!x.hidden).map(x=>x.dataset.page),[page]);
    assert.equal(h.navs.find(x=>x.dataset.nav===page).attrs["aria-current"],"page");
    assert.equal(opened.at(-1),page);
  }
  assert.equal(h.navs.some(x=>x.dataset.nav==="topics"),false,"Topics no longer appears in top navigation");
  assert.equal(h.pages.some(x=>x.dataset.page==="topics"),false,"Topics shares Categories view");
  const categoryMarkup=html.slice(html.indexOf('data-page="categories"'),html.indexOf('data-page="activity"'));
  assert.match(categoryMarkup,/id="categoriesRows"[\s\S]*id="managedTopicsPanel"[\s\S]*id="topicsRows"/,"Topics follows Categories");
  assert.match(html,/id="categoriesRefresh"[^>]*>↻ Refresh all</,"one refresh for both");
  assert.equal(html.includes('id="topicsRefresh"'),false,"no duplicate Topics refresh");
  h.go("catalog");
  await ready(h);
  const categoryReads=h.calls.filter(x=>x.url==="/api/categories/manage").length;
  const topicReads=h.calls.filter(x=>x.url==="/api/topics/manage").length;
  h.go("categories");
  await ready(h);
  assert.equal(h.calls.filter(x=>x.url==="/api/categories/manage").length,categoryReads+1,"Categories loads on combined route");
  assert.equal(h.calls.filter(x=>x.url==="/api/topics/manage").length,topicReads+1,"Topics loads on combined route");
  await h.ids.categoriesRefresh.onclick();
  assert.equal(h.calls.filter(x=>x.url==="/api/categories/manage").length,categoryReads+2,"refresh Categories");
  assert.equal(h.calls.filter(x=>x.url==="/api/topics/manage").length,topicReads+2,"refresh Topics");
  h.go("catalog");h.go("topics");
  assert.equal(h.s.currentRoute,"categories","old #topics link opens Categories");
  assert.equal(h.s.location.hash,"#categories","old bookmark canonicalized");
  assert.equal(h.ids.managedTopicsHeading.focused,true,"old bookmark focuses Topics heading");
  assert.equal(h.navs.find(x=>x.dataset.nav==="categories").attrs["aria-current"],"page");
  h.go("catalog");assert.equal(h.ids.catalogGrid.children.length,24);
  h.ids.catalogNext.onclick();assert.equal(h.ids.catalogPageStatus.textContent,"2 / 3");assert.equal(h.ids.catalogGrid.children.length,24);
  h.ids.catalogNext.onclick();assert.equal(h.ids.catalogGrid.children.length,5);assert.equal(h.ids.catalogNext.disabled,true);
  h.ids.catalogSearch.value="Page 52";h.ids.catalogSearch.oninput();
  assert.equal(h.ids.catalogGrid.children.length,1);assert.equal(h.ids.catalogPageStatus.textContent,"1 / 1");
  h.ids.catalogSearch.value="missing";h.ids.catalogSearch.oninput();assert.match(h.ids.catalogGrid.innerHTML,/No matching/);
  h.ids.catalogSearch.value="";h.ids.catalogSearch.oninput();
  h.go("edit/0000001");assert.equal(h.ids.editTitle.value,"Page 1");assert.equal(h.layout.hidden,false);
  assert.equal(h.navs.find(x=>x.dataset.nav==="catalog").attrs["aria-current"],"page");
  h.ids.editTitle.value="Unsaved";
  const analyticsOpens=opened.length;
  h.go("stats");assert.equal(h.s.location.hash,"#edit/0000001");assert.equal(opened.length,analyticsOpens);
  assert.equal(h.state.confirmText,"You have unsaved changes. Leave this page?");
  h.go("archive");assert.equal(h.s.location.hash,"#edit/0000001");assert.equal(h.ids.editTitle.value,"Unsaved");
  h.state.confirm=true;h.go("archive");assert.equal(h.s.currentRoute,"archive");
  await h.s.archiveCatalogEntry(h.state.entries[0]);assert.match(h.state.prompts.at(-1),/^Archiving hides this entry/);
  await h.s.restoreArchiveEntry(h.state.entries[0]);assert.match(h.state.prompts.at(-1),/^Restoring returns this entry/);
  h.state.answers=[h.state.entries[0].id,null];
  await h.s.permanentDeleteArchiveEntry(h.state.entries[0]);assert.match(h.state.prompts.at(-2),/^PERMANENT DELETION/);assert.equal(h.state.prompts.at(-1),"Second confirmation: type DELETE exactly");
  assert.equal(h.calls.filter(x=>["/api/catalog/archive","/api/catalog/restore","/api/archive/delete"].includes(x.url)).length,0,"cancelled confirmations do not write");
  h.go("edit/does-not-exist");assert.equal(h.layout.hidden,true);assert.equal(h.ids.editMissing.hidden,false);
  h.go("unknown");assert.equal(h.s.currentRoute,"overview");
  h.go("catalog");h.skip.onclick({preventDefault(){}});assert.equal(h.s.currentRoute,"catalog");assert.equal(h.ids.main.focused,true);

  h.go("edit/0000001");h.ids.editTitle.value="Changed";h.s.catalogEtag='"new-background-snapshot"';
  await h.ids.editForm.onsubmit({preventDefault(){}});
  const saved=h.calls.find(x=>x.url==="/api/catalog/edit");
  assert.equal(saved.options.headers["If-Match"],'"'+h.state.catalogSha+'"');
  assert.notEqual(saved.options.headers["If-Match"],h.state.etag,"weak edge ETag must not be reused for If-Match");
  assert.equal(saved.options.headers["X-Ausmalwiese-CSRF"],"fixture");
  assert.equal(JSON.parse(saved.options.body).title,"Changed");
  assert.deepEqual(JSON.parse(saved.options.body).categories,["tiere"]);
  assert.equal(JSON.parse(saved.options.body).taxonomy_sha256,"b".repeat(64));
  assert.equal(h.s.location.hash,"catalog");assert.match(h.ids.catalogFeedback.textContent,/saved/);

  h.go("catalog");h.s.err("old catalog error");assert.equal(h.ids.error.style.display,"block");h.state.answers=[h.state.entries[0].id];await h.s.archiveCatalogEntry(h.state.entries[0]);
  const archived=h.calls.findLast(x=>x.url==="/api/catalog/archive");assert.equal(archived.options.headers["If-Match"],'"'+h.state.catalogSha+'"');assert.equal(h.ids.error.style.display,"none");
  h.s.err("route-local error");h.go("archive");assert.equal(h.ids.error.style.display,"none");
  h.go("catalog");h.go("edit/0000002");h.ids.editTitle.value="Keep my draft";h.state.status=412;
  await h.ids.editForm.onsubmit({preventDefault(){}});
  assert.equal(h.ids.editTitle.value,"Keep my draft");
  assert.equal(h.ids.editSave.disabled,true);assert.match(h.ids.error.textContent,/The catalog has changed/);
  assert.equal(h.ids.error.focused,true);
  const writes=h.calls.filter(x=>x.url==="/api/catalog/edit").length;
  await h.ids.editForm.onsubmit({preventDefault(){}});
  assert.equal(h.calls.filter(x=>x.url==="/api/catalog/edit").length,writes);
  h.s.clearPublicationErr();assert.equal(h.ids.error.style.display,"block");
  h.go("catalog");h.go("edit/0000002");assert.equal(h.ids.editSave.disabled,false);
  const reload=harness();reload.s.location.hash="#edit/0000003";reload.s.routePage();await ready(reload);
  assert.equal(reload.ids.editTitle.value,"Page 3");
  console.log("Admin navigation, pagination, deep links, dirty guard, save and stale-write regressions: PASS");
})().catch(error=>{console.error(error);process.exitCode=1});
