/* Explicit edits survive subsequent natural-language parsing. */
const FormState={
  edited:new Set(),
  allowed:new Set(['people','budget','count','transport','setting','reservation','priority','max_walk','include_meal','themes','theme_mode','date_category','date_subcategory']),
  summary(data){
    const transport={walk:'도보',transit:'대중교통',car:'자가용',bicycle:'자전거'};
    return `${data.visit_date} · ${data.start}–${data.end} · ${data.people}명 · ${Number(data.budget).toLocaleString('ko-KR')}원 · ${data.count}곳 · ${transport[data.transport]||data.transport}`;
  }
};
document.getElementById('conditions').addEventListener('change',event=>{
  if(FormState.allowed.has(event.target.name))FormState.edited.add(event.target.name);
});
