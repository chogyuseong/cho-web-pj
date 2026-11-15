"""robots.txt and sitemap.xml for search engines.

- Absolute URLs come only from DATEMATE_PUBLIC_ORIGIN (the Worker always passes its
  PUBLIC_ORIGIN Secret), never from the request's Host header. Without it, robots.txt
  has no Sitemap line and /sitemap.xml answers 404.
- robots.txt blocks only /api/ (JSON, nothing to index). Pages that must stay out of
  search (/shared, /feedback/admin) are left crawlable on purpose and say noindex in
  their own response, because a crawler blocked by robots.txt never sees noindex and may
  still list the bare URL when someone links to it.
- The sitemap lists the home page only: the feedback form has no search value and the
  other pages are noindex. No lastmod, since the page has no reliable change date.
"""

from xml.sax.saxutils import escape

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response

from .config import public_origin

router = APIRouter()

DISALLOWED = ("/api/",)
SITEMAP_PATHS = ("/",)
# Small, rarely changing files; an hour keeps crawler refetches cheap.
CACHE = {"Cache-Control": "public, max-age=3600"}


@router.get("/robots.txt", include_in_schema=False)
def robots():
    lines = ["User-agent: *", *(f"Disallow: {path}" for path in DISALLOWED)]
    origin = public_origin()
    if origin:
        lines += ["", f"Sitemap: {origin}/sitemap.xml"]
    return PlainTextResponse("\n".join(lines) + "\n", headers=CACHE)


@router.get("/sitemap.xml", include_in_schema=False)
def sitemap():
    origin = public_origin()
    if not origin:
        raise HTTPException(404, "Not Found")
    urls = "".join(f"  <url><loc>{escape(origin + path)}</loc></url>\n" for path in SITEMAP_PATHS)
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}</urlset>\n"
    )
    return Response(body, media_type="application/xml", headers=CACHE)
