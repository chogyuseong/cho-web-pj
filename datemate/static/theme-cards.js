// 홈 테마 카드·조건 화면의 지역 칩·현재 위치가 함께 쓰는 지역 채우기. 분위기·분류 설정은 건드리지 않는다.
// 출발지 이름이 시·도 이름으로 시작해야 서버의 지역 일치 검증을 통과한다.
function applyArea(region,origin){
  if(form.elements.mode.value!=='real'){form.elements.mode.value='real';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));}
  // 지역 change 이벤트를 보내지 않는다. 보내면 방금 넣은 출발지가 지워진다.
  form.elements.region.value=region;
  locationState.origin={name:origin.name,lat:Number(origin.lat),lon:Number(origin.lon)};form.elements.origin_name.value=origin.name;
  // 네이버 검색에서 온 출발지는 받은 시각·검색 종류를 그대로 들고 간다(form-state.js NaverDeviceRetention, 기기 보관 24시간).
  if(NaverDeviceRetention.isNaver(origin))Object.assign(locationState.origin,{naver_at:Number(origin.naver_at),naver_query:String(origin.naver_query||'local')});
}
function applyPresetArea(card){
  applyArea(card.dataset.state,{name:card.dataset.origin,lat:card.dataset.lat,lon:card.dataset.lon});
}
(()=>{
  // 테마 카드의 시·도와 출발지를 조건 폼에 넣는다. 출발지 이름이 시·도 이름으로 시작해 서버의 지역 일치 검증을 통과한다.
  function applyCard(card){
    if(!document.querySelector('[name=themes]')){toast('장소 정보를 준비 중이에요. 잠시 후 다시 눌러 주세요.');return false;}
    const mood=card.dataset.mood||'편안한 데이트';
    applyPresetArea(card);
    setDateClassification(['사교적인','활동적인'].includes(mood)?'타입별':'콘셉트별',mood);
    return true;
  }
  // 카드를 누르면 채운 조건을 폼 맨 위에 태그로 보여 주고, '이 조건으로 바로 추천받기'에 포커스를 둔다(2026-11-24 UX P0).
  // 기본 조건(날짜·시간·예산)은 바로 아래 요약 한 줄에 보이므로, 확인만 하고 이 단추를 누르면 된다 — 카드 → 추천까지 두 번.
  // 다른 지역을 고르면 태그는 맞지 않으니 지운다(syncPresetTags).
  let presetCard=null;
  function presetTags(card){
    let box=document.getElementById('preset-tags');
    if(!box){box=node('div',undefined,'preset-tags');box.id='preset-tags';box.setAttribute('role','group');box.setAttribute('aria-label','고른 테마로 채운 조건');form.prepend(box);}
    const mood=card.querySelector('.curation-mood')?.textContent||card.dataset.mood;
    const tags=node('div',undefined,'preset-tag-list');
    for(const text of [mood,card.dataset.preset,card.dataset.mood])if(text)tags.append(node('span',text,'tag'));
    const go=button('이 조건으로 바로 추천받기',()=>form.requestSubmit(),'primary preset-go');
    box.replaceChildren(node('p','고른 테마로 채웠어요. 날짜·시간·예산은 아래 기본 조건에서 확인해 주세요.','hint'),tags,go);
    box.hidden=false;
    return go;
  }
  function syncPresetTags(){
    const box=document.getElementById('preset-tags');
    if(!box||box.hidden||!presetCard)return;
    if(locationState.origin?.name!==presetCard.dataset.origin){box.hidden=true;presetCard=null;}
  }
  document.addEventListener('click',()=>setTimeout(syncPresetTags));
  document.querySelectorAll('[data-preset]').forEach(card=>card.onclick=()=>{
    if(!applyCard(card))return;
    const region=card.dataset.preset;
    document.getElementById('nav-plan').click();
    presetCard=card;
    const go=presetTags(card);
    document.querySelector('#parse-notice').textContent=region+' 지역과 데이트 분위기를 입력했어요. 날짜·시간·예산을 확인하고 추천받아 주세요.';
    toast(region+'에서 시작하는 테마를 골랐어요.');
    requestAnimationFrame(()=>{go.focus({preventScroll:true});go.scrollIntoView({block:'center',behavior:'instant'});});
  });
})();
