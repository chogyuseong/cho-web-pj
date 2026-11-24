"""식사 추가·합의 코스 미리보기의 축제 변화 안내 (2026-11-24 점검 F4).

- 서버: 초안(app/experience.make_draft)이 원래 코스와 견줘 plan['festival_change'] 를 싣는다. 예전에는 식사 초안만
  meal_draft 에서 실었고(자동차 경로 재조회로 축제 자리가 다시 바뀌면 낡은 안내), 합의 초안은 아예 싣지 않아 확정 뒤에도 안내가 없었다.
- 화면: 미리보기(static/experience.js showDraft)가 그 한 줄을 확정 단추 앞에 보여 준다. 장소 바꾸기·레저·순서 제안과 같은 모양
  ('warning festival-change-note').
"""
import copy

from fastapi.testclient import TestClient

from app import experience, store
from app.main import app
from test_festival_middle import planned, save
from test_functional_audit import audit_page  # noqa: F401  (브라우저 고정 장치)


def drafted(change):
    """중간 축제 코스를 저장하고, change(초안 plan 을 고치는 함수)를 거친 초안을 합의 초안으로 만든다."""
    with TestClient(app) as client:
        stored = save(client, planned())
        owner = store.owner_of(client.cookies['dm_session'])
        plan = copy.deepcopy(stored)
        change(plan)
        return experience.make_draft(plan, stored, owner, 'agreement', '요약', vote_snapshot={})


def test_agreement_draft_notes_a_dropped_festival():
    draft = drafted(lambda plan: plan.pop('festival_visit'))
    assert draft['plan']['festival_change'] == '‘점검 빛축제’ 축제가 일정에서 빠져요(바꾼 코스로는 운영 시간에 맞지 않아요).'


def test_agreement_draft_notes_a_moved_festival():
    def to_the_end(plan):
        plan['festival_visit'] = dict(plan['festival_visit'], position='last')
        plan['festival_visit'].pop('after', None)
    note = drafted(to_the_end)['plan']['festival_change']
    assert note.startswith('‘점검 빛축제’ 축제 자리가 바뀌어요: 1번째 장소 뒤 → 코스 끝')


def test_draft_with_the_festival_in_place_has_no_note_even_if_one_was_left_over():
    # 같은 자리면 안내가 없다. 앞선 변경에서 남은 안내도 지운다(festival_time.set_change_note).
    draft = drafted(lambda plan: plan.update(festival_change='앞선 변경의 안내'))
    assert 'festival_change' not in draft['plan']


PREVIEW = """(note)=>{
  const plan=(extra)=>Object.assign({id:'p1',places:[{name:'A'},{name:'B'}],finish:'18:00',minutes:300,total:[10000,20000],costs:[]},extra);
  selected=plan({});
  const draft={summary:'요약',blocking:[],plan:plan(note?{festival_change:note}:{})};
  showDraft(selected,draft,()=>{});
  const d=document.querySelector('#dialog'),found=d.querySelector('.festival-change-note'),apply=[...d.querySelectorAll('button')].find(b=>b.textContent==='이 변경안으로 확정');
  return [found?found.textContent:null,found?!!(found.compareDocumentPosition(apply)&Node.DOCUMENT_POSITION_FOLLOWING):null];
}"""


def test_preview_shows_the_festival_change_before_the_apply_button(audit_page):  # noqa: F811
    page, _, _ = audit_page
    text, before_apply = page.evaluate(f"()=>({PREVIEW})('‘빛축제’ 축제가 일정에서 빠져요(바꾼 코스로는 운영 시간에 맞지 않아요).')")
    assert text == '‘빛축제’ 축제가 일정에서 빠져요(바꾼 코스로는 운영 시간에 맞지 않아요).' and before_apply
    assert page.evaluate(f'()=>({PREVIEW})(null)') == [None, None]
