"""Small, source-backed starting ideas; these are not prevalidated itineraries."""
from fastapi import APIRouter
from .catalog import places
from .routes import distance
router=APIRouter()

@router.get('/api/inspirations')
def inspirations():
    rows=places('real')
    presets=[('종로 문화 산책','종로',37.5765,126.9855,'전시 관람 후 산책',['문화·예술','산책·풍경']),
             ('성수에서 새로운 경험','성수',37.5446,127.0559,'공방 체험과 카페',['체험·제작','카페·미식']),
             ('연남에서 쉬어가는 하루','연남',37.562,126.925,'카페와 산책',['카페·미식','산책·풍경'])]
    result=[]
    from .preferences import operating_source_current
    reviewed=[p for pid in ('Q12592360','Q97205213') for p in rows if p['id']==pid and operating_source_current(p)]
    if len(reviewed)==2:
        result.append(dict(title='종로, 운영 자료를 확인한 박물관 두 곳',area='종로',origin=dict(name='종로 지역 중심',lat=37.575,lon=126.98),
            request='박물관 관람 2곳',defaults=dict(count=2,include_meal=False,start='11:00',end='15:00'),
            places=[dict(id=p['id'],name=p['name'],category=p['category'],source=p['source']) for p in reviewed],
            note='일반 관람 운영·가격 출처 확인 · 방문일 휴무·예약 예외와 이동 시간은 추천 시 재계산. 모든 방문 조건을 보장하는 확정 코스는 아닙니다.'))
    for title,area,lat,lon,request,categories in presets:
        if area=='종로' and len(reviewed)==2:continue
        point=dict(name=area+' 지역 중심',lat=lat,lon=lon)
        candidates=[p for p in rows if p.get('source') and not p.get('demo') and p.get('category') in categories and distance(point,p)<2.5]
        candidates.sort(key=lambda p:(categories.index(p['category']),distance(point,p)))
        selected=[]
        for category in categories:
            match=next((p for p in candidates if p['category']==category),None)
            if match:selected.append(match)
        for p in candidates:
            if len(selected)>=3:break
            if all(p['id']!=q['id'] for q in selected):selected.append(p)
        if not selected:continue
        result.append(dict(title=title,area=area,origin=point,request=request,
            places=[dict(id=p['id'],name=p['name'],address=p.get('address'),category=p['category'],source=p['source']) for p in selected],
            note='등록된 실제 장소 아이디어 · 영업·예산·방문 순서는 추천 시 다시 계산해요.'))
    return {'items':result}
