function chatWidget(kind,id,chatMode){
  const container=node('section'),history=node('div',undefined,'chat-box'),f=node('form',undefined,'chat-form'),input=node('input');
  input.placeholder=kind==='plan'?'예: 총비용은 얼마야? 이동 시간과 주의할 점은?':'예: 운영시간과 가격이 확인되나요?';
  input.setAttribute('aria-label','장소 또는 일정 질문');input.required=true;input.maxLength=4000;
  const send=node('button','질문하기','primary');send.type='submit';f.append(input,send);
  history.setAttribute('aria-live','polite');container.append(history,f,node('p',kind==='plan'?'현재 선택한 일정의 시간표·비용·조건을 바탕으로 답합니다. 일정 변경은 각 장소의 변경 버튼에서 확정해 주세요.':'확보한 장소 자료를 근거로 답합니다.','hint'));
  const ready=api(`/chat/${kind}/${id}?mode=${chatMode}`).then(data=>{
    history.replaceChildren();data.messages.forEach(m=>history.append(node('p',(m.role==='user'?'나: ':'메이트: ')+m.content,'message')));
    if(!data.messages.length)history.append(node('p','궁금한 내용을 입력해 주세요.'));
  }).catch(()=>history.append(node('p','이전 대화를 불러오지 못했어요. 새 질문은 입력할 수 있어요.','hint')));
  f.onsubmit=async e=>{
    e.preventDefault();const question=input.value.trim();if(send.disabled||!question)return;
    send.disabled=true;send.textContent='답변 작성 중…';input.disabled=true;await ready;
    history.append(node('p','나: '+question,'message'));const pending=node('p','일정과 근거를 확인하고 있어요…','message');history.append(pending);
    try{
      const result=await api(`/chat/${kind}/${id}`,{question,mode:chatMode});
      pending.textContent='메이트: '+result.answer;
      (result.citations||[]).forEach(c=>{history.append(link(`[${c.number}] ${c.title} · ${c.type}`,c.source));history.append(node('br'));});
      if(result.status==='plan_facts')history.append(node('p','현재 선택한 일정 기준 · 실시간 현장 정보와 다를 수 있어요.','hint'));
      input.value='';
    }catch(error){pending.textContent='답변을 가져오지 못했어요: '+error.message;pending.classList.add('warning');}
    finally{send.disabled=false;send.textContent='질문하기';input.disabled=false;history.scrollTop=history.scrollHeight;}
  };return container;
}
