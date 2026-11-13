from datetime import date
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator, field_validator
from .taxonomy import DATE_CATEGORIES
from .service_time import today
from .regions import normalize_region, region_from_address

THEMES = ['레저·활동', '카페·미식', '휴식·힐링', '문화·예술', '체험·제작', '오락·놀이', '산책·풍경']

# Every stored string has a bound: plans keep their conditions and never expire.
PlaceId = Annotated[str, StringConstraints(max_length=150)]
AvoidWord = Annotated[str, StringConstraints(max_length=30)]
ThemeName = Annotated[str, StringConstraints(max_length=20)]

class Point(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

class FestivalAnchor(BaseModel):
    """결과 화면에서 고른 축제. 코스는 이 축제 위치에서 출발한다."""
    # 관광공사 contentid(숫자) 또는 목록이 만든 '제목:시작일' 형태의 ID.
    id: str = Field(min_length=1, max_length=240)
    title: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

TransportMode = Literal['walk', 'transit', 'car', 'bicycle']


class LegMode(BaseModel):
    """한 구간의 이동 수단 예외. 출발('origin' 또는 장소 id)과 도착(장소 id 또는 'home')으로 구간을 찾는다."""
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True, extra='forbid')
    from_: PlaceId = Field(alias='from', min_length=1)
    to: PlaceId = Field(min_length=1)
    mode: TransportMode


class Conditions(BaseModel):
    planning_session_id: str = Field(default='',pattern=r'^(?:[a-f0-9]{32})?$')
    explicit_fields: list[Literal['people','budget','count','transport','setting','reservation','priority','max_walk','include_meal','themes','theme_mode','date_category','date_subcategory','meeting_type']] = Field(default_factory=list,max_length=15)
    meeting_type: Literal['regular','first','anniversary'] = 'regular'
    priority: Literal['balanced','talk','food','photo','activity'] = 'balanced'
    trust_mode: Literal['balanced','operating_sources','discovery'] = 'balanced'
    hard_constraints: list[Literal['budget','end','max_leg','max_walk','setting','reservation','themes','meal','neighborhood','avoid']] = Field(default_factory=list,max_length=10)
    use_feedback: bool = False
    excluded_place_ids: list[PlaceId] = Field(default_factory=list,max_length=100)
    include_meal: bool = False
    neighborhood_radius_km: float = Field(default=2.5,ge=0.5,le=10)
    area_center: Point | None = None
    festival: FestivalAnchor | None = None
    course_query: str = Field(default='', max_length=120)
    allow_price_estimates: bool = True
    allow_estimates: bool = False
    stay_minutes: int = Field(default=60, ge=15, le=240)
    transition_buffer_minutes: int = Field(default=0,ge=0,le=30)
    mode: Literal['demo', 'real'] = 'demo'
    region: str = Field(default='서울', max_length=20)
    origin: Point = Point(name='데모 출발점', lat=37.575, lon=126.985)
    visit_date: date
    start: str = Field(default='11:00', pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    end: str = Field(default='19:00', pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    people: int = Field(default=2, ge=1, le=20)
    budget: int = Field(default=100000, ge=0, le=10000000)
    transport: TransportMode = 'walk'
    # 코스를 만든 뒤 구간마다 바꾼 수단. 새 추천에서는 항상 비운다(recommendation_service.generate).
    leg_modes: list[LegMode] = Field(default_factory=list, max_length=6)
    count: int = Field(default=3, ge=2, le=5)
    themes: list[ThemeName] = Field(default_factory=list, max_length=7)
    date_category: Literal['', '계절별', '날씨별', '콘셉트별', '타입별'] = ''
    date_subcategory: str = Field(default='', max_length=30)
    theme_mode: Literal['mix', 'focus'] = 'mix'
    setting: Literal['any', 'indoor', 'outdoor'] = 'any'
    avoid: list[AvoidWord] = Field(default_factory=list, max_length=30)
    reservation: bool = False
    max_leg: int = Field(default=30, ge=1, le=180)
    max_walk: int | None = Field(default=None, ge=0, le=600)
    return_home: bool = False
    home: Point | None = None
    mbti: str = Field(default='', pattern=r'^([IE][NS][FT][JP])?$')
    use_mbti: bool = False
    request: str = Field(default='', max_length=4000)
    locked: dict[int, PlaceId] = Field(default_factory=dict, max_length=5)

    @field_validator('region')
    @classmethod
    def supported_region(cls, value):
        region = normalize_region(value)
        if not region:
            raise ValueError('추천 지역은 대한민국의 시·도 중에서 선택해 주세요.')
        return region

    @model_validator(mode='after')
    def valid(self):
        if self.mode == 'demo' and self.region != '서울':
            raise ValueError('가상 장소 데모는 서울 자료만 제공합니다. 전국 추천은 실제 장소 모드를 선택해 주세요.')
        origin_region = region_from_address(self.origin.name)
        if origin_region and origin_region != self.region:
            raise ValueError('선택한 시·도와 출발지 주소가 다릅니다.')
        if self.date_subcategory and self.date_subcategory not in DATE_CATEGORIES.get(self.date_category, []):
            raise ValueError('선택한 대분류에 맞는 데이트 소분류를 선택해 주세요.')
        if self.end <= self.start:
            raise ValueError('종료 시간은 같은 날 시작 시간 이후여야 합니다.')
        if self.festival and (self.mode != 'real' or abs(self.origin.lat - self.festival.lat) > 1e-6 or abs(self.origin.lon - self.festival.lon) > 1e-6):
            raise ValueError('축제 기준 코스는 실제 장소 모드에서 축제 위치를 출발지로 사용해야 합니다.')
        if self.return_home and self.home is None:
            raise ValueError('귀가 위치와 좌표가 필요합니다.')
        if any(x not in THEMES for x in self.themes):
            raise ValueError('지원하지 않는 테마입니다.')
        if any(i < 0 or i >= self.count for i in self.locked) or len(set(self.locked.values())) != len(self.locked):
            raise ValueError('고정 장소의 순서나 중복을 확인하세요.')
        if len({(m.from_, m.to) for m in self.leg_modes}) != len(self.leg_modes):
            raise ValueError('같은 구간의 이동 수단이 두 번 들어 있어요.')
        return self

class ReviewInput(BaseModel):
    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=1, max_length=2000)
    nickname: str = Field(min_length=1, max_length=40)
    visited: date

    @model_validator(mode='after')
    def valid(self):
        if not self.body.strip() or not self.nickname.strip():
            raise ValueError('내용과 별명을 입력하세요.')
        if self.visited > today():
            raise ValueError('미래 방문 후기는 작성할 수 없습니다.')
        return self

class ChatInput(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    mode: Literal['demo', 'real'] = 'demo'
