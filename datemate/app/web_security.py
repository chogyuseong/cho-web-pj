"""HTTP protections shared by local development and HTTPS deployment."""
import hashlib
import os
import time
from urllib.parse import urlsplit
from . import store
from .config import production, public_origin


def allowed_host(request):
    origin = public_origin()
    configured = os.getenv('DATEMATE_ALLOWED_HOSTS', '')
    hosts = [host.strip().lower() for host in configured.split(',') if host.strip()]
    if origin:
        hosts.append(urlsplit(origin).hostname)
    if not hosts:
        hosts = ['*.run.app'] if os.getenv('K_SERVICE') else ['*']
    # Health probes go directly to the container using its internal address.
    if request.url.path in ('/healthz', '/readyz'):
        return True
    hostname = (request.url.hostname or '').lower()
    return any(host == '*' or hostname == host or
               (host.startswith('*.') and hostname.endswith(host[1:])) for host in hosts)


def api_budget(request):
    # Use the client address resolved by trusted proxy middleware, never a raw
    # X-Forwarded-For value supplied by the browser. No raw IP is stored.
    client = request.client.host if request.client else 'unknown'
    scope = 'http:' + hashlib.sha256(client.encode()).hexdigest()
    return store.reserve_budget([(scope, int(os.getenv('DATEMATE_IP_REQUESTS_PER_MINUTE', '240')))],
                                int(time.time() // 60))


def headers(response, request, request_id):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-Request-ID'] = request_id
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), payment=()'
    response.headers['Content-Security-Policy'] = "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    if production() and request.url.scheme == 'https':
        response.headers['Strict-Transport-Security'] = 'max-age=31536000'
    if request.url.path.startswith('/api/') or request.url.path == '/shared' or response.status_code >= 400:
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
    elif request.url.path.startswith('/static/'):
        # Unversioned modules (including dynamically imported JS) must revalidate.
        response.headers['Cache-Control'] = 'public, max-age=0, must-revalidate'
    return response
