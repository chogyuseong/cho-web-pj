"""레저 종목 목록: 종목 분류 표, 자유 입력 해석, 묶음 검색(호출 12건 이하·예산 집계), 실내·실외 반경."""
import pytest
from app.sports import classify, setting_of, BY_KEY, KEYS
from app.request_intent import interpret, matches
from test_leisure_results import fixture_plan


# (업종 분류, 상호) -> (종목, 실내/실외) 또는 None(잡음·확인 불가로 후보에서 뺌)
CLASSIFY_TABLE = [
    ('스포츠,오락>볼링장', '강남볼링센터', ('bowling', 'indoor')),
    ('스포츠,오락>당구장', '큐 당구클럽', ('billiards', 'indoor')),
    ('스포츠,오락>당구장', '포켓볼 라운지', ('billiards', 'indoor')),
    ('스포츠시설>체육관', '종로 배드민턴 체육관', ('badminton', 'indoor')),
    ('스포츠,오락>클라이밍', '더클라임 종로', ('climbing', 'indoor')),
    ('스포츠,오락>골프연습장', 'OO 스크린골프', ('screen_golf', 'indoor')),
    ('스포츠,오락', '스크린테니스 OO', ('indoor_tennis', 'indoor')),
    ('스포츠,오락>롤러스케이트장', '롤러장 OO', ('roller', 'indoor')),
    ('스포츠,오락>아이스링크', '목동 아이스링크', ('skating', 'indoor')),
    ('스포츠시설>수영장', 'OO 실내수영장', ('swimming', 'indoor')),
    ('스포츠시설>수영장', 'OO 야외수영장', ('swimming', 'outdoor')),
    ('스포츠,오락>사격장', 'OO 클레이사격장', ('shooting', 'outdoor')),
    ('스포츠,오락>낚시터', 'OO 실내낚시카페', ('fishing', 'indoor')),
    ('스포츠,오락>수상레저', '뚝섬 수상레저', ('water_leisure', 'outdoor')),
    ('스포츠,오락>수상레저', '한강 카약 체험', ('paddle', 'outdoor')),
    ('스포츠,오락>승마장', '서울 승마클럽', ('horse_riding', 'outdoor')),
    ('스포츠,오락>테니스장', 'OO 테니스장', ('tennis', 'outdoor')),
    ('스포츠,오락>요트', '한강 요트투어', ('boating', 'outdoor')),
    ('여행,명소>등산로', '북한산 등산로', ('hiking', 'outdoor')),
    ('스포츠,오락>카트장', 'OO 카트장', ('kart_luge', 'outdoor')),
    ('여행,명소>루지', '스카이라인 루지', ('kart_luge', 'outdoor')),
    ('술집>다트바', '다트 펍', ('darts', 'indoor')),
    # 잡음: 용품·판매점, 학원·교습소, 협회, 마사지·병원, 식당(지명 '수영구'), 카페, 연습장, 수리점
    ('쇼핑,유통>스포츠용품', '배드민턴 용품점', None),
    ('스포츠,오락>당구장', '당구용품 판매', None),
    ('교육,학문>수영', '아쿠아 수영 학원', None),
    ('스포츠,오락>클라이밍', '클라이밍 교습소', None),
    ('단체,협회>체육단체', '대한카누연맹', None),
    ('스포츠,오락>테니스장', '테니스협회 사무실', None),
    ('의료,건강>마사지', '스포츠 마사지', None),
    ('병원,의원>정형외과', '스포츠 재활 정형외과', None),
    ('음식점>한식', '수영구 돼지국밥', None),
    ('카페,디저트', '등산로 입구 카페', None),
    ('스포츠,오락>골프연습장', 'OO골프연습장', None),
    ('자전거,수리', '자전거 수리점', None),
    ('스포츠,오락', '스포츠몬스터', None),
    # 상호의 가게 표현: '스토어'·'샵'·'숍'은 업종이 '당구장'이어도 판매점으로 보고 뺀다(실제 검색에서 채택됐던 사례).
    ('스포츠,오락>당구장', 'SS빌리어드스토어', None),
    ('스포츠,오락>당구장', '큐 당구샵', None),
    ('스포츠,오락>볼링장', '볼링 프로숍', None),
    # '몰'·'마트'는 시설이 든 건물 이름일 수 있어 업종 끝이 '…장' 시설이면 남기고, 아니면 뺀다.
    ('스포츠,오락>볼링장', '롯데몰 볼링장', ('bowling', 'indoor')),
    ('스포츠,오락', '클라이밍 몰', None),
    ('스포츠,오락>볼링장', '스마트 볼링장', ('bowling', 'indoor')),
    ('스포츠,오락>클라이밍', '몰입 클라이밍', ('climbing', 'indoor')),
    # '교실'·'클럽'은 실제 탁구장·당구장 상호에 흔해 그대로 둔다. '빌리어드'는 당구장 상호로 본다.
    ('스포츠,오락>탁구장', '성동탁구교실', ('table_tennis', 'indoor')),
    ('스포츠,오락', '성수 빌리어드', ('billiards', 'indoor')),
]


