/* 장소 둘러보기(app/explore.py).
   기본 목록: 공공 자료(한국관광공사 관광정보·소상공인 상가정보)를 우리 기준으로 정리한 카드. 사진·상세·코스에 쓰는 것은 이 목록뿐이다.
   그 아래 '네이버에서 더 찾기': 펼쳤을 때만 불러, 검색어 하나당 네이버 지역 검색 결과를 받은 순서 그대로 한 블록씩 보여 준다
   (naver-attribution.js naverResultBlock). 블록 항목은 합치거나 거르지 않고, 우리 카드·사진·장소 상세와 잇지 않는다. */
const ExploreView={
  sequence:0,offset:0,regionTouched:false,
  card(place,mode){
    const card=node('article',undefined,'place-card');
    card.append(placePhotoPanel(place,mode),node('span',place.demo?'가상 장소':place.category,'tag'),node('h3',place.name),node('p',place.address||'주소는 상세에서 확인해 주세요.','hint'),...(isPublicDataPlace(place)?[publicDataSource(place)]:[]),button('장소 자세히 보기',()=>showPlace(place.id,mode),'secondary'));
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
    if(found.items.length){const list=node('ol',undefined,'naver-local-list');list.append(...found.items.map(item=>this.naverItem(item)));block.body.append(list);}
    else block.body.append(node('p',found.status==='available'?'이 검색어의 결과가 없어요.':'이 검색어는 불러오지 못했어요.','hint'));
    return block;
  },
  // '네이버에서 더 찾기': 접어 두고, 펼쳤을 때 한 번만 부른다. 우리 안내 문장은 블록 밖(위)에 둔다.
  naverMore(c,seq,data){
    const box=this.naverBox();box.replaceChildren();
    if(!data.naver_more)return;
    const details=node('details',undefined,'explore-naver-more'),content=node('div',undefined,'explore-naver-content');
    details.append(node('summary','네이버에서 더 찾기'),node('p','같은 조건의 네이버 지역 검색 결과를 검색어마다 따로, 네이버가 준 순서 그대로 보여 드려요. 위 목록과 합치거나 다시 줄 세우지 않았고, 코스 추천에도 쓰지 않아요.','hint explore-naver-note'),content);
    let loaded=false;
    const load=async()=>{
      loaded=true;content.setAttribute('aria-busy','true');content.replaceChildren(node('p','네이버 검색 결과를 불러오고 있어요…','hint'));
      try{
        const found=await api('/explore/naver?'+new URLSearchParams({region:c.region,activity:c.activity,q:c.q}));if(seq!==this.sequence)return;
        content.replaceChildren();
        if(found.message)content.append(node('p',found.message,'hint'));
        for(const block of found.blocks||[])content.append(this.naverBlock(block));
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
