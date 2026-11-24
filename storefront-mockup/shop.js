let activeCategory='all',activeView='packaged',limit=12,visibleCount=0,linkedItem='',activeFrom='';
const makerCounts=new Map();catalog.forEach(p=>makerCounts.set(p.producerKey,(makerCounts.get(p.producerKey)||0)+1));
const validFrom=key=>Object.hasOwn(producers,key)&&makerCounts.get(key)>=2;
$('#catalog-grid').insertAdjacentHTML('beforebegin','<p class="catalog-from" hidden></p>');
// AV1352-02: one status line for a shared ?item= link to a product that is no longer listed; hidden again at the next filter change.
$('#catalog-grid').insertAdjacentHTML('beforebegin','<p class="micro" id="catalog-item-status" role="status" hidden></p>');
function maker(p){return producers[p.producerKey]}
function organic(p){return /\borganic\b/i.test(p.name)||['Ocean Ranch','Straus','Green Gold','Massa Organics'].includes(p.producerKey)}
// AV1352-01: only an installed owner photo (same shape as content_model.HOME_IMAGE_RE) is not an illustration; JS $ without the m flag is a true end.
const installedImage=s=>typeof s==='string'&&/^assets\/products\/photo-[0-9a-f]{16}\.(jpg|png)$/.test(s);
function photo(p){return `<img loading=\"lazy\" width=\"800\" height=\"800\" src=\"${esc(p.image)}\" alt=\"${esc((p.imageAlt||p.name)+(installedImage(p.image)?'':' (illustration)'))}\">`}
function origin(p){return p.supplier?`From ${p.supplier}`:maker(p)?`Based in ${maker(p).place}`:'Ask us about the source in store.'}
function badges(p){const tags=(organic(p)?'<span>Organic</span>':'')+(isNew(p,pinNow||undefined)?'<span>New</span>':'');return (tags?`<div class="food-badges">${tags}</div>`:'')+(p.availability?`<p class="product-meta availability">${esc(p.availability)}</p>`:'')}
function brand(p){return p.displayBrand||(p.brand==='Producer not identified'?'From the market':p.brand)}
// AV0222-10: a maker's story is optional. Story: story paragraph; no story but a link: place only; neither: no panel at all.
function makerStory(p){const m=maker(p);if(!m)return'';const story=typeof m.story==='string'&&m.story.trim()!=='',link=typeof m.url==='string'&&m.url!=='';if(!story&&!link)return'';
 return `<details class="maker-story"><summary>Meet the maker<span class="sr-only">: ${esc(m.name)}</span></summary><div class="maker-story-content">${story?`<p>${esc(m.story)}</p>`:`<p class="maker-place">Based in ${esc(m.place)}</p>`}${link?`<a href="${esc(m.url)}" target="_blank" rel="noopener">Visit ${esc(m.name)} <span aria-hidden="true">↗</span></a>`:''}${makerCounts.get(p.producerKey)>=2?`<button type="button" class="text-link" data-from="${esc(p.producerKey)}">See all ${makerCounts.get(p.producerKey)} from ${esc(m.name)}</button>`:''}</div></details>`}