@pytest.mark.parametrize('category,name,expected', CLASSIFY_TABLE)
def test_sport_classification_table(category, name, expected):
    sport = classify(category, name)
    if expected is None:
        assert sport is None
    else:
        assert sport and (sport.key, setting_of(sport, name + ' ' + category)[0]) == expected


def test_sport_table_covers_indoor_and_outdoor_and_defaults_are_marked():
    indoor = {k for k in KEYS if BY_KEY[k].setting == 'indoor'}
    outdoor = {k for k in KEYS if BY_KEY[k].setting == 'outdoor'}
    assert {'climbing', 'bowling', 'table_tennis', 'badminton', 'skating', 'screen_golf', 'billiards', 'screen_baseball',
            'indoor_tennis', 'archery', 'shooting', 'darts', 'roller', 'trampoline', 'swimming', 'squash',
            'indoor_surfing', 'indoor_ski', 'vr_sports', 'basketball'} <= indoor
    assert {'cycling', 'paddle', 'surfing', 'hiking', 'tennis', 'futsal', 'horse_riding', 'kart_luge', 'zipline',
            'golf', 'ski', 'boating', 'fishing', 'paragliding'} <= outdoor
    # 단서가 없으면 기본값이고, 시설에 따라 다른 종목은 화면에서 그렇게 표시한다.
    assert setting_of(BY_KEY['swimming'], 'OO 수영장') == ('indoor', 'default') and BY_KEY['swimming'].varies
    assert setting_of(BY_KEY['tennis'], 'OO 테니스장') == ('outdoor', 'default') and BY_KEY['tennis'].varies


@pytest.mark.parametrize('text,key', [
    ('당구 치고 싶어', 'billiards'), ('포켓볼 한 판', 'billiards'), ('카약 타기', 'paddle'), ('서핑 배우고 싶어', 'surfing'),
    ('루지 타러 가자', 'kart_luge'), ('고카트 타고 싶어', 'kart_luge'), ('양궁 체험', 'archery'), ('사격 해보자', 'shooting'),
    ('다트 던지러 가자', 'darts'), ('롤러장 가고 싶어', 'roller'), ('트램폴린 뛰기', 'trampoline'), ('수영하고 싶어', 'swimming'),
    ('테니스 치자', 'tennis'), ('풋살 한 게임', 'futsal'), ('등산 가자', 'hiking'), ('승마 체험', 'horse_riding'),
    ('낚시 데이트', 'fishing'), ('실내 테니스', 'indoor_tennis'), ('짚라인 타기', 'zipline'), ('패러글라이딩', 'paragliding'),
    ('스크린야구', 'screen_baseball'), ('롤러스케이트', 'roller'),
])
def test_new_sport_words_are_interpreted(text, key):
    assert key in interpret(text)['intents']


@pytest.mark.parametrize('text,wrong', [
    ('부산 수영구 맛집', 'swimming'), ('수영로 카페', 'swimming'), ('김수영 시인 기념관', 'swimming'),
    ('쇼핑 카트 끌고 장보기', 'kart_luge'), ('위스키 바', 'ski'), ('스키니진 쇼핑', 'ski'), ('인터넷 서핑', 'surfing'),
    ('다트머스 대학 이야기', 'darts'), ('자전거로 이동', 'cycling'), ('롤러스케이트', 'skating'), ('스크린골프장', 'golf'),
    ('실내 테니스', 'tennis'),
])
def test_ambiguous_words_are_not_misread(text, wrong):
    assert wrong not in interpret(text)['intents']


