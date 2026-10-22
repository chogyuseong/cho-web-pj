/* 주소 입력과 선택 좌표를 분리해 주소만 바꾼 채 이전 좌표로 제출되는 것을 막는다. */
const locationState={origin:{name:'데모 출발점',lat:37.575,lon:126.985},home:null};
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
    host.append(label,button('주소 검색 · 지도에서 선택',()=>openLocationPicker(kind),'secondary full'));
  }
}
function selectedLocation(kind){
  const point=locationState[kind];
  if(!point)throw Error((kind==='origin'?'데이트할 지역을':'귀가지를')+' 주소 검색 또는 지도에서 선택해 주세요.');
  return {...point};
}
function clearLocationsForMode(){
  locationState.origin=form.elements.mode.value==='demo'?{name:'데모 출발점',lat:37.575,lon:126.985}:null;
  locationState.home=null;
  for(const kind of ['origin','home'])form.elements[kind+'_name'].value=locationState[kind]?.name||'';
}
async function openLocationPicker(kind){
  if(locationMap){locationMap.remove();locationMap=null;}
  const title=kind==='origin'?'데이트할 지역':'귀가지';
  const root=openDialog(title+' 선택');
  $('#dialog').classList.add('location-dialog');
  const content=node('div',undefined,'location-body');
  const footer=node('div',undefined,'location-footer');
  const searchForm=node('form',undefined,'location-search');
  const label=node('label','도로명 주소 또는 지번 주소'),query=node('input');
  query.placeholder='예: 서울 중구 세종대로 110 / 태평로1가 31';query.maxLength=200;query.required=true;query.minLength=2;
  label.append(query);const searchButton=node('button','주소 검색','primary');searchForm.append(label,searchButton);
  const message=node('p',kind==='origin'?'데이트할 지역의 주소를 검색하거나 지도에서 선택하세요. 선택한 위치가 코스의 시작 기준이 됩니다.':'주소를 검색하거나 지도를 움직여 원하는 위치를 선택하세요.','hint');message.setAttribute('role','status');
  const results=node('div',undefined,'location-results');
  const canvas=node('div',undefined,'location-map');canvas.id='location-map';canvas.setAttribute('aria-label',title+' 선택 지도');
  const picked=node('p','위치를 선택하면 아래 버튼으로 확정할 수 있어요.','location-picked');picked.setAttribute('aria-live','polite');
  const confirm=button(kind==='origin'?'이 지역에서 데이트하기':'이 위치를 귀가지로 사용',()=>{
    if(!candidate)return;
    locationState[kind]={...candidate};form.elements[kind+'_name'].value=candidate.name;
    $('#dialog').close();toast((kind==='origin'?'데이트할 지역을':'귀가지를')+' 선택했습니다.');
  },'primary full');confirm.disabled=true;
  content.append(searchForm,message,results,canvas);
  footer.append(picked,confirm);
  let candidate=null,marker=null,map=null,naverMap=null,naverMarker=null;
  const previous=locationState[kind]||locationState.origin||{lat:37.5665,lon:126.978};
  function choose(point,recenter=true){
    candidate={name:point.name,lat:Number(point.lat),lon:Number(point.lon)};
    picked.textContent='선택한 위치: '+candidate.name;confirm.disabled=false;
    if(map){if(marker)marker.setLatLng([candidate.lat,candidate.lon]);else marker=L.circleMarker([candidate.lat,candidate.lon],{radius:10,color:'#294d3d',fillColor:'#e4774b',fillOpacity:1,weight:3}).addTo(map);if(recenter)map.setView([candidate.lat,candidate.lon],17,{animate:false});}
    if(naverMap){const coord=new naver.maps.LatLng(candidate.lat,candidate.lon);if(naverMarker)naverMarker.setPosition(coord);else naverMarker=new naver.maps.Marker({map:naverMap,position:coord});if(recenter)naverMap.setCenter(coord);}
  }
  content.append(button('지도 중심을 선택',()=>{
    const center=naverMap?naverMap.getCenter():map?.getCenter();
    if(center)choose({name:'지도에서 선택한 '+title,lat:naverMap?center.lat():center.lat,lon:naverMap?center.lng():center.lng},false);
  },'secondary full'),node('p','지도 클릭·터치로 선택할 수 있습니다. 키보드로 지도를 이동한 뒤 ‘지도 중심을 선택’을 사용할 수도 있어요.','hint'));
  root.append(content,footer);
  searchForm.onsubmit=async event=>{
    event.preventDefault();searchButton.disabled=true;results.replaceChildren();message.textContent='주소를 검색하고 있어요…';
    try{
      const data=await api('/locations/search',{query:query.value.trim()});
      if(!canvas.isConnected||!$('#dialog').open)return;
      message.textContent=data.message||'검색 결과에서 원하는 주소를 선택하세요. 도로명 주소를 우선 표시합니다.';
      for(const point of data.results){const option=button('',()=>choose(point),'location-result');option.append(node('strong',point.road_address||point.name));if(point.jibun_address)option.append(node('span','지번: '+point.jibun_address,'hint'));results.append(option);}
    }catch(error){message.textContent=error.message;}finally{searchButton.disabled=false;}
  };
  // 키가 있으면 네이버 지도를 우선 사용하고, 없거나 로딩 실패면 공개 지도 사용.
  if(statusData?.map_js_key){try{
    await loadNaverMaps(statusData.map_js_key);
    if(!canvas.isConnected||!$('#dialog').open)return;
    naverMap=new naver.maps.Map(canvas,{center:new naver.maps.LatLng(previous.lat,previous.lon),zoom:15});
    naver.maps.Event.addListener(naverMap,'click',event=>choose({name:'지도에서 선택한 '+title,lat:event.coord.lat(),lon:event.coord.lng()},false));
  }catch{message.textContent='네이버 지도에 연결하지 못해 OpenStreetMap 지도를 사용합니다.';}}
  if(!naverMap){
    map=L.map(canvas,{scrollWheelZoom:false,zoomAnimation:false,fadeAnimation:false,markerZoomAnimation:false}).setView([previous.lat,previous.lon],15);locationMap=map;
    const credit=document.createElement('a');credit.href='https://www.openstreetmap.org/copyright';credit.target='_blank';credit.rel='noopener';credit.textContent=statusData?.map_tile_attribution||'© OpenStreetMap contributors';
    const tiles=L.tileLayer(statusData?.map_tile_url||'https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:credit.outerHTML}).addTo(map);
    tiles.on('tileerror',()=>{message.textContent='지도 이미지를 불러오지 못했습니다. 네트워크를 확인하거나 주소 검색을 이용하세요.';});
    map.on('click',event=>choose({name:'지도에서 선택한 '+title,lat:event.latlng.lat,lon:event.latlng.lng},false));
    requestAnimationFrame(()=>{if(locationMap===map&&canvas.isConnected&&$('#dialog').open)map.invalidateSize();});
  }
  if(locationState[kind])choose(locationState[kind],false);
  if(statusData&&!statusData.geocoding_available)message.textContent='주소 검색은 네이버 Maps 키 설정 후 사용할 수 있습니다. 지금은 지도에서 선택해 주세요.';
}

document.getElementById('dialog').addEventListener('close',()=>{
  document.getElementById('dialog').classList.remove('location-dialog');
  if(locationMap){locationMap.remove();locationMap=null;}
});
