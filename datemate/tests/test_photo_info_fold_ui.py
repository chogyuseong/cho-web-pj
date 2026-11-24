"""'사진 정보' 접기를 열면 내용이 보인다 (2026-11-24 사용자 신고: '사진 정보 눌러도 안 나온다').

원인: 작은 카드(코스 카드의 장소 사진 미리보기·둘러보기)는 사진 설명(.place-photo-copy)을 숨기는 규칙이 있었는데, 2026-11-17 에 그 설명을
'사진 정보' 접기 안으로 옮긴 뒤에도 규칙이 남아 접기를 열어도 빈 상자였다. 식당 카드(.meal-photo)는 접기 안을 다시 보이게 하는 규칙이 있어 괜찮았다.
"""
import pytest

from test_functional_audit import audit_page  # noqa: F401  (fixture)
from test_results_extras_ui import mount_photo_routes, real_results

OPENED = """sel=>[...document.querySelectorAll(sel)].map(d=>{d.open=true;const c=d.querySelector('.place-photo-copy');
  return c?Math.round(c.getBoundingClientRect().height):-1;})"""


@pytest.mark.parametrize('width', [390, 1280])
def test_photo_info_fold_shows_its_content_in_the_course_preview(audit_page, width):  # noqa: F811
    page, base, _ = audit_page
    page.set_viewport_size({'width': width, 'height': 900})
    mount_photo_routes(page, base, count=2)
    page.route('**/api/places/*/blogs?*', lambda route: route.fulfill(json={'posts': [], 'message': ''}))
    real_results(page, base)
    page.evaluate("document.querySelectorAll('.plan-photo-details').forEach(d=>d.open=true)")
    page.wait_for_function("document.querySelectorAll('.plan-photo-preview details.photo-copy-fold').length>0")
    heights = page.evaluate(f"({OPENED})('.plan-photo-preview details.photo-copy-fold')")
    assert heights and all(h > 20 for h in heights), heights


def test_photo_info_fold_shows_its_content_in_explore(audit_page):  # noqa: F811
    page, base, _ = audit_page
    mount_photo_routes(page, base, count=2)
    page.get_by_role('button', name='장소 둘러보기', exact=True).click()
    page.wait_for_function("document.querySelectorAll('#catalog details.photo-copy-fold').length>0")
    heights = page.evaluate(f"({OPENED})('#catalog details.photo-copy-fold')")
    assert heights and all(h > 20 for h in heights), heights
