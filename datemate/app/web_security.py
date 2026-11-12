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
    r'^GET /api/explore$', r'^GET /api/festivals(?:/[^/]+/detail)?$',
    r'^GET /api/places/[^/]+/(?:media|blogs|menu)$',
    r'^POST /api/plans/[^/]+/(?:prices|leisure-options|alternatives)$',
    r'^GET /api/plans/[^/]+/(?:restaurants|restaurant-matches|meal-rescue)$',
    r'^POST /api/chat/[^/]+/[^/]+$',
)]


def expensive_budget(request, key):
    route = f'{request.method} {request.url.path}'
    if not any(pattern.match(route) for pattern in EXPENSIVE):
        return True
    # One explore screen asks for 24 card photos; a course result asks for up to
    # 15 place photos and 6 festival details. 120/min leaves room for both.
    return ip_allow('expensive', 'DATEMATE_IP_EXPENSIVE_REQUESTS_PER_MINUTE', 120, key=key)


def headers(response, request, request_id):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Request-ID'] = request_id
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), payment=()'
    # http 로컬 개발 주소에서는 네이버 지도 SDK가 인증·스타일 스크립트를 http로 요청한다.
    local_http = (' http://oapi.map.naver.com http://nrbe.map.naver.net http://*.pstatic.net'
                  if not production() and request.url.scheme == 'http' else '')
    response.headers['Content-Security-Policy'] = (
        f"script-src 'self' https://oapi.map.naver.com https://*.pstatic.net{local_http}; "
        "script-src-attr 'none'; object-src 'none'; base-uri 'self'; "
        "frame-ancestors 'none'; form-action 'self'"
    )
    if production() and request.url.scheme == 'https':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    if (request.url.path.startswith('/api/') or request.url.path in ('/', '/shared')
            or 'set-cookie' in response.headers or response.status_code >= 400):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
    elif request.url.path.startswith('/static/'):
        # Unversioned modules (including dynamically imported JS) must revalidate.
        response.headers['Cache-Control'] = 'public, max-age=0, must-revalidate'
    return response
