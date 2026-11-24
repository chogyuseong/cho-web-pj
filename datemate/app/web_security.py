"""HTTP protections shared by local development and HTTPS deployment."""
import hashlib
import ipaddress
import os
import re
import time
from urllib.parse import urlsplit
from fastapi import HTTPException
from . import store
from .config import production, public_origin
from .request_usage import client_range


def allowed_host(request):
    origin = public_origin()
    configured = os.getenv('DATEMATE_ALLOWED_HOSTS', '')
    hosts = [host.strip().lower() for host in configured.split(',') if host.strip()]
    if origin:
        hosts.append(urlsplit(origin).hostname)
    if not hosts:
        hosts = ['*'] if not production() else []
    # Health probes go directly to the container using its internal address.
    if request.url.path in ('/healthz', '/readyz'):
        return True
    hostname = (request.url.hostname or '').lower()
    return any(host == '*' or hostname == host or
               (host.startswith('*.') and hostname.endswith(host[1:])) for host in hosts)


def range_of(address):
    """IPv4 stays per address; IPv6 is grouped by its /64 (one subscriber's prefix)."""
    try:
        ip = ipaddress.ip_address(str(address).split('%', 1)[0])
    except ValueError:
        return str(address or 'unknown')[:64]
    if ip.version == 6:
        if ip.ipv4_mapped:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f'{ip}/64', strict=False))
    return str(ip)


def client_key(request):
    # Use the client address resolved by trusted proxy middleware, never a raw
    # X-Forwarded-For value supplied by the browser. No raw IP is stored.
    client = request.client.host if request.client else 'unknown'
    return hashlib.sha256(range_of(client).encode()).hexdigest()


