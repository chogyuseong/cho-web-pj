// 홈 테마 카드·조건 화면의 지역 칩·현재 위치가 함께 쓰는 지역 채우기. 분위기·분류 설정은 건드리지 않는다.
// 출발지 이름이 시·도 이름으로 시작해야 서버의 지역 일치 검증을 통과한다.
function applyArea(region,origin){
  if(form.elements.mode.value!=='real'){form.elements.mode.value='real';form.elements.mode.dispatchEvent(new Event('change',{bubbles:true}));}
  // 지역 change 이벤트를 보내지 않는다. 보내면 방금 넣은 출발지가 지워진다.
  form.elements.region.value=region;
  locationState.origin={name:origin.name,lat:Number(origin.lat),lon:Number(origin.lon)};form.elements.origin_name.value=origin.name;
  // 네이버 검색에서 온 출발지는 받은 시각·검색 종류를 그대로 들고 간다(form-state.js NaverDeviceRetention, 기기 보관 24시간).
  if(NaverDeviceRetention.isNaver(origin))Object.assign(locationState.origin,{naver_at:Number(origin.naver_at),naver_query:String(origin.naver_query||'local')});
}
function applyPresetArea(card){
  applyArea(card.dataset.state,{name:card.dataset.origin,lat:card.dataset.lat,lon:card.dataset.lon});
}

/* '테마로 고르는 하루' 2트랙(2026-11-24 사용자 요청).
   · 오늘의 상황으로 고르기(#curation-situation): 지역을 정하지 않고 조건만 채운다. 카드는 아래 SITUATION_THEMES·SEASON_THEMES 로 그린다.
   · 주말 떠나기 좋은 동네(#curation-areas): index.html 의 button[data-preset] 5개. 지역·출발지·분위기(data-mood)·이동 수단(data-transport).
     같은 버튼을 조건 화면의 '인기 동네' 칩(simple-form.js)도 쓴다 — 동네를 더하거나 빼면 칩도 같이 바뀐다.
   테마 값(values)의 열쇠는 조건 폼 입력 이름 그대로다(app/models.py Conditions). themes 는 서버가 강하게 거르는 큰 분류 7개
   (app/models.py THEMES) 중에서만 고른다 — 세부 업종(방탈출·소품샵)은 서버에 없어 큰 분류로 묶었다.
   잔여 조건 막기: 처음 테마를 고를 때 THEME_FIELDS 의 값을 저장(baseline)해 두고, 다른 테마로 바꾸거나 [테마 해제]를 누르면
   저장한 값으로 되돌린 뒤 새 테마를 덮는다. 새 테마가 새 입력 이름을 쓰면 THEME_FIELDS 에도 더한다(안 더하면 다음 테마에 남는다). */
