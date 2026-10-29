/* One short needs form; keep defaults in the form for existing API integrations. */
document.addEventListener('DOMContentLoaded',()=>{
  const form=document.getElementById('conditions');
  const retained=document.createElement('div');retained.hidden=true;retained.id='automatic-plan-settings';
  while(form.firstChild)retained.append(form.firstChild);
  form.append(retained);form.classList.add('simple-plan-form');
  const intro=node('p','지역·일시·예산만 정하면 시작할 수 있어요. 기본은 2인, 3곳 코스예요.','simple-form-intro');
  form.append(intro,button('내가 결정한 코스 다시 보기',()=>PlanningStudy.showDecisions(),'secondary saved-decisions'));
  function group(title,required=false){const section=node('fieldset',undefined,'simple-form-group'),legend=node('legend',title);if(required)legend.append(node('span','필수','field-requirement'));section.append(legend);form.append(section);return section;}
  function take(name){return form.elements[name]?.closest('label');}
  const region=group('1. 어디에서 만날까요?',true);
  region.append(document.getElementById('origin-location'),node('p','서울 지역명이나 주소를 검색하거나 지도에서 골라주세요.','hint'));
  const when=group('2. 언제, 몇 시에 만날까요?',true),time=node('div',undefined,'field-grid');
  when.append(take('visit_date'));time.append(take('start'),take('end'));when.append(time);
  const budget=group('3. 전체 예산은 얼마인가요?',true);
  const preview=document.querySelector('.price-input-preview');
  budget.append(take('budget'),node('p','두 사람 합계예요. 인원을 바꾸면 해당 인원 전체의 예산으로 계산해요.','hint'));
  if(preview)budget.append(preview);
  const preference=group('4. 어떤 하루를 원하세요? (선택)');
  const request=take('request');request.firstChild.textContent='원하는 활동이나 피하고 싶은 것을 알려주세요';
  form.elements.request.placeholder='예: 카페 투어 하고 싶어요 / 전시 보고 산책, 실내 위주로 / 매운 음식은 제외';
  const ideas=node('div',undefined,'simple-activity-ideas');ideas.setAttribute('aria-label','원하는 활동 입력 예시');
  for(const [label,text] of [['카페','카페 투어'],['맛집','맛집 탐방'],['산책','산책'],['전시','전시 관람'],['체험','공방 체험']]){
    ideas.append(button(label,()=>{const input=form.elements.request;input.value=input.value.trim()?input.value.trim()+', '+text:text;input.dispatchEvent(new Event('input',{bubbles:true}));input.focus();},'secondary'));
  }
  preference.append(ideas,request,document.getElementById('parse-notice'));
  const optional=node('details',undefined,'simple-extra-options');optional.append(node('summary','인원·이동·식사 설정 (선택)'));
  const extras=node('div',undefined,'field-grid');
  for(const name of ['people','count','transport','setting'])extras.append(take(name));
  optional.append(extras,take('include_meal'));
  const feedback=take('use_feedback');if(feedback)optional.append(feedback);
  const buffer=node('label','이동 구간별 여유시간'),bufferSelect=node('select');bufferSelect.name='transition_buffer_minutes';
  for(const [value,title] of [[0,'기본 · 추가 여유 없음'],[5,'구간마다 5분 여유'],[10,'느긋하게 · 구간마다 10분 여유']]){const option=node('option',title);option.value=value;bufferSelect.append(option);}buffer.append(bufferSelect);optional.append(buffer);
  const hard=retained.querySelector('.experience-controls details');
  if(hard)optional.append(hard);
  const limits=node('details');limits.append(node('summary','이동 제한·가격 추정 설정'));
  for(const name of ['max_leg','max_walk','allow_price_estimates']){const label=take(name);if(label)limits.append(label);}
  optional.append(limits);
  PlanningStudy.mount(optional);
  form.append(optional,document.getElementById('submit-plan'),node('p','조건에 맞는 후보가 부족하면 범위를 넓혀 찾고, 바뀐 조건을 알려드려요. 비용·이동 시간은 추정이 포함될 수 있어요.','hint'));
  // These are automatic planning defaults, not additional choices the user has to make.
  form.elements.trust_mode.value='balanced';form.elements.mbti.value='';form.elements.use_mbti.checked=false;
  retained.querySelectorAll('[required]').forEach(input=>input.required=false);
});