@pytest.mark.parametrize('text,excluded,wanted', [
    ('등산 말고 볼링', 'hiking', 'bowling'), ('당구는 별로고 탁구', 'billiards', 'table_tennis'),
    ('수영 빼고 클라이밍', 'swimming', 'climbing'), ('서핑 말고 카페', 'surfing', 'cafe'),
])
def test_negative_sport_is_excluded(text, excluded, wanted):
    parsed = interpret(text)
    assert excluded in parsed['excluded'] and excluded not in parsed['intents'] and wanted in parsed['intents']


def test_weather_words_inside_sport_words_do_not_force_indoor():
    # '수영하고'의 '영하'는 추위가 아니다. 실외 종목 요청은 더위 표현이 있어도 실내로 묶지 않는다.
    assert 'setting' not in interpret('수영하고 싶어')['patch']
    assert 'setting' not in interpret('더운 날 서핑')['patch']


def test_place_matching_uses_guarded_words():
    assert not matches({'name': '등산로 입구 카페'}, 'hiking')
    assert matches({'name': '북한산 등산로'}, 'hiking')
    assert not matches({'name': '롤러스케이트장'}, 'skating')
    assert matches({'name': '목동 아이스링크'}, 'skating')
    assert not matches({'name': '부산 수영구 국밥'}, 'swimming')
    assert matches({'name': '볼링장', 'tags': ['bowling']}, 'bowling')


def offset(anchor, km_north):
    return anchor['lat'] + km_north / 111.0


@pytest.fixture
def public_leisure(monkeypatch):
    """레저 후보의 공공 자료(한국관광공사 레포츠, 소상공인 상가정보 예술·스포츠 업종)를 흉내 낸다. 외부 호출 없음.
    네이버 지역 검색은 부르면 실패한다."""
    from public_fakes import fake_public_api, store_item, tour_item
    api = fake_public_api(monkeypatch)
    monkeypatch.setattr('app.naver_local.lookup', lambda *a, **k: pytest.fail('네이버 지역 검색 호출'))
    plan = fixture_plan()
    anchor = plan['places'][0]

    def shop(biz, name, code, label, km, address='서울특별시 종로구 율곡로 10'):
        return store_item(biz, name, offset(anchor, km), anchor['lon'], code=code, label=label, address=address)

    def tour(content_id, name, cat3, km):
        return tour_item(content_id, name, offset(anchor, km), anchor['lon'], cat3=cat3, type_id='28', address='서울특별시 종로구 율곡로 20')

    api['stores'] += [shop('B1', '가까운 볼링장', 'R10309', '볼링장', 1.0), shop('B2', '먼 볼링장', 'R10309', '볼링장', 3.0),
                      shop('B3', '볼링용품 판매', 'R10314', '기타 스포츠시설 운영업', .5), shop('B4', '큐 당구클럽', 'R10310', '당구장', .8),
                      shop('B5', '경기 당구장', 'R10310', '당구장', .8, '경기도 고양시 덕양구 1'), shop('B6', '파워짐', 'R10307', '헬스장', .3)]
    api['tour'] += [tour(501, '한강 카약', 'A03030200', 4.0), tour(502, '먼 승마클럽', 'A03021100', 8.0),
                    tour(503, '청소년 수련원', 'A03020200', 1.0)]
    return plan, anchor, api


def found_leisure():
    from app import public_places
    return {p['name']: p for p in public_places.candidates()}


def test_public_leisure_discovery_is_classified_counted_and_cached(public_leisure):
    from app.models import Conditions
    from app.leisure import discover_leisure
    plan, anchor, api = public_leisure
    c = Conditions.model_validate(plan['conditions'] | {'mode': 'real'})
    result = discover_leisure(c, anchor)
    assert result['search_status'] == 'complete' and result['lookups'] == 2
    assert [s['source'] for s in result['sources']] == ['tour', 'store:play']
    names = found_leisure()
    assert set(names) == {'가까운 볼링장', '큐 당구클럽', '한강 카약'}
    assert names['가까운 볼링장']['tags'][0] == 'bowling' and names['한강 카약']['tags'][0] == 'paddle'
    assert names['한강 카약']['setting'] == 'outdoor' and all(p['leisure_search'] and p['id'].startswith('public:') for p in names.values())
    # 먼 볼링장(실내 반경 1.5km 밖)은 빠지고, 용품점·헬스장·수련원·다른 시·도는 종목 장소가 아니다.
    assert result['stats']['out_of_radius'] == 1 and result['stats']['unclassified'] == 4
    assert result['adopted_by_sport'] == {'bowling': 1, 'billiards': 1, 'paddle': 1}
    # 같은 위치를 다시 찾으면 캐시를 쓰고 외부 호출이 없다.
    used = len(api['calls'])
    again = discover_leisure(c, anchor)
    assert again['cache_hit'] and again['lookups'] == 0 and len(api['calls']) == used and not api['naver']