def limit(name, default):
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def ip_allow(name, env, default, key=None, seconds=60):
    """Per-IP-range budget shared by every session from that range.

    Without a request context (scripts, unit calls) there is no client to limit.
    """
    key = key or client_range()
    if not key:
        return True
    return store.reserve_budget([(f'ip:{name}:{key}', limit(env, default))], int(time.time() // seconds))


def require_ip(name, env, default, message):
    if not ip_allow(name, env, default):
        raise HTTPException(429, message, headers={'Retry-After': '60'})


def api_budget(request, key=None):
    key = key or client_key(request)
    return store.reserve_budget([('http:' + key, limit('DATEMATE_IP_REQUESTS_PER_MINUTE', 240))],
                                int(time.time() // 60))


# Paths that reach paid or quota-limited providers (search, maps, tourism, LLM).
EXPENSIVE = [re.compile(pattern) for pattern in (
    r'^POST /api/plans$', r'^POST /api/plan-jobs$',
    r'^POST /api/locations/(?:search|region)$',
    r'^GET /api/explore(?:/naver)?$', r'^GET /api/festivals(?:/[^/]+/detail)?$', r'^GET /api/popups$',
    r'^GET /api/places/[^/]+/(?:media|blogs|menu|review-facts|identity)$',
    r'^POST /api/plans/[^/]+/(?:leisure-options|alternatives|replace|transport|reorder)$',
    # 코스를 다시 계산하는 미리보기·적용(길찾기를 다시 부를 수 있음, 2026-11-24 검토 S3).
    r'^POST /api/plans/[^/]+/(?:agreement-preview|meal-preview|festival-preview|delay-recovery|leisure-select|draft-apply)$',
    r'^GET /api/plans/[^/]+/(?:restaurants|restaurant-matches|meal-rescue|parking)$',
    r'^POST /api/chat/[^/]+/[^/]+$',
)]


# 추천(planner.recommend)을 통째로 다시 돌리는 경로. 새 추천과 같은 분당 추천 한도(app/execution.reserve_recommendation)를 쓴다.
# 소유자를 알아야 하므로 미들웨어가 코스 주인을 확인한 뒤 센다(app/main.py).
RECOMMENDING = [re.compile(r'^POST /api/plans/[^/]+/agreement-preview$')]


def recommending(request):
    route = f'{request.method} {request.url.path}'
    return any(pattern.match(route) for pattern in RECOMMENDING)


def expensive_budget(request, key):
    route = f'{request.method} {request.url.path}'
    if not any(pattern.match(route) for pattern in EXPENSIVE):
        return True
    # One explore screen asks for 24 card photos; a course result asks for up to
    # 15 place photos and 6 festival details. 120/min leaves room for both.
    return ip_allow('expensive', 'DATEMATE_IP_EXPENSIVE_REQUESTS_PER_MINUTE', 120, key=key)


SESSION_COOKIE = 'dm_session'
# Over HTTPS the __Host- prefix makes browsers refuse the cookie unless it is Secure,
# host-only (no Domain) and Path=/, so a sibling subdomain cannot plant or shadow it.
SECURE_SESSION_COOKIE = '__Host-dm_session'
SESSION_MAX_AGE = 30 * 86400


def secure_cookies(request):
    return production() or request.url.scheme == 'https'


def session_cookie(request):
    return SECURE_SESSION_COOKIE if secure_cookies(request) else SESSION_COOKIE


def local_http(request):
    return not production() and request.url.scheme == 'http'


# 네이버 지도 SDK는 인증·로그·타일·스타일을 여러 네이버 호스트에서 받는다. 지도가 깨지는
# 것보다 조금 넓은 정책이 낫기 때문에 네이버 계열 https 호스트는 묶어서 허용한다.
NAVER_HTTPS = 'https://*.naver.com https://*.naver.net https://*.navercorp.com https://*.pstatic.net'
# http 로컬 개발 주소에서는 SDK가 인증·스타일 스크립트와 타일을 http로 요청한다
# (oapi.map.naver.com, nrbe.map.naver.net, static.naver.net). 운영(https)에는 넣지 않는다.
NAVER_LOCAL_HTTP = 'http://*.naver.com http://*.naver.net http://*.pstatic.net'


def content_security_policy(local=False):
    """The page policy. The deployed https variant and the http-local variant differ
    only in http sources (Naver map scripts; images, which the page also accepts over
    http when it is itself served over http) and upgrade-insecure-requests."""
    directives = [
        "default-src 'self'",
        f"script-src 'self' https://oapi.map.naver.com {NAVER_HTTPS}"
        + (' ' + NAVER_LOCAL_HTTP if local else ''),
        "script-src-attr 'none'",
        # The map SDKs and Leaflet position tiles and markers with inline styles.
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' data: https://fonts.gstatic.com",
        # Place photos come from arbitrary https hosts (blogs, Naver, Wikimedia, tourism);
        # the course card is drawn to a canvas and saved through a blob: URL.
        "img-src 'self' data: blob: https:" + (' http:' if local else ''),
        # Wikimedia photo lookups run in the browser; the map SDK posts usage logs.
        f"connect-src 'self' https://www.wikidata.org https://commons.wikimedia.org {NAVER_HTTPS}",
        "media-src 'self'",
        "worker-src 'self' blob:",
        "child-src 'self' blob:",
        "frame-src 'none'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    ]
    if not local:
        directives.append('upgrade-insecure-requests')
    return '; '.join(directives)


STATIC_CACHE_CONTROL = 'public, max-age=0, must-revalidate'
STATIC_IMMUTABLE_CACHE_CONTROL = 'public, max-age=31536000, immutable'


def headers(response, request, request_id):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Request-ID'] = request_id
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), payment=()'
    response.headers['Content-Security-Policy'] = content_security_policy(local_http(request))
    if production() and request.url.scheme == 'https':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    if (request.url.path.startswith('/api/') or request.url.path in ('/', '/shared', '/feedback', '/feedback/admin')
            or 'set-cookie' in response.headers or response.status_code >= 400):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
    elif request.url.path.startswith('/static/'):
        # 주소의 ?v= 가 지금 보내는 파일의 내용 해시와 같을 때만 1년 동안 다시 묻지 않게 한다(파일이 바뀌면 페이지의 주소가 바뀜).
        # 해시를 확인하는 까닭: 배포 직후 새 페이지(엣지)가 예전 컨테이너에 새 주소를 물으면 예전 파일이 새 주소로 나가는데,
        # 그것을 immutable 로 두면 브라우저가 1년 동안 예전 파일을 쓴다. 해시가 없거나 다르면 전처럼 매번 확인한다.
        from .static_pages import file_version
        version = request.query_params.get('v')
        immutable = bool(version) and response.status_code in (200, 304) and version == file_version(request.url.path)
        response.headers['Cache-Control'] = STATIC_IMMUTABLE_CACHE_CONTROL if immutable else STATIC_CACHE_CONTROL
    return response
