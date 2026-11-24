"""약속 당일 도구(static/day-of.js): 마지막 출발 시각(24), 한 곳씩 크게 보기(39), 현장용 일정 복사(43)."""
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401 (fixture)


def test_last_departure_note_cases(audit_page):
    page, _, _ = audit_page
    notes = page.evaluate("""()=>{
      const base=(extra)=>Object.assign({conditions:{end:'21:00',return_home:true},places:[{name:'a'},{name:'b'}],
        legs:[{minutes:10},{minutes:12},{minutes:30,status:'estimated'}],timeline:[{departure:'18:00'},{departure:'20:00'}]},extra);
      return [
        lastDepartureNote(base({})),
        lastDepartureNote(base({timeline:[{departure:'18:00'},{departure:'20:45'}]})),
        lastDepartureNote(base({legs:[{minutes:10},{minutes:12},{minutes:null}]})),
        lastDepartureNote(base({conditions:{end:'21:00',return_home:false},legs:[{minutes:10},{minutes:12}]})),
      ];
    }""")
    assert notes[0] == '종료 21:00에 맞추려면 마지막 장소에서 늦어도 20:30에 출발해야 해요(귀가 30분 · 추정). 지금 계획은 20:00 출발 · 여유 30분.'
    assert notes[1].endswith('지금 계획(20:45 출발)은 15분 늦어요.')
    assert '귀가 시간을 몰라' in notes[2]
    assert notes[3] == '종료 21:00 기준 · 귀가를 정하지 않아 마지막 장소를 21:00까지 마치면 돼요(지금 계획은 20:00에 마침).'


def test_step_view_and_field_itinerary_work_offline_on_a_phone(audit_page):
    page, _, _ = audit_page
    generate(page)
    wait_for_selected_detail(page)
    page.set_viewport_size({'width': 390, 'height': 844})
    tools = page.locator('#plan-detail .day-of-tools')
    assert '종료' in tools.locator('.last-departure').inner_text()
    page.evaluate("Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.fieldText=text;}}})")
    page.context.set_offline(True)
    try:
        tools.get_by_role('button', name='현장용 일정 복사').click()
        page.wait_for_function('!!window.fieldText')
    finally:
        page.context.set_offline(False)
    text = page.evaluate('window.fieldText')
    names = page.evaluate('selected.places.map(p=>p.name)')
    times = page.evaluate("selected.timeline.map(t=>t.arrival+'~'+t.departure)")
    assert all(f'{i + 1}. {t} {n}' in text for i, (t, n) in enumerate(zip(times, names)))
    assert '/shared#' not in text, '링크를 만들지 않는다(서버 요청 없음)'
    tools.get_by_role('button', name='한 곳씩 크게 보기').click()
    dialog = page.locator('#dialog')
    assert dialog.locator('.step-name').inner_text() == names[0] and '1 / ' in dialog.locator('.step-count').inner_text()
    assert dialog.get_by_role('button', name='← 이전').is_disabled()
    dialog.get_by_role('button', name='다음 →').click()
    assert dialog.locator('.step-name').inner_text() == names[1]
    assert dialog.get_by_role('link', name='지도에서 열기 ↗').count() == 1
    assert page.evaluate('document.documentElement.scrollWidth<=document.documentElement.clientWidth')


# 2026-11-24 점검 F5: 「한 곳씩 크게 보기」가 축제를 건너뛰어 '현장용 일정 복사'와 어긋났다.
# 장소 2곳(A·B) 코스에 축제를 맨 앞·중간(A 뒤)·끝에 둔 세 경우. 구간 분은 서로 달라 어느 구간을 적었는지 가려낸다.
STEP_PLAN = """(visit)=>({
  id:'p1',
  conditions:{visit_date:'2026-12-01',start:'10:00',end:'19:00',return_home:false,festival:{title:'빛축제'}},
  places:[{id:'a',name:'A',address:''},{id:'b',name:'B',address:''}],
  timeline:[{arrival:'10:10',departure:'11:40'},{arrival:'12:55',departure:'14:25'}],
  legs:[{minutes:11,mode:'walk'},{minutes:17,mode:'walk'}],
  festival_visit:Object.assign({title:'빛축제',arrival:'11:50',departure:'12:50'},visit)
})"""

# 대화상자를 열고 '다음'을 끝까지 눌러 단계마다 [위쪽 표시, 이름, 구간 줄, 지도 링크 수]를 모은다.
# button()(app.js)은 누른 동작을 Promise 로 미뤄 실행하므로, 누를 때마다 한 틱 기다린다.
WALK = """async (plan)=>{
  showStepDialog(plan);
  const d=document.querySelector('#dialog'),got=[];
  for(let guard=0;guard<10;guard++){  // 단추가 끝에서 막히지 않아도 테스트가 멈추지 않게
    got.push([d.querySelector('.step-count').textContent,d.querySelector('.step-name').textContent,
              d.querySelector('.step-view .hint').textContent,d.querySelectorAll('.step-view a').length]);
    const next=[...d.querySelectorAll('button')].find(b=>b.textContent==='다음 →');
    if(next.disabled)break;
    next.click();
    await new Promise(resolve=>setTimeout(resolve,0));
  }
  return got;
}"""


def walk(page, visit):
    return page.evaluate(f'()=>({WALK})(({STEP_PLAN})({visit}))')


