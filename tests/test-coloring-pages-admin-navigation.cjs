// Offline behavioral regressions for the protected admin UI. No browser/network dependencies.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const html = fs.readFileSync(path.join(__dirname, "../ops/admin/coloring-pages/index.html"), "utf8");
const script = html.split("<script>")[1].split("</script>")[0];
class Element {
  constructor() { this.value="";this.textContent="";this.style={};this.dataset={};this.attrs={};this.children=[];this.hidden=false;this.disabled=false;this.classList={add(){},remove(){}}; }
  set innerHTML(value) { this.markup=value;this.children=[]; }
  get innerHTML() { return this.markup||""; }
  append(...items) { this.children.push(...items); }
  appendChild(item) { this.append(item); }
  setAttribute(name,value) { this.attrs[name]=value; }
  removeAttribute(name) { delete this.attrs[name]; }
  querySelectorAll() { return []; }
  focus() { this.focused=true; }
  scrollIntoView() {}
  reportValidity() { return true; }
}
function harness() {
  const ids={};
  for (const match of html.matchAll(/\bid="([^"]+)"/g)) ids[match[1]]=new Element();
  const pages=[...html.matchAll(/\bdata-page="([^"]+)"/g)].map(m=>Object.assign(new Element(),{dataset:{page:m[1]}}));
  const navs=[...html.matchAll(/\bdata-nav="([^"]+)"/g)].map(m=>Object.assign(new Element(),{dataset:{nav:m[1]}}));
  const layout=new Element(),skip=new Element(),listeners={},calls=[];
  const location={hash:""};
  const entries=Array.from({length:53},(_,i)=>({id:String(i).padStart(7,"0"),title:"Page "+i,category:i%2?"tiere":"lernen",age:"3-6",difficulty:"easy",thumb:"/media/test/thumb.webp"}));
  const state={entries,etag:'"old"',status:200,confirm:false};
  const sandbox={
    document:{
      title:"",
      getElementById:id=>ids[id],
      querySelectorAll:selector=>selector==="[data-page]"?pages:navs,
      querySelector:selector=>selector===".edit-layout"?layout:skip,
      createElement:()=>new Element()
    }, location,
    history:{replaceState(_a,_b,url){location.hash=url}},
    window:{addEventListener(name,callback){listeners[name]=callback},scrollTo(){},confirm(){return state.confirm}},
    sessionStorage:{getItem(){return null},setItem(){},removeItem(){}},
    setTimeout(){return 1},clearTimeout(){},setInterval(){return 1},clearInterval(){},
    console,
    fetch:async(url,options={})=>{
      calls.push({url,options});
      if(url==="/api/catalog/edit")return {ok:state.status===200,status:state.status,json:async()=>({error:"stale"})};
      if(url==="/api/catalog")return {ok:true,headers:{get:()=>state.etag},json:async()=>({entries:state.entries,count:state.entries.length})};
      if(url==="/api/archive")return {ok:true,json:async()=>({entries:[],count:0})};
      if(url==="/api/activity")return {ok:true,json:async()=>({events:[],count:0})};
      if(url==="/api/categories")return {ok:true,json:async()=>({categories:[]})};
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
  h.ids.navToggle.onclick();assert.equal(h.ids.primaryNav.dataset.open,"true");assert.equal(h.ids.navToggle.attrs["aria-expanded"],"true");
  h.listeners.keydown({key:"Escape"});assert.equal(h.ids.primaryNav.dataset.open,"false");assert.equal(h.ids.navToggle.focused,true);
  h.ids.navToggle.onclick();h.ids.primaryNav.onclick({target:{closest:()=>({})}});
  assert.equal(h.ids.navToggle.attrs["aria-expanded"],"false");
  h.ids.navToggle.onclick();h.go("catalog");assert.equal(h.ids.primaryNav.dataset.open,"false");
  for(const page of ["overview","upload","catalog","archive","activity"]){
    h.go(page);assert.deepEqual(h.pages.filter(x=>!x.hidden).map(x=>x.dataset.page),[page]);
    assert.equal(h.navs.find(x=>x.dataset.nav===page).attrs["aria-current"],"page");
  }
  h.go("catalog");assert.equal(h.ids.catalogGrid.children.length,24);
  h.ids.catalogNext.onclick();assert.equal(h.ids.catalogPageStatus.textContent,"2 / 3");assert.equal(h.ids.catalogGrid.children.length,24);
  h.ids.catalogNext.onclick();assert.equal(h.ids.catalogGrid.children.length,5);assert.equal(h.ids.catalogNext.disabled,true);
  h.ids.catalogSearch.value="Page 52";h.ids.catalogSearch.oninput();
  assert.equal(h.ids.catalogGrid.children.length,1);assert.equal(h.ids.catalogPageStatus.textContent,"1 / 1");
  h.ids.catalogSearch.value="missing";h.ids.catalogSearch.oninput();assert.match(h.ids.catalogGrid.innerHTML,/Nekas/);
  h.ids.catalogSearch.value="";h.ids.catalogSearch.oninput();
  h.go("edit/0000001");assert.equal(h.ids.editTitle.value,"Page 1");assert.equal(h.layout.hidden,false);
  assert.equal(h.navs.find(x=>x.dataset.nav==="catalog").attrs["aria-current"],"page");
  h.ids.editTitle.value="Unsaved";
  h.go("archive");assert.equal(h.s.location.hash,"#edit/0000001");assert.equal(h.ids.editTitle.value,"Unsaved");
  h.state.confirm=true;h.go("archive");assert.equal(h.s.currentRoute,"archive");
  h.go("edit/does-not-exist");assert.equal(h.layout.hidden,true);assert.equal(h.ids.editMissing.hidden,false);
  h.go("unknown");assert.equal(h.s.currentRoute,"overview");
  h.go("catalog");h.skip.onclick({preventDefault(){}});assert.equal(h.s.currentRoute,"catalog");assert.equal(h.ids.main.focused,true);

  h.go("edit/0000001");h.ids.editTitle.value="Changed";h.s.catalogEtag='"new-background-snapshot"';
  await h.ids.editForm.onsubmit({preventDefault(){}});
  const saved=h.calls.find(x=>x.url==="/api/catalog/edit");
  assert.equal(saved.options.headers["If-Match"],'"old"');
  assert.equal(saved.options.headers["X-Ausmalwiese-CSRF"],"fixture");
  assert.equal(JSON.parse(saved.options.body).title,"Changed");
  assert.equal(h.s.location.hash,"catalog");assert.match(h.ids.catalogFeedback.textContent,/saglabāts/);

  h.go("catalog");h.go("edit/0000002");h.ids.editTitle.value="Keep my draft";h.state.status=412;
  await h.ids.editForm.onsubmit({preventDefault(){}});
  assert.equal(h.ids.editTitle.value,"Keep my draft");
  assert.equal(h.ids.editSave.disabled,true);assert.match(h.ids.error.textContent,/Katalogs pa šo laiku/);
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
