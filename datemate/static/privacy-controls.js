(() => {
  const section = document.createElement('section');
  section.className = 'panel';
  const title = document.createElement('h2');
  title.textContent = '내 데이터 관리';
  const description = document.createElement('p');
  description.textContent = '이 브라우저에서 만든 일정, 대화, 후기, 의견과 피드백을 삭제할 수 있어요. 삭제하면 복구할 수 없으며, 별도 백업이나 외부 서비스 기록은 포함되지 않아요.';
  const retention = document.createElement('p');
  retention.className = 'hint';
  retention.textContent = '90일 동안 이용이 없으면 이 브라우저에서 저장한 일정·대화·의견이 자동으로 삭제돼요. 다른 사람에게 공개된 후기는 작성자 연결만 끊고 남겨 둬요.';
  const action = document.createElement('button');
  action.type = 'button';
  action.className = 'secondary';
  action.textContent = '이 브라우저의 저장 데이터 삭제';
  const result = document.createElement('p');
  result.setAttribute('role', 'status');
  action.onclick = async () => {
    if (!confirm('이 브라우저에서 만든 일정·대화·후기 등을 모두 삭제할까요? 복구할 수 없습니다.')) return;
    action.disabled = true;
    try {
      await api('/me/data', null, 'DELETE');
      PlanSearch.forget();
      location.replace('/');
    } catch (error) {
      result.textContent = error.message;
      action.disabled = false;
    }
  };
  section.append(title, description, retention, action, result);
  document.querySelector('main').append(section);
})();
