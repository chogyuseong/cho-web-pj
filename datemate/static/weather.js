/* 방문일 날씨(2026-11-26 요구 문서 Phase 1 '날씨 스마트 필').
   지금은 날씨 자료를 받는 곳(외부 날씨 API)이 없다. 예보를 지어내 보여 주지 않으려고, 자료 틀(WeatherAdapter)만 두고 사용자가 방문일 날씨를 고른다.
   · WeatherAdapter.forecast(dateText) → Promise<{sky:'clear'|'cloudy'|'rain'|'snow', source:string}|null>. 지금 구현은 늘 null(자료 없음).
     날씨 API 를 붙이면 이 함수만 바꾸면 된다 — 값이 오면 칩을 그 날씨로 고르고 '…기준' 출처를 붙인다(sourceNote).
   · 화면: 코스 만들기 날짜 줄 아래 '방문일 날씨(선택)' 칩 3개(맑음·흐림 / 비·눈 / 모름). '비·눈'이면 "비 소식이 있으면 실내 위주 코스로 맞출까요?"
     제안 줄과 [실내 위주로] 단추 — 누르면 상세 조건의 실내·실외(name=setting)를 '실내만'으로 바꾸고 알린다. 자동으로 바꾸지는 않는다.
   · 고른 날씨는 서버로 보내지 않는다(추천 계산은 실내·실외 조건만 쓴다). 새로 열면 '모름'.
   simple-form.js 가 날짜 줄을 그린 뒤 mountWeatherChoice(날짜 안내 줄)를 부른다. 테스트 tests/test_redesign_p1_ui.py. */
const WeatherAdapter = {
  async forecast() {
    return null;
  }
};

function mountWeatherChoice(after) {
  const form = document.getElementById('conditions');
  if (!form || !after || document.getElementById('weather-choice')) return;
  const box = node('div', undefined, 'weather-choice');
  box.id = 'weather-choice';
  box.setAttribute('role', 'group');
  box.setAttribute('aria-labelledby', 'weather-choice-title');
  const title = node('p', '방문일 날씨 (선택)', 'weather-choice-title');
  title.id = 'weather-choice-title';
  const row = node('div', undefined, 'quick-chips weather-chips');
  const suggest = node('p', undefined, 'weather-suggest');
  suggest.setAttribute('role', 'status');
  suggest.hidden = true;
  const sourceNote = node('p', '', 'hint weather-source');
  sourceNote.hidden = true;
  const CHOICES = [['clear', '맑음·흐림'], ['rain', '비·눈'], ['unknown', '모름']];
  const chips = CHOICES.map(([value, label]) => {
    const chip = button(label, () => choose(value, null), 'quick-chip weather-chip');
    chip.type = 'button';
    chip.dataset.sky = value;
    return chip;
  });
  row.append(...chips);
  function choose(value, source) {
    chips.forEach(chip => chip.setAttribute('aria-pressed', String(chip.dataset.sky === value)));
    sourceNote.hidden = !source;
    sourceNote.textContent = source ? `${source} 기준이에요.` : '';
    suggest.replaceChildren();
    const setting = form.elements.setting;
    suggest.hidden = value !== 'rain' || setting?.value === 'indoor';
    if (suggest.hidden) return;
    const go = button('실내 위주로', () => {
      if (setting) {
        setting.value = 'indoor';
        setting.dispatchEvent(new Event('input', { bubbles: true }));
        setting.dispatchEvent(new Event('change', { bubbles: true }));
      }
      suggest.replaceChildren(node('span', '실내·실외 조건을 ‘실내만’으로 바꿨어요. 상세 조건에서 다시 바꿀 수 있어요.'));
      if (typeof toast === 'function') toast('비 오는 날에 맞춰 실내 장소로만 코스를 짤게요.');
    }, 'secondary weather-indoor');
    go.type = 'button';
    suggest.append(node('span', '비 소식이 있으면 실내 위주 코스로 맞출까요? '), go);
  }
  choose('unknown', null);
  box.append(title, row, suggest, sourceNote);
  after.after(box);
  // 날짜를 바꾸면 자료를 다시 묻는다(지금은 늘 자료 없음 → 사용자가 고른 그대로 둔다).
  const date = form.elements.visit_date;
  const ask = async () => {
    const found = await WeatherAdapter.forecast(date?.value).catch(() => null);
    if (found) choose(found.sky === 'rain' || found.sky === 'snow' ? 'rain' : 'clear', found.source);
  };
  date?.addEventListener('change', ask);
  ask();
}
window.mountWeatherChoice = mountWeatherChoice;
