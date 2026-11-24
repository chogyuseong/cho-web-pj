const httpClient=import('/static/http-client.mjs');
// 서버를 깨우는 동안(server-wake.js)에는 /status 말고는 보내지 않고, 준비되면 이어서 보낸다.
async function api(...args){if(args[0]!=='/status'&&typeof ServerWake!=='undefined')await ServerWake.ready();return (await httpClient).apiRequest(...args);}

// 개선안 32: 링크가 언제까지 열리는지 현지 날짜·시각으로 알린다. 약속 날이 그 뒤면 미리 경고한다.
function shareExpiryText(expires,visitDate){
  const until=new Date(expires*1000);
  const text=until.toLocaleString('ko-KR',{month:'long',day:'numeric',weekday:'short',hour:'2-digit',minute:'2-digit'})+'까지 열려요';
  const visit=visitDate?new Date(visitDate+'T00:00:00'):null;
  if(visit&&!Number.isNaN(visit.getTime())&&until<visit)return text+` · 약속 날(${visit.toLocaleDateString('ko-KR',{month:'long',day:'numeric',weekday:'short'})})에는 만료돼요. 약속 하루 전쯤 새 링크를 만들어 보내 주세요.`;
  return text;
}
async function copyPlanShare(plan){
  const shared=await api('/plans/'+plan.id+'/shares',{});
  const url=new URL(shared.url,location.origin).href,expiry=shareExpiryText(shared.expires,plan.conditions?.visit_date);
  try{await navigator.clipboard.writeText(url);toast('24시간 공유 링크를 복사했어요. '+expiry+'. 출발지·귀가지·입력 요청은 제외됩니다.');}
  catch{const root=openDialog('공유 링크');const input=document.createElement('input');input.value=url;input.readOnly=true;input.setAttribute('aria-label','공유 링크');root.append(input,node('p',expiry,'hint'));input.select();}
  if(typeof refreshShareStatus==='function')refreshShareStatus(plan);
}

// 카톡에 바로 붙여넣기 좋은 일정 글(2026-11-24 UX P1). 날짜 → 시간별 장소(축제 포함, day-of.js dayOfSteps 순서) → 구간 이동 → 예상 비용 → 공유 링크.
// 공유 링크는 서버가 만든 24시간 링크(app/sharing.py)라 출발지·귀가지·입력 요청은 들어가지 않는다. 링크를 못 만들면 일정 글만 복사한다.
// 글 모양을 바꾸면 tests/test_ux_p1_ui.py 의 기대 문구도 고친다. 공유 줄의 「카톡용 일정 복사」와 코스 카드 창의 「코스 요약 복사」가 함께 쓴다.
function kakaoItineraryText(plan,url){
  const c=plan.conditions||{},d=new Date((c.visit_date||'')+'T00:00');
  const day=Number.isNaN(d.getTime())?(c.visit_date||''):`${d.getMonth()+1}월 ${d.getDate()}일 (${'일월화수목금토'[d.getDay()]})`;
  const lines=[`[데이트메이트] ${day} 데이트 코스`];
  const legText=leg=>leg&&Number.isFinite(leg.minutes)?(typeof legModeLabel==='function'?legModeLabel(plan,leg):`${leg.minutes}분`):'';
  const steps=typeof dayOfSteps==='function'?dayOfSteps(plan):plan.places.map((place,index)=>({place,index,time:plan.timeline[index],leg:plan.legs?.[index]}));
  for(const step of steps){
    const move=legText(step.leg);
    if(move)lines.push(`  ↓ ${move}`);
    if(step.festival)lines.push(`${step.festival.arrival} 축제 · ${step.festival.title}`);
    else lines.push(`${step.time?.arrival||''} ${step.place.name}`.trim());
  }
  if(plan.total)lines.push('',`예상 비용 ${range(plan.total)} (${c.people||2}명, 확인 못 한 비용 제외)`);
  if(url)lines.push(`코스 자세히 보기(24시간): ${url}`);
  lines.push('영업시간은 방문 전 네이버 지도에서 확인해 주세요.');
  return lines.join('\n');
}
async function copyKakaoItinerary(plan){
  let url='';
  try{const shared=await api('/plans/'+plan.id+'/shares',{});url=new URL(shared.url,location.origin).href;}catch{}
  const text=kakaoItineraryText(plan,url);
  try{await navigator.clipboard.writeText(text);toast(url?'카톡에 붙여넣을 일정과 24시간 공유 링크를 복사했어요.':'카톡에 붙여넣을 일정을 복사했어요. 공유 링크는 만들지 못했어요.');}
  catch{const root=openDialog('카톡용 일정');const area=document.createElement('textarea');area.value=text;area.readOnly=true;area.rows=Math.min(16,text.split('\n').length+1);area.setAttribute('aria-label','카톡용 일정 글');root.append(area);area.select();}
  if(url&&typeof refreshShareStatus==='function')refreshShareStatus(plan);
}

