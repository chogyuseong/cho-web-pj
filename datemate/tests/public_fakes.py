"""공공 API(한국관광공사 TourAPI, 소상공인 상가정보)의 가짜 응답. 테스트는 실제 공공 API 를 부르지 않는다.

fake_public_api(monkeypatch) 가 httpx.get 을 바꿔 끼우고 상자를 돌려준다.
  box['tour']   : 관광공사 항목(tour_item 으로 만든 dict)들. 시·군·구 목록·시·도 목록·이름 검색이 모두 이 목록에서 답한다.
  box['stores'] : 상가정보 업소(store_item)들. 업종 조건(indsLclsCd·indsSclsCd)과 반경으로 걸러 답한다.
  box['calls']  : (종류, 조건 dict) 호출 기록. 종류: tour_district(시·군·구 목록)·tour_area(시·도 목록)·tour_keyword·tour_detail·
                  tour_image(detailImage2 추가 사진)·store(업소)·probe(시·군·구를 알아내는 약국 조회).
  box['images'] : contentId → detailImage2 항목(image_item)들.
  box['fail']   : 여기에 든 종류는 500 으로 답한다.
  box['answer'] : 종류 → 그대로 돌려줄 응답(httpx.Response 또는 JSON dict). 오류 응답 모양을 흉내 낼 때 쓴다(관광공사 종류만).
  box['naver']  : 네이버 검색 API 를 부른 URL(추천 경로에서는 블로그 검색 말고는 없어야 한다).
약국 조회(probe)는 반경 안의 관광공사 항목·업소마다 그 주소의 시·군·구 코드를 가진 약국이 하나씩 있는 것처럼 답한다.
"""
import math

import httpx

# 주소 첫 낱말 → 테스트용 시·군·구 코드(상가정보 5자리 = TourAPI lDongRegnCd 2자리 + lDongSignguCd 3자리).
DISTRICTS = {'서울특별시': '11110', '부산광역시': '26230', '대구광역시': '27110', '전북특별자치도': '52111', '강원특별자치도': '51150',
             '경상남도': '48250', '경기도': '41280', '경상북도': '47130', '제주특별자치도': '50110'}
# 예전 분류(cat3)로 적은 테스트 자료 → TourAPI 새 분류(lclsSystm3). 앱은 새 분류만 본다.
LCLS = {'A05020100': 'FD010100', 'A05020200': 'FD020300', 'A05020300': 'FD020200', 'A05020900': 'FD050100', 'A05021000': 'FD040300',
        'A02060100': 'VE070100', 'A02060300': 'VE070300', 'A02060400': 'VE070400', 'A02060500': 'VE070600', 'A02020700': 'VE030100',
        'A02030600': 'VE040100', 'A01011200': 'NA020900', 'A04010700': 'SH050100', 'A03020200': 'VE100200', 'A03020600': 'LS010300',
        'A03021100': 'LS010700', 'A03021800': 'LS011300', 'A03030200': 'LS020200'}


def district_of(address):
    return DISTRICTS.get(str(address or '').split(' ', 1)[0], '11110')


def tour_item(content_id, title, lat, lon, cat3='A05020100', type_id='39', address='부산광역시 부산진구 부전동 1', photo=True, modified='20260101'):
    code = district_of(address)
    return dict(contentid=str(content_id), contenttypeid=type_id, cat3='', lclsSystm3=LCLS.get(cat3, cat3), title=title, addr1=address,
                mapx=str(lon), mapy=str(lat), lDongRegnCd=code[:2], lDongSignguCd=code[2:],
                firstimage=f'https://tong.visitkorea.or.kr/cms/resource/{content_id}.jpg' if photo else '', cpyrhtDivCd='Type1' if photo else '',
                modifiedtime=modified + '000000')


def image_item(content_id, serial, kind='Type3', url=None, name=None):
    """detailImage2 항목(2026-11-20 실제 응답 모양: originimgurl·smallimageurl·imgname·cpyrhtDivCd·serialnum)."""
    url = url or f'https://tong.visitkorea.or.kr/cms/resource/{serial}_image2_1.jpg'
    return dict(contentid=str(content_id), originimgurl=url, smallimageurl=url, imgname=name or f'사진 ({serial})', cpyrhtDivCd=kind,
                serialnum=f'{serial}_1')


def store_item(biz_id, name, lat, lon, code='I20101', label='백반/한정식', branch='', address='부산광역시 부산진구 부전동 2'):
    return dict(bizesId=str(biz_id), bizesNm=name, brchNm=branch, indsLclsCd=code[:2], indsMclsCd=code[:4], indsSclsCd=code, indsSclsNm=label,
                rdnmAdr=address, lnoAdr='', lat=lat, lon=lon, signguCd=district_of(address))


