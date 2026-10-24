"""지역·취향별 검색 후보에서 후기 5개를 선정하고 검증한 장소를 추천한다."""
import os
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import httpx
from .telemetry import observed_http
from . import store
from .image_search import plain, search_enabled
from .catalog import places
from .routes import distance


class BlogText(HTMLParser):
    def __init__(self):
        super().__init__(); self.depth=0; self.capture=0; self.skip=0; self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.skip+=1
        if tag=='div':
            self.depth+=1
            if 'se-main-container' in dict(attrs).get('class','').split():self.capture=self.depth
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.skip=max(0,self.skip-1)
        if tag=='div':
            if self.depth==self.capture:self.capture=0
            self.depth=max(0,self.depth-1)
    def handle_data(self,data):
        if self.capture and not self.skip:self.parts.append(data)


def public_body(url):
    """고정 네이버 호스트의 공개 문서만 조회. 로그인·차단 우회 없음."""
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.hostname not in ('blog.naver.com','m.blog.naver.com'):return ''
    # 외부 리디렉션 및 임의 URL 접속 방지.
    target='https://m.blog.naver.com'+parsed.path+('?' + parsed.query if parsed.query else '')
    try:
        with httpx.Client(timeout=5,follow_redirects=False) as client:
            with client.stream('GET',target) as response:
                response.raise_for_status()
                if response.status_code!=200:return ''
                data=bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data)>1_500_000:return ''
        parser=BlogText();parser.feed(data.decode('utf-8',errors='replace'))
        return ' '.join(parser.parts)[:60000]
    except (httpx.HTTPError,ValueError):return ''


def base_course_query(c):
    if c.course_query.strip():
        query=c.course_query.strip()
        from .seoul_districts import DISTRICT_ADDRESSES
        if query.removeprefix('서울특별시').removeprefix('서울').strip() in DISTRICT_ADDRESSES:
            return query+' 데이트 코스'
        from .quality import AREAS
        if any(area.rstrip('동') in query for area in AREAS) or re.search(r'[가-힣]{2,8}(?:동|구|역)',query):return query
        area=base_course_query(c.model_copy(update={'course_query':''})).replace(' 데이트 코스','')
        return area+' '+query
    name=c.origin.name
    if name.startswith('지도에서 선택'):
        from .geocoding import district_at
        name=district_at(c.origin.lat,c.origin.lon)
        if not name:return '지도 위치의 지역명 확인 필요'
    district=re.search(r'([가-힣]{1,8}구)(?:\s|$)',name)
    if district:return district[1]+' 데이트 코스'
    area=re.search(r'[가-힣]{2,8}동',c.request+' '+name)
    if area:return area[0]+' 데이트 코스'
    anchors=[('연남동',37.5572,126.9254),('성수동',37.5446,127.0559),('종로',37.5765,126.9855),('강남',37.4979,127.0276)]
    closest=min(anchors,key=lambda a:distance(c.origin.model_dump(),dict(lat=a[1],lon=a[2])))
    if distance(c.origin.model_dump(),dict(lat=closest[1],lon=closest[2]))<2:return closest[0]+' 데이트 코스'
    return re.sub(r'\s*(지역 중심|지도에서 선택.*)$','',name)+' 데이트 코스'


def course_query(c):
    from .taxonomy import CONCEPT_PROFILES
    base=base_course_query(c)
    profile=CONCEPT_PROFILES.get(c.date_subcategory)
    from .request_intent import search_terms
    additions=search_terms(c)
    if profile:additions+=[c.date_subcategory,*profile['search'].split()]
    if not additions:return base
    return base+' '+ ' '.join(word for word in additions if word not in base)


def compact(text):return re.sub(r'[^가-힣a-z0-9]','',text.casefold())


def select_posts(items,query):
    """검색 순위·지역 일치·최근성을 참고하고 작성자가 중복되지 않는 글 5개 선정."""
    area=re.search(r'[가-힣]{1,8}(?:구|동)',query)
    candidates=[];seen=set()
    for rank,item in enumerate(items,1):
        url=item.get('link','');parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.hostname not in ('blog.naver.com','m.blog.naver.com') or url in seen:continue
        seen.add(url)
        author=parsed.path.strip('/').split('/')[0]
        if author in ('PostView.naver','PostView.nhn'):
            from urllib.parse import parse_qs
            author=parse_qs(parsed.query).get('blogId',[url])[0]
        title=plain(item.get('title',''));description=plain(item.get('description',''))
        try:age=(datetime.now(timezone.utc).date()-datetime.strptime(item.get('postdate',''),'%Y%m%d').date()).days
        except (ValueError,TypeError):age=None
        recent=age is not None and 0<=age<=365
        local=bool(area and area[0] in title+' '+description)
        score=1/rank+int(local)*2+int(recent)
        candidates.append(dict(search_rank=rank,title=title,description=description,url=url,posted_at=item.get('postdate',''),author=author,
                               selection_reason=' · '.join(['검색 순위 '+str(rank)]+(['지역명 일치'] if local else [])+(['최근 1년 작성'] if recent else [])),_score=score))
    selected=[];authors=set()
    for post in sorted(candidates,key=lambda p:p['_score'],reverse=True):
        if post['author'] in authors:continue
        authors.add(post['author']);post.pop('_score');post['rank']=len(selected)+1;selected.append(post)
        if len(selected)==5:break
    return selected


