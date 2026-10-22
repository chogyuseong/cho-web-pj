function operatingFactsNotice(place){
  if(!place.operations_source)return document.createDocumentFragment();
  const box=node('p',undefined,'verified-facts');
  box.append(link('공식 운영 안내 · 확인 '+place.operations_checked_at,place.operations_source),node('span',' — '+place.operations_scope));
  return box;
}

const mealRescueRequests=new Map();
function restaurantCard(food,{badge='',near=''}={}){
  const card=node('article',undefined,'meal-card meal-card-with-photo'),info=node('div',undefined,'meal-info');
  if(badge)info.append(node('span',badge,'tag'));
  info.append(node('h5',food.name),node('span',food.cuisine||food.category||'음식점','tag'),node('p',food.address||'주소는 지도에서 확인해 주세요.','hint'));
  if(food.hours_text)info.append(node('p',food.hours_text,'small'));
  if(near)info.append(node('p',near,'hint'));
  if(food.extra_distance_km!=null)info.append(node('p','직선 기준 추가 이동 약 '+food.extra_distance_km+'km','hint'));
  if(food.recognition&&food.source)info.append(link(food.recognition+' ↗',food.source));
  const photo=node('div',undefined,'meal-photo');photo.append(placePhotoPanel(food,'real'));
  const actions=node('div',undefined,'actions meal-actions');actions.append(button('사진·장소 정보',()=>showPlace(food.id,'real'),'secondary'),link('네이버 지도·메뉴 ↗','https://map.naver.com/p/search/'+encodeURIComponent(food.name+' '+(food.address||''))));
  card.append(info,photo,actions,placeBlogPanel(food,'real'));return card;
}
function mealRescuePanel(plan){
  const panel=node('section',undefined,'meal-rescue');panel.append(node('h4','대신 들르기 좋은 코스 주변 식당'),node('p','네이버 리뷰순으로 주변 음식점을 찾고 있어요…','hint'));
  if(!mealRescueRequests.has(plan.id))mealRescueRequests.set(plan.id,api('/plans/'+encodeURIComponent(plan.id)+'/meal-rescue').catch(e=>{mealRescueRequests.delete(plan.id);throw e;}));
  mealRescueRequests.get(plan.id).then(data=>{
    panel.replaceChildren(node('h4','대신 들르기 좋은 코스 주변 식당'),node('p',data.ranking_basis||data.message||'추가 식사 후보가 없습니다.','hint'));
    for(const [i,food] of data.restaurants.entries()){
      panel.append(restaurantCard(food,{badge:i===0?'우선 추천':'주변 추천 '+(i+1),near:food.near_place+' 인근'}));
    }
    if(!data.restaurants.length&&data.message)panel.append(node('p',data.message,'hint'));
    if(data.note)panel.append(node('p',data.note,'hint'));
  }).catch(()=>{panel.replaceChildren(node('h4','코스 주변 식당'),node('p','주변 식당 조회에 실패했어요.','hint'),button('다시 찾기',()=>panel.replaceWith(mealRescuePanel(plan))));});
  return panel;
}
function estimatedPlanNotice(){return node('p','이동 시간은 추정값이에요. 장소별 운영시간·입장료의 확인 여부는 조건 확인과 비용표에서 볼 수 있어요. 길찾기로 실제 이동을 확인해 주세요.','hint');}
function mealSuggestionPanel(plan,index){
  const group=plan.meal_suggestions?.find(g=>g.after_index===index);
  if(!group)return document.createDocumentFragment();
  const panel=node('section',undefined,'meal-suggestions');
  panel.append(node('h4','이 사이에 들르기 좋은 유명 밥집'),node('p',group.origin+' → '+group.destination,'hint'));
  if(!group.restaurants.length)panel.append(node('p','이 구간 가까이에 확인된 식당 정보가 아직 부족해요.','hint'),link('주변 밥집 찾기 ↗',group.search_url));
  const list=node('div',undefined,'meal-cards');
  for(const food of group.restaurants){
    list.append(restaurantCard(food));
  }
  const moreResults=node('div',undefined,'meal-more-results');
  const more=button('주변 식당 더 찾기',async()=>{
    more.disabled=true;moreResults.replaceChildren(node('p','네이버에서 주변 음식점을 찾고 있어요…','hint'));
    try{
      const data=await api('/plans/'+plan.id+'/restaurants?after_index='+index);
      moreResults.replaceChildren(node('p',data.message||'네이버 검색 결과 · 위 공식 가이드 추천과 별도입니다.','hint'));
      for(const food of data.restaurants)moreResults.append(restaurantCard(food));
      if(data.search_url)moreResults.append(link('지도에서 더 보기 ↗',data.search_url));
    }catch(error){moreResults.replaceChildren(node('p',error.message,'hint'));}finally{more.disabled=false;}
  },'secondary meal-more');
  panel.append(list,node('p',group.note,'hint'),more,moreResults);return panel;
}
