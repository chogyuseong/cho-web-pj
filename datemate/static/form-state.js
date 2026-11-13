/* Explicit edits survive subsequent natural-language parsing. */
const FormState={
  edited:new Set(),
  allowed:new Set(['people','budget','count','transport','setting','reservation','priority','max_walk','include_meal','themes','theme_mode','date_category','date_subcategory','meeting_type']),
  summary(data){
    const transport={walk:'도보',transit:'대중교통',car:'자가용',bicycle:'자전거'};
    return `${data.visit_date} · ${data.start}–${data.end} · ${data.people}명 · ${data.budget_unlimited?'예산 무관':Number(data.budget).toLocaleString('ko-KR')+'원'} ·${data.count}곳 · ${transport[data.transport]||data.transport}`;
  }
};
document.getElementById('conditions').addEventListener('change',event=>{
  if(FormState.allowed.has(event.target.name))FormState.edited.add(event.target.name);
});
/* ‘지난번처럼 추천’에 쓰는 조건. 이 브라우저에만 남기고, 자유 입력 문장과 날짜는 저장하지 않는다. */
const LastConditions={
  key:'datemate-last-conditions',
  changed:null,
  save(data){
    try{
      // 축제를 골라 바뀐 출발지(축제 장소)와 가상 장소 데모의 출발점은 ‘지난 지역’으로 남기지 않고 이전에 저장한 지역을 유지한다.
      const own=data.mode==='real'&&!data.festival&&data.origin;
      const previous=this.load();
      const area=own?{region:data.region,origin:{name:data.origin.name,lat:data.origin.lat,lon:data.origin.lon}}:previous&&{region:previous.region,origin:previous.origin};
      if(!area)return;
      // 예산 무관은 고른 경우에만 남긴다(없으면 예산 금액대로).
      localStorage.setItem(this.key,JSON.stringify({...area,start:data.start,end:data.end,budget:data.budget,...(data.budget_unlimited?{budget_unlimited:true}:{}),people:data.people,count:data.count,transport:data.transport}));
      this.changed?.();
    }catch{}
  },
  load(){
    try{
      const v=JSON.parse(localStorage.getItem(this.key));
      const time=/^([01]\d|2[0-3]):[0-5]\d$/,whole=(n,min,max)=>Number.isInteger(n)&&n>=min&&n<=max;
      if(!v||typeof v.region!=='string'||!v.origin||typeof v.origin.name!=='string'||!v.origin.name.trim()||v.origin.name.length>200)return null;
      if(!Number.isFinite(v.origin.lat)||!Number.isFinite(v.origin.lon)||!time.test(v.start)||!time.test(v.end)||v.end<=v.start)return null;
      if(!whole(v.budget,0,10000000)||!whole(v.people,1,20)||!whole(v.count,2,5)||!['walk','transit','car','bicycle'].includes(v.transport))return null;
      return {region:v.region,origin:{name:v.origin.name,lat:v.origin.lat,lon:v.origin.lon},start:v.start,end:v.end,budget:v.budget,budget_unlimited:v.budget_unlimited===true,people:v.people,count:v.count,transport:v.transport};
    }catch{return null;}
  },
  forget(){try{localStorage.removeItem(this.key);}catch{}this.changed?.();}
};
