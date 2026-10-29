from test_functional_audit import audit_page,generate


def test_wheel_zooms_map_and_still_works_after_course_change(audit_page):
    page,base,errors=audit_page
    page.evaluate('''() => {
      window.courseMaps=[];
      const create=L.map;
      L.map=function(...args){const map=create(...args);window.courseMaps.push(map);return map;};
    }''')
    generate(page)
    canvas=page.locator('.fallback-plan-map')
    canvas.wait_for(state='visible')
    page.wait_for_function('courseMaps.length && !courseMaps.at(-1)._animatingZoom')
    canvas.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    initial=page.evaluate('courseMaps.at(-1).getZoom()')
    bounds=canvas.bounding_box()
    page.mouse.move(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
    page.mouse.wheel(0,-500)
    page.wait_for_function('zoom=>courseMaps.at(-1).getZoom()>zoom',arg=initial)
    page.wait_for_function('!courseMaps.at(-1)._animatingZoom')
    enlarged=page.evaluate('courseMaps.at(-1).getZoom()')
    page.mouse.wheel(0,500)
    page.wait_for_function('zoom=>courseMaps.at(-1).getZoom()<zoom',arg=enlarged)
    page.wait_for_function('!courseMaps.at(-1)._animatingZoom')
    count=page.evaluate('courseMaps.length')
    page.locator('.map-option-tabs button').nth(1).click()
    page.wait_for_function('count=>courseMaps.length>count',arg=count)
    canvas.scroll_into_view_if_needed()
    page.wait_for_timeout(400)
    initial=page.evaluate('courseMaps.at(-1).getZoom()')
    bounds=canvas.bounding_box()
    page.mouse.move(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
    page.mouse.wheel(0,-500)
    page.wait_for_function('zoom=>courseMaps.at(-1).getZoom()>zoom',arg=initial)
    page.wait_for_function('!courseMaps.at(-1)._animatingZoom')