def metres(lat1, lon1, lat2, lon2):
    return math.hypot((lat2 - lat1) * 111_320, (lon2 - lon1) * 111_320 * math.cos(math.radians(lat1)))


def fake_public_api(monkeypatch, key="'test-public-key'"):
    monkeypatch.setenv('TOUR_API_KEY', key)
    box = dict(tour=[], stores=[], calls=[], fail=set(), naver=[], detail={}, images={}, answer={})

    def tour_body(items, total=None):
        return dict(response=dict(header=dict(resultCode='0000'),
                                  body=dict(items=dict(item=items) if items else '', totalCount=len(items) if total is None else total)))

    def store_answer(request, params):
        near = lambda row: metres(float(params['cy']), float(params['cx']), float(row['lat']), float(row['lon'])) <= float(params['radius'])
        if params.get('indsSclsCd') == 'G21501':
            box['calls'].append(('probe', params))
            if 'probe' in box['fail']:
                return httpx.Response(500, text='error', request=request)
            spots = [dict(lat=float(t['mapy']), lon=float(t['mapx']), signguCd=t['lDongRegnCd'] + t['lDongSignguCd']) for t in box['tour']]
            spots += [dict(lat=s['lat'], lon=s['lon'], signguCd=s['signguCd']) for s in box['stores']]
            rows = [dict(bizesId=f'pharmacy-{i}', bizesNm='약국', indsSclsCd='G21501', signguCd=spot['signguCd'], lat=spot['lat'], lon=spot['lon'])
                    for i, spot in enumerate(spots) if near(spot)]
        else:
            box['calls'].append(('store', params))
            if 'store' in box['fail']:
                return httpx.Response(500, text='error', request=request)
            rows = [s for s in box['stores'] if near(s) and all(s.get(name) == value for name, value in params.items() if name.startswith('inds'))]
        if not rows:
            return httpx.Response(200, json=dict(header=dict(resultCode='03', resultMsg='NODATA_ERROR'), body={}), request=request)
        page, size = int(params.get('pageNo', 1)), int(params.get('numOfRows', 1000))
        return httpx.Response(200, json=dict(header=dict(resultCode='00', stdrYm='202609'),
                                             body=dict(items=rows[(page - 1) * size:page * size], totalCount=len(rows))), request=request)

    def get(url, params=None, **kwargs):
        params = dict(params or {})
        request = httpx.Request('GET', url)
        if 'naverapihub' in url:
            box['naver'].append(url)
            return httpx.Response(200, json=dict(items=[]), request=request)
        if 'storeListInRadius' in url:
            return store_answer(request, params)
        kind = ('tour_district' if 'areaBasedList2' in url and params.get('lDongSignguCd') else 'tour_area' if 'areaBasedList2' in url
                else 'tour_keyword' if 'searchKeyword2' in url else 'tour_detail' if 'detailIntro2' in url
                else 'tour_image' if 'detailImage2' in url else None)
        if kind is None:
            return httpx.Response(404, text='not mocked', request=request)
        box['calls'].append((kind, params))
        if kind in box['fail']:
            return httpx.Response(500, text='error', request=request)
        if kind in box['answer']:
            answer = box['answer'][kind]
            return httpx.Response(answer.status_code, content=answer.content, request=request) if isinstance(answer, httpx.Response) \
                else httpx.Response(200, json=answer, request=request)
        if kind == 'tour_image':
            return httpx.Response(200, json=tour_body(box['images'].get(str(params.get('contentId')), [])), request=request)
        if kind == 'tour_detail':
            intro = box['detail'].get(str(params.get('contentId')))
            return httpx.Response(200, json=tour_body([intro] if intro else []), request=request)
        rows = [t for t in box['tour'] if t['lDongRegnCd'] == str(params.get('lDongRegnCd'))]
        if params.get('lDongSignguCd'):
            rows = [t for t in rows if t['lDongSignguCd'] == str(params['lDongSignguCd'])]
        if kind == 'tour_keyword':
            rows = [t for t in rows if params['keyword'] in t['title']]
        if params.get('contentTypeId'):
            rows = [t for t in rows if t['contenttypeid'] == str(params['contentTypeId'])]
        for name in ('lclsSystm1', 'lclsSystm2', 'lclsSystm3'):
            if params.get(name):
                rows = [t for t in rows if t['lclsSystm3'].startswith(params[name])]
        page, size = int(params.get('pageNo', 1)), int(params.get('numOfRows', 100))
        return httpx.Response(200, json=tour_body(rows[(page - 1) * size:page * size], len(rows)), request=request)

    monkeypatch.setattr(httpx, 'get', get)
    return box


def calls(box, kind):
    return [params for name, params in box['calls'] if name == kind]
