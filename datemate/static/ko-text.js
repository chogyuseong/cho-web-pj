/* 'use strict' 를 쓰지 않는다: 이 파일은 첫 화면 묶음(static/bundles/index.js)의 맨 앞이라, 여기 적으면 묶음 전체가 엄격 모드가 된다.
   한국어 조사(2026-11-27 2차 QA-18). 안내 문구가 '서울 성수을(를) …'처럼 조사를 둘 다 적던 것을, 앞말의 받침에 맞는 조사 하나로 고른다.

   withObjectParticle('서울 성수') → '서울 성수를',  withObjectParticle('성수동') → '성수동을'
   - 판단은 앞말의 마지막 한글 음절로 한다: 받침이 있으면 '을', 없으면 '를'.
   - 끝에 붙은 따옴표·닫는 괄호와 괄호 안 설명은 건너뛴다. 괄호는 앞말을 읽은 뒤 덧붙인 설명이라 조사는 괄호 앞 말에 맞춘다
     (예: '성수카페(서울 성수동)' → 판단은 '성수카페' → '성수카페(서울 성수동)를', '‘성수’' → '‘성수’를').
   - 마지막 글자가 한글이 아니면(영문·숫자·기호, 예: 'CGV', '2호점') 읽는 법을 확정할 수 없어 예전처럼 '을(를)' 그대로 둔다.
     숫자·영문까지 읽기를 넣고 싶으면 fallback 앞에 규칙을 더하면 된다(예: 끝 숫자 0·1·3·6·7·8 은 받침 있음).
   쓰는 곳: simple-form.js(지역 고름·장소 검색 중), explore.js(코스에 담기), shared.js(공유 화면 축제 안내).
   index.html·shared.html 에서 이 파일은 그 파일들보다 먼저 온다(묶음 static/bundles/*.js 안에서도 같은 순서). */
function withObjectParticle(word) {
  const text = String(word ?? '').trim();
  // 끝의 괄호 설명 '(…)'과 닫는 따옴표·괄호·공백을 떼고 남은 말의 마지막 글자로 판단한다.
  const core = text.replace(/\s*\([^()]*\)\s*$/u, '').replace(/[\s'"’”)\]}>」』]+$/u, '');
  const code = core.charCodeAt(core.length - 1);
  if (code >= 0xac00 && code <= 0xd7a3) return text + ((code - 0xac00) % 28 ? '을' : '를');
  return text + '을(를)';
}
