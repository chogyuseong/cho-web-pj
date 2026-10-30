"""The supplied visual theme must keep navigation and the sticky map usable."""
from test_functional_audit import audit_page,generate


def test_imported_theme_anchors_and_sticky_map_clear_header(audit_page):
    page,base,errors=audit_page
    page.emulate_media(reduced_motion='reduce')
    for width in (1440,768,390,320):
        page.set_viewport_size({'width':width,'height':1000})
        page.wait_for_function("parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--site-header-height'))===Math.ceil(document.querySelector('header').getBoundingClientRect().height)")
        page.locator('header nav a[href="#curation"]').click()
        page.wait_for_function("document.querySelector('#curation').getBoundingClientRect().top>=document.querySelector('header').getBoundingClientRect().bottom")
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        page.locator('header #nav-plan').click()
    page.set_viewport_size({'width':1440,'height':1000})
    generate(page)
    page.locator('.execution-summary').scroll_into_view_if_needed()
    page.wait_for_function("document.querySelector('.plan-map-card').getBoundingClientRect().top>=document.querySelector('header').getBoundingClientRect().bottom")
    assert page.locator('.map-option-tabs').is_visible()
    assert page.locator('.hero-photo img').evaluate('(el)=>el.complete&&el.naturalWidth===1400')