const THEME_FIELDS=['setting','max_walk','max_leg','start','end','count','stay_minutes','reservation','theme_mode','meeting_type','priority','include_meal','transport'];
const SITUATION_THEMES=[
  {key:'indoor',title:'비·더위 피하는 올-실내 코스',copy:'날씨 걱정 없이 쾌적하게 이어지는 하루',tags:['#실내만','#도보 최소화','#전시·공방'],
    values:{setting:'indoor',max_walk:15,max_leg:15,themes:['문화·예술','체험·제작','카페·미식']}},
  {key:'first-date',title:'어색함 없는 썸·소개팅 코스',copy:'대화가 자연스럽게 이어지는 편안한 동선',tags:['#4시간','#도보 15분 이하','#대화하기 좋은 곳'],
    values:{start:'13:00',end:'17:00',count:3,max_walk:15,meeting_type:'first',priority:'talk',themes:['문화·예술','카페·미식']}},
  {key:'activity',title:'손과 몸을 쓰는 이색 액티비티',copy:'밥과 카페만 오가던 날에서 한 걸음 벗어나는 하루',tags:['#체험 중심','#활동적','#식사 포함'],
    values:{theme_mode:'mix',priority:'activity',include_meal:true,themes:['체험·제작','오락·놀이','레저·활동']}},
  {key:'after-work',title:'퇴근 후 3시간 · 저녁과 야경',copy:'평일 저녁에도 부담 없이 알차게 보내는 밤',tags:['#18:30~21:30','#2곳','#저녁·산책'],
    values:{start:'18:30',end:'21:30',count:2,themes:['카페·미식','산책·풍경']}},
  {key:'anniversary',title:'기념일 · 오늘은 조금 특별하게',copy:'생일이나 N주년, 미리 준비하는 근사한 하루',tags:['#예약 필요한 곳 포함','#3곳','#분위기'],
    values:{reservation:true,count:3,meeting_type:'anniversary',themes:['카페·미식','문화·예술']}},
  {key:'rest',title:'최소 도보 · 지치지 않는 힐링',copy:'많이 걷기 힘든 날, 한 곳에서 오래 쉬는 코스',tags:['#도보 15분 제한','#장소당 2시간','#힐링'],
    values:{max_walk:15,stay_minutes:120,count:2,themes:['휴식·힐링','카페·미식','산책·풍경','문화·예술']}}
];
// 계절 카드: 지금 달(1~12)로 하나만 보인다(seasonFor). 분류는 '계절별' 소분류를 화면이 대신 넣은 것이라 우선순위로만 쓴다(app/taxonomy.classification_strict).
const SEASON_THEMES={
  spring:{key:'season-spring',title:'봄바람 · 꽃길 산책과 피크닉',copy:'햇살 좋은 날, 밖에서 오래 머무는 하루',tags:['#실외 포함','#산책·정원','#야외 카페'],
    values:{season:'봄',themes:['산책·풍경','카페·미식']}},
  summer:{key:'season-summer',title:'한여름 · 시원한 실내 피서 데이트',copy:'더위는 피하고 대화는 길게',tags:['#실내만','#도보 10분','#전시·북카페'],
    values:{season:'여름',setting:'indoor',max_walk:10,themes:['문화·예술','카페·미식']}},
  autumn:{key:'season-autumn',title:'선선한 가을 · 골목 산책과 노을',copy:'걷기 좋은 오후를 천천히 나눠 쓰는 날',tags:['#걷기 좋은 날','#산책·전시','#오후 코스'],
    values:{season:'가을',start:'13:00',end:'18:00',themes:['산책·풍경','카페·미식','문화·예술']}},
  winter:{key:'season-winter',title:'겨울 감성 · 따뜻한 실내와 연말 야경',copy:'따뜻한 곳에서 쉬다가 저녁 불빛을 보러 가는 날',tags:['#실내 위주','#저녁 산책','#따뜻한 카페'],
    values:{season:'겨울',start:'15:00',end:'21:00',themes:['카페·미식','문화·예술','산책·풍경']}}
};
// 히어로 '바로 시작' 칩(2026-11-24 리디자인 1단계, 가이드 2.2). 상황 테마 + 동네를 한 번에 채운다(동네만 있으면 동네 카드 그대로).
// area 출발지 이름은 시·도 이름으로 시작해야 서버의 지역 일치 검증을 통과한다. 한남·서촌은 동네 카드에 없어 기준 역 좌표를 여기 둔다
// (한남 = 6호선 한강진역, 서촌 = 3호선 경복궁역). 칩을 바꾸면 tests/test_redesign_shell_ui.py 의 기대값도 함께 고친다.
const HERO_QUICK_STARTS=[
  {label:'비 오는 날 성수 실내',situation:'indoor',area:{region:'서울',name:'서울 성수역 지역 중심',lat:37.5446,lon:127.0559,label:'서울 성수'}},
  {label:'퇴근 후 한남 3시간',situation:'after-work',area:{region:'서울',name:'서울 한남 한강진역 지역 중심',lat:37.5396,lon:127.0017,label:'서울 한남'}},
  {label:'강릉 바다 드라이브',preset:'강릉 안목해변'},
  {label:'어색함 없는 서촌 소개팅',situation:'first-date',area:{region:'서울',name:'서울 서촌 경복궁역 지역 중심',lat:37.5757,lon:126.9735,label:'서울 서촌'}}
];
function seasonFor(month){return month>=3&&month<=5?'spring':month>=6&&month<=8?'summer':month>=9&&month<=11?'autumn':'winter';}