// The maker's key and name are always on the card (screen-reader only), so a preview finds the card with or without the panel.
function card(p){
 const m=maker(p);
 const amount=p.sellingPrice?`<p class="product-meta product-price">$${esc(p.sellingPrice)}</p>`:'';
 return `<article data-product-id="${esc(p.id)}" data-category="${esc(p.category)}"${m?` data-maker-key="${esc(p.producerKey)}"`:''}><div class="food-card-top"><div class="product-image">${photo(p)}</div><div class="food-identity"><p class="product-meta">${esc(brand(p))}</p><h3>${esc(p.name)}</h3>${amount}<p class="origin-label">${esc(origin(p))}</p>${m?`<span class="sr-only maker-name">${esc(m.name)}</span>`:''}${badges(p)}</div></div><p class="food-description">${esc(p.description)}</p>${makerStory(p)}<a class="text-link card-link" href="?item=${esc(encodeURIComponent(p.id))}#market">Link to this</a></article>`;
}
[...new Set(catalog.map(p=>p.brand))].sort().forEach(b=>{const o=document.createElement('option');o.value=b;o.textContent=b==='Producer not identified'?'Other market selections':b;$('#brand-filter').append(o)});
// AV1622-04: shelf-check words and the selection line are worked out here, in the visitor's browser, from the recorded dates
// in catalog-products.js and today's date in Pacific time, with the same rule as sitegen (pinned by test_browser_freshness).
// The words are never published and no date is invented; the build-time paragraph stays as the no-JS fallback.
// FRESHNESS-BEGIN
const STALE_AFTER_DAYS=7,AVAILABILITY_WORDS={yes:'Available today',limited:'Limited',no:'Sold out'};
const DAY_NAMES=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'],MONTH_NAMES=['January','February','March','April','May','June','July','August','September','October','November','December'];
const PACIFIC_DAY=new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',year:'numeric',month:'2-digit',day:'2-digit'});
function pacificDay(now){const q={};for(const x of PACIFIC_DAY.formatToParts(now))q[x.type]=x.value;return `${q.year}-${q.month}-${q.day}`}
// UTC day number of a real YYYY-MM-DD date, else null (impossible dates such as 2026-02-30 are rejected).
function dayNumber(s){const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(typeof s==='string'?s:'');if(!m)return null;const y=+m[1],mo=+m[2],d=+m[3],t=new Date(Date.UTC(y,mo-1,d));return t.getUTCFullYear()===y&&t.getUTCMonth()===mo-1&&t.getUTCDate()===d?t.getTime()/864e5:null}
function dayText(s){const t=new Date(dayNumber(s)*864e5);return `${DAY_NAMES[t.getUTCDay()]}, ${MONTH_NAMES[t.getUTCMonth()]} ${t.getUTCDate()}`}
// Whole calendar days from the check to today, or null (missing, invalid or future date).
function checkAge(checked,today){const a=dayNumber(checked),t=dayNumber(today);return a===null||t===null||a>t?null:t-a}
function selectionLine(checked,today,phone){const age=checkAge(checked,today);if(age===null)return null;
 const call=/^\d{10}$/.test(phone||'')?` call (${phone.slice(0,3)}) ${phone.slice(3,6)}-${phone.slice(6)} or`:' call or';
 return `Selection last checked by Michael on ${dayText(checked)}${age>STALE_AFTER_DAYS?` (more than a week ago -${call} visit to confirm)`:''}.`}
function availabilityWord(state,on,checked,today){const age=checkAge(checked,today),o=dayNumber(on),t=dayNumber(today);
 if(age===null||o===null||o>t||typeof state!=='string'||!Object.hasOwn(AVAILABILITY_WORDS,state))return null;
 return o>=dayNumber(checked)&&t-o<=STALE_AFTER_DAYS?AVAILABILITY_WORDS[state]:`Last confirmed ${dayText(on)}`}
function refreshFreshness(now=new Date()){const today=pacificDay(now),checked=typeof catalogFreshness==='object'&&catalogFreshness?catalogFreshness.selectionCheckedOn:null;
 catalog.forEach(p=>{const w=availabilityWord(p.availabilityState,p.availabilityCheckedOn,checked,today);if(w===null)delete p.availability;else p.availability=w});
 const note=document.querySelector('.selection-checked'),line=note&&selectionLine(note.dataset.checkedOn,today,note.dataset.phone);if(line)note.textContent=line}
