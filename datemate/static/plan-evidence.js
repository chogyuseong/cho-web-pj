function optionComparison(items){
  const wrap=node('section',undefined,'option-comparison');wrap.setAttribute('aria-label','옵션 한눈에 비교');
  wrap.append(node('h3','어떤 코스가 더 끌리나요?'));
  const scroll=node('div',undefined,'table-scroll'),table=node('table'),head=node('tr');
  ['코스','주요 활동','예상 전체 비용','총 이동 시간','장소 차이'].forEach(x=>head.append(node('th',x)));table.append(head);
  items.forEach((p,i)=>{const row=node('tr');const others=p.places.filter(x=>!items[0].places.some(y=>y.id===x.id)).length;
    [String(i+1)+' · '+(p.decision_summary?.title||p.option_purpose||'추천'),[...new Set(p.places.map(x=>x.category))].join(' · '),range(p.total),`${p.decision_summary?.travel_minutes??p.legs.reduce((n,x)=>n+(x.minutes||0),0)}분`,i?`코스 1과 ${others}곳 다름`:'비교 기준'].forEach(x=>row.append(node('td',x)));table.append(row);
  });scroll.append(table);scroll.tabIndex=0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label','코스 비교 표 · 가로로 넘겨 확인');wrap.append(node('p','비용과 이동 시간을 비교해 보세요. 표는 좌우로 넘길 수 있어요.','hint'),scroll);return wrap;
}
function placeEvidencePanel(plan,index){
  const place=plan.places[index],fact=plan.place_evidence?.find(x=>x.place_id===place.id);
  const details=node('details',undefined,'place-evidence');details.append(node('summary','추천 이유 · 정보 확인'));
  details.append(linkedText('p',fact?.reason||plan.reasons?.[index]||'입력 조건으로 비교한 후보','hint'));
  details.append(node('p',fact?.address||place.address||'주소 미확인','hint'));
  if(fact){details.append(node('p',fact.identity,'hint'),node('p',fact.operating_status+(fact.operating_age_days!=null?` · 자료 확인 ${fact.operating_age_days}일 경과`:''),'hint'),node('p',fact.blog_match?'코스 검색 글에서 등장 확인 · 평점이나 방문자 수 검증은 아님':'검색 글에서 직접 등장 확인 없음 · 조건 기반 보완 후보','hint'));
    const labels={web_reference:'블로그 언급 가격 · 현재가 미검증',planning_assumption:'예산 계획용 가정 · 실제 메뉴 가격 아님',naver_menu:'수집 메뉴 가격 · 현재가 원문 확인',confirmed:'등록 단가',estimated:'추정 단가',unknown:'가격 미확인'};
    details.append(node('p','가격 근거: '+(labels[fact.price_kind]||fact.price_kind),'hint'));
    for(const q of fact.price_sources){details.append(sourceLinks('참고한 블로그 · '+(q.posted_at||'작성일 미확인'),q.source,place.name+' 메뉴 가격'),node('p',q.evidence||'','hint'));}
  }
  return details;
}
