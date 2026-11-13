"""사용자용 데이트 분류와 기존 장소 유형 사이의 서비스 분류 규칙."""
DATE_CATEGORIES = {
    '계절별': ['봄', '여름', '가을', '겨울'],
    '날씨별': ['맑은 날', '비 오는 날', '눈 오는 날'],
    '콘셉트별': ['즐거운 데이트', '편안한 데이트', '지적인 데이트', '동심 데이트'],
    '타입별': ['활동적인', '사교적인'],
}
DATE_THEMES = {
    '봄': ['산책·풍경', '문화·예술'],
    '여름': ['카페·미식', '문화·예술', '오락·놀이'],
    '가을': ['산책·풍경', '문화·예술', '휴식·힐링'],
    '겨울': ['카페·미식', '체험·제작', '문화·예술'],
    '맑은 날': ['산책·풍경', '레저·활동'],
    '비 오는 날': ['카페·미식', '문화·예술', '체험·제작', '오락·놀이'],
    '눈 오는 날': ['카페·미식', '문화·예술', '휴식·힐링'],
    '즐거운 데이트': ['오락·놀이', '레저·활동', '체험·제작'],
    '편안한 데이트': ['휴식·힐링', '산책·풍경', '카페·미식'],
    '지적인 데이트': ['문화·예술', '체험·제작'],
    '동심 데이트': ['오락·놀이', '체험·제작'],
    '활동적인': ['레저·활동', '산책·풍경', '체험·제작'],
    '사교적인': ['카페·미식', '체험·제작', '오락·놀이'],
}


def classification_themes(conditions):
    return DATE_THEMES.get(conditions.date_subcategory, [])


def classification_strict(c):
    """데이트 분류를 후보 조건으로 지킬지. 사용자가 조건 화면에서 소분류를 직접 고르거나(explicit_fields)
    자유 입력 글에서 분류가 나온 경우만 조건이다. 홈 동네 카드처럼 화면이 대신 넣은 분류는 우선순위로만 쓴다
    (분류에 맞는 장소를 먼저 넣고, 모자라면 다른 종류로 채운다. 완화·미충족으로 표시하지 않는다)."""
    if not c.date_subcategory:return False
    if {'date_category','date_subcategory'}&set(c.explicit_fields):return True
    from .request_intent import intent
    return intent(c)['patch'].get('date_subcategory')==c.date_subcategory


def filtering_themes(c):
    """후보를 거르는 분류 유형(직접 고른 분류만)."""
    return classification_themes(c) if classification_strict(c) else []


def preferred_themes(c):
    """우선순위로만 쓰는 분류 유형(화면이 대신 넣은 분류)."""
    return [] if classification_strict(c) else classification_themes(c)


def matches_classification(place,themes):
    return bool(set(place.get('themes') or [place['category']]).intersection(themes))


def indoor_weather(c):
    """'비 오는 날'·'눈 오는 날'을 직접 골랐을 때만 실내 장소로 한정한다."""
    return c.date_category=='날씨별' and c.date_subcategory in ('비 오는 날','눈 오는 날') and classification_strict(c)


CONCEPT_PROFILES = {
    '즐거운 데이트': {'search':'놀거리 체험', 'keywords':['방탈출','보드게임','오락실','게임','놀이','레저','액티비티']},
    '편안한 데이트': {'search':'산책 힐링', 'keywords':['정원','공원','숲','산책','휴식','힐링','한옥','북카페']},
    '지적인 데이트': {'search':'전시 박물관', 'keywords':['박물관','미술관','전시','서점','도서관','역사','문학','과학']},
    '동심 데이트': {'search':'장난감 오락실', 'keywords':['장난감','인형','오락실','놀이공원','테마파크','만화','애니메이션','레고','캐릭터']},
}


def concept_signals(place,c):
    profile=CONCEPT_PROFILES.get(c.date_subcategory,{})
    text=' '.join(str(value) for value in [place.get('name'),place.get('description'),*(place.get('tags') or []),*(place.get('search_aliases') or [])] if value)
    return [word for word in profile.get('keywords',[]) if word.casefold() in text.casefold()]


def concept_score(place,c):
    if c.date_subcategory not in CONCEPT_PROFILES:return 0
    # 구체적인 장소 단서를 큰 유형 분류보다 우선하되 적합성이 검증됐다고 주장하지 않는다.
    return min(3,len(concept_signals(place,c)))*2+(.25 if place.get('category') in classification_themes(c) else 0)
