"""인쇄 / PDF: 선택한 코스의 제목·일정·장소가 종이에 나오고, 단추·다른 코스·부가 구역은 빠진다."""
import pytest
from test_functional_audit import audit_page, generate, wait_for_selected_detail  # noqa: F401

# 화면에 실제로 그려지는지(display:none 조상이 있으면 상자가 없다).
SHOWN = "(selector)=>[...document.querySelectorAll(selector)].filter(el=>el.getClientRects().length>0).length"


def check_print_layout(page):
    title = page.locator('#results .plan-card h3').inner_text()
    names = page.evaluate('selected.places.map(p=>p.name)')
    arrivals = page.evaluate('selected.timeline.map(t=>t.arrival)')
    page.emulate_media(media='print')
    detail = page.locator('#plan-detail section.detail.panel').first
    assert detail.is_visible()
    height = detail.evaluate('(el)=>el.getBoundingClientRect().height')
    assert height > 300, height
    # 코스 제목과 일정·장소 이름, 비용 합계가 보인다.
    assert page.locator('#results .plan-card h3').is_visible()
    text = page.locator('#plan-detail').inner_text()
    for name in names:
        assert name in text, name
    for arrival in arrivals:
        assert arrival in text, arrival
    assert page.evaluate(SHOWN, '#plan-detail .stop h4') == len(names)
    assert page.evaluate(SHOWN, '#plan-detail .route-line') >= len(names)
    assert page.evaluate(SHOWN, '#plan-detail .total-row') >= 2
    assert page.evaluate(SHOWN, '#plan-detail .execution-summary') == 1
    # 종이에서 쓸모없는 조작 요소, 고르지 않은 코스와 부가 구역은 숨긴다.
    assert page.evaluate(SHOWN, 'button') == 0
    assert not page.get_by_role('button', name='인쇄 / PDF').is_visible()
    for selector in ('.plan-option-tabs', '.comparison-details', '#progress', '#festival-section', '#plan-extras',
                     '#popup-course', '.plan-map-rail', '.plan-map-slot', 'header', 'footer', '.conditions',
                     '.plan-share', '.privacy-controls', '.map-link-list', '.transport-bulk'):
        assert page.evaluate(SHOWN, selector) == 0, selector
    # 인쇄 문서 높이는 코스 상세가 대부분을 차지한다.
    doc = page.evaluate('document.documentElement.scrollHeight')
    assert height > doc * 0.5, (height, doc)
    page.emulate_media(media='screen')
    # 화면 모양은 그대로다.
    assert page.locator('.plan-option-tabs').is_visible()
    assert page.get_by_role('button', name='인쇄 / PDF').is_visible()
    return title, names, height, doc


@pytest.mark.parametrize('width', [1440, 390])
def test_print_shows_selected_plan_and_hides_controls(audit_page, width):
    page, base, errors = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    generate(page)
    check_print_layout(page)
    # 다른 코스를 고른 뒤에도 그 코스가 인쇄된다.
    page.locator('.plan-option-tabs button').nth(1).click()
    page.wait_for_function('document.querySelector(".plan-option-tabs button:nth-child(2)").getAttribute("aria-pressed")==="true"')
    wait_for_selected_detail(page)
    check_print_layout(page)


def test_print_pdf_contains_selected_plan(audit_page, tmp_path):
    pypdf = pytest.importorskip('pypdf')
    page, base, errors = audit_page
    generate(page)
    title, names, height, doc = check_print_layout(page)
    target = tmp_path / 'plan.pdf'
    # check_print_layout 가 화면 매체로 되돌려 두었으므로, 브라우저 인쇄와 같은 print 매체로 다시 맞춘다.
    page.emulate_media(media='print')
    page.pdf(path=str(target), format='A4', print_background=True)
    reader = pypdf.PdfReader(str(target))
    text = ''.join(sheet.extract_text() for sheet in reader.pages)
    squeezed = ''.join(text.split())
    for name in names:
        assert ''.join(name.split()) in squeezed, name
    assert ''.join(title.split()) in squeezed
    assert '인쇄/PDF' not in squeezed and '공유링크복사' not in squeezed
    assert 1 <= len(reader.pages) <= 12, len(reader.pages)
    print(f'print layout: detail {height:.0f}px, document {doc}px, pdf pages {len(reader.pages)}')


def test_print_lets_long_place_cards_split_across_pages(audit_page):
    """장소 카드를 통째로 다음 쪽에 넘기면 앞 쪽이 대부분 빈다(2026-11-17 운영 PDF 2·4쪽). 카드는 나뉘고 머리 줄은 아래 내용과 붙는다."""
    page, base, errors = audit_page
    generate(page)
    page.emulate_media(media='print')
    styles = page.evaluate("""()=>{const stop=document.querySelector('#plan-detail .stop');const head=stop.querySelector('h4');
      const parking=document.createElement('div');parking.className='parking-panel';document.querySelector('#plan-detail').append(parking);
      const result=[getComputedStyle(stop).breakInside,getComputedStyle(head).breakAfter,getComputedStyle(parking).breakInside];parking.remove();return result;}""")
    page.emulate_media(media='screen')
    assert styles == ['auto', 'avoid', 'avoid'], styles


def test_print_button_calls_print_inside_the_click(audit_page):
    """아이폰 Safari 는 사용자 조작 밖에서 부른 window.print() 를 무시한다(2026-11-17 신고). 누른 click 처리 안에서 바로 불러야 한다."""
    page, base, errors = audit_page
    generate(page)
    page.evaluate("window.print=()=>{window.printedIn=window.event?window.event.type:'outside-event';}")
    page.get_by_role('button', name='인쇄 / PDF', exact=True).click()
    page.wait_for_function('window.printedIn!==undefined')
    assert page.evaluate('window.printedIn') == 'click'
    # 데스크톱 브라우저에는 아이폰 안내가 없다.
    assert page.locator('.ios-print-hint').count() == 0


def test_iphone_sees_the_share_sheet_print_hint(audit_page):
    page, base, errors = audit_page
    page.add_init_script("Object.defineProperty(navigator,'userAgent',{get:()=>'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'})")
    page.reload(wait_until='networkidle')
    page.wait_for_function("typeof statusData!=='undefined'&&!!statusData&&document.querySelector('.simple-plan-form')")
    generate(page)
    hint = page.locator('.plan-share .ios-print-hint')
    assert hint.count() == 1 and '프린트' in hint.inner_text()
    page.emulate_media(media='print')
    assert not hint.is_visible()
    page.emulate_media(media='screen')