// 배너에 보여 줄 '실제로 채운 조건' 문장(카드의 # 태그는 홍보 문구라 따로 둔다).
function themeConditionText(values){
  const out=[];
  if(values.setting==='indoor')out.push('실내만');
  if(values.max_walk)out.push(`전체 도보 ${values.max_walk}분 이하`);
  if(values.max_leg)out.push(`구간 이동 ${values.max_leg}분까지`);
  if(values.start)out.push(`${values.start}~${values.end}`);
  if(values.count)out.push(`${values.count}곳`);
  if(values.stay_minutes)out.push(`장소당 ${values.stay_minutes}분`);
  if(values.reservation)out.push('예약 필요한 곳 포함');
  if(values.meeting_type==='first')out.push('첫 만남');
  if(values.meeting_type==='anniversary')out.push('기념일');
  if(values.include_meal)out.push('식사 포함');
  if(values.transport)out.push({walk:'도보',transit:'대중교통',car:'자가용',bicycle:'자전거'}[values.transport]);
  if(values.season)out.push(`계절 ${values.season}`);
  if(values.themes?.length)out.push('분류 '+values.themes.join(', '));
  return out;
}

const ThemePresets=(()=>{
  let baseline=null,active=null;
  const fields=()=>THEME_FIELDS.map(name=>form.elements[name]).filter(Boolean);
  function setField(name,value){
    const input=form.elements[name];if(!input)return;
    if(input.type==='checkbox')input.checked=Boolean(value);else input.value=value==null?'':String(value);
    // 요약 줄·상세 조건 배지·칩 눌림이 따라오도록 사용자가 고친 것과 같은 이벤트를 보낸다(simple-form.js refresh·detailSummary).
    for(const type of ['input','change'])input.dispatchEvent(new Event(type,{bubbles:true}));
  }
  function setThemes(list){document.querySelectorAll('[name=themes]').forEach(input=>input.checked=list.includes(input.value));}
  function capture(){
    const values={};
    for(const input of fields())values[input.name]=input.type==='checkbox'?input.checked:input.value;
    return {values,themes:[...document.querySelectorAll('[name=themes]:checked')].map(i=>i.value),
      category:form.elements.date_category.value,subcategory:form.querySelector('[name=date_subcategory]:checked')?.value||'',
      region:form.elements.region.value,origin:locationState.origin};
  }
  function restore(saved){
    for(const [name,value] of Object.entries(saved.values))setField(name,value);
    // setDateClassification 은 분류 체크를 지우므로 먼저 부르고 체크를 되살린다.
    setDateClassification(saved.category||'콘셉트별',saved.subcategory);
    setThemes(saved.themes);
  }
  function begin(){if(baseline)restore(baseline);else baseline=capture();}
  function applyValues(values){
    if(values.season)setDateClassification('계절별',values.season);
    if(values.themes)setThemes(values.themes);
    for(const [name,value] of Object.entries(values))if(THEME_FIELDS.includes(name))setField(name,value);
  }
  return {
    // area: 히어로 칩처럼 동네까지 함께 정할 때(없으면 지금 고른 지역을 그대로 둔다).
    situation(theme,area){
      begin();applyValues(theme.values);
      if(area)applyArea(area.region,{name:area.name,lat:area.lat,lon:area.lon});
      active={kind:'situation',theme,area:area||null};return active;
    },
    area(card){
      begin();
      applyPresetArea(card);
      const mood=card.dataset.mood||'편안한 데이트';
      setDateClassification(['사교적인','활동적인'].includes(mood)?'타입별':'콘셉트별',mood);
      if(card.dataset.transport)setField('transport',card.dataset.transport);
      active={kind:'area',card};return active;
    },
    // [테마 해제]: 테마를 고르기 전 값으로 되돌린다. 동네 테마가 넣은 지역·출발지도 고르기 전으로(없었으면 비운다).
    clear(){
      if(!baseline)return;
      const saved=baseline;restore(saved);
      if(active?.kind==='area'||active?.area){
        locationState.origin=saved.origin;form.elements.region.value=saved.region;form.elements.origin_name.value=saved.origin?.name||'';
      }
      baseline=null;active=null;
    },
    // 동네 테마를 고른 뒤 다른 지역을 고르면 그 테마는 끝난 것으로 본다(값은 그대로 두고 되돌릴 기준만 버린다).
    forget(){baseline=null;active=null;},
    get active(){return active;}
  };
})();

