"""네이버 검색 API 특약 개정(2026-09) 1단계: 공용 캐시 정리와 저장 코스의 이력 보관 기한 표시.

- 사용자 공용 cache 에 남은 네이버 검색 결과·파생물 행을 지운다(블로그·지역·이미지 검색 결과, 발견 장소,
  둘러보기 장소, 가격 근거, 팝업 원문·거점 좌표·사진, 장소 확인 결과, 예전 LLM 답변 answer:* 등. 목록은
  app/naver_cache.SHARED_PREFIXES). 이제 네이버 데이터는 사용자별 'nv:' 키에 최대 24시간만 둔다.
- plans.naver_cleared: 만든 지 21일이 지나 네이버 유래 필드를 지운 시각(app/naver_terms.cleanup_expired_plans).
"""

VERSION = "0005-naver-terms-2026-09"

# 마이그레이션은 바뀌면 안 되므로 지울 키 앞부분을 여기에 고정한다(app/naver_cache.SHARED_PREFIXES 와 같게 시작).
SHARED_PREFIXES = (
    "place-blogs-",
    "course-blog-five-",
    "discovered-place:",
    "explore-query-",
    "explore-result-",
    "explore-place:",
    "image-strict-",
    "image-search-",
    "intent-local-",
    "leisure-local-",
    "restaurant-menu-",
    "parking-local-",
    "place-identity-",
    "popups-raw:",
    "popup-hub-point:",
    "popup-photo:",
    "price-search-",
    "restaurant:",
    "local-restaurants-",
    "meal-rescue-",
    "review-facts-",
    "caption-blog-photos-",
    "public-place-photos-",
    "photo-subject-",
    "answer:",
)


def _columns(db, backend, table):
    if backend == "postgres":
        rows = db.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema=current_schema() AND table_name=?",
            (table,),
        ).fetchall()
        return {row[0] for row in rows}
    return {row[1] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}


def upgrade(db, backend):
    if "naver_cleared" not in _columns(db, backend, "plans"):
        kind = "DOUBLE PRECISION" if backend == "postgres" else "REAL"
        db.execute(f"ALTER TABLE plans ADD COLUMN naver_cleared {kind}")
    db.execute("CREATE INDEX IF NOT EXISTS plans_naver_cleanup ON plans(naver_cleared, created)")
    for prefix in SHARED_PREFIXES:
        db.execute("DELETE FROM cache WHERE key LIKE ?", (prefix + "%",))
