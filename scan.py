#!/usr/bin/env python3
"""Daily job / internship scanner.

Searches several job sites for fresh postings that match config.toml and prints
them as Markdown (default) or JSON. Uses only the Python standard library.

    python3 scan.py                 # Markdown report of new matches
    python3 scan.py --json          # machine-readable output
    python3 scan.py --hours 168     # look back a week instead of a day
    python3 scan.py --state data/seen.json   # skip postings already reported
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
NOW = datetime.now(timezone.utc)

INTERN_RE = re.compile(
    r"\b(intern|interns|internship|internships|ojt|on[- ]the[- ]job|practicum|trainee|traineeship|"
    r"apprentice|apprenticeship|co-?op|student|immersion)\b",
    re.I,
)
ENTRY_RE = re.compile(
    r"\b(junior|jr\.?|entry[- ]level|entry|graduate|fresh[- ]?grads?|new grad|associate|trainee|"
    r"level 1)\b",
    re.I,
)
REMOTE_OK_RE = re.compile(
    r"\b(worldwide|anywhere|global|asia|apac|southeast asia|sea|philippines|ph)\b", re.I
)


@dataclass
class Job:
    title: str
    company: str
    location: str
    url: str
    source: str
    posted: str = ""  # ISO date/time if known
    remote: bool = False
    snippet: str = ""
    tags: list[str] = field(default_factory=list)
    undated: bool = False  # the site gave no posting date, so it may be old

    @property
    def key(self) -> str:
        norm = lambda s: re.sub(r"\b(inc|corp|corporation|co|ltd|llc|opc|incorporated)\b", "",
                                re.sub(r"[^a-z0-9]+", " ", s.lower())).split()
        norm = (lambda f: lambda s: " ".join(f(s)))(norm)
        return f"{norm(self.title)}|{norm(self.company)}"


# ---------------------------------------------------------------- helpers


def fetch(url: str, *, as_json: bool = False, data: bytes | None = None, retries: int = 2):
    headers = {"User-Agent": UA, "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read().decode("utf-8", "replace")
            return json.loads(body) if as_json else body
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError:
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise


def strip_tags(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def any_word(text: str, words: list[str]) -> bool:
    for w in words:
        if re.search(r"(?<![a-z0-9])" + re.escape(w.lower()) + r"(?![a-z0-9])", text.lower()):
            return True
    return False


# ---------------------------------------------------------------- sources


def src_linkedin(cfg, hours):
    """LinkedIn public (logged-out) job search."""
    jobs = []
    secs = int(hours * 3600)
    queries = [(t, "Cebu, Central Visayas, Philippines", None) for t in cfg["search_terms"]]
    if cfg.get("include_remote"):
        queries += [(t, "Philippines", "2") for t in cfg["search_terms"][:3]]  # f_WT=2 remote
    for term, loc, wt in queries:
        params = {"keywords": term, "location": loc, "f_TPR": f"r{secs}", "start": "0"}
        if wt:
            params["f_WT"] = wt
        url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?" + urllib.parse.urlencode(params)
        page = fetch(url)
        for card in page.split('<div class="base-card')[1:]:
            g = lambda pat: (m.group(1) if (m := re.search(pat, card, re.S)) else "")
            title = strip_tags(g(r'base-search-card__title">(.*?)</h3>'))
            company = strip_tags(g(r'base-search-card__subtitle">(.*?)</h4>'))
            location = strip_tags(g(r'job-search-card__location">(.*?)</span>'))
            link = html.unescape(g(r'base-card__full-link[^>]*href="([^"]+)"')).split("?")[0]
            posted = g(r'datetime="([^"]+)"')
            # LinkedIn's remote filter also returns onsite roles, so only trust it when the
            # location is the whole country (how remote roles are listed) or says "remote".
            remote = bool(wt) and (location.strip().lower() == "philippines"
                                   or "remote" in f"{title} {location}".lower())
            if title and link:
                jobs.append(Job(title, company, location, link, "LinkedIn", posted, remote=remote))
        time.sleep(1.0)
    return jobs


def src_jobstreet(cfg, hours):
    """JobStreet Philippines search API."""
    jobs = []
    days = max(1, math.ceil(hours / 24))
    for term in cfg["search_terms"]:
        params = {"siteKey": "PH-Main", "where": "Cebu", "keywords": term, "page": "1",
                  "pageSize": "100", "daterange": str(days)}
        url = "https://ph.jobstreet.com/api/jobsearch/v5/search?" + urllib.parse.urlencode(params)
        for d in fetch(url, as_json=True).get("data", []):
            locs = ", ".join(l.get("label", "") for l in d.get("locations", []))
            arr = " ".join(a["label"]["text"] for a in (d.get("workArrangements") or {}).get("data", []))
            jobs.append(Job(
                d.get("title", ""), d.get("companyName") or (d.get("advertiser") or {}).get("description", ""),
                locs, f"https://ph.jobstreet.com/job/{d['id']}", "JobStreet", d.get("listingDate", ""),
                remote="remote" in arr.lower(), snippet=d.get("teaser", ""),
                tags=list(d.get("workTypes") or []) + ([arr] if arr else []),
            ))
        time.sleep(0.5)
    return jobs


def src_kalibrr(cfg, hours):
    """Kalibrr job board (filters to Cebu or work-from-home client-side)."""
    jobs = []
    for term in cfg["search_terms"]:
        url = "https://www.kalibrr.com/kjs/job_board/search?" + urllib.parse.urlencode(
            {"limit": "100", "offset": "0", "text": term})
        for d in fetch(url, as_json=True).get("jobs", []):
            addr = (d.get("google_location") or {}).get("address_components") or {}
            loc = ", ".join(x for x in (addr.get("city"), addr.get("region"), addr.get("country")) if x)
            code = (d.get("company") or {}).get("code", "")
            jobs.append(Job(
                d.get("name", ""), d.get("company_name", ""), loc,
                f"https://www.kalibrr.com/c/{code}/jobs/{d['id']}/{d.get('slug', '')}", "Kalibrr",
                d.get("activation_date") or d.get("created_at", ""), remote=bool(d.get("is_work_from_home")),
                snippet=strip_tags(d.get("description", ""))[:240], tags=[d.get("tenure") or ""],
            ))
        time.sleep(0.5)
    return jobs


def src_remotive(cfg, hours):
    """Remotive remote jobs (only ones open to Asia / worldwide)."""
    if not cfg.get("include_remote"):
        return []
    jobs = []
    for term in ("intern", "internship", "junior") if "entry" in cfg["job_types"] else ("intern", "internship"):
        data = fetch("https://remotive.com/api/remote-jobs?" + urllib.parse.urlencode({"search": term}), as_json=True)
        for d in data.get("jobs", []):
            loc = d.get("candidate_required_location", "")
            if not REMOTE_OK_RE.search(loc or "worldwide"):
                continue
            jobs.append(Job(d["title"], d.get("company_name", ""), f"Remote ({loc})", d["url"], "Remotive",
                            d.get("publication_date", ""), remote=True, snippet=strip_tags(d.get("description", ""))[:240]))
    return jobs


def src_lever(cfg, hours):
    jobs = []
    for co in cfg.get("lever_companies", []):
        for d in fetch(f"https://api.lever.co/v0/postings/{co}?mode=json", as_json=True):
            cat = d.get("categories") or {}
            created = datetime.fromtimestamp(d.get("createdAt", 0) / 1000, timezone.utc).isoformat()
            jobs.append(Job(d.get("text", ""), co, cat.get("location", ""), d.get("hostedUrl", ""), "Lever",
                            created, remote="remote" in (d.get("workplaceType") or "").lower()))
    return jobs


def src_ashby(cfg, hours):
    jobs = []
    for co in cfg.get("ashby_companies", []):
        data = fetch(f"https://api.ashbyhq.com/posting-api/job-board/{co}", as_json=True)
        for d in data.get("jobs", []):
            jobs.append(Job(d.get("title", ""), co, d.get("location", ""), d.get("jobUrl", ""), "Ashby",
                            d.get("publishedAt", ""), remote=bool(d.get("isRemote"))))
    return jobs


def src_greenhouse(cfg, hours):
    jobs = []
    for co in cfg.get("greenhouse_companies", []):
        data = fetch(f"https://boards-api.greenhouse.io/v1/boards/{co}/jobs", as_json=True)
        for d in data.get("jobs", []):
            loc = (d.get("location") or {}).get("name", "")
            jobs.append(Job(d.get("title", ""), co, loc, d.get("absolute_url", ""), "Greenhouse",
                            d.get("first_published") or d.get("updated_at", ""), remote="remote" in loc.lower()))
    return jobs


def _ago_to_iso(text: str) -> str:
    """Turn Google's '3 days ago' / '5 hours ago' into an ISO timestamp."""
    m = re.search(r"(\d+)\+?\s*(minute|hour|day|week|month)", text or "", re.I)
    if not m:
        return ""
    n, unit = int(m.group(1)), m.group(2).lower()
    delta = {"minute": timedelta(minutes=n), "hour": timedelta(hours=n), "day": timedelta(days=n),
             "week": timedelta(weeks=n), "month": timedelta(days=30 * n)}[unit]
    return (NOW - delta).isoformat()


