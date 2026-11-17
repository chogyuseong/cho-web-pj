"""가독성 정리 1단계(2026-11-17): 장소 카드는 이름 → 한 줄 요약 순서, 출처 문장·사진 정보는 접고,
구간 설명이 모두 같으면 한 번만, 네이버 지도 찾기는 한 줄 링크 묶음."""
from test_functional_audit import audit_page, generate  # noqa: F401


def test_stop_card_reads_name_then_one_summary_line(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    generate(page)
    card = page.evaluate("""()=>{const c=document.querySelector('#plan-detail .timeline-card');
      const kids=[...c.children].map(e=>e.tagName+(e.className?'.'+e.className.split(' ')[0]:''));
      const meta=c.querySelector('.stop-meta');
      return {first:kids[0],second:kids[1],meta:meta.innerText,source:!!c.querySelector('details.stop-source:not([open]) p.hint'),
        nameSize:parseFloat(getComputedStyle(c.querySelector('h4')).fontSize),
        dupTime:[...c.querySelectorAll(':scope > .small')].length};}""")
    assert card['first'] == 'H4' and card['second'] == 'P.stop-meta', card
    assert '분 머묾' in card['meta'] and '2인' in card['meta'], card
    assert card['source'] and card['dupTime'] == 0, card
    assert card['nameSize'] >= 20, card
    # 비용·머무는 시간은 줄 중간에서 끊기지 않는다.
    assert page.evaluate("getComputedStyle(document.querySelector('#plan-detail .stop-meta .stop-cost')).whiteSpace") == 'nowrap'
    assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')


def test_same_leg_note_is_written_once_above_the_timeline(audit_page):
    page, base, errors = audit_page
    generate(page)
    state = page.evaluate("""()=>({shared:sharedLegSource(selected),
      perLeg:document.querySelectorAll('#plan-detail .route-line-source').length,
      once:document.querySelectorAll('#plan-detail .route-source-note').length})""")
    if state['shared']:
        assert state == {'shared': state['shared'], 'perLeg': 0, 'once': 1}, state
    else:
        assert state['once'] == 0, state
    assert page.evaluate("sharedLegSource({legs:[{source:'a'},{source:'a'}]})") == 'a'
    assert page.evaluate("sharedLegSource({legs:[{source:'a'},{source:'b'}]})") is None
    assert page.evaluate("sharedLegSource({legs:[{source:'a'}]})") is None


def test_map_links_are_one_compact_row(audit_page):
    page, base, errors = audit_page
    page.set_viewport_size({'width': 390, 'height': 844})
    generate(page)
    links = page.locator('#plan-detail .map-link-list a')
    names = page.evaluate('selected.places.map(p=>p.name)')
    assert links.all_inner_texts() == [f'{i + 1}. {name}' for i, name in enumerate(names)]
    height = page.evaluate("document.querySelector('#plan-detail .map-link-list').getBoundingClientRect().height")
    assert height < 120, height  # 전에는 화면 폭 단추 3개(약 170px)
