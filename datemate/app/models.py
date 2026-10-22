from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator, field_validator
from .taxonomy import DATE_CATEGORIES

THEMES = ['레저·활동', '카페·미식', '휴식·힐링', '문화·예술', '체험·제작', '오락·놀이', '산책·풍경']

class Point(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

class Conditions(BaseModel):
    include_meal: bool = False
    neighborhood_radius_km: float = Field(default=2.5,ge=0.5,le=10)
    area_center: Point | None = None
    course_query: str = Field(default='', max_length=120)
    allow_price_estimates: bool = True
    allow_estimates: bool = False
    stay_minutes: int = Field(default=60, ge=15, le=240)
    mode: Literal['demo', 'real'] = 'demo'
    region: str = '서울'
    origin: Point = Point(name='데모 출발점', lat=37.575, lon=126.985)
    visit_date: date
    start: str = Field(default='11:00', pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    end: str = Field(default='19:00', pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    people: int = Field(default=2, ge=1, le=20)
    budget: int = Field(default=100000, ge=0, le=10000000)
    transport: Literal['walk', 'transit', 'car', 'bicycle'] = 'walk'
    count: int = Field(default=3, ge=2, le=5)
    themes: list[str] = Field(default_factory=list, max_length=7)
    date_category: Literal['', '계절별', '날씨별', '콘셉트별', '타입별'] = ''
    date_subcategory: str = Field(default='', max_length=30)
    theme_mode: Literal['mix', 'focus'] = 'mix'
    setting: Literal['any', 'indoor', 'outdoor'] = 'any'
    avoid: list[str] = Field(default_factory=list, max_length=30)
    reservation: bool = False
    max_leg: int = Field(default=30, ge=1, le=180)
    max_walk: int | None = Field(default=None, ge=0, le=600)
    return_home: bool = False
    home: Point | None = None
    mbti: str = Field(default='', pattern=r'^([IE][NS][FT][JP])?$')
    use_mbti: bool = False
    request: str = Field(default='', max_length=4000)
    locked: dict[int, str] = Field(default_factory=dict)

    @field_validator('region')
    @classmethod
    def seoul_only(cls, value):
        if value.strip() not in ('서울', '서울시', '서울특별시'):
            raise ValueError('데이트 코스는 서울특별시 내 장소만 추천합니다. 서비스 지역은 서울로 선택해 주세요.')
        return '서울'

    @model_validator(mode='after')
    def valid(self):
        if self.date_subcategory and self.date_subcategory not in DATE_CATEGORIES.get(self.date_category, []):
            raise ValueError('선택한 대분류에 맞는 데이트 소분류를 선택해 주세요.')
        if self.end <= self.start:
            raise ValueError('종료 시간은 같은 날 시작 시간 이후여야 합니다.')
        if self.return_home and self.home is None:
            raise ValueError('귀가 위치와 좌표가 필요합니다.')
        if any(x not in THEMES for x in self.themes):
            raise ValueError('지원하지 않는 테마입니다.')
        if any(i < 0 or i >= self.count for i in self.locked) or len(set(self.locked.values())) != len(self.locked):
            raise ValueError('고정 장소의 순서나 중복을 확인하세요.')
        return self

class ReviewInput(BaseModel):
    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=1, max_length=500000)
    nickname: str = Field(min_length=1, max_length=40)
    visited: date

    @model_validator(mode='after')
    def valid(self):
        if not self.body.strip() or not self.nickname.strip():
            raise ValueError('내용과 별명을 입력하세요.')
        if self.visited > date.today():
            raise ValueError('미래 방문 후기는 작성할 수 없습니다.')
        return self

class ChatInput(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    mode: Literal['demo', 'real'] = 'demo'
