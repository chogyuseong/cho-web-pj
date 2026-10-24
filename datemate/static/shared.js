'use strict';
(() => {
  const token=location.hash.slice(1), status=document.getElementById('shared-status'), form=document.getElementById('shared-form');
  async function request(path,body){
    const response=await fetch(path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(15000)});
    const data=await response.json();if(!response.ok)throw Error(data.detail||'연결하지 못했어요.');return data;
  }
  request('/api/shared-plan').then(data=>{
    status.textContent=data.notice;
    for(const place of data.places){
      const article=document.createElement('article'),title=document.createElement('h2'),text=document.createElement('p'),label=document.createElement('label'),select=document.createElement('select');
      title.textContent=place.name;text.textContent=`${place.arrival} ~ ${place.departure} · ${place.address}`;
      label.textContent=place.name+'에 대한 의견';select.name=place.id;
      for(const [value,title] of [['neutral','아직 모르겠어요'],['yes','좋아요'],['no','다른 곳이 좋아요']])select.add(new Option(title,value));
      label.append(select);article.append(title,text,label);document.getElementById('shared-places').append(article);
    }
    form.hidden=false;
  }).catch(error=>status.textContent=error.message);
  form.onsubmit=async event=>{
    event.preventDefault();const button=form.querySelector('button');button.disabled=true;
    try{await request('/api/shared-plan/vote',{choices:Object.fromEntries(new FormData(form))});status.textContent='의견을 전달했어요.';}
    catch(error){status.textContent=error.message;}finally{button.disabled=false;}
  };
})();
