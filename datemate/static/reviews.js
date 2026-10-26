'use strict';
// Review form and list rendering; uses app.js UI helpers and api-client.js.
async function loadReviews(root, p) {
  const data = await api('/plans/' + p.id + '/reviews');
  root.replaceChildren(node('h3', '우리 서비스의 일정 이용 후기'), node('strong', data.average == null ? data.label : `★ ${data.average} / 5 · ${data.count}건`), node('p', data.verification, 'hint'));
  const f = node('form', undefined, 'review-form'),
    grid = node('div', undefined, 'field-grid');

  function field(label, type, name, value) {
    const l = node('label', label),
      i = node(type === 'textarea' ? 'textarea' : 'input');
    i.name = name;
    if (type !== 'textarea') i.type = type;
    i.required = true;
    i.value = value || '';
    l.append(i);
    return [l, i];
  }
  const [nick, n] = field('공개 별명', 'text', 'nickname', '산책하는 우리');
  n.maxLength = 40;
  const [rating, r] = field('별점 (1~5)', 'number', 'rating', '5');
  r.min = 1;
  r.max = 5;
  const [visit, v] = field('방문일 (자기 신고)', 'date', 'visited', today());
  v.max = today();
  const [body, b] = field('후기 내용', 'textarea', 'body');
  b.rows = 4;
  grid.append(nick, rating, visit);
  const save = node('button', '후기 저장 / 내 후기 수정', 'primary');
  f.append(grid, body, save, node('p', '최대 2 MiB 요청. 같은 브라우저의 동일 방문 순서 후기는 한 건으로 갱신됩니다.', 'hint'));
  const mine = data.rows.find(x => x.mine);
  if (mine) {
    n.value = mine.nickname;
    r.value = mine.rating;
    v.value = mine.visited;
    b.value = mine.body;
  }
  f.onsubmit = async e => {
    e.preventDefault();
    save.disabled = true;
    try {
      await api('/plans/' + p.id + '/review', {
        nickname: n.value,
        rating: Number(r.value),
        visited: v.value,
        body: b.value
      }, 'PUT');
      await loadReviews(root, p);
      toast('후기를 저장했습니다.');
    } catch (error) {
      toast(error.message);
    } finally {
      save.disabled = false;
    }
  };
  root.append(f);
  for (const review of data.rows) {
    const row = node('article', undefined, 'review');
    row.append(node('strong', `${review.nickname} · ★ ${review.rating}`), node('p', `방문 ${review.visited} · 작성 ${new Date(review.created*1000).toLocaleDateString('ko-KR')} · 자기 신고`, 'review-meta'), node('p', review.body, 'review-body'));
    const actions = node('div', undefined, 'actions');
    if (review.mine) actions.append(button('내 후기 삭제', async () => {
      await api('/reviews/' + review.id, null, 'DELETE');
      await loadReviews(root, p);
    }));
    actions.append(button('신고', async () => {
      const reason = prompt('신고 사유를 입력해 주세요.');
      if (reason?.trim()) {
        const answer = await api('/reviews/' + review.id + '/report', {
          reason
        });
        toast(answer.notice);
      }
    }));
    row.append(actions);
    root.append(row);
  }
}
