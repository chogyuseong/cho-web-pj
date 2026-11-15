'use strict';
/* 자유 입력 해석 결과 ‘이렇게 이해했어요’와 자주 쓰는 조건 칩.
   - 이해한 조건은 칩으로 보여 주고, 누르면 그 조건을 빼거나 다시 넣는다. 뺀 조건 id 는 해석(/conditions/parse 의 ignore)과
     추천 요청(request_ignore)에 함께 실어 서버도 같은 글에서 그 조건을 빼고 쓴다.
   - 반영하지 못한 표현은 서버가 만든 문장(‘○○’는 아직 반영하지 못했어요)으로 밝힌다.
   - 입력 글은 화면에서만 다루고 이 브라우저에 저장하지 않는다. */
const RequestUnderstanding = {
  ignore: new Set(),
  last: null,
  box: null,
  status: null,
  quick: [],
  // [칩 이름, 켜졌는지 보는 해석 항목 id(첫 번째가 기준), 칩을 켤 때 글에 더하는 말]. 서버 규칙이 실제로 알아듣는 말만 둔다.
  QUICK: [
    ['조용한 곳', ['priority:talk'], '조용한 곳'],
    ['비 와도 OK', ['setting:indoor', 'date:비 오는 날'], '비 와도 괜찮은 곳'],
    ['걷기 적게', ['transport:transit', 'exclude:walk'], '걷기 적게'],
    ['사진 잘 나오는 곳', ['priority:photo'], '사진 잘 나오는 곳'],
    ['가성비', ['budget_style:low'], '가성비 좋게'],
    ['기념일', ['meeting_type:anniversary'], '기념일 데이트']
  ],
  mount(host, before) {
    const row = node('div', undefined, 'quick-chips request-quick-chips');
    row.setAttribute('role', 'group');
    this.quick = this.QUICK.map(([label, ids, phrase]) => {
      const chip = button(label, () => this.quickToggle(chip), 'quick-chip');
      chip.setAttribute('aria-pressed', 'false');
      chip.request = {
        ids,
        phrase
      };
      return chip;
    });
    row.append(...this.quick);
    const title = node('p', '자주 쓰는 조건', 'request-quick-title');
    title.id = 'request-quick-title';
    row.setAttribute('aria-labelledby', title.id);
    this.box = node('section', undefined, 'request-understanding');
    this.box.id = 'request-understanding';
    this.box.setAttribute('aria-labelledby', 'request-understanding-title');
    this.box.hidden = true;
    this.status = node('p', '', 'hint request-understanding-status');
    this.status.setAttribute('role', 'status');
    host.insertBefore(title, before);
    host.insertBefore(row, before);
    return [this.box, this.status];
  },
  activeIds() {
    return new Set((this.last?.understood || []).map(item => item.id));
  },
  requestIgnore() {
    return [...this.ignore];
  },
  prune(result) {
    const known = new Set([...(result.understood || []), ...(result.ignored || [])].map(item => item.id));
    for (const id of [...this.ignore])
      if (!known.has(id)) this.ignore.delete(id);
  },
  clear() {
    this.last = null;
    this.ignore.clear();
    if (this.box) {
      this.box.hidden = true;
      this.box.replaceChildren();
    }
    this.syncQuick();
  },
  render(result) {
    this.last = result;
    this.syncQuick();
    const box = this.box;
    if (!box) return;
    const focused = document.activeElement?.dataset?.requestItem;
    const items = [...(result.understood || []).map(item => [item, true]), ...(result.ignored || []).map(item => [item, false])];
    const gaps = result.not_understood || [];
    box.replaceChildren();
    box.hidden = !items.length && !gaps.length;
    if (box.hidden) return;
    const title = node('h3', '이렇게 이해했어요', 'request-understanding-title');
    title.id = 'request-understanding-title';
    box.append(title);
    if (items.length) {
      const row = node('div', undefined, 'quick-chips understood-chips');
      row.setAttribute('role', 'group');
      row.setAttribute('aria-label', '이해한 조건 · 누르면 빼거나 다시 넣어요');
      for (const [item, on] of items) {
        const chip = button('', () => this.toggle(item), 'quick-chip understood-chip' + (on ? '' : ' is-removed'));
        chip.dataset.requestItem = item.id;
        chip.setAttribute('aria-pressed', String(on));
        const evidence = (item.evidence || []).map(text => '‘' + text + '’').join(', ');
        chip.setAttribute('aria-label', item.label + (item.estimated ? ' (추정)' : '') + (evidence ? ', 근거 ' + evidence : '') + (on ? ', 누르면 빼요' : ', 뺀 조건 · 누르면 다시 넣어요'));
        chip.title = evidence ? '근거: ' + evidence : item.label;
        chip.append(node('span', item.label));
        if (item.estimated) chip.append(node('span', '추정', 'understood-estimated'));
        const mark = node('span', on ? '✕' : '+', 'understood-mark');
        mark.setAttribute('aria-hidden', 'true');
        chip.append(mark);
        row.append(chip);
      }
      box.append(row, node('p', '칩을 누르면 그 조건을 빼거나 다시 넣어요. 뺀 조건은 추천에도 쓰지 않아요.', 'hint'));
    }
    const notes = [...new Map((result.understood || []).filter(item => item.estimated && item.note).map(item => [item.note, item.label])).entries()];
    if (notes.length) {
      const list = node('ul', undefined, 'understood-notes');
      for (const [note, label] of notes) list.append(node('li', '추정 · ' + label + ': ' + note));
      box.append(list);
    }
    if (gaps.length) {
      const list = node('ul', undefined, 'request-gaps');
      list.setAttribute('aria-label', '반영하지 못한 표현');
      for (const gap of gaps) list.append(node('li', gap.message));
      box.append(list);
    }
    if (focused) box.querySelector(`[data-request-item="${CSS.escape(focused)}"]`)?.focus();
  },
  say(text) {
    if (this.status) this.status.textContent = text;
  },
  syncQuick() {
    const active = this.activeIds();
    for (const chip of this.quick) chip.setAttribute('aria-pressed', String(active.has(chip.request.ids[0])));
  },
  async toggle(item) {
    const removing = !this.ignore.has(item.id);
    if (removing) this.ignore.add(item.id);
    else this.ignore.delete(item.id);
    await applyRequest();
    this.say('‘' + item.label + '’ 조건을 ' + (removing ? '뺐어요. 추천에도 쓰지 않아요.' : '다시 넣었어요.'));
  },
  async quickToggle(chip) {
    const {
      ids,
      phrase
    } = chip.request;
    const label = chip.textContent;
    if (this.activeIds().has(ids[0])) {
      for (const id of ids)
        if (this.activeIds().has(id)) this.ignore.add(id);
      await applyRequest();
      this.say('‘' + label + '’ 조건을 뺐어요.');
      return;
    }
    const input = form.elements.request;
    if (ids.some(id => this.ignore.has(id))) ids.forEach(id => this.ignore.delete(id));
    else if (!input.value.includes(phrase)) {
      input.value = input.value.trim() ? input.value.trim() + ', ' + phrase : phrase;
      input.dispatchEvent(new Event('input', {
        bubbles: true
      }));
    }
    await applyRequest();
    this.say(this.activeIds().has(ids[0]) ? '‘' + label + '’ 조건을 넣었어요.' : '‘' + label + '’ 조건은 다른 조건과 함께 고를 수 없어 넣지 못했어요. 아래 안내를 확인해 주세요.');
  }
};
