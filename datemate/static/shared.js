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
  // 응답 없이 실패한 fetch(연결 끊김 'Failed to fetch', 시간 초과 'signal timed out')는 브라우저 원문 대신 코스 화면과 같은
  // 한국어 문구로(http-client.mjs, 2026-11-25 운영 QA 덧붙임). status 를 붙이지 않아 서버 깨우기(server-wake.js)는 전처럼 다시 묻는다.
  async function noAnswer(cause){
    // 문구 모듈마저 받지 못했으면(첫 화면 직후 끊김) 짧은 한국어 문구로 대신한다.
    const texts=await httpClient.catch(()=>({}));
    const timedOut=cause?.name==='TimeoutError'||cause?.name==='AbortError';
    const text=(timedOut?texts.TIMEOUT_ERROR_TEXT:texts.NETWORK_ERROR_TEXT)||'서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.';
    const error=Error(text);error.network=!timedOut;error.cause=cause;return error;
  }
  async function request(path,body,timeout=15000){
    let response;
    try{response=await fetch(path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(timeout)});}
    catch(cause){throw await noAnswer(cause);}
    let data;try{data=await response.json();}catch{const error=Error('연결하지 못했어요.');error.status=response.status;error.unreadable=true;throw error;}
    if(!response.ok){const error=Error(data.detail||'연결하지 못했어요.');error.status=response.status;throw error;}return data;
  }
  // 잠든 서버가 켜지는 동안에는 다시 물으며 안내를 보여 준다(server-wake.js).
  ServerWake.load(timeout=>request('/api/shared-plan',undefined,timeout)).then(data=>{
    status.textContent=data.notice;
    // 운영 시간에 맞춰 고정한 축제(이름·시각·자리만 공유된다). 의견을 고르는 장소 칸(article)이 아니라 장소 앞(저녁 축제면 장소 뒤,
    // 코스 중간 축제면 after 번째 장소 뒤)의 section 이다.
    const visit=data.festival_visit,last=visit?.position==='last',places=data.places||[];
    const middle=visit?.position==='middle'&&Number.isInteger(visit.after)&&visit.after>=0&&visit.after<places.length-1?visit.after:null;
    function festivalBlock(){
      const block=node('section',undefined,'shared-festival-visit'+(last?' last':middle!==null?' middle':''));
      block.setAttribute('aria-label',last?'코스 끝에 둔 축제 방문':middle!==null?'코스 중간에 둔 축제 방문':'코스 맨 앞에 고정한 축제 방문');
      // apart: 만든 코스에 나중에 넣은 축제(행사장이 출발지가 아님, app/sharing.festival_visit). 돌아오는 게 아니라 가는 것이다.
      const text=last?`장소를 둘러본 뒤 행사장으로 ${visit.apart?'가서':'돌아와'} 축제로 마무리해요.`:middle!==null?`${withObjectParticle(places[middle].name)} 둘러본 뒤 행사장에 들러 축제를 보고 다음 장소로 이동해요.`:'축제를 먼저 들른 뒤 아래 장소로 이동해요.';
      block.append(node('h2',`${visit.title} · ${visit.arrival}~${visit.departure}`),node('p',text+' 개최·운영 시간은 방문 전 주최 측 안내를 확인해 주세요.','hint'));
      document.getElementById('shared-places').append(block);
    }
    if(visit&&!last&&middle===null)festivalBlock();
    for(const [index,place] of places.entries()){
      const article=document.createElement('article'),title=document.createElement('h2'),text=document.createElement('p'),label=document.createElement('label'),select=document.createElement('select');
      title.textContent=place.name;// 주소가 없는 장소는 시각만 적는다(예전에는 '14:26 ~ 15:26 · null' 로 보였다). 서버도 빈 글로 보내지만(app/sharing.py) 옛 응답·캐시에 대비해 여기서도 거른다.
      text.textContent=`${place.arrival} ~ ${place.departure}`+(place.address?` · ${place.address}`:'');
      label.textContent=place.name+'에 대한 의견';select.name=place.id;
      for(const [value,title] of [['','아직 안 정했어요'],['neutral','상관없어요'],['yes','좋아요'],['must','꼭 가고 싶어요'],['no','빼주세요']])select.add(new Option(title,value));
      select.value=data.my_choices?.[place.id]||'';
      label.append(select);article.append(title,text);if(typeof isNaverResult==='function'&&isNaverResult(place))article.append(naverAttribution('지역 검색',place.source));article.append(label);document.getElementById('shared-places').append(article);
      if(index===middle)festivalBlock();
    }
    if(visit&&last)festivalBlock();
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
