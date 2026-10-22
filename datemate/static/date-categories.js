let dateCategoryOptions={};
function mountDateCategories(options){
  dateCategoryOptions=options;
  const major=document.getElementById('date-category-tabs');
  major.replaceChildren();
  for(const name of Object.keys(options)){
    const tab=button(name,()=>setDateClassification(name,''),'date-category-tab');
    tab.dataset.category=name;
    tab.setAttribute('aria-controls','date-subcategories');
    major.append(tab);
  }
  setDateClassification('콘셉트별','');
}
function setDateClassification(category,subcategory=''){
  if(!dateCategoryOptions[category])return;
  form.elements.date_category.value=category;
  document.querySelectorAll('[data-category]').forEach(tab=>tab.setAttribute('aria-pressed',String(tab.dataset.category===category)));
  const list=document.getElementById('date-subcategories');
  list.replaceChildren();
  const all=node('label'),any=node('input');
  any.type='radio';any.name='date_subcategory';any.value='';any.checked=!subcategory;
  all.append(any,node('span','전체'));list.append(all);
  for(const name of dateCategoryOptions[category]){
    const label=node('label'),input=node('input');
    input.type='radio';input.name='date_subcategory';input.value=name;input.checked=name===subcategory;
    label.append(input,node('span',name));list.append(label);
  }
  document.getElementById('date-subcategory-title').textContent=category+' 소분류';
  const notes={
    '계절별':'계절 분위기에 맞는 장소 유형으로 추천해요. 실제 기온이나 개화·단풍 상태를 보장하지는 않아요.',
    '날씨별':'원하는 날씨를 직접 골라주세요. 비·눈 오는 날은 실내 장소로 찾으며, 실시간 예보는 조회하지 않아요.',
    '콘셉트별':'오늘 함께 느끼고 싶은 분위기를 골라주세요.',
    '타입별':'함께 즐기고 싶은 데이트 스타일을 골라주세요. 성격을 진단하는 분류는 아니에요.'};
  document.getElementById('date-category-note').textContent=notes[category];
  document.querySelectorAll('[name=themes]').forEach(input=>input.checked=false);
  document.querySelectorAll('[data-mood]').forEach(item=>item.setAttribute('aria-pressed','false'));
}