def test_car_widens_outdoor_radius_and_excluded_sport_is_left_out(public_leisure):
    from app.models import Conditions
    from app.leisure import discover_leisure
    plan, anchor, api = public_leisure
    c = Conditions.model_validate(plan['conditions'] | {'mode': 'real', 'transport': 'car', 'request': '승마 하고 볼링은 말고'})
    result = discover_leisure(c, anchor)
    names = found_leisure()
    assert '먼 승마클럽' in names and names['먼 승마클럽']['tags'][0] == 'horse_riding'
    assert '가까운 볼링장' not in names and result['stats']['excluded'] == 2


def sport_row(anchor, pid, name, key, category, km):
    return dict(anchor, id=pid, name=name, category='레저·활동', themes=['레저·활동'], tags=[key, category],
                description=category, lat=offset(anchor, km))


def test_options_split_indoor_outdoor_with_radius_avoid_and_exclusions(monkeypatch):
    from app.leisure import options, nearby_sports
    plan = fixture_plan()
    anchor = plan['places'][0]
    rows = [
        sport_row(anchor, 'in-near', '가까운 볼링장', 'bowling', '스포츠,오락>볼링장', 1.0),
        sport_row(anchor, 'in-far', '먼 클라이밍', 'climbing', '스포츠,오락>클라이밍', 2.5),
        sport_row(anchor, 'out-near', '한강 수상레저', 'water_leisure', '스포츠,오락>수상레저', 4.0),
        sport_row(anchor, 'out-far', '먼 승마클럽', 'horse_riding', '스포츠,오락>승마장', 8.0),
        sport_row(anchor, 'avoided', '시끄러운 당구장', 'billiards', '스포츠,오락>당구장', .5),
    ]
    monkeypatch.setattr('app.catalog.places', lambda *args: [*rows, *plan['places']])
    plan['conditions'].update(max_leg=180, avoid=['시끄러운'])
    ids = [p['id'] for _, p in nearby_sports(plan, 0)]
    assert ids == ['in-near', 'out-near']
    result = options(plan, 0, [])
    sports = {r['plan']['places'][0]['id']: r['sport'] for r in result}
    assert sports['in-near']['setting'] == 'indoor' and sports['in-near']['label'] == '볼링'
    assert sports['out-near']['setting'] == 'outdoor' and sports['out-near']['radius_km'] == 5.0
    assert all(r['plan']['places'][1] == plan['places'][1] for r in result)
    # 자동차면 실외 반경이 넓어진다. 실내 반경은 그대로다.
    car = dict(plan, conditions=dict(plan['conditions'], transport='car'))
    assert [p['id'] for _, p in nearby_sports(car, 0)] == ['in-near', 'out-near', 'out-far']
    # 제외한 활동은 후보에서 빠진다.
    excluded = dict(plan, conditions=dict(plan['conditions'], request='볼링은 말고'))
    assert 'in-near' not in [p['id'] for _, p in nearby_sports(excluded, 0)]
    # 고정한 장소는 바꾸지 않는다.
    with pytest.raises(ValueError):
        options(plan, 0, [0])
    locked = dict(plan, conditions=dict(plan['conditions'], locked={'0': anchor['id']}))
    with pytest.raises(ValueError):
        options(locked, 0, [])


