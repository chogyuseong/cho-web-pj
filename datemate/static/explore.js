const ExploreView={
  sequence:0,timer:null,offset:0,signature:'',
  card(place,mode){
    const card=node('article',undefined,'place-card');
    card.append(placePhotoPanel(place,mode),node('span',place.demo?'가상 장소':place.category,'tag'),node('h3',place.name),node('p',place.address||'주소는 상세에서 확인해 주세요.','hint'),button('장소 자세히 보기',()=>showPlace(place.id,mode),'secondary'));
    return card;
  },
  controls(){let controls=document.getElementById('explore-controls');if(!controls){controls=node('div',undefined,'explore-controls');controls.id='explore-controls';document.getElementById('catalog').after(controls);}return controls;},
  async search(){
    const seq=++this.sequence;clearTimeout(this.timer);this.offset=0;this.signature='';
    const root=document.getElementById('catalog');root.replaceChildren(node('p','장소를 불러오고 있어요.'));this.controls().replaceChildren();
    const q=document.getElementById('search').value.trim();
    await this.page(q,seq,false);
  },
  error(error,seq){if(seq!==this.sequence)return;document.getElementById('catalog').replaceChildren(node('p',error.message,'hint'),button('다시 불러오기',()=>this.search()));},
  async page(q,seq,more){
    try{
      const data=await api('/explore?q='+encodeURIComponent(q)+'&offset='+(more?this.offset:0)+'&limit=24');if(seq!==this.sequence)return;
      const root=document.getElementById('catalog'),controls=this.controls(),collecting=data.status==='collecting';
      const signature=data.places.map(p=>p.id).join('|');
      if(more)root.append(...data.places.map(p=>this.card(p,'real')));
      else if(signature!==this.signature||!data.places.length){root.replaceChildren(...data.places.map(p=>this.card(p,'real')));this.signature=signature;}
      this.offset=more?this.offset+data.places.length:data.places.length;
      document.getElementById('search-info').textContent=collecting?`서울 장소 수집 중 · 중복 제거 ${data.collected} / 500곳 · 검색 ${data.queries_done||0} / ${data.queries_max||209}회 완료`:`검색 결과 ${data.total}곳 · 전체 ${data.collected} / 최대 500곳 · 현재 ${this.offset}곳 표시`;
      controls.replaceChildren(node('p',data.ranking_method||data.message||'네이버 지역·활동별 검색 결과입니다.','hint'));
      if(!collecting&&data.message)controls.append(node('p',data.message,'hint'));
      if(!data.places.length)root.append(node('p',collecting?'실제 서울 장소를 수집하고 있어요. 잠시 기다려 주세요.':data.message||'해당 검색어에 맞는 장소가 없어요. 다른 지역·활동으로 찾아보세요.','hint'));
      if(data.has_more&&!collecting)controls.append(button('장소 더 보기 · '+this.offset+' / '+data.total,async()=>{const btn=controls.querySelector('button');if(btn)btn.disabled=true;await this.page(q,seq,true);},'primary'));
      const refresh=button(collecting?'서울 장소 수집 중…':'500곳 목록 새로 수집',async()=>{await api('/explore/refresh',{});await this.search();},'secondary');refresh.disabled=collecting;controls.append(refresh);
      if(collecting)this.timer=setTimeout(()=>{if(seq===this.sequence&&!document.getElementById('explore-section').hidden)this.page(q,seq,false);},2000);
    }catch(e){this.error(e,seq);}
  }
};
