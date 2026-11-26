/* Explicit edits survive subsequent natural-language parsing. */
const FormState={
  edited:new Set(),
  allowed:new Set(['people','budget','count','transport','setting','reservation','priority','max_walk','include_meal','themes','theme_mode','date_category','date_subcategory','meeting_type']),
  summary(data){
    const transport={walk:'도보',transit:'대중교통',car:'자가용',bicycle:'자전거'};
    return `${data.visit_date} · ${data.start}–${data.end} · ${data.people}명 · ${data.budget_unlimited?'예산 무관':Number(data.budget).toLocaleString('ko-KR')+'원'} ·${data.count}곳 · ${transport[data.transport]||data.transport}`;
  }
};
// 'input'(입력하는 순간)에서도 기록한다. 'change'(칸을 벗어날 때)만 보면, 예산을 입력하고 칸을 벗어나기 전에
// 자연어 해석('2명 5만원')이 도착해 입력한 값을 덮었다(2026-11-19 출시 흐름 테스트가 가끔 50000 으로 실패해 재현·확인).
// 빠른 선택 단추(simple-form.js setValue)는 원래 input·change 를 함께 보내므로 동작이 바뀌지 않고,
// 해석 결과를 넣는 setRequestField(app.js)는 이벤트를 보내지 않아 여전히 '바꾼 칸'으로 세지 않는다.
for(const type of ['input','change'])document.getElementById('conditions').addEventListener(type,event=>{
  if(FormState.allowed.has(event.target.name))FormState.edited.add(event.target.name);
});
/* 네이버 검색 API 결과에서 온 출발지(특약 1.4 기기 보관: 24시간 또는 새 질의 시까지 중 짧은 기간).
   지역 검색으로 고른 곳(이름·주소·좌표가 검색 결과)은 출발지에 naver_at(결과를 받은 시각, ms)과
   naver_query(어느 검색에서 왔는지: 지금은 'local' 출발지 검색 하나)를 붙인다. 동네 칩·현재 위치·지도에서 고른 곳·주소 검색(지오코딩)·
   축제(관광공사)·팝업 거점(우리 거점 사전, 좌표는 관광공사 자료. 2026-11-20 부터)은 네이버 검색 결과가 아니라 붙이지 않고 기한 없이 그대로 둔다.
   2026-11-20 전에 팝업 거점으로 저장된 출발지(naver_query 'popups', 좌표가 지역 검색 결과)는 받은 지 24시간이 지나면 아래 규칙으로 지워진다.
   기기에 남기는 곳은 ‘지난번처럼 추천’(LastConditions) 하나다. 24시간이 지나거나 같은 종류의 새 검색을 하면 그 출발지만 지우고 나머지 조건은 둔다. */
const NaverDeviceRetention={
  maxMs:86400000,
  // at: 검색 응답을 받은 시각(없으면 지금). 같은 출발지를 다시 쓰거나 저장해도 이 값을 유지한다(다시 저장해서 기한이 늘지 않게).
  mark(origin,query,at){return {...origin,naver_at:Number.isFinite(at)?at:Date.now(),naver_query:query};},
  isNaver(origin){return Boolean(origin&&typeof origin==='object'&&('naver_at' in origin||'naver_query' in origin));},
  expired(origin,now=Date.now()){
    const at=Number(origin?.naver_at);
    // 시각이 없거나 숫자가 아니거나 미래(시계를 되돌린 경우 1분 여유)면 지난 것으로 본다.
    return !Number.isFinite(at)||at>now+60000||now-at>=this.maxMs;
  },
  // 저장·전달할 출발지 필드(이름·좌표, 네이버 결과면 받은 시각과 검색 종류).
  fields(origin){
    const own={name:origin.name,lat:origin.lat,lon:origin.lon};
    if(this.isNaver(origin))Object.assign(own,{naver_at:Number(origin.naver_at),naver_query:String(origin.naver_query||'local')});
    return own;
  }
};
/* ‘지난번처럼 추천’에 쓰는 조건. 이 브라우저에만 남기고, 자유 입력 문장과 날짜는 저장하지 않는다. */
const LastConditions={
  key:'datemate-last-conditions',
  changed:null,
  save(data){
    try{
      // 축제를 골라 바뀐 출발지(축제 장소)와 가상 장소 데모의 출발점은 ‘지난 지역’으로 남기지 않고 이전에 저장한 지역을 유지한다.
      // 받은 지 24시간이 지난 네이버 검색 출발지도 새로 남기지 않는다(페이지를 하루 넘게 열어 둔 경우).
      const own=data.mode==='real'&&!data.festival&&data.origin&&!(NaverDeviceRetention.isNaver(data.origin)&&NaverDeviceRetention.expired(data.origin));
      const previous=this.load();
      const area=own?{region:data.region,origin:NaverDeviceRetention.fields(data.origin)}:previous&&{region:previous.region,origin:previous.origin};
      if(!area)return;
      // 예산 무관은 고른 경우에만 남긴다(없으면 예산 금액대로).
      localStorage.setItem(this.key,JSON.stringify({...area,start:data.start,end:data.end,budget:data.budget,...(data.budget_unlimited?{budget_unlimited:true}:{}),people:data.people,count:data.count,transport:data.transport}));
      this.changed?.();
    }catch{}
  },
  load(){
    try{
      const v=JSON.parse(localStorage.getItem(this.key));
      // 네이버 검색 출발지가 24시간을 넘었으면 출발지만 지우고(나머지 조건은 그대로) 없는 것으로 본다.
      if(v&&NaverDeviceRetention.isNaver(v.origin)&&NaverDeviceRetention.expired(v.origin)){this.dropOrigin(v);return null;}
      const time=/^([01]\d|2[0-3]):[0-5]\d$/,whole=(n,min,max)=>Number.isInteger(n)&&n>=min&&n<=max;
      if(!v||typeof v.region!=='string'||!v.origin||typeof v.origin.name!=='string'||!v.origin.name.trim()||v.origin.name.length>200)return null;
      if(!Number.isFinite(v.origin.lat)||!Number.isFinite(v.origin.lon)||!time.test(v.start)||!time.test(v.end)||v.end<=v.start)return null;
      if(!whole(v.budget,0,10000000)||!whole(v.people,1,20)||!whole(v.count,2,5)||!['walk','transit','car','bicycle'].includes(v.transport))return null;
      return {region:v.region,origin:NaverDeviceRetention.fields(v.origin),start:v.start,end:v.end,budget:v.budget,budget_unlimited:v.budget_unlimited===true,people:v.people,count:v.count,transport:v.transport};
    }catch{return null;}
  },
  // 저장한 기록에서 출발지만 뺀다(시간·예산·인원·장소 수·이동 수단·시·도는 네이버 결과가 아니라 남긴다).
  dropOrigin(v){
    try{const {origin,...rest}=v;localStorage.setItem(this.key,JSON.stringify(rest));}catch{}
  },
  // 새 질의: 같은 종류(query)의 네이버 검색을 새로 하면 앞 검색에서 온 저장 출발지를 지운다.
  newQuery(query){
    try{
      const v=JSON.parse(localStorage.getItem(this.key));
      if(!v||!NaverDeviceRetention.isNaver(v.origin)||String(v.origin.naver_query||'local')!==query)return;
      this.dropOrigin(v);
    }catch{return;}
    this.changed?.();
  },
  forget(){try{localStorage.removeItem(this.key);}catch{}this.changed?.();}
};
