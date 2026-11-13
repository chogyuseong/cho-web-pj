// 홈 테마 카드·조건 화면의 지역 칩·현재 위치가 함께 쓰는 지역 채우기. 분위기·분류 설정은 건드리지 않는다.
// 출발지 이름이 시·도 이름으로 시작해야 서버의 지역 일치 검증을 통과한다.
function applyArea(region,origin){
  if(form.elements.mode.value!=='real'){form.elements.mode.value='real';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));}
  // 지역 change 이벤트를 보내지 않는다. 보내면 방금 넣은 출발지가 지워진다.
  form.elements.region.value=region;
  locationState.origin={name:origin.name,lat:Number(origin.lat),lon:Number(origin.lon)};form.elements.origin_name.value=origin.name;
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
  document.querySelectorAll('[data-preset]').forEach(card=>card.onclick=()=>{
    if(!applyCard(card))return;
    const region=card.dataset.preset;
    document.getElementById('nav-plan').click();
    document.querySelector('#parse-notice').textContent=region+' 지역과 데이트 분위기를 입력했어요. 날짜·시간·예산을 확인하고 추천받아 주세요.';
    toast(region+'에서 시작하는 취향을 골랐어요. 조건을 확인하고 코스를 만들어 보세요.');
  });
})();
