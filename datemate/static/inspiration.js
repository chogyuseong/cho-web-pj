function applyInspiration(idea){
  if(!statusData){toast('장소 정보를 준비 중이에요. 잠시 후 다시 눌러 주세요.');return;}
  if(form.elements.mode.value!=='real'){form.elements.mode.value='real';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));}
  locationState.origin={...idea.origin};form.elements.origin_name.value=idea.origin.name;
  form.elements.request.value=idea.request;parsedRequest='';setDateClassification('콘셉트별','');
  if(idea.defaults){locks.clear();for(const [key,value] of Object.entries(idea.defaults)){const input=form.elements[key];if(input){if(input.type==='checkbox')input.checked=value;else input.value=value;FormState.edited.delete(key);}}}
  setTab(false);showPlannerPage(false);
  document.querySelector('#parse-notice').textContent=idea.area+' 지역과 활동을 입력했어요. 날짜·시간·예산을 확인하고 추천받아 주세요.';
  toast('장소 예시는 확정 코스가 아니에요. 입력 조건에 맞춰 새로 계산합니다.');
}
document.addEventListener('DOMContentLoaded',async()=>{
  const grid=document.querySelector('.inspiration-grid');
  async function load(){
    try{
      const data=await api('/inspirations');grid.replaceChildren();
      for(const idea of data.items){
        const card=node('article',undefined,'inspiration-card');card.append(node('span',idea.area,'tag'),node('h3',idea.title));
        const list=node('ul');idea.places.forEach(p=>{const item=node('li');item.append(node('strong',p.name),node('small',p.category));list.append(item);});
        card.append(list,node('p',idea.note,'hint'),button('이 방향으로 조건 채우기 →',()=>applyInspiration(idea),'secondary'));grid.append(card);
      }
      if(!data.items.length)grid.append(node('p','지역과 원하는 활동을 입력하면 실제 장소를 검색해 코스를 만들어요.','hint'));
    }catch{grid.replaceChildren(node('p','장소 예시를 불러오지 못했어요. 아래에서 직접 코스를 만들 수 있어요.','hint'),button('예시 다시 불러오기',load));}
  }
  await load();
  const presets={성수:{lat:37.5446,lon:127.0559,request:'전시 관람과 산책'},연남:{lat:37.562,lon:126.925,request:'카페와 산책'},종로:{lat:37.5765,lon:126.9855,request:'박물관과 산책'}};
  document.querySelectorAll('[data-preset]').forEach(b=>b.onclick=()=>{const area=b.dataset.preset,p=presets[area];if(p)applyInspiration({area,origin:{name:area+' 지역 중심',lat:p.lat,lon:p.lon},request:p.request});});
});
