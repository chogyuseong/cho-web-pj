/* 공개 클라이언트 ID가 설정된 경우에만 로드한다. 비밀 API 키는 사용하지 않는다. */
let naverLoader;
function loadNaverMaps(key,force=false){
  if(force){naverLoader=null;window.naverMapAuthFailed=false;}
  if(window.naverMapAuthFailed)return Promise.reject(Error('지도 인증 실패'));
  if(!force&&window.naver?.maps)return Promise.resolve();
  if(naverLoader)return naverLoader;
  naverLoader=new Promise((resolve,reject)=>{
    const script=document.createElement('script');
    script.dataset.datemateNaver='true';
    const timeout=setTimeout(()=>{script.remove();reject(Error('지도 응답 시간 초과'));},20000);
    window.navermap_authFailure=()=>{
      window.naverMapAuthFailed=true;clearTimeout(timeout);reject(Error('지도 인증 실패'));
      // 인증 실패는 SDK onload 이후에도 도착할 수 있다.
      document.querySelectorAll('.plan-map').forEach(w=>w.showMapFallback?.());
    };
    script.src='https://oapi.map.naver.com/openapi/v3/maps.js?ncpKeyId='+encodeURIComponent(key);
    script.onload=()=>{clearTimeout(timeout);window.naver?.maps?resolve():reject(Error('지도 인증 실패'));};
    script.onerror=()=>{clearTimeout(timeout);reject(Error('지도 로딩 실패'));};
    document.head.append(script);
  });
  const pending=naverLoader;
  pending.catch(()=>{if(naverLoader===pending)naverLoader=null;});
  return pending;
}

function renderPlanMapCard(){
  let rail=document.getElementById('plan-map-rail');
  if(!rail){rail=node('aside',undefined,'plan-map-rail');rail.id='plan-map-rail';rail.setAttribute('aria-label','데이트 코스 지도');document.getElementById('planner-section').append(rail);}
  rail.querySelectorAll('.plan-map').forEach(map=>map.disposeMap?.());
  rail.replaceChildren();rail.hidden=!selected;
  document.getElementById('planner-section').classList.toggle('has-plan-map',Boolean(selected));
  if(!selected)return;
  const card=node('section',undefined,'plan-map-card'),tabs=node('div',undefined,'map-option-tabs');
  tabs.setAttribute('aria-label','지도에서 볼 코스 선택');
  plans.forEach((plan,index)=>{
    const tab=button('Option'+(index+1),()=>{
      if(selected?.id===plan.id)return;
      const scrollY=window.scrollY;
      selected=plan;locks=new Set(Object.keys(plan.conditions.locked||{}).map(Number));
      api('/plans/'+plan.id+'/feedback',{kind:'selection'}).catch(()=>{});
      renderResults();renderDetail();
      requestAnimationFrame(()=>{window.scrollTo({top:scrollY,behavior:'instant'});document.querySelector('#plan-map-rail [aria-pressed="true"]')?.focus({preventScroll:true});});
    },selected.id===plan.id?'primary':'secondary');
    tab.dataset.mapOption=String(index+1);tab.setAttribute('aria-pressed',String(selected.id===plan.id));tabs.append(tab);
  });
  card.append(node('h2','우리 코스 지도'),tabs,node('p',courseTitle(selected),'map-course-title'),drawPlanMap(selected));
  const places=node('div',undefined,'map-place-list');
  selected.places.forEach((place,index)=>places.append(link((index+1)+'. '+place.name,'https://map.naver.com/p/search/'+encodeURIComponent(place.name+' '+place.region))));
  card.append(places);rail.append(card);
}

