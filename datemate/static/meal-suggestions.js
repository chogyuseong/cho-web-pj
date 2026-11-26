function operatingFactsNotice(place){
  if(!place.operations_source)return document.createDocumentFragment();
  const box=node('p',undefined,'verified-facts');
  box.append(link('공식 운영 안내 · 확인 '+place.operations_checked_at,place.operations_source),node('span',' — '+place.operations_scope));
  return box;
}

const mealRescueRequests=new Map();
const restaurantMenuRequests=new Map();
function menuImage(imageUrl,name){
  const a=link('',imageUrl),img=node('img');img.src=imageUrl;img.alt=name+' 메뉴판 원문';img.loading='lazy';img.referrerPolicy='no-referrer';
  img.onerror=()=>img.replaceWith(node('span','메뉴판 이미지를 표시하지 못했어요. 눌러 원문을 확인해 주세요.','hint'));a.append(img);return a;
}
function showMenuImages(food,data){
  const root=openDialog(food.name+' 메뉴판');root.append(node('p','매장이 공개한 메뉴판 이미지예요. 숫자 자동 추출 없이 원문 그대로 표시합니다.','hint'));
  const gallery=node('div',undefined,'menu-image-gallery');for(const url of data.menu_images||[])gallery.append(menuImage(url,food.name));root.append(gallery);
  if(data.source_url)root.append(link((data.source_label||'메뉴')+' 원문 ↗',data.source_url));
}
function hasPlaceMenu(place){
  return Boolean(place.meal||place.cuisine||/카페|미식|식당|음식점|베이커리/.test(place.category||'')||(place.tags||[]).some(tag=>['cafe','restaurant','bakery'].includes(tag)));
}
// 관광공사 대표 메뉴(first)·취급 메뉴(treat) 글을 메뉴 이름 목록으로 나눈다. 예: '에비에비가츠동 / 대창 소고기 카레 누들 / 모듬 카레 누들 등'
// → 이름 3개. 나누는 기호: , / · ・ 줄바꿈. 끝의 '등'·'외'는 뗀다. 같은 이름은 한 번만(대표 메뉴에 있으면 main:true).
// 글은 고치지 않고 나누기만 한다 — 이름 안의 띄어쓰기·표기는 그대로. 기호 없이 한 문장으로 쓴 곳은 그 문장이 칩 하나가 된다.
const TOUR_MENU_CHIPS=6; // 칩 최대 개수. 넘으면 '외 n개'. 바꾸면 tests/test_public_text_lines_ui.py 도 함께.
function tourMenuNames(tour){
  if(!tour)return [];
  const split=text=>String(text||'').split(/\s*[,/·・\n]\s*/).map(s=>s.replace(/\s*(등|외)\s*$/,'').trim()).filter(Boolean);
  const out=[],seen=new Set();
  for(const [text,main] of [[tour.first,true],[tour.treat,false]])for(const name of split(text)){const key=name.replace(/\s+/g,'');if(seen.has(key))continue;seen.add(key);out.push({name,main});}
  return out;
}
// 서울시 착한가격업소 메뉴·가격(서버 source_kind 'seoul_good_price', app/good_price.py — 2026-11-26). 이름·가격은 받은 글 그대로.
// 출처 한 줄('착한가격업소 · 서울시 제공 · 날짜 확인')과 지도 링크를 둔다. 다시 조회해도 하루 한 번 받는 자료라 '새로 조회' 단추는 없다.
const GOOD_PRICE_ROWS=6; // 보여 줄 메뉴 줄 수. 넘으면 '외 n개'. 바꾸면 tests/test_good_price.py 도 함께.
function goodPriceMenu(box,data,food){
  box.replaceChildren(node('strong','메뉴·가격','menu-heading'));
  for(const item of data.items.slice(0,GOOD_PRICE_ROWS)){const row=node('div',undefined,'menu-price-row');row.append(node('span',item.name),node('b',item.display_price));box.append(row);}
  if(data.items.length>GOOD_PRICE_ROWS)box.append(node('small','외 '+(data.items.length-GOOD_PRICE_ROWS)+'개 메뉴','menu-checked'));
  const source=node('p',undefined,'menu-checked good-price-source');
  source.append(document.createTextNode((data.source_label||'착한가격업소 · 서울시 제공')+(data.good_price?.fetched_on?' · '+data.good_price.fetched_on+' 확인':'')+' '));
  if(data.source_url)source.append(link('출처 ↗',data.source_url));
  box.append(source,node('small',data.note||'지금 매장 가격과 다를 수 있어요.','menu-checked'));
  const mapLink=link('네이버 지도에서 메뉴보기 ↗',data.search_url||placeMapUrl(food));mapLink.classList.add('menu-map-link');box.append(mapLink);
}
function restaurantMenuPanel(food){
  const box=node('div',undefined,'restaurant-menu');box.setAttribute('aria-label',food.name+' 메뉴 가격');box.append(node('p','메뉴 가격을 확인하고 있어요…','hint loading-note'));
  async function load(refresh=false){
    box.replaceChildren(node('p','메뉴 가격을 확인하고 있어요…','hint loading-note'));
    try{
      if(refresh)restaurantMenuRequests.delete(food.id);
      if(!restaurantMenuRequests.has(food.id))restaurantMenuRequests.set(food.id,api('/places/'+encodeURIComponent(food.id)+'/menu?mode=real'+(refresh?'&refresh=true':'')).catch(e=>{restaurantMenuRequests.delete(food.id);throw e;}));
      const data=await restaurantMenuRequests.get(food.id);
      if(data.source_kind==='seoul_good_price'&&data.items?.length){goodPriceMenu(box,data,food);return;}
      // 관광공사 메뉴 이름만 있고 가격 자료가 없으면 제목에서 '가격'을 뺀다(2026-11-26: '대표 메뉴·가격' 아래 가격이 없어 오류처럼 보였다).
      const tourOnly=!data.items?.length&&!data.menu_images?.length&&tourMenuNames(data.tour_menu).length>0;
      box.replaceChildren(node('strong',data.status==='image_only'?'매장 메뉴판·가격':tourOnly?'대표 메뉴':'대표 메뉴·가격','menu-heading'));
      if(data.items?.length){
        for(const item of data.items.slice(0,4)){const row=node('div',undefined,'menu-price-row');row.append(node('span',item.name),node('b',item.display_price));box.append(row);}
        if(data.source_url)box.append(link((data.source_label||'메뉴')+' 원문 ↗',data.source_url));
        box.append(node('small','조회 '+(data.checked_at?.slice(0,10)||'시점 미확인')+(data.menu_updated_at?' · 메뉴 자료 '+data.menu_updated_at:''),'menu-checked'),node('small',data.note||'현재 가격은 원문과 확인해 주세요.','menu-checked'));
      }
      if(data.menu_images?.length){
        box.append(node('p',data.message,'hint'));const preview=node('div',undefined,'menu-image-preview');for(const url of data.menu_images.slice(0,2))preview.append(menuImage(url,food.name));box.append(preview,button('메뉴판 크게 보기 · '+data.menu_images.length+'장',()=>showMenuImages(food,data),'secondary'),node('small',data.note,'menu-checked'));
      }else if(!data.items?.length){
        // 관광공사 음식점 안내의 대표·취급 메뉴(서버 tour_menu, app/tour_places.tour_menu — 2026-11-24). 글 그대로, 가격 없음.
        // 있으면 '모아 두지 않았어요' 문구 대신 이 한 줄과 출처를 먼저 보여 주고, 지도 링크는 그대로 둔다(지금 메뉴·가격은 지도에서).
        // 2026-11-26 사용자 지적(아이폰 캡처, 성수 '탐광'): 한 줄 글 + '(가격·지금 메뉴는 지도에서 확인해 주세요)'가 '메뉴를 못 받아온 오류'처럼 보였다.
        // → 메뉴 이름을 칩으로 나누고(대표 메뉴는 '대표' 표시), 가격은 네이버 지도 메뉴 탭에 있다는 안내를 따로 적고, 지도 링크는 단추 모양(.menu-map-link).
        // 가격을 못 싣는 까닭: 네이버 지도 메뉴는 공개 API 가 없고 화면을 읽을 수 없으며(약관), 블로그 요약에서 가격 읽기는 검색 API 특약 1.2·1.3 으로 뺐다(60차).
        //   네이버에 메뉴 표시를 문의 중 — datemate/docs/naver-terms-inquiry-draft-2026-11-20.ko.md '네 번째 문의 초안'. 답이 오면 이 칸을 바꾼다.
        const tour=data.tour_menu,names=tourMenuNames(tour);
        if(names.length){
          const chips=node('ul',undefined,'tour-menu-chips');chips.setAttribute('aria-label','한국관광공사 안내의 메뉴');
          for(const item of names.slice(0,TOUR_MENU_CHIPS)){const li=node('li',undefined,'tour-menu-chip');if(item.main)li.append(node('span','대표','tour-menu-main'));li.append(document.createTextNode(item.name));chips.append(li);}
          if(names.length>TOUR_MENU_CHIPS)chips.append(node('li','외 '+(names.length-TOUR_MENU_CHIPS)+'개','tour-menu-chip tour-menu-more'));
          const note=node('p',undefined,'menu-checked tour-menu-note');
          note.append(document.createTextNode('가격은 네이버 지도 메뉴 탭에서 볼 수 있어요. 메뉴 이름은 한국관광공사 안내 기준이라 지금과 다를 수 있어요. '));
          if(tour.source_url)note.append(link('출처 ↗',tour.source_url));
          box.append(chips,note);
        }else box.append(node('p',data.message||'공개 메뉴 자료가 없습니다.','hint'));
        const mapLink=link('네이버 지도에서 메뉴보기 ↗',data.source_url||placeMapUrl(food));mapLink.classList.add('menu-map-link');box.append(mapLink);
      }
      // 모아 둔 메뉴 자료가 없는 식당(서버 reason not_collected)은 다시 조회해도 달라지지 않아 단추를 두지 않는다.
      if(data.reason!=='not_collected')box.append(button('메뉴 새로 조회',()=>load(true),'secondary menu-refresh'));
    }catch(error){box.replaceChildren(node('p','메뉴 조회를 완료하지 못했어요. '+error.message,'hint'),button('메뉴 다시 확인',()=>load(true)));}
  }
  if('IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){observer.disconnect();load();}},{rootMargin:'100px'});observer.observe(box);}else load();
  return box;
}

function restaurantCard(food,{badge='',near='',plan=null,index=0}={}){
  const card=node('article',undefined,'meal-card meal-card-with-photo'),info=node('div',undefined,'meal-info');
  if(badge)info.append(node('span',badge,'tag'));
  info.append(node('h5',food.name),node('span',food.cuisine||food.category||'음식점','tag'),node('p',food.address||'주소는 지도에서 확인해 주세요.','hint'));
  info.append(restaurantMenuPanel(food));
  if(food.hours_text)info.append(node('p',food.hours_text,'small'));
  if(near)info.append(node('p',near,'hint'));
  if(food.extra_distance_km!=null)info.append(node('p','직선 기준 추가 이동 약 '+food.extra_distance_km+'km','hint'));
  // 공공 자료(한국관광공사·소상공인 상가정보)에서 찾은 식당은 출처 한 줄, 우리 식당 자료는 근거 링크(app/restaurants.py).
  if(isPublicDataPlace(food))info.append(publicDataSource(food));
  else if(food.recognition&&food.source)info.append(link(food.recognition+' ↗',food.source));
  const photo=node('div',undefined,'meal-photo');photo.append(placePhotoPanel(food,'real'));
  // '사진·장소 정보'는 앱 안 창이 바로 뜨지만 이 링크는 네이버 지도로 나간다 — 어디로 가서 무엇을 보는지 이름에 적는다(2026-11-24 사용자 요청).
  // 같은 문구: 아래 메뉴 칸의 링크, maps.js 식당 정보창. ↗ 는 새 창으로 나간다는 앱 공통 표시.
  const actions=node('div',undefined,'actions meal-actions');actions.append(button('사진·장소 정보',()=>showPlace(food.id,'real'),'secondary'),placeMapLink('네이버 지도에서 메뉴보기 ↗',food));
  if(plan&&plan.can_edit!==false)actions.append(button('이 식당을 일정에 넣기',()=>showMealChange(food,plan,index),'primary'));card.append(info,photo,actions,placeBlogPanel(food,'real'));return card;
}
function mealRescuePanel(plan){
  // 보관 기간(21일)이 지나 좌표를 지운 장소가 있는 코스는 주변 식당을 찾지 않는다(서버 409, naver-attribution.js planHistoryExpired).
  if(planHistoryExpired(plan))return document.createDocumentFragment();
  const panel=node('section',undefined,'meal-rescue');panel.append(node('h4','대신 들르기 좋은 코스 주변 식당'),node('p','공공 자료에서 주변 음식점을 찾고 있어요…','hint'));
  if(!mealRescueRequests.has(plan.id))mealRescueRequests.set(plan.id,api('/plans/'+encodeURIComponent(plan.id)+'/meal-rescue').catch(e=>{mealRescueRequests.delete(plan.id);throw e;}));
  mealRescueRequests.get(plan.id).then(data=>{
    panel.replaceChildren(node('h4','대신 들르기 좋은 코스 주변 식당'),node('p',data.ranking_basis||data.message||'추가 식사 후보가 없습니다.','hint'));
    for(const [i,food] of data.restaurants.entries()){
      panel.append(restaurantCard(food,{badge:'주변 식당 '+(i+1),near:food.near_place+' 인근',plan,index:food.after_index||0}));
    }
    if(!data.restaurants.length&&data.message)panel.append(node('p',data.message,'hint'));
    if(data.note)panel.append(node('p',data.note,'hint'));
  }).catch(()=>{panel.replaceChildren(node('h4','코스 주변 식당'),node('p','주변 식당 조회에 실패했어요.','hint'),button('다시 찾기',()=>panel.replaceWith(mealRescuePanel(plan))));});
  return panel;
}
function estimatedPlanNotice(){return node('p','이동 시간은 추정값이에요. 장소별 운영시간·입장료의 확인 여부는 조건 확인과 비용표에서 볼 수 있어요. 길찾기로 실제 이동을 확인해 주세요.','hint');}
const restaurantMatchRequests=new Map();
function fetchRestaurantMatches(plan){
  if(planHistoryExpired(plan))return Promise.resolve({groups:[]});
  if(!restaurantMatchRequests.has(plan.id))restaurantMatchRequests.set(plan.id,api('/plans/'+encodeURIComponent(plan.id)+'/restaurant-matches').catch(error=>{restaurantMatchRequests.delete(plan.id);throw error;}));
  return restaurantMatchRequests.get(plan.id);
}
function mealSuggestionPanel(plan,index){
  if(plan.conditions.mode!=='real'||planHistoryExpired(plan))return document.createDocumentFragment();
  const place=plan.places[index],panel=node('section',undefined,'meal-suggestions');
  panel.append(node('h4',`${index+1}번 코스 · ${place.name} 주변 식당`),node('p','500m 안에서 먼저 찾고, 3곳 미만이면 1,000m·1,500m까지 넓혀 찾고 있어요…','hint'));
  fetchRestaurantMatches(plan).then(data=>{
    const group=data.groups.find(g=>g.after_index===index);
    panel.replaceChildren(node('h4',`${index+1}번 코스 · ${place.name} 주변 식당`));
    const list=node('div',undefined,'meal-cards');
    let previousRadius=0;
    for(const [j,food] of (group?.restaurants||[]).entries()){
      const radius=food.search_radius_m||500;
      if(radius!==previousRadius){list.append(node('h5',radius===500?'500m 안의 주변 식당':radius.toLocaleString()+'m로 범위를 넓혀 찾은 식당','restaurant-radius-heading'));previousRadius=radius;}
      list.append(restaurantCard(food,{badge:`${index+1}-${j+1} · 지도 표시`,near:place.name+'에서 직선 '+Number(food.distance_m).toLocaleString()+'m',plan,index}));
    }
    const origin=plan.conditions.origin?.name||'';
    const area=(origin&&!origin.startsWith('지도에서 선택')?origin:plan.conditions.area_center?.name||place.name)
      .replace(/\s*대표 위치.*$/,'').replace(/\s*(지역 중심|중심)$/,'').trim()||place.name;
    // 후기가 많은 곳·유명한 곳은 공공 자료로 알 수 없어 네이버 검색으로 잇는다(검색 결과를 우리가 받아 쓰지 않는 바깥 링크).
    const more=link('후기 많은 맛집은 네이버에서 찾기 ↗','https://search.naver.com/search.naver?'+new URLSearchParams({query:area+' 주변 맛집'}));
    more.className='secondary more-restaurants';
    more.title=area+' 주변 맛집 네이버 검색 · 새 탭';
    // 찾은 식당이 없으면 큰 상자 대신 한 줄 안내와 검색 링크만 둔다(2026-11-17 가독성 정리).
    if(!group?.restaurants.length){panel.classList.add('is-empty');panel.append(node('p',group?.message||'반경 1,500m 안에서 공공 자료에 실린 음식점을 찾지 못했어요.','hint'),more);return;}
    panel.append(list,more);
    if(group?.ranking_basis)panel.append(node('p',group.ranking_basis,'hint meal-ranking-basis'));
    panel.append(node('p',group?.note||'반경 500m · 직선거리 기준','hint'));
  }).catch(()=>panel.append(node('p','식당 검색에 실패했어요.','hint'),button('다시 찾기',()=>panel.replaceWith(mealSuggestionPanel(plan,index)))));
  return panel;
}
