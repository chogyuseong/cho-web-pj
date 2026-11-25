/* One HTTP boundary: bounded waiting, structured errors, no mutation retries. */
// 화면에 나가는 오류 문구는 모두 한국어다(2026-11-25 운영 QA-01~03). 브라우저·검증 라이브러리의 원문(영문, 칸 위치)은 보이지 않는다.
export const NETWORK_ERROR_TEXT='연결이 끊겨 서버에 닿지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.';
export const INVALID_INPUT_TEXT='입력값을 확인해 주세요. 허용 범위를 벗어난 값이 있어요.';
export const TIMEOUT_ERROR_TEXT='요청 대기 시간이 끝났거나 취소됐어요. 연결 상태를 확인해 주세요.';
const HANGUL=/[가-힣]/;
// 422 검증 오류 목록 → 사용자 문구. 서버 검사(ValueError)의 한국어 문구는 'Value error, ' 접두어만 떼고 쓰고,
// 영문으로만 된 검증 오류(글자 수·숫자 범위·형식)는 칸 이름 없이 일반 안내로 바꾼다.
export function validationMessage(items){
  const lines=new Set();
  for(const item of items){
    const text=String(item?.msg??'').replace(/^(Value error|Assertion failed), /,'').trim();
    if(HANGUL.test(text))lines.add(text);
    else if(item?.type==='string_too_long'&&Number.isFinite(Number(item?.ctx?.max_length)))lines.add(`입력한 글이 너무 길어요. ${Number(item.ctx.max_length).toLocaleString('ko-KR')}자 이하로 줄여 주세요.`);
  }
  // 한국어로 옮길 수 있는 문구가 하나도 없으면(영문 검증 오류뿐) 일반 안내 한 줄.
  return [...lines].join('\n')||INVALID_INPUT_TEXT;
}
export async function apiRequest(path,body,method,options={}){
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),options.timeout||30000);
  const abort=()=>controller.abort();
  if(options.signal){if(options.signal.aborted)abort();else options.signal.addEventListener('abort',abort,{once:true});}
  try{
    let response;
    // fetch 가 응답 없이 실패(TypeError: Failed to fetch 등)하면 연결 문제다. status 없이 network 표시만 붙인다 —
    // 추천 요청(plan-progress.js)·서버 깨우기(server-wake.js)는 status 가 없는 오류를 '응답을 받지 못함'으로 본다.
    try{response=await fetch('/api'+path,{method:method||(body?'POST':'GET'),headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal:controller.signal});}
    catch(error){if(error?.name==='AbortError')throw error;const failure=Error(NETWORK_ERROR_TEXT);failure.network=true;failure.cause=error;throw failure;}
    let data;try{data=await response.json();}catch{const error=Error('서버 응답을 읽을 수 없습니다.');error.status=response.status;error.unreadable=true;throw error;}
    // 구조화된 오류(detail 이 {code,message,...})는 message 를 보이고 code·detail 을 붙여 화면이 경우별로 다르게 안내할 수 있게 한다.
    if(!response.ok){const structured=data.detail&&typeof data.detail==='object'&&!Array.isArray(data.detail)&&typeof data.detail.message==='string';const error=Error(typeof data.detail==='string'?data.detail:structured?data.detail.message:Array.isArray(data.detail)?validationMessage(data.detail):'요청에 실패했습니다.');error.status=response.status;if(Array.isArray(data.detail))error.validation=true;if(structured){error.code=data.detail.code;error.detail=data.detail;}error.requestId=response.headers.get('X-Request-ID');throw error;}
    return data;
  }catch(error){if(error.name==='AbortError')throw Error(TIMEOUT_ERROR_TEXT);throw error;}
  finally{clearTimeout(timeout);options.signal?.removeEventListener('abort',abort);}
}

