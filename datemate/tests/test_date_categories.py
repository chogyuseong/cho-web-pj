import pytest
from pydantic import ValidationError
from app.models import Conditions
from app.planner import candidates
from app.taxonomy import DATE_CATEGORIES, DATE_THEMES


@pytest.mark.parametrize('category,sub',[(c,s) for c,values in DATE_CATEGORIES.items() for s in values])
def test_classification_filters_recommendation(category,sub):
    conditions=Conditions(visit_date='2026-10-24',date_category=category,date_subcategory=sub)
    rows=candidates(conditions)
    assert rows
    assert all(row['category'] in DATE_THEMES[sub] for row in rows)
    if category=='날씨별' and sub in ('비 오는 날','눈 오는 날'):
        assert all(row['setting']=='indoor' for row in rows)


def test_invalid_category_pair_rejected():
    with pytest.raises(ValidationError):
        Conditions(visit_date='2026-10-24',date_category='타입별',date_subcategory='지적인 데이트')