// 개선안 31: 같은 변경 계열 코스의 열린 공유 링크를 일정 화면 공유 구역에 알린다(app/sharing.share_status).
// 이 코스 → 바뀌기 전 코스(earlier) → 되돌리기 전·따로 바꾼 코스(other, 2026-11-24 점검 F1). 링크와 상대 의견은 코스마다 따로라,
// 다른 버전의 링크를 받은 사람은 그 코스를 보고 의견도 그 코스에 남는다(지금 코스의 합의에는 잡히지 않는다).
const shareOpinionText=rows=>{const n=rows.reduce((sum,row)=>sum+(row.opinions||0),0);return n?` 그 코스에 남은 상대 의견 ${n}건은 이 코스의 합의에 들어오지 않아요.`:'';};
async function revokeShareRows(plan,rows,message){for(const row of rows)await api('/plans/'+row.plan_id+'/shares',null,'DELETE');toast(message);refreshShareStatus(plan);}
async function refreshShareStatus(plan){
  const line=document.querySelector('#plan-detail .share-status');if(!line||line.dataset.plan!==plan.id)return;
  let data;try{data=await api('/plans/'+plan.id+'/shares');}catch{line.textContent='';return;}
  if(line.dataset.plan!==plan.id)return;
  line.replaceChildren();
  const now=data.current.active?`이 코스의 공유 링크 ${data.current.active}개 · `+shareExpiryText(data.current.expires,plan.conditions?.visit_date):'이 코스로 만든 공유 링크는 없어요.';
  line.append(node('span',now));
  if(data.earlier.length){
    const count=data.earlier.reduce((n,row)=>n+row.active,0);
    line.append(node('strong',` 바뀌기 전 코스의 공유 링크 ${count}개가 아직 열려 있어요. 그 링크를 받은 사람은 바뀌기 전 코스를 봐요.${shareOpinionText(data.earlier)}`),
      button('이전 링크 취소',()=>revokeShareRows(plan,data.earlier,'바뀌기 전 코스의 공유 링크를 취소했어요.')));
  }
  const other=data.other||[];
  if(other.length){
    const count=other.reduce((n,row)=>n+row.active,0),later=other.every(row=>row.relation==='later');
    const where=later?'되돌리기 전 코스':'되돌리기 전이나 따로 바꾼 코스';
    // 어느 코스인지 장소 순서로 적는다(공유 구역은 문단 하나라 목록 대신 줄 안의 span 으로 둔다).
    const courses=other.map(row=>`‘${row.places.join(' → ')||'장소 정보 없음'}’ 링크 ${row.active}개${row.opinions?` · 상대 의견 ${row.opinions}건`:''}`).join(' / ');
    line.append(node('strong',` ${where}의 공유 링크 ${count}개가 아직 열려 있어요. 그 링크를 받은 사람은 그 코스를 보고, 의견도 그 코스에 남아 이 코스의 합의에는 들어오지 않아요.`),
      node('span',' '+courses+' ','share-other-courses'),button('그 링크 취소',()=>revokeShareRows(plan,other,where+'의 공유 링크를 취소했어요.')));
  }
}
async function revokePlanShares(plan){
  await api('/plans/'+plan.id+'/shares',null,'DELETE');toast('이 일정의 공유 링크를 모두 취소했어요.');
  if(typeof refreshShareStatus==='function')refreshShareStatus(plan);
}
