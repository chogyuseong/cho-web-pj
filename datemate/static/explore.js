/* 장소 둘러보기(app/explore.py).
   기본 목록: 공공 자료(한국관광공사 관광정보·소상공인 상가정보)를 우리 기준으로 정리한 카드. 사진·상세·코스에 쓰는 것은 이 목록뿐이다.
   그 아래 '네이버에서 더 찾기': 펼쳤을 때만 불러, 검색어 하나당 네이버 지역 검색 결과를 받은 순서 그대로 한 블록씩 보여 준다
   (naver-attribution.js naverResultBlock). 블록 항목은 합치거나 거르지 않고, 우리 카드·사진·장소 상세와 잇지 않는다. */
// 꼭 들를 장소(2026-11-26 요구 문서 Phase 4 '코스 바구니'). 둘러보기 카드의 「+ 코스에 담기」로 담고(Basket, 최대 5곳·한 시·도),
// 화면 아래 바구니 도크의 「담은 N곳으로 코스 짜기」를 누르면 includePlaces 가 코스 만들기로 넘긴다.
// app.js values() 가 추천 요청의 고정 자리(locked)에 비어 있는 앞자리부터 넣는다 — 서버는 고정 장소가 후보에 없으면 둘러보기 보관분에서 찾아 넣는다
// (app/quality.py pool, 예전 한 곳 포함 기능 2026-11-24 UX P2 와 같은 길). 담은 수가 장소 수보다 많으면 장소 수를 늘린다(최대 5).
// 출발 기준은 첫 장소 위치(서버 지역 일치 검증: 출발지 이름은 시·도로 시작). 출발지를 다른 곳으로 바꾸면 꼭 들를 장소도 비운다.
let includedPlaces=[],includedOrigin=null;
const BASKET_MAX=5;
function includePlaces(list,region){
  const first=list[0];if(!first)return;
  const origin={name:`${region} ${first.name} 주변`,lat:first.lat,lon:first.lon};
  applyArea(region,origin);
  includedPlaces=list.map(p=>({id:p.id,name:p.name}));includedOrigin=origin.name;
  const count=form.elements.count;
  if(count&&Number(count.value)<includedPlaces.length){count.value=String(Math.min(BASKET_MAX,includedPlaces.length));count.dispatchEvent(new Event('change',{bubbles:true}));}
  document.getElementById('nav-plan').click();
  renderIncludedTags(true);
  toast(includedPlaces.length===1?withObjectParticle(first.name)+' 넣어 코스를 짜요.':`담은 ${includedPlaces.length}곳을 꼭 넣어 코스를 짜요.`);
}
// 예전 이름(한 곳). 다른 파일·테스트가 부를 수 있어 남긴다.
function includePlace(place,region){includePlaces([place],region);}
// 코스 만들기 맨 위 '꼭 들를 장소' 칩 목록(테마 배너와 같은 자리 #preset-tags). 칩마다 ×로 뺀다.
function renderIncludedTags(focus=false){
  let box=document.getElementById('preset-tags');
  if(!box){box=node('div',undefined,'preset-tags');box.id='preset-tags';box.setAttribute('role','group');form.prepend(box);}
  if(!includedPlaces.length){if(box.getAttribute('aria-label')==='포함할 장소')box.hidden=true;return;}
  box.setAttribute('aria-label','포함할 장소');
  const tags=node('div',undefined,'preset-tag-list');tags.append(node('span','꼭 들를 장소','tag'));
  for(const place of includedPlaces){
    const chip=node('span',undefined,'include-chip');chip.append(node('strong',place.name));
    const x=button('×',()=>{includedPlaces=includedPlaces.filter(p=>p.id!==place.id);if(!includedPlaces.length)includedOrigin=null;renderIncludedTags();},'include-chip-remove');
    x.setAttribute('aria-label',place.name+' 빼기');chip.append(x);tags.append(chip);
  }
  const go=button('이 조건으로 바로 추천받기',()=>form.requestSubmit(),'primary preset-go');
  const drop=button(includedPlaces.length===1?'이 장소 빼기':'모두 빼기',()=>{includedPlaces=[];includedOrigin=null;box.hidden=true;},'secondary');
  box.replaceChildren(node('p',includedPlaces.length===1?'이 장소를 꼭 넣고, 그 주변에서 나머지 장소를 찾아요. 날짜·시간·예산은 아래 기본 조건에서 확인해 주세요.':`담은 ${includedPlaces.length}곳을 꼭 넣고, 첫 장소 주변에서 나머지를 찾아요. 날짜·시간·예산은 아래 기본 조건에서 확인해 주세요.`,'hint'),tags,go,drop);
  box.hidden=false;
  if(focus)requestAnimationFrame(()=>{go.focus({preventScroll:true});go.scrollIntoView({block:'center',behavior:'instant'});});
}
// 출발지를 다른 곳으로 바꾸면 꼭 들를 장소도 비운다(그 장소가 동선 범위를 벗어날 수 있다).
document.addEventListener('click',()=>setTimeout(()=>{
  if(!includedPlaces.length||locationState.origin?.name===includedOrigin)return;
  includedPlaces=[];includedOrigin=null;const box=document.getElementById('preset-tags');if(box&&box.getAttribute('aria-label')==='포함할 장소')box.hidden=true;
}));
// 코스 바구니(둘러보기 화면 아래 도크). 담은 장소 {id,name,lat,lon} 과 그 시·도. 다른 시·도의 장소를 담으면 새로 시작한다.
const Basket={
  items:[],region:null,
  has(id){return this.items.some(p=>p.id===id);},
  toggle(place,region){
    if(this.has(place.id)){this.remove(place.id);return;}
    if(this.region&&this.region!==region&&this.items.length){this.items=[];toast(`다른 시·도(${region})의 장소라 바구니를 새로 시작했어요.`);}
    if(this.items.length>=BASKET_MAX){toast(`한 코스에는 ${BASKET_MAX}곳까지 담을 수 있어요.`);return;}
    this.region=region;this.items.push({id:place.id,name:place.name,lat:Number(place.lat),lon:Number(place.lon)});this.render();
  },
  remove(id){this.items=this.items.filter(p=>p.id!==id);if(!this.items.length)this.region=null;this.render();},
  clear(){this.items=[];this.region=null;this.render();},
  go(){const list=[...this.items],region=this.region;this.clear();includePlaces(list,region);},
  render(){
    // 담은 카드의 단추는 보조 단추 모양으로(.primary 는 shell.css 가 !important 로 칠해 aria-pressed 만으로는 바꿀 수 없다).
    document.querySelectorAll('#catalog .basket-add').forEach(b=>{const on=this.has(b.dataset.placeId);b.setAttribute('aria-pressed',String(on));b.textContent=on?'담음 ✓ (빼기)':'+ 코스에 담기';b.classList.toggle('primary',!on);b.classList.toggle('secondary',on);});
    let dock=document.getElementById('basket-dock');
    if(!dock){dock=node('section',undefined,'basket-dock');dock.id='basket-dock';dock.setAttribute('aria-label','코스 바구니');document.body.append(dock);}
    dock.hidden=!this.items.length;
    if(!this.items.length){dock.replaceChildren();return;}
    const list=node('ul',undefined,'basket-list');
    for(const place of this.items){const li=node('li',undefined,'basket-item');li.append(node('span',place.name));const x=button('×',()=>this.remove(place.id),'basket-remove');x.setAttribute('aria-label',place.name+' 바구니에서 빼기');li.append(x);list.append(li);}
    const head=node('p',`코스 바구니 · ${this.region} ${this.items.length}곳`,'basket-title');
    const clear=button('비우기',()=>this.clear(),'secondary basket-clear');
    const go=button(`담은 ${this.items.length}곳으로 코스 짜기`,()=>this.go(),'primary basket-go');
    dock.replaceChildren(head,list,clear,go);
  }
};
const ExploreView={
  sequence:0,offset:0,regionTouched:false,
  card(place,mode){
    const card=node('article',undefined,'place-card');
    // 실제 장소에만 「+ 코스에 담기」(좌표가 있어야 출발 기준이 된다). 담기·빼기 토글, 바구니 도크에서 코스를 짠다(Basket).
    const add=button(Basket.has(place.id)?'담음 ✓ (빼기)':'+ 코스에 담기',()=>Basket.toggle(place,this.conditions().region),(Basket.has(place.id)?'secondary':'primary')+' include-place basket-add');add.dataset.placeId=place.id;add.setAttribute('aria-pressed',String(Basket.has(place.id)));
    const include=!place.demo&&Number.isFinite(Number(place.lat))&&Number.isFinite(Number(place.lon))?[add]:[];
    card.append(placePhotoPanel(place,mode),node('span',place.demo?'가상 장소':place.category,'tag'),node('h3',place.name),node('p',place.address||'주소는 상세에서 확인해 주세요.','hint'),...(isPublicDataPlace(place)?[publicDataSource(place)]:[]),...include,button('장소 자세히 보기',()=>showPlace(place.id,mode),'secondary'));
    return card;
  },
  controls(){let controls=document.getElementById('explore-controls');if(!controls){controls=node('div',undefined,'explore-controls');controls.id='explore-controls';document.getElementById('catalog').after(controls);}return controls;},
  naverBox(){let box=document.getElementById('explore-naver');if(!box){box=node('div',undefined,'explore-naver');box.id='explore-naver';this.controls().after(box);}return box;},
  // 둘러보기 시·도는 직접 고르기 전까지 코스 폼에서 고른 시·도를 따른다.
  syncRegion(){if(this.regionTouched)return;const select=document.getElementById('explore-region'),value=document.getElementById('conditions')?.elements.region?.value;select.value=[...select.options].some(o=>o.value===value)?value:'서울';},
  conditions(){this.syncRegion();return {region:document.getElementById('explore-region').value,activity:document.getElementById('explore-activity').value,q:document.getElementById('search').value.trim()};},
  async search(){
    const seq=++this.sequence;this.offset=0;
    const root=document.getElementById('catalog');root.replaceChildren(node('p','장소를 찾고 있어요.'));this.controls().replaceChildren();this.naverBox().replaceChildren();document.getElementById('search-info').textContent='';
    await this.page(this.conditions(),seq,false);
  },
  error(error,seq){if(seq!==this.sequence)return;document.getElementById('catalog').replaceChildren(node('p',error.message,'hint'),button('다시 불러오기',()=>this.search()));},
  async page(c,seq,more){
    try{
      const params=new URLSearchParams({region:c.region,activity:c.activity,q:c.q,offset:more?this.offset:0,limit:24});
      const data=await api('/explore?'+params);if(seq!==this.sequence)return;
      const root=document.getElementById('catalog'),controls=this.controls(),cards=data.places.map(p=>this.card(p,'real'));
      if(more)root.append(...cards);else root.replaceChildren(...cards);
      this.offset=more?this.offset+data.places.length:data.places.length;
      document.getElementById('search-info').textContent=`${data.region||c.region} · ${data.activity||'전체'} · 공공 자료 ${data.total}곳 · 현재 ${this.offset}곳 표시`;
      controls.replaceChildren();
      if(data.places.length){
        controls.append(node('p',data.ranking_method,'hint explore-ranking'));
        // 공공 자료라 '확인 필요'가 많은 까닭을 한 줄로 밝힌다.
        if(data.data_note)controls.append(node('p',data.data_note,'hint explore-data-note'));
      }
      if(data.center_hint)controls.append(node('p',data.center_hint,'hint explore-center-hint'));
      if(data.message&&data.places.length)controls.append(node('p',data.message,'hint'));
      if(!data.places.length)root.append(node('p',data.message||'조건에 맞는 장소를 찾지 못했어요. 다른 활동이나 검색어로 찾아보세요.','hint'));
      if(data.has_more)controls.append(button('장소 더 보기 · '+this.offset+' / '+data.total,async()=>{const btn=controls.querySelector('button');if(btn)btn.disabled=true;await this.page(c,seq,true);},'primary'));
      // '더 보기'로 붙인 장소: 누른 단추는 위에서 지워져 포커스가 BODY 로 빠진다. 새로 붙은 첫 장소의 제목으로 옮겨
      // 키보드·화면 읽기 사용자가 이어서 읽게 한다(2026-11-25 운영 QA-05). 제목은 Tab 순서에는 넣지 않는다(tabindex=-1).
      if(more&&cards.length){const title=cards[0].querySelector('h3');if(title){title.tabIndex=-1;title.focus();}}
      if(!more)this.naverMore(c,seq,data);
    }catch(e){this.error(e,seq);}
  },
  // 블록 항목 하나: 네이버가 준 값만(이름·분류·주소·설명·전화·홈페이지)과 그 항목의 원본(네이버 지도) 링크.
  naverItem(item){
    const row=node('li',undefined,'naver-local-item');
    row.append(node('strong',item.title||'(이름 없음)','naver-local-title'));
    if(item.category)row.append(node('span',item.category,'naver-local-category'));
    const address=item.road_address||item.address;
    if(address)row.append(node('p',address,'naver-local-address'));
    if(item.description)row.append(node('p',item.description,'naver-local-description'));
    if(item.telephone)row.append(node('p',item.telephone,'naver-local-phone'));
    const links=node('p',undefined,'naver-local-links');
    links.append(link('네이버 지도에서 보기 ↗',item.map_url));
    if(item.link)links.append(document.createTextNode(' · '),link('홈페이지 ↗',item.link));
    row.append(links);
    return row;
  },
  naverBlock(found){
    const block=naverResultBlock('지역 검색',found.search_url,{heading:node('h4',`‘${found.query}’ 검색 결과 ${found.items.length}건`,'naver-result-title')});
    // 결과가 있는 검색어만 블록으로 그린다(아래 naverMore). 예전 '이 검색어의 결과가 없어요.'를 블록 본문에 넣던 것은 우리 글을 블록 안에 넣는 것이라 뺐다
    // (네이버 답 2026-11-24 첫 문의 2-1: 앞·뒤·중간 삽입 불가). 결과 없는 검색어는 그리지 않는다.
    const list=node('ol',undefined,'naver-local-list');list.append(...found.items.map(item=>this.naverItem(item)));block.body.append(list);
    return block;
  },
  // '네이버에서 더 찾기': 접어 두고, 펼쳤을 때 한 번만 부른다. 우리 안내 문장은 블록 밖(위)에 둔다.
  naverMore(c,seq,data){
    const box=this.naverBox();box.replaceChildren();
    if(!data.naver_more)return;
    const details=node('details',undefined,'explore-naver-more'),content=node('div',undefined,'explore-naver-content');
    // 펼친 칸 안에는 네이버 블록만 둔다. 예전 블록 앞 안내('…네이버가 준 순서 그대로 보여 드려요. 위 목록과 합치거나…')는 앞 삽입이라 뺐다(네이버 답 2-2, 2026-11-26).
    details.append(node('summary','네이버에서 더 찾기'),content);
    let loaded=false;
    const load=async()=>{
      loaded=true;content.setAttribute('aria-busy','true');content.replaceChildren(node('p','네이버 검색 결과를 불러오고 있어요…','hint'));
      try{
        const found=await api('/explore/naver?'+new URLSearchParams({region:c.region,activity:c.activity,q:c.q}));if(seq!==this.sequence)return;
        content.replaceChildren();
        const withItems=(found.blocks||[]).filter(block=>block.items?.length);
        // 결과가 하나도 없으면 우리 안내만(블록 없음). 있으면 블록만 — 빈 검색어는 알리지 않고 건너뛴다(블록 바로 뒤에 우리 글을 두지 않으려고).
        if(!withItems.length){content.append(node('p',found.message||'네이버 지역 검색 결과가 없어요.','hint'));return;}
        for(const block of withItems)content.append(this.naverBlock(block));
      }catch(error){loaded=false;content.replaceChildren(node('p',error.message||'네이버 검색 결과를 불러오지 못했어요.','hint'),button('다시 불러오기',load,'secondary'));}
      finally{content.setAttribute('aria-busy','false');}
    };
    details.addEventListener('toggle',()=>{if(details.open&&!loaded)load();});
    box.append(details);
  }
};
document.getElementById('explore-region').addEventListener('change',()=>{ExploreView.regionTouched=true;ExploreView.search();});
document.getElementById('explore-activity').addEventListener('change',()=>ExploreView.search());
document.getElementById('conditions').addEventListener('change',e=>{if(e.target.name==='region')ExploreView.regionTouched=false;});
