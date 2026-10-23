function leisureSuggestionPanel(plan,index){
  const panel=node('details',undefined,'leisure-results');
  panel.append(node('summary',`${index+1}. ${plan.places[index].name} 주변 레저`));
  const content=node('div');panel.append(content);let loaded=false;
  async function load(){
    content.replaceChildren(node('p','코스 주변의 클라이밍·볼링 등 스포츠 장소를 찾고 있어요…','hint'));panel.setAttribute('aria-busy','true');
    try{
      const data=await api('/plans/'+plan.id+'/leisure-options',{index,locked:[...locks]});
      content.replaceChildren(node('p',data.message,'hint'));
      for(const row of data.options){
        const place=row.place,card=node('article',undefined,'leisure-result-card');
        card.append(node('strong',place.name),node('p',`${place.description||place.category} · 현재 장소에서 직선 ${row.distance_m}m`,'hint'),node('p',`교체 시 전체 소요 시간 ${row.delta.minutes>=0?'+':''}${row.delta.minutes}분 · 비용 변화 ${range(row.delta.cost)}`,'hint'));
        const actions=node('div',undefined,'actions');
        const select=button('이 레저로 교체',async()=>{
          if(selected?.id!==plan.id){toast('선택한 코스가 바뀌었어요. 현재 코스에서 다시 골라주세요.');return;}
          select.disabled=true;
          try{const updated=await api('/plans/'+plan.id+'/leisure-select',{index,locked:[...locks],replacement_id:place.id});selected=updated;replaceInList(plan.id,updated);renderResults();renderDetail();toast('선택한 레저로 교체하고 시간·비용·지도를 다시 계산했어요.');}
          catch(error){toast(error.message);select.disabled=false;}
        },'primary');
        select.disabled=plan.can_edit===false||locks.has(index);
        actions.append(select,link('지도에서 확인 ↗','https://map.naver.com/p/search/'+encodeURIComponent(placeSearchQuery(place))));
        card.append(actions);content.append(card);
      }
      if(!data.options.length)content.append(node('p','반경 1.5km에서 현재 일정에 넣을 수 있는 스포츠 후보를 찾지 못했어요. 다른 코스 위치에서 확인하거나 시간·조건을 조정해 주세요.','hint'));
      content.append(button('주변 레저 다시 찾기',load,'secondary'));loaded=true;
    }catch(error){content.replaceChildren(node('p',error.message,'warning'),button('다시 찾기',load,'secondary'));}
    finally{panel.setAttribute('aria-busy','false');}
  }
  panel.addEventListener('toggle',()=>{if(panel.open&&!loaded&&panel.getAttribute('aria-busy')!=='true')load();});
  return panel;
}

function leisureCoursePanel(plan){
  const section=node('section',undefined,'leisure-course-panel');
  section.setAttribute('aria-label','이 동선에서 즐길 레저 골라보기');
  section.append(node('h3','이 동선에서 즐길 레저 골라보기'),node('p','주변 레저를 찾을 코스 위치를 펼쳐주세요. 선택하면 그 순서의 방문지만 교체해요.','hint'));
  plan.places.forEach((place,index)=>section.append(leisureSuggestionPanel(plan,index)));
  return section;
}
