"""코스 카드의 '장소 사진 N곳' 미리보기(static/place-photos.js planPhotoPreview)에서 한 장소의 '블로그 후기 보기'를 펼칠 때 (2026-11-24 사용자 신고).

예전: 세 칸이 한 줄(그리드)이라 한 칸을 펼치면 양옆 칸도 같은 높이로 늘어나 빈칸이 생겼고, 펼친 칸 안 후기도 보이지 않았다.
지금: 펼친 칸만 늘어나고, 펼친 칸 안에 받은 글이 보인다.
"""
from test_functional_audit import audit_page  # noqa: F401  (fixture)
from test_results_extras_ui import POSTS, mount_photo_routes, real_results


def open_first_preview_blog(page, base):
    page.set_viewport_size({'width': 1440, 'height': 1000})
    mount_photo_routes(page, base, count=1)
    page.route('**/api/places/*/blogs?*', lambda route: route.fulfill(json={
        'posts': POSTS, 'query': '어느 장소 후기', 'search_url': 'https://search.naver.com/search.naver?where=blog&query=x', 'message': ''}))
    real_results(page, base)
    page.evaluate("document.querySelectorAll('.plan-photo-details').forEach(d=>d.open=true)")
    preview = page.locator('.plan-photo-preview').first
    preview.wait_for()
    preview.scroll_into_view_if_needed()
    before = preview.evaluate("r=>[...r.querySelectorAll('.plan-photo-item')].map(i=>Math.round(i.getBoundingClientRect().height))")
    preview.locator('.place-blogs summary').first.click()
    page.wait_for_function("(r=>r.querySelector('.place-blog-content')?.getAttribute('aria-busy')==='false')(document.querySelector('.plan-photo-preview'))")
    return preview, before


def test_opening_one_review_grows_only_that_column(audit_page):  # noqa: F811
    page, base, _ = audit_page
    preview, before = open_first_preview_blog(page, base)
    after = preview.evaluate("r=>[...r.querySelectorAll('.plan-photo-item')].map(i=>Math.round(i.getBoundingClientRect().height))")
    assert len(after) >= 2, after
    assert after[0] > before[0] + 100, (before, after)
    # 양옆 칸은 그대로(몇 px 오차만 허용).
    assert all(abs(a - b) <= 4 for a, b in zip(after[1:], before[1:])), (before, after)


def test_opened_reviews_are_visible_inside_the_column(audit_page):  # noqa: F811
    page, base, _ = audit_page
    preview, _ = open_first_preview_blog(page, base)
    # 펼친 칸의 첫 글 제목이 실제로 화면에 그려진다(크기가 있고, 조상의 overflow 로 잘리지 않는다).
    seen = preview.evaluate("""r=>{
      const title=r.querySelector('.place-blogs[open] .blog-post-title');
      if(!title)return 'no title';
      const box=title.getBoundingClientRect();
      if(box.width<40||box.height<10)return 'tiny '+JSON.stringify(box);
      for(let el=title.parentElement;el&&el!==document.body;el=el.parentElement){
        const s=getComputedStyle(el),b=el.getBoundingClientRect();
        if(s.display==='none'||s.visibility==='hidden')return 'hidden by '+el.className;
        if(s.overflow!=='visible'&&(box.top>=b.bottom||box.bottom<=b.top))return 'clipped by '+el.className+' '+JSON.stringify([b.top,b.bottom,box.top,box.bottom]);
      }
      return 'ok';
    }""")
    assert seen == 'ok', seen
    assert preview.locator('.place-blogs[open] .blog-post-title').first.inner_text() == POSTS[0]['title']
