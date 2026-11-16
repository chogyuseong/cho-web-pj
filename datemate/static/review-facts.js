// 블로그 후기 본문에서 읽은 영업시간·휴무(참고용). 일정 계산에는 쓰지 않고 '후기 기준'으로 밝혀 보여 준다.
// 장소 카드가 화면에 보일 때 한 번만 요청하고, 읽은 것이 없거나 실패하면 아무것도 보이지 않는다.
const reviewFactRequests = new Map();

function reviewFactsLine(place, mode) {
  if (mode !== 'real' || place.demo || place.hours || place.category === '산책·풍경') return document.createDocumentFragment();
  const box = node('div', undefined, 'review-facts');
  box.hidden = true;
  const key = place.id;

  function show(data) {
    if (!data || data.status !== 'available' || !data.hours) {
      box.remove();
      return;
    }
    const line = node('p', undefined, 'review-facts-hours');
    line.append(node('span', '후기에서 읽은 영업시간', 'tag review-facts-tag'), document.createTextNode(' ' + data.hours + (data.closed ? ' · ' + data.closed : '')));
    const source = data.source || {};
    const meta = node('p', `블로그 글${source.posted_at ? '(' + source.posted_at + ')' : ''} 기준 · 지금과 다를 수 있어요.`, 'hint review-facts-note');
    box.replaceChildren(line, meta);
    if (source.url) box.append(link('근거 글 보기 ↗', source.url));
    box.hidden = false;
  }

  function start() {
    if (!reviewFactRequests.has(key)) {
      reviewFactRequests.set(key, api('/places/' + encodeURIComponent(place.id) + '/review-facts?mode=real').catch(error => {
        reviewFactRequests.delete(key);
        throw error;
      }));
    }
    reviewFactRequests.get(key).then(show, () => box.remove());
  }
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting)) {
        observer.disconnect();
        start();
      }
    }, {
      rootMargin: '200px'
    });
    // 숨긴 상자는 크기가 없어 관찰되지 않으므로, 붙은 뒤 부모(장소 카드)를 본다.
    requestAnimationFrame(() => {
      if (box.isConnected && box.parentElement) observer.observe(box.parentElement);
    });
  } else start();
  return box;
}
