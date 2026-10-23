from app.request_intent import matches


def test_broad_dining_theme_does_not_turn_a_museum_into_a_cafe():
    p=dict(id='museum',name='차박물관',category='카페·미식',description='차 관련 전시 공간',tags=['카페·미식','문화·예술'])
    assert not matches(p,'cafe')
    assert matches(dict(p,id='coffee',name='로스터리 카페',tags=['cafe']),'cafe')