function drawPlanMap(plan){
  let activeMap=null,resizeObserver=null,disposed=false;
  const wrap=node('section',undefined,'plan-map');
  wrap.disposeMap=()=>{disposed=true;resizeObserver?.disconnect();activeMap?.remove?.();activeMap?.destroy?.();activeMap=null;};
  const canvas=node('div','네이버 지도를 불러오는 중…','naver-plan-map');
  canvas.setAttribute('aria-label','출발지와 방문 순서가 표시된 네이버 지도');
  const caption=node('p','출발 → 방문 순서 → 귀가','map-caption');
  caption.setAttribute('role','status');
  wrap.append(canvas,caption);
  wrap.showMapFallback=()=>fallback('네이버 지도 인증에 실패했습니다. Dynamic Map 권한과 등록 웹 주소를 확인해 주세요.');
  requestAnimationFrame(()=>render());
  async function render(force=false){
    if(!wrap.isConnected)return;
    resizeObserver?.disconnect();activeMap?.remove?.();activeMap?.destroy?.();activeMap=null;
    if(!statusData?.map_js_key){fallback('네이버 지도 클라이언트 ID가 설정되지 않았습니다.');return;}
    canvas.textContent='네이버 지도를 불러오는 중…';
    wrap.replaceChildren(canvas,caption);
    try{
      await loadNaverMaps(statusData.map_js_key,force);
      if(window.naverMapAuthFailed)throw Error('지도 인증 실패');
      if(!wrap.isConnected)return;
      canvas.replaceChildren();
      const points=[plan.conditions.origin,...plan.places,...(plan.conditions.return_home?[plan.conditions.home]:[])];
      const coord=p=>new naver.maps.LatLng(p.lat,p.lon);
      const map=new naver.maps.Map(canvas,{center:coord(points[0]),zoom:14,zoomControl:true,scrollWheel:false});activeMap=map;
      const bounds=new naver.maps.LatLngBounds();
      points.forEach((point,i)=>{
        const label=i===0?'출발':i>plan.places.length?'귀가':String(i);
        // 장소명은 HTML에 삽입하지 않고 텍스트·title로만 전달한다.
        const marker=new naver.maps.Marker({map,position:coord(point),title:label+' · '+point.name,
          icon:{content:'<span class="route-marker '+(i===0?'route-start':'')+'">'+label+'</span>',anchor:new naver.maps.Point(19,19)}});
        bounds.extend(coord(point));
      });
      let actual=0;
      for(let i=0;i<points.length-1;i++){
        const leg=plan.legs[i];
        const isRoad=plan.conditions.mode==='real'&&plan.conditions.transport==='car'&&leg?.status==='api'&&leg.path?.length>1;
        const path=isRoad?leg.path.map(([lon,lat])=>new naver.maps.LatLng(lat,lon)):[coord(points[i]),coord(points[i+1])];
        if(isRoad){actual++;path.forEach(p=>bounds.extend(p));}
        new naver.maps.Polyline({map,path,strokeColor:isRoad?'#294d3d':'#a16b45',strokeWeight:isRoad?5:3,
          strokeOpacity:.9,strokeStyle:isRoad?'solid':'shortdash'});
      }
      map.fitBounds(bounds,{top:45,right:45,bottom:45,left:45});
      caption.textContent=actual===points.length-1
        ?'네이버 지도 · 자동차 실제 도로 경로 (조회 시점 기준)'
        :'네이버 지도 · 점선은 방문 순서의 직선 연결이며 실제 이동 경로가 아닙니다.';
      if(plan.conditions.mode==='demo')caption.textContent+=' 가상 장소 데모입니다.';
      else if(actual)caption.textContent+=' 실선만 자동차 실제 경로입니다.';
      if(plan.conditions.mode==='real'){
        const originalCaption=caption.textContent;
        // 반경은 각 방문 장소 중심의 직선거리이며 추천 식당은 경로선에 포함하지 않는다.
        plan.places.forEach(place=>new naver.maps.Circle({map,center:coord(place),radius:500,
          strokeColor:'#8758c7',strokeOpacity:.4,strokeWeight:1,fillColor:'#8758c7',fillOpacity:.06}));
        fetchRestaurantMatches(plan).then(data=>{
          if(!wrap.isConnected||!canvas.isConnected)return;
          const locations=new Map();let count=0;
          const mapGroups=[...data.groups,...(data.popular?[{label_prefix:'맛',restaurants:data.popular.restaurants}]:[])];
          for(const group of mapGroups){for(const [j,food] of group.restaurants.entries()){
            const key=food.lat.toFixed(5)+','+food.lon.toFixed(5);
            const label=(group.label_prefix||(group.after_index+1))+'-'+(j+1);
            if(locations.has(key))locations.get(key).labels.push(label);
            else locations.set(key,{food,labels:[label]});
          }}
          for(const {food,labels} of locations.values()){
            const label=labels.join(' / ');
            const marker=new naver.maps.Marker({map,position:coord(food),title:label+' · '+food.name,
              icon:{content:'<span class="route-marker restaurant-marker">'+label+'</span>',anchor:new naver.maps.Point(19,19)}});
            const content=node('div',undefined,'restaurant-map-info');content.append(node('strong',label+' · '+food.name),node('p',food.address||''),link('네이버 지도·메뉴 ↗','https://map.naver.com/p/search/'+encodeURIComponent(placeSearchQuery(food))));
            const info=new naver.maps.InfoWindow({content});naver.maps.Event.addListener(marker,'click',()=>info.open(map,marker));
            bounds.extend(coord(food));count++;
          }
          if(count)map.fitBounds(bounds,{top:45,right:45,bottom:45,left:45});
          caption.textContent=originalCaption+' 보라색 원: 각 코스 반경 500m · 주황색 번호: 식당 '+count+'곳 (일정 미포함, 맛: 지역 추천).';
        }).catch(()=>{caption.textContent=originalCaption+' 주변 식당 표시를 불러오지 못했어요.';});
      }
    }catch(error){if(wrap.isConnected){
      const reasons={'지도 인증 실패':'네이버 지도 인증에 실패했습니다. 등록 웹 주소와 Dynamic Map 권한을 확인해 주세요.',
        '지도 응답 시간 초과':'지도 서버의 응답이 늦어 연결이 중단됐습니다.',
        '지도 로딩 실패':'네이버 지도 스크립트를 받지 못했습니다. 네트워크나 콘텐츠 차단 설정을 확인해 주세요.'};
      fallback(reasons[error.message]||'네이버 지도 화면을 표시하지 못했습니다. 다시 연결해 주세요.');
    }}
  }
  function fallback(message){
    if(disposed||!wrap.isConnected)return;
    resizeObserver?.disconnect();activeMap?.remove?.();activeMap?.destroy?.();activeMap=null;
    const notice=node('div',undefined,'map-reconnect');
    notice.setAttribute('role','status');
    notice.append(node('strong','네이버 지도 연결이 잠시 끊겼어요'),node('p',message,'hint'),
      button('지도 다시 연결',()=>render(true),'primary'));
    const schematic=node('details',undefined,'map-schematic');
    schematic.append(node('summary','방문 순서 개략도 보기 (실제 지도 아님)'),drawMap(plan));
    wrap.replaceChildren(notice,schematic);
    if(window.L){
      const mapCanvas=node('div',undefined,'naver-plan-map fallback-plan-map');mapCanvas.setAttribute('aria-label','데이트 코스 공개 지도');
      const mapCaption=node('p','공개 지도 · 점선은 방문 순서이며 실제 이동 경로가 아닙니다.','map-caption');
      wrap.prepend(mapCanvas,mapCaption);
      const points=[plan.conditions.origin,...plan.places,...(plan.conditions.return_home?[plan.conditions.home]:[])].filter(point=>Number.isFinite(point?.lat)&&Number.isFinite(point?.lon));
      if(!points.length)return;
      try{
        const map=L.map(mapCanvas,{scrollWheelZoom:false}).setView([points[0].lat,points[0].lon],14);activeMap=map;
        const layer=L.tileLayer(statusData?.map_tile_url||'https://tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:statusData?.map_tile_attribution||'© OpenStreetMap contributors',maxZoom:19}).addTo(map);
        layer.on('tileerror',()=>mapCaption.textContent='지도 배경을 불러오지 못했어요. 장소 링크와 아래 개략도를 이용해 주세요.');
        const coordinates=points.map(point=>[point.lat,point.lon]);
        points.forEach((point,i)=>{
          const title=node('span',(i===0?'출발':i>plan.places.length?'귀가':String(i))+' · '+point.name);
          L.circleMarker([point.lat,point.lon],{radius:9,color:i===0?'#c65b32':'#294d3d',fillOpacity:.85}).addTo(map).bindTooltip(title,{permanent:true,direction:'top'});
        });
        L.polyline(coordinates,{color:'#a16b45',weight:3,dashArray:'6 8'}).addTo(map);
        const fit=()=>{if(!disposed&&mapCanvas.isConnected){map.invalidateSize();map.fitBounds(L.latLngBounds(coordinates),{padding:[35,35],maxZoom:16});}};
        requestAnimationFrame(fit);
        if(window.ResizeObserver){resizeObserver=new ResizeObserver(fit);resizeObserver.observe(mapCanvas);}
      }catch{mapCanvas.replaceWith(node('p','공개 지도를 표시하지 못했어요. 아래 개략도와 장소 링크를 이용해 주세요.','hint'));}
    }
  }
  return wrap;
}
async function officialPlaceMap(container,place,key){
  try{
    await loadNaverMaps(key);
    if(!container.isConnected)return;
    const coordinates=new naver.maps.LatLng(place.lat,place.lon);
    container.replaceChildren();
    const map=new naver.maps.Map(container,{center:coordinates,zoom:15});
    new naver.maps.Marker({position:coordinates,map,title:place.name});
  }catch{
    container.textContent='네이버 지도 로딩 실패. 아래 지도 링크에서 위치를 확인해 주세요.';
  }
}