def test_step_view_includes_the_festival_where_the_course_visits_it(audit_page):
    page, _, _ = audit_page
    # 중간: A → (행사장으로 9분) 축제 → (행사장에서 17분) B.
    middle = walk(page, "{position:'middle',after:0,leg:{minutes:9,mode:'walk'}}")
    assert [s[:2] for s in middle] == [['1 / 2', 'A'], ['축제', '빛축제'], ['2 / 2', 'B']]
    assert '11분' in middle[0][2] and '행사장' not in middle[0][2]
    assert middle[1][2].startswith('행사장까지') and '9분' in middle[1][2]
    assert middle[2][2].startswith('축제 행사장에서 여기까지') and '17분' in middle[2][2]
    # 축제 단계에는 지도 링크가 없다(기록에 행사장 주소·좌표가 없음). 장소 단계는 하나씩.
    assert [s[3] for s in middle] == [1, 0, 1]
    # 맨 앞: 코스가 행사장에서 시작 — 축제로 가는 구간 줄이 없고, 첫 장소 구간은 행사장에서 출발.
    first = walk(page, "{position:'first'}")
    assert [s[:2] for s in first] == [['축제', '빛축제'], ['1 / 2', 'A'], ['2 / 2', 'B']]
    assert first[0][2] == '' and first[1][2].startswith('축제 행사장에서 여기까지')
    assert first[2][2].startswith('여기까지')
    # 끝: B 뒤에 축제, 들어가는 구간은 festival.leg.
    last = walk(page, "{position:'last',leg:{minutes:9,mode:'walk'}}")
    assert [s[:2] for s in last] == [['1 / 2', 'A'], ['2 / 2', 'B'], ['축제', '빛축제']]
    assert last[2][2].startswith('행사장까지') and not last[1][2].startswith('축제 행사장')
    # 축제 없는 코스는 예전과 같다.
    plain = page.evaluate(f"async ()=>{{const p=({STEP_PLAN})({{}});delete p.festival_visit;return await ({WALK})(p);}}")
    assert [s[:2] for s in plain] == [['1 / 2', 'A'], ['2 / 2', 'B']]
    # 자리가 잘못 저장된 중간 기록(마지막 장소 뒤)은 맨 앞 축제로 본다 — 현장용 일정 복사와 같은 판단.
    broken = walk(page, "{position:'middle',after:1}")
    assert broken[0][:2] == ['축제', '빛축제']


def test_step_view_order_matches_the_field_itinerary(audit_page):
    page, _, _ = audit_page
    for visit in ("{position:'first'}", "{position:'middle',after:0,leg:{minutes:9,mode:'walk'}}",
                  "{position:'last',leg:{minutes:9,mode:'walk'}}"):
        names = [s[1] for s in walk(page, visit)]
        assert names.count('빛축제') == 1, (visit, names)
        text = page.evaluate(f'()=>fieldItineraryText(({STEP_PLAN})({visit}))')
        # 현장용 일정에서 각 이름이 처음 나오는 자리의 순서가 단계 순서와 같다.
        positions = [text.index(' ' + n if n != '빛축제' else '축제 · 빛축제') for n in names]
        assert positions == sorted(positions), (visit, names, text)


def test_step_view_shows_the_place_photo(audit_page):
    """2026-11-24 사용자 요청: 한 곳씩 크게 보기에서 그 장소 사진도 보인다(코스 화면과 같은 사진 패널). 축제 단계·가상 장소에는 없다."""
    from test_results_extras_ui import mount_photo_routes
    page, base, _ = audit_page
    mount_photo_routes(page, base, count=1)
    got = page.evaluate(f"""async ()=>{{
      const plan=({STEP_PLAN})({{position:'middle',after:0,leg:{{minutes:9,mode:'walk'}}}});
      plan.conditions.mode='real';
      showStepDialog(plan);
      const d=document.querySelector('#dialog'),rows=[];
      for(let guard=0;guard<10;guard++){{
        const panel=d.querySelector('.step-view .place-photo-panel');
        if(panel)await new Promise(r=>{{const t=Date.now();(function wait(){{const img=panel.querySelector('img');if((img&&!img.hidden&&img.complete&&img.naturalWidth)||Date.now()-t>5000)r();else setTimeout(wait,50);}})();}});
        const img=panel?.querySelector('img');
        rows.push([d.querySelector('.step-name').textContent,!!panel,!!(img&&!img.hidden&&img.naturalWidth),
                   panel?!!(d.querySelector('.step-name').compareDocumentPosition(panel)&Node.DOCUMENT_POSITION_FOLLOWING):null]);
        const next=[...d.querySelectorAll('button')].find(b=>b.textContent==='다음 →');
        if(next.disabled)break;
        next.click();await new Promise(r=>setTimeout(r,0));
      }}
      return rows;
    }}""")
    assert [r[0] for r in got] == ['A', '빛축제', 'B']
    assert got[0][1:] == [True, True, True] and got[2][1:] == [True, True, True], got
    assert got[1][1] is False, '축제 단계에는 사진 패널이 없다(행사장 사진 자료가 없음)'
    # 가상 장소(데모)는 사진 패널을 넣지 않는다.
    demo = page.evaluate(f"""async ()=>{{const p=({STEP_PLAN})({{position:'first'}});p.conditions.mode='demo';showStepDialog(p);
      await new Promise(r=>setTimeout(r,0));return document.querySelectorAll('#dialog .step-view .place-photo-panel').length;}}""")
    assert demo == 0