def match_places(posts,rows):
    matches={}
    rank_ceiling=max(3,max((p['rank'] for p in posts),default=3))+1
    for place in rows:
        names=[place['name'],*(place.get('search_aliases') or [])]
        wiki=urlsplit(place.get('wikipedia') or '')
        if wiki.hostname=='ko.wikipedia.org':names.append(unquote(wiki.path.rsplit('/',1)[-1]).replace('_',' '))
        names=[compact(re.sub(r'\s*\([^)]*\)$','',n)) for n in names]
        hits=[]
        for post in posts:
            text=compact(post['title']+' '+post['description']+' '+post.get('_body',''))
            if any(len(n)>=3 and n in text for n in names):hits.append(post['rank'])
        if hits:matches[place['id']]={'ranks':hits,'score':sum(rank_ceiling-rank for rank in hits)}
    return matches


def search_courses(c):
    query=course_query(c)
    result=dict(query=query,provider='네이버 검색 후보에서 지역·최근성·작성자 중복을 고려한 후기 최대 5개',posts=[],matches={},
                requested_query=query,search_history=[],concept=c.date_subcategory,search_relaxed=False,
                rating_status='unavailable',rating_note='현재 연결된 공식 API는 네이버 장소 평점을 제공하지 않아 평점을 순위에 반영하지 않았어요.',
                checked_at=datetime.now(timezone.utc).isoformat(),status='key_missing')
    if not search_enabled():return result
    if '지도 위치의 지역명 확인 필요' in query:
        result.update(status='location_unresolved',message='선택 좌표의 지역명을 확인하지 못했어요. 지역명을 검색해 선택하거나 네이버 Maps Reverse Geocoding 설정을 확인해 주세요. 위치 주변 기존 장소로 보완합니다.')
        return result
    key='course-blog-five-v2:'+query+':'+str(c.visit_date)
    cached=store.cached(key)
    if cached:return cached
    try:
        response=observed_http(httpx.get,'https://naverapihub.apigw.ntruss.com/search/v1/blog',params=dict(query=query,display=20,start=1,sort='sim',format='json'),
            headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']},timeout=8)
        response.raise_for_status()
        result['search_history'].append(dict(query=query,result_count=len(response.json().get('items',[]))))
        if not response.json().get('items') and query!=base_course_query(c):
            query=base_course_query(c)
            response=observed_http(httpx.get,'https://naverapihub.apigw.ntruss.com/search/v1/blog',params=dict(query=query,display=20,start=1,sort='sim',format='json'),
                headers={'X-NCP-APIGW-API-KEY-ID':os.environ['NAVER_SEARCH_CLIENT_ID'],'X-NCP-APIGW-API-KEY':os.environ['NAVER_SEARCH_CLIENT_SECRET']},timeout=8)
            response.raise_for_status()
            result.update(query=query,search_relaxed=True)
            result['search_history'].append(dict(query=query,result_count=len(response.json().get('items',[]))))
        result['posts']=select_posts(response.json().get('items',[]),query)
        result['selection_note']='실제 방문자 수나 평점 순위가 아닌, 검색 결과 기반 선정입니다.'
        with ThreadPoolExecutor(max_workers=5) as pool:
            bodies=list(pool.map(public_body,[p['url'] for p in result['posts']]))
        for post,body in zip(result['posts'],bodies):post.update(_body=body,content_scope='공개 본문 + 검색 요약' if body else '검색 요약만 확인',summary=post['description'])
        from .discovery import discover
        new_places,discovery=discover(result['posts'],base_course_query(c))
        result['discovery']=discovery
        result['discovered_ids']=[p['id'] for p in new_places]
        result['matches']=match_places(result['posts'],places('real',c.visit_date))
        rows=places('real',c.visit_date)
        for post in result['posts']:
            post['mentioned_places']=[p['name'] for p in rows if post['rank'] in result['matches'].get(p['id'],{}).get('ranks',[])][:12]
        # 같은 작성자의 반복 게시물은 독립적인 추천으로 중복 가산하지 않는다.
        for match in result['matches'].values():
            authors=set();score=0
            for post in result['posts']:
                if post['rank'] not in match['ranks'] or post['author'] in authors:continue
                authors.add(post['author'])
                try:age=(datetime.now(timezone.utc).date()-datetime.strptime(post['posted_at'],'%Y%m%d').date()).days
                except (ValueError,TypeError):age=None
                score+=(6-post['rank'])*(1 if age is not None and 0<=age<=365 else .5)
            match.update(score=score,independent_authors=len(authors))
        for post in result['posts']:post.pop('_body',None)
        result['status']='available' if result['posts'] else 'not_found'
        result['message']='검색 글에서 확인한 장소를 우선 추천해요.' if result['matches'] else '상위 글에서 현재 장소 데이터와 연결되는 장소를 찾지 못해 기존 조건 기반 추천을 표시해요.'
        store.cache(key,result,900)
    except (httpx.HTTPError,ValueError,TypeError,KeyError):result.update(status='unavailable',message='네이버 코스 검색에 연결하지 못해 기존 조건 기반 추천을 표시해요.')
    return result


def priority(plan,evidence):
    return sum(evidence.get('matches',{}).get(p['id'],{}).get('score',0) for p in plan['places'])