def src_google_jobs(cfg, hours):
    """Google Jobs, through SearchApi.io (Google has no public jobs API).

    Needs a SearchApi key. In the Claude cloud environment the network proxy adds it
    to requests for www.searchapi.io; elsewhere set SEARCHAPI_KEY. Each query uses one
    of the account's searches, so keep google_jobs_queries short.
    """
    queries = cfg.get("google_jobs_queries") or []
    if not queries:
        return []
    key = os.environ.get("SEARCHAPI_KEY", "injected-by-proxy")
    jobs = []
    for q in queries:
        url = "https://www.searchapi.io/api/v1/search?" + urllib.parse.urlencode(
            {"engine": "google_jobs", "q": q, "location": cfg.get("google_jobs_location", "Cebu City,Central Visayas,Philippines"),
             "gl": "ph", "hl": "en"})
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=40) as r:
                data = json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError("no working SearchApi key (add one to turn on Google Jobs)") from None
            if e.code == 429:
                raise RuntimeError("SearchApi searches used up for now") from None
            raise
        for d in data.get("jobs", []):
            ext = d.get("detected_extensions") or {}
            links = d.get("apply_links") or []
            link = d.get("apply_link") or (links[0].get("link") if links else "") or d.get("sharing_link", "")
            via = (d.get("via") or "").replace("via ", "")
            jobs.append(Job(
                d.get("title", ""), d.get("company_name", ""), d.get("location", ""), link,
                f"Google Jobs ({via})" if via else "Google Jobs", _ago_to_iso(ext.get("posted_at", "")),
                remote=bool(ext.get("work_from_home")) or "remote" in (d.get("location") or "").lower(),
                snippet=strip_tags(d.get("description", ""))[:240], tags=[ext.get("schedule") or ""],
            ))
    return jobs


