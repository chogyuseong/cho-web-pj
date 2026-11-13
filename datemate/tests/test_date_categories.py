import pytest
from pydantic import ValidationError
from app.models import Conditions
from app.planner import candidates
from app.taxonomy import DATE_CATEGORIES, DATE_THEMES


@pytest.mark.parametrize('category,sub',[(c,s) for c,values in DATE_CATEGORIES.items() for s in values])
def test_classification_filters_recommendation(category,sub):
    # 조건 화면에서 직접 고른 분류(explicit_fields)는 후보를 거른다. 화면이 대신 넣은 분류는 아래 테스트.
    conditions=Conditions(visit_date='2026-10-24',date_category=category,date_subcategory=sub,explicit_fields=['date_subcategory'])
    rows=candidates(conditions)
    assert rows
    assert all(row['category'] in DATE_THEMES[sub] for row in rows)
    if category=='날씨별' and sub in ('비 오는 날','눈 오는 날'):
        assert all(row['setting']=='indoor' for row in rows)


def test_classification_set_by_the_screen_only_orders_candidates():
    # 홈 동네 카드처럼 화면이 넣은 분류는 거르지 않고, 분류에 맞는 장소를 앞에 둔다.
    preset=Conditions(visit_date='2026-10-24',date_category='타입별',date_subcategory='활동적인')
    rows=candidates(preset)
    assert {row['category'] for row in rows}-set(DATE_THEMES['활동적인'])
    matching=[bool(set(row.get('themes') or [row['category']])&set(DATE_THEMES['활동적인'])) for row in rows]
    assert any(matching) and matching==sorted(matching,reverse=True)


def test_invalid_category_pair_rejected():
    with pytest.raises(ValidationError):
        Conditions(visit_date='2026-10-24',date_category='타입별',date_subcategory='지적인 데이트')
