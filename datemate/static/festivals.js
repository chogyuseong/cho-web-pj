/* Festivals for the submitted course conditions. Provider photos are KOGL Type1/Type3 (attribution, no alteration),
   so they are shown whole (never cropped or filtered) with a credit line, and dropped when missing or broken.
   Runs beside the course search and never blocks or fails it. */
const FestivalPanel = {
  generation: 0,
  firstPage: 6,
  load(conditions) {
    const generation = ++this.generation;
    this.request(conditions, generation).catch(() => {
      if (generation === this.generation) this.status('축제 자료에 연결하지 못했어요. 코스 추천에는 영향이 없어요.');
    });
  },
  photo(festival) {
    const url = String(festival.image_url || '');
    if (!url.startsWith('https://tong.visitkorea.or.kr/')) return null;
    const figure = node('figure', undefined, 'festival-photo');
    const frame = node('div', undefined, 'festival-photo-frame');
    const img = document.createElement('img');
    img.loading = 'lazy';
    img.decoding = 'async';
    img.referrerPolicy = 'no-referrer';
    img.alt = `${festival.title} 대표 사진`;
    img.addEventListener('error', () => figure.remove(), {
      once: true
    });
    img.src = url;
    frame.append(img);
    figure.append(frame, node('figcaption', '사진: 한국관광공사', 'festival-photo-credit'));
    return figure;
  },
  status(text) {
    document.getElementById('festival-status').textContent = text;
  },
  async request(conditions, generation) {
    const section = document.getElementById('festival-section');
    const results = document.getElementById('festival-results');
    const more = document.getElementById('festival-more');
    const day = conditions.visit_date;
    const region = conditions.region || '서울';
    document.getElementById('festival-title').textContent = `${day || '방문일'} ${region}에서 열리는 축제·행사`;
    document.getElementById('festival-demo-note').hidden = conditions.mode !== 'demo';
    results.replaceChildren();
    more.hidden = true;
    more.onclick = null;
    section.hidden = false;
    if (!day) {
      this.status('방문 날짜를 정하면 그날 열리는 축제를 함께 보여드려요.');
      return;
    }
    this.status('방문일에 열리는 축제를 찾는 중…');
    const params = new URLSearchParams({
      start: day,
      end: day,
      region
    });
    const data = await api('/festivals?' + params, null, 'GET', {
      timeout: 90000
    });
    if (generation !== this.generation) return;
    if (data.status !== 'available') {
      this.status(data.status === 'key_missing' ? '축제 자료 키가 설정되지 않아 축제를 표시할 수 없어요. 코스 추천은 그대로 이용할 수 있어요.' : '축제 자료에 연결하지 못했어요. 코스 추천에는 영향이 없어요.');
      return;
    }
    const festivals = Array.isArray(data.festivals) ? data.festivals : [];
    if (!festivals.length) {
      this.status('');
      results.append(node('p', '방문일에 확인된 축제가 없어요.', 'hint'));
      return;
    }
    let text = `${festivals.length}건 · ${data.message || ''}`;
    if (data.truncated) text += ' 조회 결과가 많아 일부만 표시합니다.';
    this.status(text);
    const render = items => results.append(...items.map(festival => {
      const card = node('article', undefined, 'festival-card');
      const photo = this.photo(festival);
      if (photo) card.append(photo);
      card.append(node('strong', festival.title),
        node('p', `${festival.start} ~ ${festival.end} · ${festival.region}`, 'hint'),
        node('p', festival.address, 'hint'),
        link('한국관광공사에서 확인 ↗', festival.source_url));
      return card;
    }));
    render(festivals.slice(0, this.firstPage));
    if (festivals.length > this.firstPage) {
      more.textContent = `축제 더 보기 (${festivals.length - this.firstPage}건)`;
      more.hidden = false;
      more.onclick = () => {
        more.hidden = true;
        more.onclick = null;
        render(festivals.slice(this.firstPage));
      };
    }
  }
};