def src_pythonph(cfg, hours):
    """PythonPH community jobs board (python.ph/jobs). Lists real posting dates."""
    jobs = []
    for page in (1, 2, 3):
        body = fetch(f"https://python.ph/jobs/?page={page}")
        cards = re.findall(r"<article\b.*?</article>", body, re.S)
        if not cards:
            break
        for c in cards:
            g = lambda pat: (m.group(1) if (m := re.search(pat, c, re.S)) else "")
            title = strip_tags(g(r'<h2[^>]*>.*?<a[^>]*>(.*?)</a>'))
            path = g(r'<h2[^>]*>.*?<a href="(/jobs/job/\d+/)"')
            company = strip_tags(g(r'</h2>\s*<p[^>]*>(.*?)</p>'))
            badges = [strip_tags(b) for b in re.findall(r'class="badge badge-outline[^"]*">(.*?)</span>', c, re.S)]
            location = badges[0] if badges else ""
            posted = g(r"Posted ([A-Z][a-z]{2} \d{1,2}, \d{4})")
            try:
                posted = datetime.strptime(posted, "%b %d, %Y").date().isoformat() if posted else ""
            except ValueError:
                posted = ""
            if title and path:
                jobs.append(Job(title, company, location, "https://python.ph" + path, "PythonPH", posted,
                                remote=any("work from home" in b.lower() or "remote" in b.lower() for b in badges),
                                snippet=strip_tags(g(r'<p class="m-0 mt-3[^"]*">(.*?)</p>'))[:240]))
        time.sleep(0.5)
    return jobs


SOURCES = {
    "LinkedIn": src_linkedin,
    "JobStreet": src_jobstreet,
    "Kalibrr": src_kalibrr,
    "Remotive": src_remotive,
    "Lever": src_lever,
    "Ashby": src_ashby,
    "Greenhouse": src_greenhouse,
    "Google": src_google_jobs,
    "PythonPH": src_pythonph,
}

# ---------------------------------------------------------------- filtering


def level_ok(job: Job, types: list[str]) -> bool:
    if "any" in types:
        return True
    text = f"{job.title} {' '.join(job.tags)}"
    if "internship" in types and INTERN_RE.search(text):
        return True
    if "entry" in types and ENTRY_RE.search(job.title):
        return True
    return False


