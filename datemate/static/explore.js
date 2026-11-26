/* 장소 둘러보기(app/explore.py).
   기본 목록: 공공 자료(한국관광공사 관광정보·소상공인 상가정보)를 우리 기준으로 정리한 카드. 사진·상세·코스에 쓰는 것은 이 목록뿐이다.
   그 아래 '네이버에서 더 찾기': 펼쳤을 때만 불러, 검색어 하나당 네이버 지역 검색 결과를 받은 순서 그대로 한 블록씩 보여 준다
   (naver-attribution.js naverResultBlock). 블록 항목은 합치거나 거르지 않고, 우리 카드·사진·장소 상세와 잇지 않는다. */
// 둘러보기에서 「이 장소 포함해서 코스 짜기」로 고른 장소 {id,name,origin}(2026-11-24 UX P2). app.js values() 가 추천 요청의
// 고정 자리(locked)에 넣는다. 다른 지역을 고르거나 '이 장소 빼기'를 누르면 비운다. 화면 태그는 테마 카드와 같은 자리(#preset-tags)를 쓴다.
let includedPlace=null;
function includePlace(place,region){
  // 출발 기준을 그 장소 위치로 둔다(서버의 지역 일치 검증: 출발지 이름은 시·도로 시작). 그래야 그 장소가 동선 범위 안에 든다.
  const origin={name:`${region} ${place.name} 주변`,lat:place.lat,lon:place.lon};
  applyArea(region,origin);
  includedPlace={id:place.id,name:place.name,origin:origin.name};
  document.getElementById('nav-plan').click();
  let box=document.getElementById('preset-tags');
  if(!box){box=node('div',undefined,'preset-tags');box.id='preset-tags';box.setAttribute('role','group');form.prepend(box);}
  box.setAttribute('aria-label','포함할 장소');
  const tags=node('div',undefined,'preset-tag-list');tags.append(node('span','포함할 장소','tag'),node('strong',place.name));
  const go=button('이 조건으로 바로 추천받기',()=>form.requestSubmit(),'primary preset-go');
  const drop=button('이 장소 빼기',()=>{includedPlace=null;box.hidden=true;},'secondary');
  box.replaceChildren(node('p','이 장소를 꼭 넣고, 그 주변에서 나머지 장소를 찾아요. 날짜·시간·예산은 아래 기본 조건에서 확인해 주세요.','hint'),tags,go,drop);
  box.hidden=false;
  toast(place.name+'을(를) 넣어 코스를 짜요.');
  requestAnimationFrame(()=>{go.focus({preventScroll:true});go.scrollIntoView({block:'center',behavior:'instant'});});
}
// 출발지를 다른 곳으로 바꾸면 포함할 장소도 비운다(그 장소가 동선 범위를 벗어날 수 있다).
document.addEventListener('click',()=>setTimeout(()=>{
  if(!includedPlace||locationState.origin?.name===includedPlace.origin)return;
  includedPlace=null;const box=document.getElementById('preset-tags');if(box&&box.getAttribute('aria-label')==='포함할 장소')box.hidden=true;
}));
const ExploreView={
  sequence:0,offset:0,regionTouched:false,
  card(place,mode){
    const card=node('article',undefined,'place-card');
    // 실제 장소에만 「이 장소 포함해서 코스 짜기」(좌표가 있어야 출발 기준이 된다).
    const include=!place.demo&&Number.isFinite(Number(place.lat))&&Number.isFinite(Number(place.lon))?[button('이 장소 포함해서 코스 짜기',()=>includePlace(place,this.conditions().region),'primary include-place')]:[];
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
