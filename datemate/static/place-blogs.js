const placeBlogRequests=new Map();
function placeBlogPanel(place,blogMode){
  const panel=node('details',undefined,'place-blogs');
  if(place.demo||blogMode==='demo')return document.createDocumentFragment();
  panel.setAttribute('aria-label',place.name+' 블로그 후기');
  const summary=node('summary','블로그 후기 보기'),content=node('div',undefined,'place-blog-content');
  panel.append(summary,content);
  let loaded=false;
  async function load(){
    loaded=true;content.replaceChildren(node('p','네이버 블로그 후기를 찾고 있어요…','hint'));
    const key=blogMode+':'+place.id;
    try{
      if(!placeBlogRequests.has(key))placeBlogRequests.set(key,api('/places/'+encodeURIComponent(place.id)+'/blogs?mode='+blogMode).catch(error=>{placeBlogRequests.delete(key);throw error;}));
      const data=await placeBlogRequests.get(key);
      content.replaceChildren(node('p',place.name+' · 네이버 블로그 관련도순 최대 3개','hint'));
      if(!data.posts.length)content.append(node('p',data.message,'hint'));
      data.posts.slice(0,3).forEach((post,index)=>{const article=node('article',undefined,'blog-search-post');article.append(sourceLinks((index+1)+'. '+post.title+' ↗',post.url,place.name+' '+post.title),node('small',(post.blogger||'블로그')+' · '+(post.posted_at||'작성일 미확인')));if(post.description)article.append(node('p',post.description,'blog-excerpt'));article.append(node('small','검색 요약 발췌 · 본문 전체나 실제 방문 여부는 확인하지 않았어요.','hint'));content.append(article);});
      if(data.search_url)content.append(link('네이버 블로그에서 더 보기 ↗',data.search_url));
      if(!data.posts.length)content.append(button('후기 다시 검색',()=>{placeBlogRequests.delete(key);return load();}));
    }catch(error){content.replaceChildren(node('p','블로그 검색을 불러오지 못했습니다.','hint'),button('후기 다시 검색',()=>{placeBlogRequests.delete(key);return load();}));}
  }
  panel.addEventListener('toggle',()=>{if(panel.open&&!loaded)load();});
  return panel;
}