def location_ok(job: Job, cfg) -> bool:
    if any_word(job.location, cfg["locations"]):
        return True
    if cfg.get("include_remote") and job.remote:
        return True  # Remotive is already limited to Asia / worldwide roles
    return False


def keep(job: Job, cfg, hours: float) -> bool:
    if not job.title or not job.url:
        return False
    if not any_word(job.title, cfg["field_keywords"]):
        return False
    if any_word(job.title, cfg["exclude_keywords"]):
        return False
    if not level_ok(job, cfg["job_types"]):
        return False
    if not location_ok(job, cfg):
        return False
    t = parse_time(job.posted)
    if t is None:
        job.undated = True  # kept, but reported separately as "date not confirmed"
    elif len(job.posted) == 10:
        # Date-only values: compare whole days (PH calendar), allowing the current day.
        days = max(1, math.ceil(hours / 24))
        today_ph = NOW.astimezone(timezone(timedelta(hours=8))).date()
        if (today_ph - t.date()).days > days:
            return False
    elif NOW - t > timedelta(hours=hours):
        return False
    return True


# ---------------------------------------------------------------- main


def scan(cfg, hours: float, only: list[str] | None = None):
    found, errors = [], {}
    for name, fn in SOURCES.items():
        if only and name.lower() not in only:
            continue
        try:
            found += fn(cfg, hours)
        except Exception as e:  # one broken site must not stop the others
            errors[name] = f"{type(e).__name__}: {e}"
    # If one site gives no date but another lists the same posting with a date,
    # use that date, so an old posting can't pass as new just because it's undated.
    dated = {}
    for j in found:
        if parse_time(j.posted) is not None:
            prev = dated.get(j.key)
            if prev is None or (parse_time(j.posted) < parse_time(prev)):
                dated[j.key] = j.posted
    for j in found:
        if parse_time(j.posted) is None and j.key in dated:
            j.posted = dated[j.key]
    seen, matches = set(), []
    for j in found:
        if j.key in seen or not keep(j, cfg, hours):
            continue
        seen.add(j.key)
        matches.append(j)
    matches.sort(key=lambda j: parse_time(j.posted) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return matches, errors, len(found)


def to_markdown(matches: list[Job], errors: dict, scanned: int, hours: float) -> str:
    out = [f"# Job scan — {NOW.astimezone(timezone(timedelta(hours=8))):%a %d %b %Y, %H:%M} (PH time)", ""]
    out.append(f"{len(matches)} new match(es) from {scanned} postings scanned (last {hours:g}h).")
    out.append("")
    for j in matches:
        t = parse_time(j.posted)
        when = f"posted {t.astimezone(timezone(timedelta(hours=8))):%d %b}" if t else "⚠️ posting date unknown"
        out.append(f"- **{j.title}** — {j.company} · {j.location}{' · remote' if j.remote else ''} "
                   f"· {j.source}, {when}\n  {j.url}")
    if errors:
        out += ["", "Sources that failed this run:"] + [f"- {k}: {v}" for k, v in errors.items()]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE / "config.toml"))
    ap.add_argument("--hours", type=float, help="look-back window (default: max_age_hours in config)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of Markdown")
    ap.add_argument("--state", help="JSON file of already-reported postings; new ones are added to it")
    ap.add_argument("--only", help="comma-separated source names to run, e.g. linkedin,kalibrr")
    args = ap.parse_args()

    cfg = tomllib.loads(Path(args.config).read_text())
    hours = args.hours or cfg.get("max_age_hours", 26)
    only = [s.strip().lower() for s in args.only.split(",")] if args.only else None
    matches, errors, scanned = scan(cfg, hours, only)

    if args.state:
        state_path = Path(args.state)
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        matches = [j for j in matches if j.key not in state]
        for j in matches:
            state[j.key] = NOW.date().isoformat()
        cutoff = (NOW - timedelta(days=60)).date().isoformat()  # forget entries after 60 days
        state = {k: v for k, v in state.items() if v >= cutoff}
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=1, sort_keys=True))

    if args.json:
        print(json.dumps({"generated": NOW.isoformat(), "hours": hours, "scanned": scanned,
                          "errors": errors, "matches": [asdict(j) for j in matches]}, indent=2))
    else:
        print(to_markdown(matches, errors, scanned, hours))
    return 0


if __name__ == "__main__":
    sys.exit(main())
