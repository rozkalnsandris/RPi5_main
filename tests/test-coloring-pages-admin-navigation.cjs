// Offline behavioral regressions for the protected admin UI. No browser/network dependencies.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const html = fs.readFileSync(path.join(__dirname, "../ops/admin/coloring-pages/index.html"), "utf8");
const script = html.split("<script>")[1].split("</script>")[0];
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
  reportValidity() { return true; }
}
function harness() {
  const ids={};
  for (const match of html.matchAll(/\bid="([^"]+)"/g)) ids[match[1]]=new Element();
  const pages=[...html.matchAll(/\bdata-page="([^"]+)"/g)].map(m=>Object.assign(new Element(),{dataset:{page:m[1]}}));
  const navs=[...html.matchAll(/\bdata-nav="([^"]+)"/g)].map(m=>Object.assign(new Element(),{dataset:{nav:m[1]}}));
  for(const id of ["category","catalogFilter","editCategory"])ids[id].children=[new Element("option")];
  const layout=new Element(),skip=new Element(),listeners={},calls=[];
  const location={hash:""};
  const entries=Array.from({length:53},(_,i)=>({id:String(i).padStart(7,"0"),title:"Page "+i,category:i%2?"tiere":"lernen",age:"3-6",difficulty:"easy",thumb:"/media/test/thumb.webp"}));
  const state={entries,etag:'W/"edge-weakened"',catalogSha:"a".repeat(64),status:200,confirm:false,prompts:[],answers:[],
    taxonomy:{version:"b".repeat(64),categories:[{id:"tiere",label:"Tiere"},{id:"lernen",label:"Lernen"},{id:"jahreszeiten",label:"Jahreszeiten & Feste"}],
    topics:[{id:"weihnachten",label:"Weihnachten",kind:"seasonal"},{id:"obst",label:"Obst",kind:"evergreen"}]}};
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
      if(url==="/api/catalog")return {ok:true,headers:{get:()=>state.etag},json:async()=>({entries:state.entries,count:state.entries.length,catalog_sha256:state.catalogSha})};
      if(url==="/api/archive")return {ok:true,json:async()=>({entries:[],count:0})};
      if(url==="/api/activity")return {ok:true,json:async()=>({events:[],count:0})};
      if(url==="/api/categories")return {ok:true,json:async()=>state.taxonomy};
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
async function ready(h){for(let i=0;i<15;i++)await Promise.resolve();h.s.categoriesReady=true;}
(async()=>{
  const h=harness();await ready(h);
  assert.equal(h.s.taxonomyVersion,"b".repeat(64));
  assert.equal(h.s.topicReady,true);
  assert.equal(h.ids.category.children.some(x=>x.value==="jahreszeiten"&&x.textContent==="Jahreszeiten & Feste"),true);
  assert.equal(Object.keys(h.s.topicInputs).length,2);
  h.ids.category.value="jahreszeiten";h.ids.category.onchange();
  assert.equal(h.s.topicInputs.weihnachten.disabled,false);
  assert.equal(h.s.topicInputs.obst.disabled,true);
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
  assert.equal(h.ids.category.options.find(x=>x.value==="jahreszeiten").disabled,true);
  await h.s.sendZip({name:"weihnachten.zip"});
  await h.ids.publish.onclick();
  const pub=h.calls.find(x=>x.url==="/api/jobs");
  assert.equal(JSON.parse(pub.options.body).topic,"weihnachten");
  assert.deepEqual(JSON.parse(pub.options.body).topics,["weihnachten"]);
  assert.deepEqual(JSON.parse(pub.options.body).categories,["jahreszeiten"]);
  assert.equal(JSON.parse(pub.options.body).category,"jahreszeiten");
  assert.equal(JSON.parse(pub.options.body).taxonomy_sha256,"b".repeat(64));
  h.state.taxonomy.topics.push({id:"laterne",label:"Laterne",kind:"seasonal"});
  await h.s.loadCategories();
  assert.equal(Object.keys(h.s.topicInputs).includes("laterne"),true);
  const multi=harness();await ready(multi);
  const add=id=>{multi.ids.category.value=id;multi.ids.category.onchange()};
  add("tiere");add("jahreszeiten");add("lernen");add("lernen");
  assert.deepEqual(Array.from(multi.s.selectedCategories),["tiere","jahreszeiten","lernen"],"duplicate category ignored");
  assert.equal(multi.ids.chosenCategories.children.length,3);
  assert.equal(multi.ids.category.options.find(x=>x.value==="lernen").disabled,true);
  multi.s.topicInputs.weihnachten.checked=true;multi.s.topicInputs.weihnachten.onchange();
  multi.s.topicInputs.obst.checked=true;multi.s.topicInputs.obst.onchange();
  assert.deepEqual(Array.from(multi.s.selectedTopics),["weihnachten","obst"]);
  assert.equal(multi.ids.chosenTopic.children.length,2);
  multi.ids.chosenCategories.children[1].children[1].onclick();
  assert.deepEqual(Array.from(multi.s.selectedTopics),["obst"],"removing seasonal category clears seasonal topic only");
  assert.equal(multi.ids.chosenTopic.children.length,1,"compatible evergreen topic remains");
  assert.equal(multi.ids.category.focused,true,"focus returns to category select");
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
  multi.go("edit/0000001");
  assert.deepEqual(Array.from(multi.s.editSelectedTopics),["obst","weihnachten"],"all edited topics loaded");
  assert.deepEqual(Array.from(multi.s.editValues().topics),["obst","weihnachten"],"catalog edit preserves both topics");
  multi.ids.editChosenTopics.children[0].children[1].onclick();
  assert.deepEqual(Array.from(multi.s.editSelectedTopics),["weihnachten"]);
  assert.equal(multi.ids.editTopicPicker.querySelector("summary").focused,true);
  multi.ids.editChosenCategories.children[1].children[1].onclick();
  assert.deepEqual(Array.from(multi.s.editSelectedTopics),[],"removing seasonal category removes only incompatible remaining topic");
  h.ids.navToggle.onclick();assert.equal(h.ids.primaryNav.dataset.open,"true");assert.equal(h.ids.navToggle.attrs["aria-expanded"],"true");
  h.listeners.keydown({key:"Escape"});assert.equal(h.ids.primaryNav.dataset.open,"false");assert.equal(h.ids.navToggle.focused,true);
  h.ids.navToggle.onclick();h.ids.primaryNav.onclick({target:{closest:()=>({})}});
  assert.equal(h.ids.navToggle.attrs["aria-expanded"],"false");
  h.ids.navToggle.onclick();h.go("catalog");assert.equal(h.ids.primaryNav.dataset.open,"false");
  const opened=[];h.s.window.AdminAnalytics={open:page=>opened.push(page)};
  for(const page of ["overview","upload","catalog","archive","activity","stats","traffic"]){
    h.go(page);assert.deepEqual(h.pages.filter(x=>!x.hidden).map(x=>x.dataset.page),[page]);
    assert.equal(h.navs.find(x=>x.dataset.nav===page).attrs["aria-current"],"page");
    assert.equal(opened.at(-1),page);
  }
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
