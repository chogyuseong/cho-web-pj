function courseSearchPanel(evidence,plan){
  const box=node('section',undefined,'course-search-panel');
  box.append(node('p','NAVER COURSE RESEARCH','eyebrow'),node('h3',evidence.query),node('p',evidence.provider+' · 통합검색 화면 순위와 다를 수 있어요.','hint'));
  const count=plan?.places.filter(p=>evidence.matches[p.id]).length||0;
  if(plan?.conditions.area_center)box.append(node('p',`${plan.conditions.area_center.name} 반경 ${plan.conditions.neighborhood_radius_km}km · ${plan.conditions.include_meal?'식사 시간대 밥집 포함 우선':'식사 자유 선택'}`,'hint'));
  const discovery=evidence.discovery;
  if(discovery){box.append(node('p',`블로그 발견 장소 ${discovery.extracted}곳 중 주소·좌표 연결 ${discovery.resolved}곳`,'hint'));if(discovery.local_permission_required)box.append(node('p','새 업체 연결 확대: NAVER API HUB의 기존 Application에서 NAVER 검색 → 지역 API를 활성화해 주세요. 현재는 글에 주소가 있는 곳을 주소 검색으로 연결해요.','warning'));if(discovery.status==='extraction_unavailable')box.append(node('p','새 장소 추출에 실패하여 확인된 기존 장소로 보완했어요.','hint'));}
  if(plan?.route_verification)box.append(node('p',plan.route_verification,'hint'));
  box.append(node('p',count?`이번 코스 ${count}곳이 상위 글에서 확인됐어요. 나머지는 입력 조건에 맞춰 보완했어요.`:evidence.message||'검색 근거를 확보하지 못해 기존 조건 기반 코스를 표시해요.','hint'));
  for(const post of evidence.posts){const item=node('div',undefined,'course-source');item.append(link(`${post.rank}. ${post.title}`,post.url),node('small',post.content_scope+' · '+(post.posted_at||'작성일 미제공')));box.append(item);}
  box.append(node('p',evidence.rating_note,'hint'));return box;
}
(()=>{const label=node('label','네이버에서 찾을 데이트 코스');const input=node('input');input.name='course_query';input.maxLength=120;input.placeholder='예: 연남동 데이트 코스 (비우면 출발지 기준)';label.append(input,node('small','검색 상위 3개 글에 등장하는 장소를 우선 추천해요.','hint'));form.prepend(label);})();
(()=>{
  const label=node('label','동네 안에서 이동할 범위'),select=node('select');select.name='neighborhood_radius_km';
  for(const [value,text] of [[1.5,'가까운 골목 위주 · 반경 1.5km'],[2.5,'인근 동네까지 · 반경 2.5km'],[5,'넓게 둘러보기 · 반경 5km']]){const o=node('option',text);o.value=value;o.selected=value===2.5;select.append(o);}label.append(select);
  const meal=node('label',undefined,'check'),check=node('input');check.type='checkbox';check.name='include_meal';check.checked=true;meal.append(check,document.createTextNode('식사 시간대에 밥집 한 곳 포함 (방문 수·예산 반영)'));
  const hint=node('p','동네 범위를 벗어난 장소는 자동으로 끼워 넣지 않아요. 식당 영업·예약은 확인이 필요해요.','hint');
  form.querySelector('[name=course_query]').closest('label').after(label,meal,hint);
})();
