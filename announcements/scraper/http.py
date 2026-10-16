"""Polite HTTP client: robots.txt, per-host rate limit, timeouts, retries, raw cache."""
import hashlib
import json
import logging
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

import requests
import truststore

# Use the OS certificate store: kenyanews.go.ke's chain does not validate against certifi's bundle
truststore.inject_into_ssl()

log = logging.getLogger(__name__)


class RobotsDisallowed(Exception):
    pass


class PoliteSession:
    def __init__(self, defaults: dict, cache_dir: Path, refresh: bool = False):
        self.ua = defaults.get("user_agent", "research-bot/0.1")
        self.delay = float(defaults.get("min_delay_seconds", 2.0))
        self.timeout = (defaults.get("connect_timeout", 15), defaults.get("read_timeout", 60))
        self.retries = int(defaults.get("max_retries", 2))
        self.cache_dir = cache_dir
        self.refresh = refresh
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": self.ua, "Accept-Language": "en"})
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last: dict[str, float] = {}
        self.stats = {"requests": 0, "cache_hits": 0, "errors": 0, "robots_blocked": 0}

    # robots ---------------------------------------------------------------
    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        host = f"{p.scheme}://{p.netloc}"
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                self._wait(p.netloc)
                r = self.s.get(host + "/robots.txt", timeout=self.timeout)
                self.stats["requests"] += 1
                if r.status_code == 200 and "html" not in r.headers.get("content-type", ""):
                    rp.parse(r.text.splitlines())
                else:  # 404 / HTML error page => no rules declared
                    rp.parse([])
            except requests.RequestException as e:
                # unreachable robots.txt => be conservative and treat the host as disallowed
                log.warning("robots.txt fetch failed for %s: %s (treating host as disallowed)", host, e)
                rp.parse(["User-agent: *", "Disallow: /"])
            self._robots[host] = rp
        return self._robots[host].can_fetch(self.ua, url)

    def _wait(self, netloc: str):
        last = self._last.get(netloc)
        if last is not None:
            gap = time.monotonic() - last
            if gap < self.delay:
                time.sleep(self.delay - gap)
        self._last[netloc] = time.monotonic()

    # fetch ----------------------------------------------------------------
    def _cache_path(self, url: str, sub: str) -> Path:
        h = hashlib.sha1(url.encode()).hexdigest()[:16]
        d = self.cache_dir / sub
        d.mkdir(parents=True, exist_ok=True)
        return d / h

    def get(self, url: str, sub: str = "misc", params: dict | None = None) -> tuple[bytes, dict]:
        """Return (body, meta). meta = {url, status, content_type, fetched_at, raw_path}."""
        full = requests.Request("GET", url, params=params).prepare().url
        if not self.allowed(full):
            self.stats["robots_blocked"] += 1
            raise RobotsDisallowed(full)
        base = self._cache_path(full, sub)
        meta_p, body_p = base.with_suffix(".meta.json"), base.with_suffix(".body")
        if not self.refresh and meta_p.exists() and body_p.exists():
            self.stats["cache_hits"] += 1
            return body_p.read_bytes(), json.loads(meta_p.read_text(encoding="utf-8"))

        err = None
        for attempt in range(self.retries + 1):
            try:
                self._wait(urlparse(full).netloc)
                self.stats["requests"] += 1
                r = self.s.get(full, timeout=self.timeout)
                if r.status_code >= 500 or r.status_code == 429:
                    raise requests.HTTPError(f"HTTP {r.status_code}")
                r.raise_for_status()
                meta = {
                    "url": full,
                    "final_url": r.url,
                    "status": r.status_code,
                    "content_type": r.headers.get("content-type", ""),
                    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "raw_path": str(body_p),
                    # WordPress REST pagination
                    "wp_total": r.headers.get("X-WP-Total"),
                    "wp_total_pages": r.headers.get("X-WP-TotalPages"),
                }
                body_p.write_bytes(r.content)
                meta_p.write_text(json.dumps(meta), encoding="utf-8")
                return r.content, meta
            except requests.RequestException as e:
                err = e
                if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code < 500:
                    break  # 4xx: do not retry
                time.sleep(2 * (attempt + 1))
        self.stats["errors"] += 1
        raise err

    def get_json(self, url: str, sub: str, params: dict | None = None):
        body, meta = self.get(url, sub, params)
        return json.loads(body.decode("utf-8-sig")), meta
