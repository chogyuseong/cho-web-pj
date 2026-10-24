/* One HTTP boundary: bounded waiting, structured errors, no mutation retries. */
export async function apiRequest(path,body,method,options={}){
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),options.timeout||30000);
  const abort=()=>controller.abort();
  if(options.signal){if(options.signal.aborted)abort();else options.signal.addEventListener('abort',abort,{once:true});}
  try{
    const response=await fetch('/api'+path,{method:method||(body?'POST':'GET'),headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal:controller.signal});
    let data;try{data=await response.json();}catch{throw Error('서버 응답을 읽을 수 없습니다.');}
    if(!response.ok){const error=Error(typeof data.detail==='string'?data.detail:Array.isArray(data.detail)?data.detail.map(x=>`${x.loc.at(-1)}: ${x.msg}`).join('\n'):'요청에 실패했습니다.');error.status=response.status;error.requestId=response.headers.get('X-Request-ID');throw error;}
    return data;
  }catch(error){if(error.name==='AbortError')throw Error('요청 대기 시간이 끝났거나 취소됐어요. 연결 상태를 확인해 주세요.');throw error;}
  finally{clearTimeout(timeout);options.signal?.removeEventListener('abort',abort);}
}

