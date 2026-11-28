/* 주소 입력과 선택 좌표를 분리해 주소만 바꾼 채 이전 좌표로 제출되는 것을 막는다. */
const locationState={origin:null,home:null};
let locationMap=null;
function mountLocationFields(){
  for(const kind of ['origin','home']){
    const host=document.getElementById(kind+'-location');
    const title=kind==='origin'?'데이트할 지역':'귀가지';
    const label=node('label',title),selectedInput=node('input');
    selectedInput.name=kind+'_name';selectedInput.readOnly=true;
    selectedInput.value=locationState[kind]?.name||'';
    selectedInput.placeholder='주소 검색 또는 지도에서 선택하세요';
    label.append(selectedInput);
    // 데이트할 지역은 조건 화면이 이 칸을 바로 검색하는 칸으로 바꾸고(simple-form.js), 이 버튼은 지도에서 고를 때 쓴다.
    host.append(label,button(kind==='origin'?'지도에서 고르기':'주소 검색 · 지도에서 선택',()=>openLocationPicker(kind),'secondary full'));
  }
}
function selectedLocation(kind){
  const point=locationState[kind];
  if(!point)throw Error(kind==='origin'?'데이트할 지역을 동네 칩·검색·지도에서 골라 주세요.':'귀가지를 주소 검색 또는 지도에서 선택해 주세요.');
  return {...point};
}
function clearLocationsForMode(){
  locationState.origin=form.elements.mode.value==='demo'?{name:'데모 출발점',lat:37.575,lon:126.985}:null;
  locationState.home=null;
  for(const kind of ['origin','home'])form.elements[kind+'_name'].value=locationState[kind]?.name||'';
}
async function openLocationPicker(kind){
  // 대화창(place-dialog.js openDialog)과 지도(maps.js)는 나중 묶음이다(later-scripts.js). 아직이면 기다리고, 받지 못했으면 알린다(다시 누르면 다시 받는다).
  try{await DatemateLater.need();}catch(error){toast(error.message);return;}
  if(locationMap){locationMap.remove();locationMap=null;}
  const title=kind==='origin'?'데이트할 지역':'귀가지';
  const root=openDialog(title+' 선택');
  $('#dialog').classList.add('location-dialog');
  const content=node('div',undefined,'location-body');
  const footer=node('div',undefined,'location-footer');
  const searchForm=node('form',undefined,'location-search');
  const label=node('label','도로명 주소 또는 지번 주소'),query=node('input');
  query.placeholder='예: 부산 해운대구 해운대로 264';query.enterKeyHint='search';query.maxLength=200;query.required=true;query.minLength=2;
  label.append(query);const searchButton=node('button','주소 검색','primary');searchForm.append(label,searchButton);
  const message=node('p',kind==='origin'?'데이트할 지역의 주소를 검색하거나 지도에서 선택하세요. 선택한 위치가 코스의 시작 기준이 됩니다.':'주소를 검색하거나 지도를 움직여 원하는 위치를 선택하세요.','hint');message.setAttribute('role','status');
  const results=node('div',undefined,'location-results');
  const canvas=node('div',undefined,'location-map');canvas.id='location-map';canvas.setAttribute('aria-label',title+' 선택 지도');
  const picked=node('p','위치를 선택하면 아래 버튼으로 확정할 수 있어요.','location-picked');picked.setAttribute('aria-live','polite');
  const confirm=button(kind==='origin'?'이 지역에서 데이트하기':'이 위치를 귀가지로 사용',()=>{
    if(!candidate||confirm.disabled)return;
    locationState[kind]={name:candidate.name,lat:candidate.lat,lon:candidate.lon};form.elements[kind+'_name'].value=candidate.name;
    // 장소 이름으로 찾은 결과(네이버 지역 검색)는 받은 시각을 들고 간다(form-state.js NaverDeviceRetention, 기기 보관 24시간).
    if(NaverDeviceRetention.isNaver(candidate))Object.assign(locationState[kind],{naver_at:candidate.naver_at,naver_query:candidate.naver_query});
    if(kind==='origin'){
      // change 이벤트를 보내지 않는다. 보내면 방금 고른 출발지가 초기화된다.
      const region=candidate.region||regionFromAddress(candidate.name);
      if(region)form.elements.region.value=region;
    }
    $('#dialog').close();toast((kind==='origin'?'데이트할 지역을':'귀가지를')+' 선택했습니다.');
  },'primary full');confirm.disabled=true;
  // 지도 선택 좌표의 시·도를 확인하지 못하면 직접 고르게 한다(서울로 조용히 남기지 않음).
  const regionBox=node('label','시·도 직접 선택','location-region'),regionSelect=node('select');
  regionSelect.name='location_region';regionSelect.append(new Option('시·도를 선택하세요',''));
  for(const region of new Set(Object.values(REGION_ALIASES)))regionSelect.append(new Option(region,region));
  regionBox.append(regionSelect);regionBox.hidden=true;
  regionSelect.onchange=()=>{
    if(!candidate||!regionSelect.value)return;
    candidate={...candidate,name:regionSelect.value+' · 지도에서 선택',region:regionSelect.value};
    picked.textContent='선택한 위치: '+candidate.name;confirm.disabled=false;
  };
  content.append(searchForm,message,results,canvas);
  footer.append(picked,regionBox,confirm);
  let candidate=null,marker=null,map=null,naverMap=null,naverMarker=null,regionCheck=0;
  const previous=locationState[kind]||locationState.origin||{lat:37.5665,lon:126.978};
  function choose(point,recenter=true){
    regionCheck++;regionBox.hidden=true;regionSelect.value='';
    candidate={name:point.name,lat:Number(point.lat),lon:Number(point.lon),region:regionFromAddress(point.name)};
    if(point.place_name)candidate=NaverDeviceRetention.mark(candidate,'local',point.received_at);
    picked.textContent='선택한 위치: '+candidate.name;confirm.disabled=false;
    if(map){if(marker)marker.setLatLng([candidate.lat,candidate.lon]);else marker=L.circleMarker([candidate.lat,candidate.lon],{radius:10,color:'#b5245e',fillColor:'#fff',fillOpacity:1,weight:3}).addTo(map);if(recenter)map.setView([candidate.lat,candidate.lon],17,{animate:false});}
    if(naverMap){const coord=new naver.maps.LatLng(candidate.lat,candidate.lon);if(naverMarker)naverMarker.setPosition(coord);else naverMarker=new naver.maps.Marker({map:naverMap,position:coord});if(recenter)naverMap.setCenter(coord);}
  }
  function pickOnMap(lat,lon){
    choose({name:'지도에서 선택한 '+title,lat,lon},false);
    // 귀가지는 시·도를 바꾸지 않는다.
    if(kind==='origin')resolveRegion(candidate);
  }
  async function resolveRegion(point){
    const token=++regionCheck,current=()=>token===regionCheck&&canvas.isConnected&&$('#dialog').open;
    confirm.disabled=true;picked.textContent='선택한 위치의 시·도를 확인하고 있어요…';
    let data=null;
    for(let attempt=0;attempt<3&&!data;attempt++){
      try{data=await api('/locations/region',{lat:point.lat,lon:point.lon});}
      catch(error){if(error.status!==429)break;await new Promise(resolve=>setTimeout(resolve,1100));}
      if(!current())return;
    }
    if(!current())return;
    if(data?.status==='ok'&&data.region){
      candidate={...point,name:(data.label||data.region)+' · 지도에서 선택',region:data.region};
      picked.textContent='선택한 위치: '+candidate.name;confirm.disabled=false;return;
    }
    candidate={...point,region:null};
    picked.textContent=data?.message||'선택한 위치의 시·도를 확인하지 못했어요. 시·도를 직접 골라 주세요.';
    regionSelect.value='';regionBox.hidden=false;
  }
  content.append(button('지도 중심을 선택',()=>{
    const center=naverMap?naverMap.getCenter():map?.getCenter();
    if(center)pickOnMap(naverMap?center.lat():center.lat,naverMap?center.lng():center.lng);
  },'secondary full'),node('p','지도 클릭·터치로 선택할 수 있습니다. 키보드로 지도를 이동한 뒤 ‘지도 중심을 선택’을 사용할 수도 있어요.','hint'));
  root.append(content,footer);
  searchForm.onsubmit=async event=>{
    event.preventDefault();searchButton.disabled=true;results.replaceChildren();message.classList.remove('visually-hidden');message.textContent='주소를 검색하고 있어요…';
    // 새 질의: 앞서 지역 검색으로 고른 출발지를 이 브라우저(지난번처럼 추천)에서 지운다(특약 1.4, form-state.js).
    LastConditions.newQuery('local');
    try{
      const data=await api('/locations/search',{query:query.value.trim()}),at=Date.now();
      if(!canvas.isConnected||!$('#dialog').open)return;
      message.textContent=data.message||'검색 결과에서 원하는 주소를 선택하세요. 도로명 주소를 우선 표시합니다.';
      // 장소 이름으로 찾은 결과(네이버 지역 검색)는 받은 순서 그대로 '네이버 검색결과' 블록 하나에 담는다(naver-attribution.js naverResultBlock).
      // 주소 검색(네이버 Maps 지오코딩) 결과는 검색 API 결과가 아니라 블록 없이 그린다.
      const local=data.results.some(found=>found.place_name);
      const block=local?naverResultBlock('지역 검색','https://map.naver.com/p/search/'+encodeURIComponent(query.value.trim()),{tag:'div',className:'location-naver-block'}):null;
      const target=block?block.body:results;
      if(block)results.append(block);
      // 네이버 블록이 있으면 블록 바로 위 우리 안내(message)는 보이지 않게(화면 읽기용으로만) 한다 — 네이버 답 2-2 앞 삽입(2026-11-26).
      message.classList.toggle('visually-hidden',Boolean(block));
      // 블록 안 항목에는 API 가 준 값만: 장소 이름·도로명 주소·지번 주소(우리 꼬리표 '지번: '은 붙이지 않는다 — 2-1 중간 삽입).
      for(const found of data.results){const point={...found,received_at:at};const option=button('',()=>choose(point),'location-result');if(point.place_name){option.append(node('strong',point.place_name));if(point.road_address)option.append(node('span',point.road_address,'location-result-address'));if(point.jibun_address&&point.jibun_address!==point.road_address)option.append(node('span',point.jibun_address,'hint'));}else{option.append(node('strong',point.road_address||point.name));if(point.jibun_address)option.append(node('span','지번: '+point.jibun_address,'hint'));}target.append(option);}
    }catch(error){message.textContent=error.message;}finally{searchButton.disabled=false;}
  };
  // 키가 있으면 네이버 지도를 우선 사용하고, 없거나 로딩 실패면 공개 지도 사용.
  if(statusData?.map_js_key){try{
    await loadNaverMaps(statusData.map_js_key);
    if(!canvas.isConnected||!$('#dialog').open)return;
    naverMap=new naver.maps.Map(canvas,{center:new naver.maps.LatLng(previous.lat,previous.lon),zoom:15});
    naver.maps.Event.addListener(naverMap,'click',event=>pickOnMap(event.coord.lat(),event.coord.lng()));
  }catch{message.textContent='네이버 지도에 연결하지 못해 OpenStreetMap 지도를 사용합니다.';}}
  // 공개 지도(Leaflet)는 여기서 처음 불러온다. 받지 못하면 지도 없이 주소 검색만 쓴다.
  if(!naverMap&&!await loadLeaflet().then(()=>true,()=>false))message.textContent='지도를 불러오지 못했어요. 주소 검색을 이용해 주세요.';
  else if(!naverMap&&canvas.isConnected&&$('#dialog').open){
    map=L.map(canvas,{scrollWheelZoom:false,zoomAnimation:false,fadeAnimation:false,markerZoomAnimation:false}).setView([previous.lat,previous.lon],15);locationMap=map;
    const credit=document.createElement('a');credit.href='https://www.openstreetmap.org/copyright';credit.target='_blank';credit.rel='noopener';credit.textContent=statusData?.map_tile_attribution||'© OpenStreetMap contributors';
    const tiles=L.tileLayer(statusData?.map_tile_url||'https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:credit.outerHTML}).addTo(map);
    tiles.on('tileerror',()=>{message.textContent='지도 이미지를 불러오지 못했습니다. 네트워크를 확인하거나 주소 검색을 이용하세요.';});
    map.on('click',event=>pickOnMap(event.latlng.lat,event.latlng.lng));
    requestAnimationFrame(()=>{if(locationMap===map&&canvas.isConnected&&$('#dialog').open)map.invalidateSize();});
  }
  if(locationState[kind])choose(locationState[kind],false);
  if(statusData&&!statusData.geocoding_available)message.textContent='주소 검색은 네이버 Maps 키 설정 후 사용할 수 있습니다. 지금은 지도에서 선택해 주세요.';
}

document.getElementById('dialog').addEventListener('close',()=>{
  document.getElementById('dialog').classList.remove('location-dialog');
  if(locationMap){locationMap.remove();locationMap=null;}
});