(()=>{
  const situationGrid=document.getElementById('curation-situation'),areaGrid=document.getElementById('curation-areas');
  // 카드 모양: 배지 → 제목 → 한 줄 문구 → 조건 미리보기 태그. 동네 카드(index.html)도 같은 순서다.
  function situationCard(theme,badge){
    const card=node('button',undefined,'curation-card');card.type='button';card.dataset.situation=theme.key;
    const tags=node('span',undefined,'curation-tags');for(const tag of theme.tags)tags.append(node('span',tag));
    card.append(node('span',badge,'curation-badge'+(badge==='지금 시즌'?' is-season':'')),node('span',theme.title,'curation-mood'),node('span',theme.copy,'curation-copy'),tags);
    card.addEventListener('click',()=>pickSituation(theme));
    return card;
  }
  if(situationGrid){
    const season=SEASON_THEMES[seasonFor(new Date().getMonth()+1)];
    situationGrid.append(situationCard(season,'지금 시즌'),...SITUATION_THEMES.map(theme=>situationCard(theme,'상황 테마')));
  }

  // 탭: 화살표·Home·End 로 옮겨 다닌다(WAI-ARIA 탭 패턴).
  const tabs=[...document.querySelectorAll('#curation [role=tab]')];
  function selectTab(tab,focus){
    for(const item of tabs){
      const on=item===tab;item.setAttribute('aria-selected',String(on));item.tabIndex=on?0:-1;
      document.getElementById(item.getAttribute('aria-controls')).hidden=!on;
    }
    if(focus)tab.focus();
  }
  tabs.forEach((tab,i)=>{
    tab.addEventListener('click',()=>selectTab(tab,false));
    tab.addEventListener('keydown',event=>{
      const next={ArrowRight:i+1,ArrowLeft:i-1,Home:0,End:tabs.length-1}[event.key];
      if(next===undefined)return;
      event.preventDefault();selectTab(tabs[(next+tabs.length)%tabs.length],true);
    });
  });

  function ready(){if(document.querySelector('[name=themes]'))return true;toast('장소 정보를 준비 중이에요. 잠시 후 다시 눌러 주세요.');return false;}
  function markPressed(card){document.querySelectorAll('#curation .curation-card').forEach(item=>item.setAttribute('aria-pressed',String(item===card)));}
  // 조건 화면 맨 위 안내(#preset-tags). 상황 테마: 지역·날짜를 고르라고, 동네 테마: 날짜·시간만 확인하고 바로 추천받으라고.
  function banner(){
    let box=document.getElementById('preset-tags');
    if(!box){box=node('div',undefined,'preset-tags');box.id='preset-tags';box.setAttribute('role','group');box.setAttribute('aria-label','고른 테마로 채운 조건');form.prepend(box);}
    // '1. 어디에서 만날까요?' 바로 위에 둔다. 폼 맨 위에 두면 자유 입력 칸이 사이에 끼어 안내와 지역 칸이 한 화면에 들어오지 않았다(375px).
    const group=areaGroup();if(group&&box.nextElementSibling!==group)group.before(box);
    return box;
  }
  function showBanner(state){
    const box=banner(),name=state.kind==='area'?state.card.dataset.preset:state.theme.title;
    const message=state.kind==='area'
      ?`‘${name}’ 추천 조건을 채웠어요. 날짜와 시간만 확인하고 바로 추천받아 보세요.`
      :state.area?`‘${name}’ 조건과 ${state.area.label} 지역을 채웠어요. 날짜와 시간만 확인하고 바로 추천받아 보세요.`
      :`‘${name}’ 조건을 채웠어요. 데이트할 지역과 날짜만 골라 주세요.`;
    const values=state.kind==='area'?{transport:state.card.dataset.transport}:state.theme.values;
    const conditions=themeConditionText(values);
    if(state.kind==='area')conditions.unshift(state.card.dataset.preset,state.card.dataset.mood);
    const tags=node('div',undefined,'preset-tag-list');
    for(const text of conditions)if(text)tags.append(node('span',text,'tag'));
    const actions=node('div',undefined,'preset-actions');
    const go=button('이 조건으로 바로 추천받기',()=>form.requestSubmit(),'primary preset-go');
    go.hidden=!locationState.origin;
    actions.append(go,button('테마 해제',clearTheme,'secondary preset-clear'));
    box.replaceChildren(node('p',message,'hint'),tags,actions);
    box.hidden=false;
    return go;
  }
  function areaGroup(){return document.getElementById('origin-location')?.closest('.simple-form-group');}
  function pickSituation(theme,area){
    if(!ready())return;
    const state=ThemePresets.situation(theme,area);
    markPressed(document.querySelector(`[data-situation="${theme.key}"]`));
    document.getElementById('nav-plan').click();
    const go=showBanner(state);
    document.querySelector('#parse-notice').textContent=theme.title+' 조건을 채웠어요.';
    toast(theme.title+' 테마를 골랐어요.');
    requestAnimationFrame(()=>{
      if(locationState.origin){go.focus({preventScroll:true});go.scrollIntoView({block:'center',behavior:'instant'});return;}
      // 지역을 아직 안 골랐으면 '어디에서 만날까요?'를 강조하고 그리로 옮긴다. 지역을 고르면 강조를 끈다(syncBanner).
      // 화면은 안내(#preset-tags)가 맨 위에 오게 옮긴다 — 강조한 지역 묶음은 바로 아래에 이어서 보인다(지역 묶음으로 옮기면 안내가 밀려 올라갔다).
      const group=areaGroup();if(!group)return;
      group.classList.add('needs-area');group.tabIndex=-1;
      document.getElementById('preset-tags').scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
      group.focus({preventScroll:true});
    });
  }
  function pickArea(card){
    if(!ready())return;
    const state=ThemePresets.area(card);
    markPressed(card);
    document.getElementById('nav-plan').click();
    const go=showBanner(state);
    document.querySelector('#parse-notice').textContent=card.dataset.preset+' 지역과 데이트 분위기를 입력했어요. 날짜·시간·예산을 확인하고 추천받아 주세요.';
    toast(card.dataset.preset+'에서 시작하는 테마를 골랐어요.');
    requestAnimationFrame(()=>{go.focus({preventScroll:true});go.scrollIntoView({block:'center',behavior:'instant'});});
  }
  function clearTheme(){
    ThemePresets.clear();
    const box=document.getElementById('preset-tags');if(box)box.hidden=true;
    areaGroup()?.classList.remove('needs-area');
    markPressed(null);
    document.querySelector('#parse-notice').textContent='테마를 해제하고 고르기 전 조건으로 되돌렸어요.';
    toast('테마를 해제했어요.');
  }
  // 지역을 고르면 강조를 끄고 '바로 추천받기'를 보인다. 동네 테마 뒤 다른 지역을 고르면 그 동네 안내는 맞지 않으니 접는다.
  function syncBanner(){
    const state=ThemePresets.active,box=document.getElementById('preset-tags');
    if(locationState.origin)areaGroup()?.classList.remove('needs-area');
    if(!state||!box||box.hidden)return;
    if(state.kind==='area'&&locationState.origin?.name!==state.card.dataset.origin){box.hidden=true;ThemePresets.forget();markPressed(null);return;}
    const go=box.querySelector('.preset-go');if(go)go.hidden=!locationState.origin;
  }
  document.addEventListener('click',()=>setTimeout(syncBanner));
  form.addEventListener('change',()=>setTimeout(syncBanner));
  areaGrid?.querySelectorAll('[data-preset]').forEach(card=>card.addEventListener('click',()=>pickArea(card)));

  // 히어로(index.html .hero-start): 바로 시작 칩과 한 줄 입력.
  const quick=document.getElementById('hero-quick');
  for(const start of quick?HERO_QUICK_STARTS:[]){
    const chip=button(start.label,()=>{
      if(start.preset){const card=areaGrid?.querySelector(`[data-preset="${start.preset}"]`);if(card)pickArea(card);return;}
      const theme=SITUATION_THEMES.find(item=>item.key===start.situation);
      if(theme)pickSituation(theme,start.area);
    });
    chip.type='button';chip.dataset.quick=start.label;quick.append(chip);
  }
  // 한 줄 입력 → 조건 화면의 '어떤 데이트를 꿈꾸나요?' 칸에 넣고 해석 단추(#parse, app.js applyRequest)를 누른다.
  // 해석은 지역을 정하지 않으므로, 지역이 비어 있으면 상황 테마처럼 '어디에서 만날까요?'를 강조한다.
  document.getElementById('hero-command')?.addEventListener('submit',event=>{
    event.preventDefault();
    const input=document.getElementById('hero-command-input'),text=input.value.trim();
    if(!text){input.focus();toast('원하는 데이트를 한 줄로 적어 주세요.');return;}
    if(!ready())return;
    const request=form.elements.request;request.value=text;request.dispatchEvent(new Event('input',{bubbles:true}));
    document.getElementById('nav-plan').click();
    document.getElementById('parse').click();
    requestAnimationFrame(()=>{
      const dream=document.querySelector('.simple-dream')||request;
      if(!locationState.origin)areaGroup()?.classList.add('needs-area');
      dream.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
    });
  });
})();
