const placeBlogRequests=new Map();
/* 네이버 블로그 검색 결과 블록(네이버 검색 API 특약 2.2, 2026-09 개정).
   받은 순서 그대로, 받은 건수 그대로, 제목·요약은 API 가 준 글자 그대로 넣는다. 고르거나 다시 줄 세우지 않고, 잘린 제목·요약을 다듬지 않으며,
   블록 안에는 API 가 준 것(제목·작성자·작성일·요약·원본 링크)과 출처 표시만 둔다. 우리 설명·판정은 블록 밖에 적는다.
   목록이 길면 처음 first 건만 펴고 나머지는 블록 뒤의 「더 보기」로 편다(순서·내용은 그대로).
   장소 블로그 후기 패널(아래)과 코스 조사 패널(course-search.js)이 함께 쓴다. */
function naverBlogItem(post){
  const item=node('li',undefined,'blog-search-post'),title=link(post.title||post.url||'',post.url);
  title.classList.add('blog-post-title');
  item.append(title);
  const meta=[post.blogger,post.posted_at].filter(Boolean).join(' · ');
  if(meta)item.append(node('small',meta,'blog-meta'));
  if(post.description)item.append(node('p',post.description,'blog-summary'));
  return item;
}
function naverBlogBlock(posts,searchUrl,first=5){
  // 블록 공통 부품(naver-attribution.js naverResultBlock): 머리글(출처 표시) + 본문(받은 글 목록).
  const wrap=document.createDocumentFragment(),block=naverResultBlock('블로그 검색',searchUrl,{tag:'div'}),list=node('ol',undefined,'blog-post-list');
  list.append(...posts.slice(0,first).map(naverBlogItem));
  block.body.append(list);
  wrap.append(block);
  if(posts.length>first){
    const more=button(`나머지 ${posts.length-first}건 더 보기`,()=>{more.remove();list.append(...posts.slice(first).map(naverBlogItem));},'secondary blog-more');
    wrap.append(more);
  }
  return wrap;
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
    const status=node('p','네이버 블로그 글을 찾고 있어요…','hint blog-status');status.setAttribute('role','status');
    content.replaceChildren(status,skeleton());
    const key=blogMode+':'+place.id;
    try{
      if(!placeBlogRequests.has(key))placeBlogRequests.set(key,api('/places/'+encodeURIComponent(place.id)+'/blogs?mode='+blogMode).catch(error=>{placeBlogRequests.delete(key);throw error;}));
      const data=await placeBlogRequests.get(key);
      const posts=Array.isArray(data.posts)?data.posts:[];
      status.textContent=posts.length?`‘${data.query||place.name}’ 네이버 블로그 검색 결과 ${posts.length}건`:'블로그 글을 찾지 못했어요.';
      content.replaceChildren(status);
      if(!posts.length){content.append(state(data.message||'네이버에서 직접 검색해 보세요.',key));}
      else{
        // 우리 안내는 블록 밖에 한 번만. 블록 안은 네이버가 준 순서·건수·글자 그대로다.
        content.append(node('p','네이버가 준 순서 그대로예요. 이 장소와 관련 없는 글이나 광고·협찬 글이 섞여 있을 수 있고, 실제 방문 여부는 확인하지 않았어요.','hint blog-scope-note'),naverBlogBlock(posts,data.search_url,3));
      }
      if(data.search_url)content.append(link('네이버 블로그에서 더 보기 ↗',data.search_url));
    }catch(error){status.textContent='블로그 검색을 불러오지 못했어요.';content.replaceChildren(status,state('잠시 후 다시 검색해 주세요.',key));}
    finally{content.setAttribute('aria-busy','false');}
  }
  panel.addEventListener('toggle',()=>{if(panel.open&&!loaded)load();});
  return panel;
}