// FRESHNESS-END
// AV1622-06: a product Hass added shows New for its first NEW_BADGE_DAYS Pacific calendar days (addedOn, same day rule as above);
// a missing, invalid or future date shows nothing. Worked out each time a card is drawn, from the visitor's clock.
const NEW_BADGE_DAYS=14;
let renderNow=new Date(),pinNow=null;  // pinNow: the render day, set only while cards are drawn
const isNew=(p,now=new Date())=>{const a=dayNumber(p.addedOn),t=dayNumber(pacificDay(now));return a!==null&&t!==null&&t-a>=0&&t-a<NEW_BADGE_DAYS};
// AV1102-03: the words match sitegen.AVAILABILITY_WORDS (pinned by a test); "Last confirmed ..." is never current.
refreshFreshness();
const CURRENT=new Set(['Available today','Limited','Sold out']),AVAIL=new Set(['Available today','Limited']);let availBox=null;
if(catalog.some(p=>CURRENT.has(p.availability))){$('#brand-filter').closest('label').insertAdjacentHTML('afterend','<label class="avail-filter"><input type="checkbox" id="avail-filter"> Available today</label>');availBox=$('#avail-filter')}
const fold=s=>String(s||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[\u2018\u2019\u02bc]/g,"'").toLowerCase();
const SHELF=Object.fromEntries([...document.querySelectorAll('[data-filter]')].filter(b=>b.dataset.filter!=='all').map(b=>[b.dataset.filter,b.textContent.trim()]));
// AV1052-02: a shelf with no product in the published catalog is not offered; worked out once per page load.
const SHELVES=new Set(catalog.map(p=>p.category));
// AVO-SHOP-CLEAN-1: the shop opens on packaged goods. The shelves split into packaged goods and fresh produce (fruit, vegetables,
// flowers); photo-product-018 (tortilla chips) is filed under vegetables but is sold in a bag, so it is packaged. ?view=packaged|produce|all
// is the shareable state; a link with ?shelf= but no view opens on that shelf's own view, ?from= or ?item= on all items.
const PRODUCE_SHELVES=new Set(['fruit','vegetables','flowers']),PACKAGED_IDS=new Set(['photo-product-018']),VIEWS=['packaged','produce','all'];
const isPackaged=p=>PACKAGED_IDS.has(p.id)||!PRODUCE_SHELVES.has(p.category);
const inView=p=>activeView==='all'||isPackaged(p)===(activeView==='packaged');
const viewOfShelf=s=>PRODUCE_SHELVES.has(s)?'produce':'packaged';
function shelfButtons(){document.querySelectorAll('[data-filter]').forEach(b=>{const f=b.dataset.filter;b.hidden=f!=='all'&&(!SHELVES.has(f)||(activeView!=='all'&&viewOfShelf(f)!==activeView))})}
function setView(v){activeView=v;document.querySelectorAll('[data-view]').forEach(x=>{x.classList.toggle('selected',x.dataset.view===v);x.setAttribute('aria-pressed',String(x.dataset.view===v))});
 const cur=document.querySelector('[data-filter].selected');if(cur&&cur.dataset.filter!=='all'&&activeView!=='all'&&viewOfShelf(cur.dataset.filter)!==activeView)selectShelf($('[data-filter="all"]'));shelfButtons()}
shelfButtons();
// One search normalization for filtering, the address and restore: trimmed, at most 80 characters (code points).
const searchText=s=>[...String(s||'').trim()].slice(0,80).join('').trim();
// AV0222-09: products the badge shows as New come first, newest addedOn first (ties and every other product keep catalog sequence).
// A new array each time; the day is renderNow's, so badges and sequence agree for one render.
function orderedProducts(now=renderNow){const d=catalog.map((p,i)=>({p,i,n:isNew(p,now)}));
 d.sort((x,y)=>x.n!==y.n?(x.n?-1:1):x.n&&x.p.addedOn!==y.p.addedOn?(x.p.addedOn>y.p.addedOn?-1:1):x.i-y.i);return d.map(x=>x.p)}
