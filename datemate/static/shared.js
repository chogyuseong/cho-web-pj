'use strict';
// festivals.js 가 쓰는 화면 도구(app.js 의 같은 이름 함수와 같은 동작). 공유 화면은 https 출처 링크만 연다.
function node(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function link(text,url){
  let href=null;try{const u=new URL(String(url||''));if(u.protocol==='https:'&&!u.username&&!u.password)href=u.href;}catch{}
  if(!href)return node('span',text||'출처 주소 없음');
  const a=node('a',text);a.href=href;a.target='_blank';a.rel='noopener noreferrer';return a;
}
(() => {
  const token=location.hash.slice(1), status=document.getElementById('shared-status'), form=document.getElementById('shared-form');
  // 개선안 28·34: '아직 안 정했어요'(무응답)는 보내지 않는다. 마지막으로 저장한 의견(saved)과 지금 폼을 비교해,
  // 바꿨지만 아직 전달하지 않은 곳이 있으면 알려 준다(저장 직후 다른 선택을 하고 전달됐다고 착각하지 않게).
  let saved={};
  const dirty=document.createElement('p');dirty.className='hint shared-dirty';dirty.setAttribute('aria-live','polite');
  const current=()=>Object.fromEntries([...new FormData(form)].filter(([,value])=>value));
  function showDirty(){
    const now=current(),ids=new Set([...Object.keys(now),...Object.keys(saved)]);
    const changed=[...ids].filter(id=>now[id]!==saved[id]).length;
    dirty.textContent=!Object.keys(saved).length&&!changed?'아직 전달한 의견이 없어요. 원하는 곳만 골라도 돼요.':changed?`바꿨지만 아직 전달하지 않은 곳이 ${changed}곳 있어요. '내 의견 전달하기'를 눌러야 전해져요.`:'전달한 의견과 지금 선택이 같아요.';
  }
  form.addEventListener('change',showDirty);
  async function request(path,body,timeout=15000){
    const response=await fetch(path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(timeout)});
    let data;try{data=await response.json();}catch{const error=Error('연결하지 못했어요.');error.status=response.status;error.unreadable=true;throw error;}
    if(!response.ok){const error=Error(data.detail||'연결하지 못했어요.');error.status=response.status;throw error;}return data;
  }
  // 잠든 서버가 켜지는 동안에는 다시 물으며 안내를 보여 준다(server-wake.js).
  ServerWake.load(timeout=>request('/api/shared-plan',undefined,timeout)).then(data=>{
    status.textContent=data.notice;
    for(const place of data.places){
      const article=document.createElement('article'),title=document.createElement('h2'),text=document.createElement('p'),label=document.createElement('label'),select=document.createElement('select');
      title.textContent=place.name;text.textContent=`${place.arrival} ~ ${place.departure} · ${place.address}`;
      label.textContent=place.name+'에 대한 의견';select.name=place.id;
      for(const [value,title] of [['','아직 안 정했어요'],['neutral','상관없어요'],['yes','좋아요'],['must','꼭 가고 싶어요'],['no','빼주세요']])select.add(new Option(title,value));
      select.value=data.my_choices?.[place.id]||'';
      label.append(select);article.append(title,text);if(typeof isNaverResult==='function'&&isNaverResult(place))article.append(naverAttribution('지역 검색',place.source));article.append(label);document.getElementById('shared-places').append(article);
    }
    saved={...(data.my_choices||{})};form.querySelector('button').before(dirty);showDirty();
    form.hidden=false;
    // 코스의 지역·방문일(공유되는 정보는 이 둘뿐)로 그날 축제를 보여 준다. 실패해도 의견 전달에는 영향이 없다.
    if(data.festival_search){
      try{FestivalPanel.readOnly=true;FestivalPanel.load({region:data.festival_search.region,visit_date:data.festival_search.visit_date});}catch{}
    }
  }).catch(error=>status.textContent=error.message);
  form.onsubmit=async event=>{
    event.preventDefault();const button=form.querySelector('button');button.disabled=true;
    const choices=current();
    if(!Object.keys(choices).length){status.textContent='한 곳 이상 의견을 골라 주세요. 고르지 않은 곳은 아직 안 정한 것으로 남아요.';button.disabled=false;return;}
    try{await request('/api/shared-plan/vote',{choices});saved=choices;showDirty();status.textContent='의견을 전달했어요. 코스를 만든 사람이 두 사람의 취향으로 다시 계산할 수 있어요.';}
    catch(error){status.textContent=error.message;}finally{button.disabled=false;}
  };
})();
