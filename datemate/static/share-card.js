function wrapCanvasText(ctx,text,x,y,maxWidth,lineHeight,maxLines=2){
  let line='',lines=[];
  for(const char of String(text||'')){if(ctx.measureText(line+char).width>maxWidth&&line){lines.push(line);line=char;}else line+=char;}
  if(line)lines.push(line);
  lines.slice(0,maxLines).forEach((line,i)=>ctx.fillText(i===maxLines-1&&lines.length>maxLines?line.slice(0,-1)+'…':line,x,y+i*lineHeight));
  return Math.min(lines.length,maxLines)*lineHeight;
}
async function makeShareCanvas(plan){
  await document.fonts.ready;
  const canvas=document.createElement('canvas');canvas.width=1080;canvas.height=1350;
  const c=canvas.getContext('2d');if(!c)throw Error('이 브라우저에서는 이미지 저장을 지원하지 않아요. 인쇄/PDF를 이용해 주세요.');
  // 화면과 같은 노선 디자인: 승강장색 테두리, 홍색 노선 띠와 흰 역 원, 먹색 글.
  const INK='#1f2328',MUTED='#55606b',HONG='#b5245e',BODY='"Apple SD Gothic Neo","Noto Sans KR","Malgun Gothic",sans-serif',HEAD='"DateMate Line Heading",'+BODY;
  c.fillStyle='#f1f3f2';c.fillRect(0,0,1080,1350);c.fillStyle='#fff';c.fillRect(48,48,984,1254);
  c.fillStyle=HONG;c.font='800 28px '+HEAD;c.fillText('데이트메이트',96,112);
  c.fillStyle=INK;c.font='800 46px '+HEAD;wrapCanvasText(c,plan.decision_summary?.title||'함께 보내는 하루',96,184,880,58,2);
  c.font='26px '+BODY;c.fillStyle=MUTED;c.fillText(`${plan.conditions.visit_date} · ${plan.conditions.people}명 · ${plan.places.length}곳`,96,310);
  if(plan.places.length>1){c.fillStyle=HONG;c.fillRect(116,394,8,(plan.places.length-1)*137);}
  plan.places.forEach((p,i)=>{
    const y=386+i*137;c.fillStyle='#fff';c.beginPath();c.arc(120,y+8,24,0,Math.PI*2);c.fill();c.lineWidth=6;c.strokeStyle=HONG;c.stroke();
    c.fillStyle=HONG;c.font='800 24px '+HEAD;c.textAlign='center';c.fillText(String(i+1),120,y+17);c.textAlign='left';
    c.fillStyle=INK;c.font='800 31px '+HEAD;wrapCanvasText(c,p.name,170,y+2,770,38,2);
    c.fillStyle=MUTED;c.font='23px '+BODY;c.fillText(`${plan.timeline[i]?.arrival||''} · ${p.category}`,170,y+86);
  });
  c.fillStyle=INK;c.font='800 32px '+HEAD;c.fillText(`예상 비용 ${range(plan.total)}`,96,1136);
  c.font='23px '+BODY;c.fillStyle=MUTED;const mode=travelMode(plan);c.fillText(`${mode.name} 이동 약 ${travelMinutes(plan)}분 · ${mode.basis}`,96,1181);
  c.font='21px sans-serif';wrapCanvasText(c,'영업·예약·현재 가격은 방문 전 확인해 주세요. 미확인 비용은 합계에서 제외될 수 있어요.',96,1230,880,29,2);
  return canvas;
}
async function showShareCard(plan){
  const root=openDialog('우리 코스, 한 장으로 저장');root.append(node('p','외부 사진 없이 장소와 일정으로 만든 공유 카드예요.','hint'));
  const canvas=await makeShareCanvas(plan);canvas.className='share-canvas';canvas.setAttribute('aria-label',plan.places.map(p=>p.name).join(' → '));root.append(canvas);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw Error('이미지를 만들지 못했어요. 다시 시도해 주세요.');
  const filename='datemate-'+plan.conditions.visit_date+'.png';
  const actions=node('div',undefined,'actions');actions.append(button('PNG 이미지 저장',()=>{const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);},'primary'));
  const file=new File([blob],filename,{type:'image/png'});
  if(navigator.canShare?.({files:[file]}))actions.append(button('공유하기',async()=>{try{await navigator.share({files:[file],title:'우리 데이트 코스'});}catch(e){if(e.name!=='AbortError')throw e;}}));
  actions.append(button('코스 요약 복사',async()=>{const share=await api('/plans/'+plan.id+'/shares',{});await navigator.clipboard.writeText(`${plan.decision_summary?.title||'우리 코스'}\n${plan.places.map((p,i)=>`${i+1}. ${p.name}`).join('\n')}\n예상 ${range(plan.total)} · 추정/미확인 비용 포함 여부 확인 필요\n${location.origin}${share.url}`);toast('코스 요약과 24시간 공유 링크를 복사했어요.');}));root.append(actions);
}