def test_api_returns_sport_and_new_radius_message(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app import store
    with TestClient(app) as client:
        client.get('/api/status')
        plan = store.save_plan(fixture_plan(), store.owner_of(client.cookies.get('dm_session')))
        anchor = plan['places'][0]
        row = sport_row(anchor, 'api-tennis', 'OO 테니스장', 'tennis', '스포츠,오락>테니스장', 2.0)
        monkeypatch.setattr('app.catalog.places', lambda *args: [row, *plan['places']])
        data = client.post('/api/plans/' + plan['id'] + '/leisure-options', json={'index': 0}).json()
        assert '1.5km' in data['message'] and '5km' in data['message']
        option = next(o for o in data['options'] if o['place']['id'] == 'api-tennis')
        assert option['sport'] == {'key': 'tennis', 'label': '테니스', 'setting': 'outdoor', 'setting_basis': 'default',
                                   'varies': True, 'radius_km': 5.0}


def test_same_venue_in_both_public_sources_is_kept_once(public_leisure):
    from app.models import Conditions
    from app.leisure import discover_leisure
    from public_fakes import store_item, tour_item
    plan, anchor, api = public_leisure
    api['stores'].append(store_item('C1', '그루트  클라이밍', offset(anchor, .9), anchor['lon'], code='R10314', label='기타 스포츠시설 운영업',
                                    address='서울특별시 종로구 율곡로 30'))
    api['tour'].append(tour_item(601, '그루트 클라이밍', offset(anchor, .9), anchor['lon'], cat3='A03021800', type_id='28',
                                 address='서울특별시 종로구 율곡로 30'))
    c = Conditions.model_validate(plan['conditions'] | {'mode': 'real'})
    result = discover_leisure(c, anchor)
    assert [name for name in found_leisure() if '그루트' in name] == ['그루트 클라이밍']
    assert result['stats']['duplicate'] == 1 and result['adopted_by_sport']['climbing'] == 1


def test_nearby_sports_merges_same_name_and_keeps_distinct_neighbours(monkeypatch):
    from app.leisure import nearby_sports
    plan = fixture_plan()
    anchor = plan['places'][0]
    rows = [
        sport_row(anchor, 'a', '그루트  클라이밍', 'climbing', '스포츠,오락>클라이밍', .9),
        sport_row(anchor, 'b', '그루트 클라이밍!', 'climbing', '스포츠,오락>클라이밍', .9005),
        sport_row(anchor, 'c', '그루트 클라이밍 성수점', 'climbing', '스포츠,오락>클라이밍', .901),
        # 같은 건물의 다른 업체(이름이 다름)는 합치지 않는다.
        sport_row(anchor, 'd', '성수 볼링센터', 'bowling', '스포츠,오락>볼링장', .9),
        # 이름이 겹쳐도 30m 밖이면 다른 지점이다.
        sport_row(anchor, 'e', '그루트 클라이밍 뚝섬점', 'climbing', '스포츠,오락>클라이밍', 1.2),
    ]
    monkeypatch.setattr('app.catalog.places', lambda *args: [*rows, *plan['places']])
    plan['conditions'].update(max_leg=180)
    assert sorted(p['id'] for _, p in nearby_sports(plan, 0)) == ['a', 'd', 'e']


def test_rejections_are_counted_per_setting(monkeypatch):
    from app.leisure import options
    import app.planner as planner
    plan = fixture_plan()
    anchor = plan['places'][0]
    rows = [sport_row(anchor, 'in', '가까운 볼링장', 'bowling', '스포츠,오락>볼링장', .5),
            sport_row(anchor, 'out1', '먼 테니스장', 'tennis', '스포츠,오락>테니스장', 3.0),
            sport_row(anchor, 'out2', '먼 승마클럽', 'horse_riding', '스포츠,오락>승마장', 4.0)]
    monkeypatch.setattr('app.catalog.places', lambda *args: [*rows, *plan['places']])
    plan['conditions'].update(max_leg=180)
    evaluate = planner.evaluate
    monkeypatch.setattr(planner, 'evaluate', lambda chosen, c, **kw: (None, '구간 이동 시간 초과')
                        if chosen[0]['id'].startswith('out') else evaluate(chosen, c, **kw))
    diagnostics = {}
    result = options(plan, 0, [], diagnostics=diagnostics)
    assert [r['plan']['places'][0]['id'] for r in result] == ['in']
    assert diagnostics['rejected_by_setting']['outdoor'] == {'count': 2, 'reasons': {'구간 이동 시간 초과': 2}}
    assert diagnostics['rejected_by_setting']['indoor']['count'] == 0
