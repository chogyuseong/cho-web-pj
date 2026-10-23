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
    for title,area,lat,lon,request,categories in presets:
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
