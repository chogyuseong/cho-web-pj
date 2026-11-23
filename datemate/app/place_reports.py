"""장소 제보 중 지금 추천·표시에 반영할 것 (docs/reviews/2026-11-24-full-review.md S1).

제보는 익명 브라우저 하나가 보낼 수 있으므로 1건으로 모든 사용자의 추천을 바꾸지 않는다.
- 서로 다른 브라우저(소유자) GLOBAL_REPORTERS 곳 이상이 제보한 장소만 모든 사용자에게 '제보 확인 필요'로 보이고 감점된다.
  한 브라우저가 사유를 바꿔 여러 번 제보해도 1곳으로 센다.
- 제보한 본인(viewer)에게는 자기 제보 1건으로도 바로 반영한다.
- 제보는 TTL_DAYS 일이 지나면 세지 않는다(행은 남겨 운영자 검토 scripts/review_place_reports.py 가 그대로 본다).
- 운영자가 처리한(resolved=1) 제보는 세지 않는다(예전과 같음).
표를 바꾸지 않으므로 마이그레이션은 없다. created 는 예전부터 저장하던 유닉스 초다.
"""
import time

from . import store

GLOBAL_REPORTERS = 3
TTL_DAYS = 30


def pending_place_ids(viewer=None):
    """viewer(소유자 해시)가 보는 추천·코스에서 '제보 확인 필요'로 다룰 장소 id 집합.

    viewer 를 주지 않으면 지금 요청의 소유자(app/naver_cache.current_owner — 미들웨어와 추천 작업이 건다)를 쓴다.
    """
    if viewer is None:
        from .naver_cache import current_owner

        viewer = current_owner()
    since = time.time() - TTL_DAYS * 86400
    with store.connect() as db:
        rows = db.execute(
            "SELECT place_id,COUNT(DISTINCT owner) AS reporters,"
            " SUM(CASE WHEN owner=? THEN 1 ELSE 0 END) AS mine"
            " FROM place_reports WHERE resolved=0 AND created>=? GROUP BY place_id",
            (viewer or "", since),
        ).fetchall()
    return {r[0] for r in rows if r[1] >= GLOBAL_REPORTERS or (viewer and r[2])}
