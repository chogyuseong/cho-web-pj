const ExploreView={
  sequence:0,offset:0,regionTouched:false,
  card(place,mode){
    const card=node('article',undefined,'place-card');
    card.append(placePhotoPanel(place,mode),node('span',place.demo?'가상 장소':place.category,'tag'),node('h3',place.name),node('p',place.address||'주소는 상세에서 확인해 주세요.','hint'),button('장소 자세히 보기',()=>showPlace(place.id,mode),'secondary'));
    return card;
  },
  controls(){let controls=document.getElementById('explore-controls');if(!controls){controls=node('div',undefined,'explore-controls');controls.id='explore-controls';document.getElementById('catalog').after(controls);}return controls;},
  // 둘러보기 시·도는 직접 고르기 전까지 코스 폼에서 고른 시·도를 따른다.
  syncRegion(){if(this.regionTouched)return;const select=document.getElementById('explore-region'),value=document.getElementById('conditions')?.elements.region?.value;select.value=[...select.options].some(o=>o.value===value)?value:'서울';},
  conditions(){this.syncRegion();return {region:document.getElementById('explore-region').value,activity:document.getElementById('explore-activity').value,q:document.getElementById('search').value.trim()};},
  async search(){
    const seq=++this.sequence;this.offset=0;
    const root=document.getElementById('catalog');root.replaceChildren(node('p','장소를 찾고 있어요.'));this.controls().replaceChildren();document.getElementById('search-info').textContent='';
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
      document.getElementById('search-info').textContent=`${data.region||c.region} · ${data.activity||'전체'} · 검색 결과 ${data.total}곳 · 현재 ${this.offset}곳 표시`;
      controls.replaceChildren();
      if(data.message&&data.places.length)controls.append(node('p',data.message,'hint'));
      if(!data.places.length)root.append(node('p',data.message||'조건에 맞는 장소를 찾지 못했어요. 다른 활동이나 검색어로 찾아보세요.','hint'));
      if(data.has_more)controls.append(button('장소 더 보기 · '+this.offset+' / '+data.total,async()=>{const btn=controls.querySelector('button');if(btn)btn.disabled=true;await this.page(c,seq,true);},'primary'));
    }catch(e){this.error(e,seq);}
  }
};
document.getElementById('explore-region').addEventListener('change',()=>{ExploreView.regionTouched=true;ExploreView.search();});
document.getElementById('explore-activity').addEventListener('change',()=>ExploreView.search());
document.getElementById('conditions').addEventListener('change',e=>{if(e.target.name==='region')ExploreView.regionTouched=false;});
