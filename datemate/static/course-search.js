/* 코스 조사 패널: 코스를 어떻게 짰는지에 대한 우리 메모(콘셉트 단서·요청 해석·동네 범위)와, 같은 지역 검색어로 찾은 네이버 블로그 글 블록.
   블로그 글은 추천 계산에 쓰지 않는다(app/course_search.py). 글 블록은 네이버가 준 순서·건수·제목·요약 그대로다(place-blogs.js naverBlogBlock).
   2026-11-26 네이버 답(특약 1.2, 첫 문의 2-1·2-2): 같은 칸 안 블록 바로 위·아래 자체 정보, 블록 앞 안내 문구 모두 불가
   → 두 칸으로 나눈다: ① 우리 메모 상자(.course-search-memo, 테두리 상자) ② 블로그 칸(.course-search-blogs, 블록 하나만).
     두 칸 사이는 22px 띄우고 각자 테두리를 가진다(results.css). 예전 블록 앞 안내('…순서 그대로 보여 드려요 … 광고·협찬 글이 섞여 있을 수 있어요')는 뺐다.
     '…로는 글이 없어 …로 다시 찾았어요'·글 없음 안내는 우리 정보라 메모 상자에 둔다.
   예전 형식(우리가 고른 5건, format 없음)은 그리지 않는다(plan-detail.js 가 format 을 본다). */
function courseSearchPanel(evidence,plan){
  const box=node('div',undefined,'course-search-panel'),memo=node('section',undefined,'course-search-memo');
  memo.setAttribute('aria-label','코스 구성 메모');
  memo.append(node('h3','코스 구성 메모'));
  if(plan){const reasons=node('div',undefined,'concept-place-reasons');for(const place of plan.places){const row=plan.concept_matches?.find(r=>r.place_id===place.id);if(row)reasons.append(node('p',place.name+' · '+(row.signals.length?'콘셉트 단서: '+row.signals.join(', '):'구체적인 콘셉트 단서 부족 · 조건 보완 후보'),'hint'));}memo.append(reasons);}
  if(plan?.request_interpretation){const parsed=plan.request_interpretation;if(parsed.intents.length)memo.append(node('p','입력에서 반영한 활동: '+parsed.intents.join(' · '),'hint'));if(parsed.excluded.length)memo.append(node('p','제외한 활동: '+parsed.excluded.join(' · '),'hint'));}
  if(plan?.conditions.area_center)memo.append(node('p',`${plan.conditions.area_center.name} 반경 ${plan.conditions.neighborhood_radius_km}km · ${plan.conditions.include_meal?'식사 시간대 밥집 포함 우선':'식사 자유 선택'}`,'hint'));
  if(plan?.route_verification)memo.append(node('p',plan.route_verification,'hint'));
  const posts=Array.isArray(evidence.posts)?evidence.posts:[];
  if(evidence.search_relaxed)memo.append(node('p',`블로그 글은 ‘${evidence.requested_query}’로는 없어 ‘${evidence.query}’로 다시 찾았어요.`,'hint'));
  if(!posts.length)memo.append(node('p',evidence.message||'보여 드릴 블로그 글이 없어요.','hint'));
  // 메모가 제목뿐이면(단서·해석·범위·글 없음 안내가 하나도 없으면) 빈 상자를 그리지 않는다.
  if(memo.querySelector('p'))box.append(memo);
  if(posts.length){
    const blogs=node('section',undefined,'course-search-blogs');
    blogs.setAttribute('aria-label','네이버 블로그 검색 결과');
    blogs.append(naverBlogBlock(posts,'https://search.naver.com/search.naver?'+new URLSearchParams({where:'blog',query:evidence.query}),5,
      node('h3',`‘${evidence.query}’ 블로그 검색 결과 ${posts.length}건`,'naver-result-title')));
    box.append(blogs);
  }
  return box;
}
(()=>{const label=node('label','찾고 싶은 데이트 코스·동네');const input=node('input');input.name='course_query';input.maxLength=120;input.placeholder='예: 연남동 데이트 코스 (비우면 선택한 지역 기준)';label.append(input,node('small','적은 동네·활동을 기준으로 장소를 찾아요. 같은 검색어의 네이버 블로그 글은 결과 아래에 따로 보여 드려요(추천 계산에는 쓰지 않아요).','hint'));form.prepend(label);})();
(()=>{
  const label=node('label','동네 안에서 이동할 범위'),select=node('select');select.name='neighborhood_radius_km';
  for(const [value,text] of [[1.5,'가까운 골목 위주 · 반경 1.5km'],[2.5,'인근 동네까지 · 반경 2.5km'],[5,'넓게 둘러보기 · 반경 5km']]){const o=node('option',text);o.value=value;o.selected=value===2.5;select.append(o);}label.append(select);
  const meal=node('label',undefined,'check'),check=node('input');check.type='checkbox';check.name='include_meal';check.checked=true;meal.append(check,document.createTextNode('식사 시간대에 밥집 한 곳 포함 (방문 수·예산 반영)'));
  const hint=node('p','동네 범위를 벗어난 장소는 자동으로 끼워 넣지 않아요. 식당 영업·예약은 확인이 필요해요.','hint');
  form.querySelector('[name=course_query]').closest('label').after(label,meal,hint);
})();
