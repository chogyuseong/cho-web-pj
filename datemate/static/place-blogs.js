const placeBlogRequests=new Map();
/* 네이버 블로그 검색이 중간에서 자른 제목·요약 다듬기(순수 함수). 잘린 표시(... / …)가 있을 때만 손대고, 없는 글자는 채우지 않는다. */
const BLOG_CUT_MARK=/(?:\s*(?:\.{3,}|…))+\s*$/;
const BLOG_TRAILING_MARKS=/[\s|\-–—:·,/\\[(<{【「『"']+$/;
// 낱말이 이 글자로 끝나면 다 쓴 낱말(문장 끝)로 본다.
const BLOG_WORD_END=/(?:[.!?~)\]」』】"'”’]|요|다)$/;
function blogCleanText(value){return String(value||'').replace(/\s+/g,' ').trim();}
// 잘림 표시를 걷어 내고, 표시가 낱말에 바로 붙어 있던 덜 끝난 낱말과 남은 구분 기호를 뗀다.
function blogDropPartial(text){
  const attached=/[^\s.…](?:\.{3,}|…)+\s*$/.test(text);
  let rest=text.replace(BLOG_CUT_MARK,'');
  if(attached){const words=rest.split(' ');if(words.length>1&&!BLOG_WORD_END.test(words.at(-1))){words.pop();rest=words.join(' ');}}
  rest=rest.replace(BLOG_TRAILING_MARKS,'');
  // 닫히지 않은 괄호로 시작한 꾸밈말(예: "[분위기")은 덜 끝난 조각이라 괄호부터 뗀다.
  const open=Math.max(...['[','(','【','「','『','<'].map(mark=>rest.lastIndexOf(mark)));
  if(open>0&&!/[\])】」』>]/.test(rest.slice(open)))rest=rest.slice(0,open).replace(BLOG_TRAILING_MARKS,'');
  return rest||text.replace(BLOG_CUT_MARK,'');
}
function blogTitleText(value){
  const text=blogCleanText(value);
  if(!BLOG_CUT_MARK.test(text))return {text,cut:false};
  return {text:blogDropPartial(text)+'…',cut:true};
}
// 요약은 마지막으로 끝난 문장까지만 남긴다. 그러면 너무 짧아질 때(40자 미만)는 낱말 경계에서 끊고 …를 붙인다.
function blogExcerptText(value,minimum=40){
  const text=blogCleanText(value);
  if(!BLOG_CUT_MARK.test(text))return {text,cut:false};
  const rest=text.replace(BLOG_CUT_MARK,'');
  let end=-1;
  for(const match of rest.matchAll(/[.!?](?=\s|$)|(?:[아어여해세이에예네죠까]요|니다|[었았였했]다)(?=\s)/g))end=match.index+match[0].length;
  if(end>=minimum)return {text:rest.slice(0,end).trim(),cut:true};
  return {text:blogDropPartial(text)+'…',cut:true};
}
function placeBlogPanel(place,blogMode){
  const panel=node('details',undefined,'place-blogs');
  if(place.demo||blogMode==='demo')return document.createDocumentFragment();
  panel.setAttribute('aria-label',place.name+' 블로그 후기');
  const summary=node('summary','블로그 후기 보기'),content=node('div',undefined,'place-blog-content');
  panel.append(summary,content);
  let loaded=false;
  const retry=key=>button('후기 다시 검색',()=>{placeBlogRequests.delete(key);return load();},'secondary blog-retry');
  // 불러오는 동안 글 3개 자리의 뼈대를 두어 결과가 들어올 때 높이가 크게 튀지 않게 한다.
  function skeleton(){
    const list=node('div',undefined,'blog-skeleton-list');list.setAttribute('aria-hidden','true');
    for(let i=0;i<3;i++){const item=node('div',undefined,'blog-skeleton');item.append(node('span','','blog-skeleton-title'),node('span','','blog-skeleton-line'),node('span','','blog-skeleton-line short'));list.append(item);}
    return list;
  }
  function state(text,key){const box=node('div',undefined,'blog-state');box.append(node('p',text,'hint'),retry(key));return box;}
  async function load(){
    loaded=true;content.setAttribute('aria-busy','true');
    const status=node('p','네이버 블로그 후기를 찾고 있어요…','hint blog-status');status.setAttribute('role','status');
    content.replaceChildren(status,skeleton());
    const key=blogMode+':'+place.id;
    try{
      if(!placeBlogRequests.has(key))placeBlogRequests.set(key,api('/places/'+encodeURIComponent(place.id)+'/blogs?mode='+blogMode).catch(error=>{placeBlogRequests.delete(key);throw error;}));
      const data=await placeBlogRequests.get(key);
      const posts=data.posts.slice(0,3);
      status.textContent=posts.length?place.name+' · 네이버 블로그 관련도순 최대 3개':'블로그 후기를 찾지 못했어요.';
      content.replaceChildren(status);
      if(!posts.length){content.append(state(data.message||'다른 이름으로 다시 찾아보거나 네이버에서 직접 검색해 보세요.',key));}
      else{
        // 발췌 안내는 목록 맨 위에 한 번만.
        content.append(node('p','검색 요약 발췌 · 본문 전체나 실제 방문 여부는 확인하지 않았어요.','hint blog-scope-note'));
        const list=node('ol',undefined,'blog-post-list');
        posts.forEach((post,index)=>{
          const item=node('li',undefined,'blog-search-post'),title=blogTitleText(post.title),full=blogCleanText(post.title);
          const links=sourceLinks((index+1)+'. '+title.text+' ↗',post.url,place.name+' '+full);
          const anchor=links.querySelector('a');
          if(anchor){anchor.classList.add('blog-post-title');anchor.title=full;anchor.setAttribute('aria-label',(index+1)+'. '+full+' (새 탭에서 원문 열기)');}
          item.append(links,node('small',(post.blogger||'블로그')+' · '+(post.posted_at||'작성일 미확인'),'blog-meta'));
          if(post.description){
            const excerpt=blogExcerptText(post.description),body=node('p',undefined,'blog-excerpt');
            body.append(node('span','미리보기','blog-preview-label'),document.createTextNode(' '+excerpt.text+' '));
            const more=link('원문에서 이어 읽기 ↗',post.url);more.classList.add('blog-read-more');
            body.append(more);item.append(body);
          }
          list.append(item);
        });
        content.append(list);
      }
      if(data.search_url)content.append(link('네이버 블로그에서 더 보기 ↗',data.search_url));
    }catch(error){status.textContent='블로그 검색을 불러오지 못했어요.';content.replaceChildren(status,state('잠시 후 다시 검색해 주세요.',key));}
    finally{content.setAttribute('aria-busy','false');}
  }
  panel.addEventListener('toggle',()=>{if(panel.open&&!loaded)load();});
  return panel;
}
