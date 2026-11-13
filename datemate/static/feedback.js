'use strict';

// 피드백 작성 화면. 함께 보내는 것은 화면 폭뿐이고 브라우저 종류는 서버가 User-Agent 에서 이름만 뽑는다.
(() => {
  const MIN = 5;
  const MAX = 1000;
  const form = document.getElementById('feedback-form');
  const message = document.getElementById('feedback-message');
  const contact = document.getElementById('feedback-contact');
  const screenSelect = document.getElementById('feedback-screen');
  const trap = document.getElementById('feedback-website');
  const count = document.getElementById('feedback-count');
  const submit = document.getElementById('feedback-submit');
  const statusLine = document.getElementById('feedback-status');
  const errorLine = document.getElementById('feedback-error');
  const widthLine = document.getElementById('feedback-width');
  let sending = false;
  let sentUnchanged = false;

  function viewportWidth() {
    return Math.max(1, Math.min(10000, Math.round(window.innerWidth || document.documentElement.clientWidth || 1)));
  }

  function showWidth() {
    widthLine.textContent = viewportWidth() + 'px';
  }

  function trimmedLength() {
    return message.value.trim().length;
  }

  function updateCount() {
    const left = MAX - message.value.length;
    count.textContent = '남은 글자 ' + Math.max(0, left) + '자';
  }

  function setError(text) {
    errorLine.textContent = text;
    if (text) statusLine.textContent = '';
  }

  function detailOf(body, fallback) {
    if (body && typeof body.detail === 'string' && body.detail) return body.detail;
    return fallback;
  }

  message.addEventListener('input', () => {
    updateCount();
    sentUnchanged = false;
    submit.disabled = sending;
  });
  contact.addEventListener('input', () => {
    sentUnchanged = false;
    submit.disabled = sending;
  });
  window.addEventListener('resize', showWidth);

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (sending || sentUnchanged) return;
    const length = trimmedLength();
    if (length < MIN) {
      setError('내용을 ' + MIN + '자 이상 적어 주세요.');
      message.focus();
      return;
    }
    if (message.value.length > MAX) {
      setError('내용은 ' + MAX + '자까지 보낼 수 있어요.');
      message.focus();
      return;
    }
    if (contact.value.trim().length > 100) {
      setError('연락처는 100자까지 적을 수 있어요.');
      contact.focus();
      return;
    }
    sending = true;
    submit.disabled = true;
    setError('');
    statusLine.textContent = '보내는 중이에요.';
    try {
      const response = await fetch('/api/feedback', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message: message.value,
          screen: screenSelect.value,
          contact: contact.value,
          viewport_width: viewportWidth(),
          website: trap.value
        })
      });
      let body = null;
      try {
        body = await response.json();
      } catch (_) {
        body = null;
      }
      if (!response.ok) {
        const fallback = response.status === 429 ? '요청이 많아요. 잠시 후 다시 보내 주세요.' : '보내지 못했어요. 잠시 후 다시 시도해 주세요.';
        setError(detailOf(body, fallback));
        return;
      }
      form.reset();
      updateCount();
      sentUnchanged = true;
      statusLine.textContent = detailOf(body && {
        detail: body.message
      }, '보내 주셔서 고마워요.');
    } catch (_) {
      setError('연결이 끊겨 보내지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.');
    } finally {
      sending = false;
      submit.disabled = sentUnchanged;
    }
  });

  showWidth();
  updateCount();
})();
