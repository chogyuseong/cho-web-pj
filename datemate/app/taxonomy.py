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
