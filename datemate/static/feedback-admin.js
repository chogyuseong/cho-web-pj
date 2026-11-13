'use strict';

// 피드백 관리 화면. 키는 이 함수 안의 변수에만 두고 저장소·주소에는 남기지 않는다.
// 글 내용은 모두 textContent 로 그린다(받은 글의 HTML·스크립트가 실행되지 않게).
(() => {
  let key = '';
  let page = 1;
  let pages = 1;
  const login = document.getElementById('admin-login');
  const keyInput = document.getElementById('admin-key');
  const list = document.getElementById('admin-list');
  const entries = document.getElementById('admin-entries');
  const summary = document.getElementById('admin-summary');
  const pageLabel = document.getElementById('admin-page');
  const prev = document.getElementById('admin-prev');
  const next = document.getElementById('admin-next');
  const statusLine = document.getElementById('admin-status');
  const errorLine = document.getElementById('admin-error');

  function say(text) {
    errorLine.textContent = '';
    statusLine.textContent = text;
  }

  function fail(text) {
    statusLine.textContent = '';
    errorLine.textContent = text;
  }

  async function call(path, options = {}) {
    const response = await fetch(path, Object.assign({}, options, {
      headers: Object.assign({
        'Authorization': 'Bearer ' + key
      }, options.headers || {}),
      cache: 'no-store'
    }));
    let body = null;
    try {
      body = await response.json();
    } catch (_) {
      body = null;
    }
    return {
      response,
      body
    };
  }

  function lock(message) {
    key = '';
    entries.replaceChildren();
    list.hidden = true;
    login.hidden = false;
    keyInput.value = '';
    keyInput.focus();
    if (message) fail(message);
  }

  function formatTime(seconds) {
    const date = new Date(seconds * 1000);
    return date.toLocaleString('ko-KR', {
      timeZone: 'Asia/Seoul',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  }

  function text(tag, value, className) {
    const node = document.createElement(tag);
    node.textContent = value;
    if (className) node.className = className;
    return node;
  }

  function entryItem(entry) {
    const item = document.createElement('li');
    item.className = 'admin-entry' + (entry.handled ? ' handled' : '');
    const meta = [formatTime(entry.created)];
    if (entry.screen_label) meta.push('화면: ' + entry.screen_label);
    if (entry.viewport_width) meta.push('폭 ' + entry.viewport_width + 'px');
    if (entry.browser) meta.push(entry.browser);
    meta.push(entry.handled ? '처리함' : '처리 안 함');
    item.append(text('p', meta.join(' · '), 'admin-meta'));
    item.append(text('p', entry.message, 'admin-message'));
    if (entry.contact) item.append(text('p', '연락처: ' + entry.contact, 'admin-contact'));
    const actions = document.createElement('div');
    actions.className = 'admin-actions';
    const toggle = text('button', entry.handled ? '처리 안 함으로 표시' : '처리함으로 표시', 'secondary');
    toggle.type = 'button';
    toggle.addEventListener('click', () => mark(entry, !entry.handled, toggle));
    const remove = text('button', '삭제', 'secondary admin-delete');
    remove.type = 'button';
    remove.addEventListener('click', () => removeEntry(entry, remove));
    actions.append(toggle, remove);
    item.append(actions);
    return item;
  }

  async function load(target = page) {
    say('목록을 불러오는 중이에요.');
    let result;
    try {
      result = await call('/api/feedback/admin/entries?page=' + encodeURIComponent(target));
    } catch (_) {
      fail('연결이 끊겨 목록을 불러오지 못했어요.');
      return;
    }
    const {
      response,
      body
    } = result;
    if (response.status === 404) {
      lock('키가 맞지 않거나 관리자 열람이 꺼져 있어요. 여러 번 틀리면 10분 동안 열리지 않아요.');
      return;
    }
    if (!response.ok || !body) {
      fail((body && typeof body.detail === 'string' && body.detail) || '목록을 불러오지 못했어요.');
      return;
    }
    if (body.entries.length === 0 && body.page > 1 && body.page > body.pages) {
      load(body.pages);
      return;
    }
    const opening = list.hidden;
    page = body.page;
    pages = body.pages;
    login.hidden = true;
    keyInput.value = '';
    list.hidden = false;
    entries.replaceChildren(...body.entries.map(entryItem));
    if (!body.entries.length) entries.append(text('li', '받은 글이 없어요.', 'admin-empty'));
    summary.textContent = '전체 ' + body.total + '건 · 처리 안 함 ' + body.unhandled + '건';
    pageLabel.textContent = page + ' / ' + pages + '쪽';
    prev.disabled = page <= 1;
    next.disabled = page >= pages;
    say(page + '쪽을 불러왔어요.');
    if (opening) document.getElementById('admin-list-title').focus();
  }

  async function mark(entry, handled, button) {
    button.disabled = true;
    try {
      const {
        response
      } = await call('/api/feedback/admin/entries/' + encodeURIComponent(entry.id), {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          handled
        })
      });
      if (!response.ok) {
        fail('표시를 바꾸지 못했어요. 목록을 새로 고친 뒤 다시 시도해 주세요.');
        return;
      }
      await load(page);
      say(handled ? '처리함으로 표시했어요.' : '처리 안 함으로 표시했어요.');
    } catch (_) {
      fail('연결이 끊겨 표시를 바꾸지 못했어요.');
    } finally {
      button.disabled = false;
    }
  }

  async function removeEntry(entry, button) {
    if (!window.confirm('이 글을 지울까요? 되돌릴 수 없어요.')) return;
    button.disabled = true;
    try {
      const {
        response
      } = await call('/api/feedback/admin/entries/' + encodeURIComponent(entry.id), {
        method: 'DELETE'
      });
      if (!response.ok) {
        fail('지우지 못했어요. 목록을 새로 고친 뒤 다시 시도해 주세요.');
        return;
      }
      await load(page);
      say('글을 지웠어요.');
    } catch (_) {
      fail('연결이 끊겨 지우지 못했어요.');
    } finally {
      button.disabled = false;
    }
  }

  login.addEventListener('submit', event => {
    event.preventDefault();
    key = keyInput.value.trim();
    if (!key) {
      fail('관리자 키를 넣어 주세요.');
      keyInput.focus();
      return;
    }
    load(1);
  });
  document.getElementById('admin-reload').addEventListener('click', () => load(page));
  document.getElementById('admin-lock').addEventListener('click', () => {
    lock('');
    say('잠갔어요. 다시 보려면 키를 넣어 주세요.');
  });
  prev.addEventListener('click', () => load(Math.max(1, page - 1)));
  next.addEventListener('click', () => load(Math.min(pages, page + 1)));
})();