// AV1104-02: cards whose current word is exactly Sold out go last; other positions stay stable (new array, nothing mutated).
const soldLast=l=>l.filter(p=>p.availability!=='Sold out').concat(l.filter(p=>p.availability==='Sold out'));
function drawCards(l){pinNow=renderNow;try{return l.map(card).join('')}finally{pinNow=null}}
// AV1052-01: a search term also matches the description, after the card's own words. One stable pass splits the ordered list:
// name, brand, town, shelf or Organic badge first, then description hits (a card in both groups appears once, in the first).
// AV1104-01: the term is split into words; a card matches when EVERY word is found, regardless of sequence, each in any searched field. A word is found
// in a field as literal text, or as a whole field word with the same one-step -ies/-y, -es or -s form (words of 4+ letters, reductions of 3+). Fields are folded and searched separately.
const wordsOf=t=>t.match(/[\p{L}\p{N}]+(?:'[\p{L}\p{N}]+)*/gu)||[];
const forms=w=>{const f=new Set([w]);if(/^\p{L}+$/u.test(w)&&[...w].length>=4){const add=x=>{if([...x].length>=3)f.add(x)};if(w.endsWith('ies'))add(w.slice(0,-3)+'y');if(w.endsWith('es'))add(w.slice(0,-2));if(w.endsWith('s'))add(w.slice(0,-1))}return f};
const hasWord=(field,piece,pf)=>field.includes(piece)||wordsOf(field).some(w=>{for(const x of forms(w))if(pf.has(x))return true;return false});
function filteredProducts(){const pieces=fold(searchText($('#product-search').value)).split(/\s+/).filter(Boolean),brand=$('#brand-filter').value;
 const list=orderedProducts().filter(p=>inView(p)&&(!activeFrom||p.producerKey===activeFrom)&&(activeCategory==='all'||p.category===activeCategory)&&(!brand||p.brand===brand)&&(!availBox?.checked||AVAIL.has(p.availability)));
 if(!pieces.length)return soldLast(list);const first=[],second=[],pf=pieces.map(forms);
 for(const p of list){const meta=[p.name,p.brand,maker(p)?.place,SHELF[p.category],organic(p)?'Organic':''].map(fold),desc=fold(p.description),got=(i,f)=>hasWord(f,pieces[i],pf[i]);
  if(pieces.every((_,i)=>meta.some(f=>got(i,f))))first.push(p);else if(pieces.every((_,i)=>meta.some(f=>got(i,f))||got(i,desc)))second.push(p)}
 return soldLast(first).concat(soldLast(second))}
// RF0854-13: once a render re-ages every word to Last confirmed, the Available today control is retired as a reload would:
// unchecked, removed, and only ?avail dropped (replaceState; other params, hash and item state untouched). Whole catalog, not the results.
function retireStaleAvail(){if(!availBox||catalog.some(p=>CURRENT.has(p.availability)))return false;availBox.checked=false;availBox.closest('.avail-filter').remove();availBox=null;
 const u=new URLSearchParams(location.search);if(u.has('avail')){u.delete('avail');const q=u.toString();history.replaceState(history.state,'',location.pathname+(q?'?'+q:'')+location.hash)}return true}
function renderCatalog(append=false){refreshFreshness();if(retireStaleAvail())append=false;const t=new Date();if(!append||pacificDay(t)!==pacificDay(renderNow)){append=false;renderNow=t}const chip=$('.catalog-from');chip.hidden=!activeFrom;chip.innerHTML=activeFrom?`From ${esc(producers[activeFrom].name)} <button type="button" data-clear-from>Show everything</button>`:'';const list=filteredProducts(),end=Math.min(limit,list.length);if(!append){$('#catalog-grid').innerHTML='';visibleCount=0}$('#catalog-grid').insertAdjacentHTML('beforeend',drawCards(list.slice(visibleCount,end)));visibleCount=end;$('#catalog-count').textContent=`${list.length} selections · ${visibleCount} shown`;$('#catalog-sentinel').textContent=visibleCount<list.length?'More good things as you scroll.':list.length?'That’s this selection. Explore another category, producer, or town.':activeView==='all'?'Nothing here just yet. Try another category or clear your filters.':'Nothing here just yet. Try All items, another category, or clear your filters.';$('#more-products').hidden=('IntersectionObserver' in window)||visibleCount>=list.length;$('#clear-filters').hidden=!anyFilter()}
function anyFilter(){return activeView!=='packaged'||activeCategory!=='all'||!!searchText($('#product-search').value)||!!$('#brand-filter').value||!!activeFrom||!!availBox?.checked}
function syncUrl(){const p=new URLSearchParams(location.search),set=(k,v)=>v?p.set(k,v):p.delete(k),s=()=>p.toString();
 linkedItem='';p.delete('item');const gone=$('#catalog-item-status');gone.hidden=true;gone.textContent='';  // A filter change also cancels any pending item scroll/focus.
 set('from',activeFrom);set('shelf',activeCategory==='all'?'':activeCategory);set('view',activeView===(activeCategory!=='all'?viewOfShelf(activeCategory):activeFrom?'all':'packaged')?'':activeView);set('q',searchText($('#product-search').value));set('maker',$('#brand-filter').value);set('avail',availBox?.checked?'1':'');
 history.replaceState(null,'',location.pathname+(s()?'?'+s():'')+location.hash)}
function resetCatalog(){limit=12;syncUrl();renderCatalog();scheduleScroll()}
$('#clear-filters').onclick=()=>{setView('packaged');selectShelf($('[data-filter="all"]'));$('#product-search').value='';$('#brand-filter').value='';activeFrom='';if(availBox)availBox.checked=false;resetCatalog();$('#product-search').focus()};
function loadMore(){if(visibleCount>=filteredProducts().length)return;limit+=12;renderCatalog(true)}
// Typed or pasted text past the limit is cut in the box too, so the box, the results and a shared address agree.
$('#product-search').oninput=()=>{const box=$('#product-search');if([...box.value.trim()].length>80)box.value=searchText(box.value);resetCatalog()};$('#brand-filter').onchange=resetCatalog;if(availBox)availBox.onchange=resetCatalog;$('#more-products').onclick=loadMore;
function selectShelf(b){activeCategory=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(x=>{x.classList.toggle('selected',x===b);x.setAttribute('aria-pressed',String(x===b))})}
document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{selectShelf(b);resetCatalog()});
document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{setView(b.dataset.view);resetCatalog()});
document.addEventListener('click',e=>{const b=e.target.closest('[data-from],[data-clear-from]');if(!b)return;const key=b.dataset.from||'';if(key&&!validFrom(key))return;activeFrom=key;setView('all');selectShelf($('[data-filter="all"]'));$('#product-search').value='';$('#brand-filter').value='';if(availBox)availBox.checked=false;resetCatalog();$('#catalog-grid').scrollIntoView({block:'start'})});
let scrollFrame=0, sectionNavigation=false, sectionTimer;
function checkScroll(){
 scrollFrame=0;
 const edge=$('#catalog-sentinel').getBoundingClientRect();
 // Loading products above a visitor who has moved on would shift their section.
 if(!sectionNavigation&&visibleCount<filteredProducts().length&&edge.bottom>=0&&edge.top<innerHeight+600){loadMore();scrollFrame=requestAnimationFrame(checkScroll)}
}
function scheduleScroll(){if(!scrollFrame)scrollFrame=requestAnimationFrame(checkScroll)}
function resumeCatalog(){clearTimeout(sectionTimer);sectionNavigation=false;scheduleScroll()}
function waitForSectionScroll(){clearTimeout(sectionTimer);sectionTimer=setTimeout(resumeCatalog,250)}
function followSection(hash){
 const target=document.getElementById(hash.slice(1));
 if(target&&target!==$('#market')&&!$('#market').contains(target)){sectionNavigation=true;waitForSectionScroll()}
}
// Pause during anchor scrolling through the catalog, including direct hash links.
followSection(location.hash);
document.addEventListener('click',event=>{const link=event.target.closest('a[href^="#"]');if(link)followSection(link.getAttribute('href'))},true);
window.addEventListener('hashchange',()=>followSection(location.hash));
// Restore shelf, search, brand and maker views; only a known multi-product maker can be active.
// A malformed address must never stop the catalog, so the whole restore is guarded.
try{const u=new URLSearchParams(location.search),shelf=[...document.querySelectorAll('[data-filter]')].find(x=>x.dataset.filter===u.get('shelf')),mk=u.get('maker');
 activeFrom=validFrom(u.get('from'))?u.get('from'):'';
 setView(VIEWS.includes(u.get('view'))?u.get('view'):shelf&&(shelf.dataset.filter==='all'||SHELVES.has(shelf.dataset.filter))?viewOfShelf(shelf.dataset.filter):activeFrom?'all':'packaged');
 if(shelf&&!shelf.hidden)selectShelf(shelf);$('#product-search').value=searchText(u.get('q'));$('#brand-filter').value=mk&&[...$('#brand-filter').options].some(o=>o.value===mk)?mk:'';
 // AV1322-10: ?item=<catalog id> wins over the filters: show everything, load enough cards to reach it.
 // An unknown, empty or over-80-character id is ignored and the filters above apply as before.
 const item=u.get('item'),i=item&&[...item].length<=80?soldLast(orderedProducts()).findIndex(p=>p.id===item):-1;
 if(i>=0){activeFrom='';setView('all');selectShelf($('[data-filter="all"]'));$('#product-search').value='';$('#brand-filter').value='';limit=Math.max(12,Math.ceil((i+1)/12)*12);linkedItem=item;if(availBox)availBox.checked=false}
 if(availBox)availBox.checked=u.get('avail')==='1'&&i<0;
 let fix=false;
 // AV1352-02: a nonempty id of at most 80 characters that is not in the catalog gets one neutral line and loses ?item (exact id, nothing echoed).
 if(i<0&&item&&[...item].length<=80){const s=$('#catalog-item-status');s.textContent='That item is not in our catalog right now. Here is everything else.';s.hidden=false;u.delete('item');fix=true}if(shelf?.hidden){u.delete('shelf');fix=true}if(u.has('view')&&!VIEWS.includes(u.get('view'))){u.delete('view');fix=true}if(u.has('from')&&!activeFrom){u.delete('from');fix=true}if(u.has('avail')&&!availBox?.checked){u.delete('avail');fix=true}
 if(fix){const q=u.toString();history.replaceState(null,'',location.pathname+(q?'?'+q:'')+location.hash)}}catch(e){}
renderCatalog();
// Prefer load, after the browser's #market jump, but do not wait indefinitely for a nonessential asset.
let linkedShown=false;
function showLinked(){const el=[...document.querySelectorAll('#catalog-grid article')].find(a=>a.dataset.productId===linkedItem);
 const active=document.activeElement;
 const untouched=!active||active===document.body||active===document.documentElement;
 // First reveal only on an untouched page; repair the anchor jump only while the card has focus.
 if(el&&(active===el||(!linkedShown&&untouched))){linkedShown=true;el.setAttribute('tabindex','-1');el.scrollIntoView({block:'center'});el.focus({preventScroll:true})}}
if(linkedItem){if(document.readyState==='complete')showLinked();else{
 const fallback=setTimeout(showLinked,1000);
 addEventListener('load',()=>{clearTimeout(fallback);requestAnimationFrame(showLinked)},{once:true});
}}
if('IntersectionObserver' in window){
 const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting))scheduleScroll()},{rootMargin:'600px 0px'});
 observer.observe($('#catalog-sentinel'));
 window.addEventListener('scroll',()=>{if(sectionNavigation)waitForSectionScroll();else scheduleScroll()},{passive:true});
 window.addEventListener('resize',scheduleScroll);
}
