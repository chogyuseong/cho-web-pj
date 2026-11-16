const httpClient=import('/static/http-client.mjs');
// 서버를 깨우는 동안(server-wake.js)에는 /status 말고는 보내지 않고, 준비되면 이어서 보낸다.
async function api(...args){if(args[0]!=='/status'&&typeof ServerWake!=='undefined')await ServerWake.ready();return (await httpClient).apiRequest(...args);}

async function copyPlanShare(plan){
  const shared=await api('/plans/'+plan.id+'/shares',{});
  const url=new URL(shared.url,location.origin).href;
  try{await navigator.clipboard.writeText(url);toast('24시간 공유 링크를 복사했어요. 출발지·귀가지·입력 요청은 제외됩니다.');}
  catch{const root=openDialog('공유 링크');const input=document.createElement('input');input.value=url;input.readOnly=true;input.setAttribute('aria-label','공유 링크');root.append(input);input.select();}
}

async function revokePlanShares(plan){
  await api('/plans/'+plan.id+'/shares',null,'DELETE');toast('이 일정의 공유 링크를 모두 취소했어요.');
}
