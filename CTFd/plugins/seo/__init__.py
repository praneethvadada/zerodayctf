"""ZeroDayCTF SEO helpers.

* /sitemap.xml          - public pages only
* /favicon.ico, /apple-touch-icon*.png - the logo icons browsers ask for by default
* zd_jsonld()           - schema.org structured data (Organization, WebSite, Event) for the home page
* X-Robots-Tag header   - keeps private/app pages (admin, API, login, challenges...) out of search results

The canonical host is always https://www.zerodayctf.com so a wrong Host header can never leak into
sitemaps, canonical links or structured data.
"""
import datetime
import json
import os

from flask import Response, send_file
from markupsafe import Markup

from CTFd.utils import get_config

SITE = "https://www.zerodayctf.com"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
BRAND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "themes",
    "core",
    "static",
    "img",
    "brand",
)

# Pages that should appear in search results
PUBLIC_PATHS = ["/", "/rules", "/register"]

# Everything under these prefixes is private application space: never index
NOINDEX_PREFIXES = (
    "/admin",
    "/api",
    "/login",
    "/logout",
    "/register/",
    "/reset_password",
    "/confirm",
    "/settings",
    "/notifications",
    "/writeups",
    "/challenges",
    "/scoreboard",
    "/users",
    "/user",
    "/team",
    "/teams",
    "/files",
    "/events",
    "/setup",
    "/server-time",
    "/healthcheck",
    "/profile",
    "/share",
    "/oauth",
    "/redirect",
)


def _ts(key):
    try:
        return int(get_config(key))
    except (TypeError, ValueError):
        return None


def _iso(ts):
    return datetime.datetime.fromtimestamp(ts, IST).isoformat()


def build_jsonld():
    name = "ZeroDayCTF"
    description = (
        "ZeroDayCTF is a capture-the-flag (CTF) cybersecurity competition. "
        "Hack real-world challenges, learn practical security skills and compete on a live scoreboard."
    )
    logo = SITE + "/themes/core/static/img/brand/icon-512.png"
    org = {
        "@type": "Organization",
        "@id": SITE + "/#organization",
        "name": name,
        "url": SITE + "/",
        "logo": logo,
        "description": description,
        "parentOrganization": {
            "@type": "Organization",
            "name": "Trivon Software Solutions Private Limited",
        },
    }
    site = {
        "@type": "WebSite",
        "@id": SITE + "/#website",
        "url": SITE + "/",
        "name": name,
        "description": description,
        "inLanguage": "en",
        "publisher": {"@id": SITE + "/#organization"},
    }
    graph = [org, site]
    start, end, writeup_end = _ts("start"), _ts("end"), _ts("writeup_end")
    if start:
        graph.append(
            {
                "@type": "Event",
                "name": name + " Capture The Flag",
                "description": description,
                "startDate": _iso(start),
                "endDate": _iso(writeup_end or end or start),
                "eventStatus": "https://schema.org/EventScheduled",
                "eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode",
                "location": {"@type": "VirtualLocation", "url": SITE + "/"},
                "image": SITE + "/themes/core/static/img/brand/og-image.png",
                "organizer": {"@id": SITE + "/#organization"},
                "url": SITE + "/",
            }
        )
    data = {"@context": "https://schema.org", "@graph": graph}
    # "</" must never appear inside a <script> block
    body = json.dumps(data, ensure_ascii=False, indent=2).replace("</", "<\\/")
    return Markup('<script type="application/ld+json">\n%s\n</script>' % body)


def _icon(filename):
    path = os.path.join(BRAND_DIR, filename)

    def view():
        resp = send_file(path, max_age=86400)
        resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp

    return view


def sitemap():
    urls = "".join(
        "  <url><loc>%s%s</loc></url>\n" % (SITE, p if p != "/" else "/")
        for p in PUBLIC_PATHS
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s</urlset>\n'
        % urls
    )
    return Response(xml, mimetype="application/xml")


def load(app):
    app.add_url_rule("/sitemap.xml", "seo_sitemap", sitemap)
    app.add_url_rule("/favicon.ico", "seo_favicon", _icon("favicon.ico"))
    app.add_url_rule(
        "/apple-touch-icon.png", "seo_apple_icon", _icon("apple-touch-icon.png")
    )
    app.add_url_rule(
        "/apple-touch-icon-precomposed.png",
        "seo_apple_icon_pre",
        _icon("apple-touch-icon.png"),
    )
    app.jinja_env.globals.update(zd_jsonld=build_jsonld)

    @app.after_request
    def seo_robots_header(response):
        from flask import request

        path = request.path
        if path.startswith(NOINDEX_PREFIXES) and path != "/register":
            response.headers.setdefault("X-Robots-Tag", "noindex, nofollow")
        return response
