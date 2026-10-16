"""HSBC careers (portal.careers.hsbc.com, Eightfold) -> jobs.json for the dashboard."""
import re, json, time, pathlib, datetime as dt
import requests

BASE = "https://portal.careers.hsbc.com"
SEARCH = BASE + "/api/apply/v2/jobs"
KEYWORDS = ["custody", "fund accounting", "fund administration", "MSS", "FSS", "Asset Servicing",
            "transfer agency", "Securities Services", "digital assets", "transaction bank",
            "fund services", "capital markets", "COO", "Asset Owner", "ETF Servicing"]
MAX_PER_KEYWORD = 200
OUT = pathlib.Path(__file__).with_name("jobs.json")
S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                  "Accept": "application/json, text/plain, */*", "Referer": BASE + "/careers?domain=hsbc.com"})

# "Director and above" = portal seniority facet Director/CXO, or a senior-sounding title
SENIOR = re.compile(r"\b(managing director|director|head of|global head|regional head|country head|chief|"
                    r"ceo|cfo|cro|general manager|md)\b", re.I)
JUNIOR = re.compile(r"\b(associate|assistant|deputy)\s+director\b", re.I)

REGION = {}
for region, names in {
 "APAC": "Singapore,Hong Kong,China,Mainland China,India,Australia,Malaysia,Indonesia,Thailand,Vietnam,Philippines,"
         "Taiwan,South Korea,Korea,Japan,Sri Lanka,Bangladesh,New Zealand,Macau,Macao,Brunei,Pakistan",
 "Europe": "United Kingdom,UK,France,Germany,Luxembourg,Ireland,Malta,Poland,Greece,Switzerland,Italy,Spain,"
           "Turkey,Netherlands,Belgium,Czech Republic,Jersey,Guernsey,Isle of Man,Channel Islands,Sweden,Russia",
 "MENA": "United Arab Emirates,UAE,Saudi Arabia,Qatar,Bahrain,Kuwait,Oman,Egypt,Jordan,Lebanon,Israel,Algeria,Morocco",
 "Americas": "United States,USA,Canada,Mexico,Brazil,Argentina,Chile,Colombia,Bermuda,Cayman Islands,Uruguay,Peru",
}.items():
    for n in names.split(","): REGION[n.lower()] = region

def rx(k):  # acronyms case-sensitive, phrases case-insensitive
    return re.compile(r"\b" + re.escape(k) + r"\b", 0 if k.isupper() else re.I)
PATTERNS = {k: rx(k) for k in KEYWORDS}

def api(url, **params):
    for i in range(3):
        try:
            r = S.get(url, params=params, timeout=30)
            if r.status_code == 200: return r.json()
            print(f"  HTTP {r.status_code} for {r.url[:120]}")
        except (requests.RequestException, ValueError) as e:
            print("  error:", e)
        time.sleep(2 * (i + 1))
    return None

def search(keyword, **extra):
    found, start, total = {}, 0, None
    while start < MAX_PER_KEYWORD:
        d = api(SEARCH, domain="hsbc.com", query=keyword, start=start, num=10, sort_by="relevance", **extra)
        if not d or not d.get("positions"): break
        total = d.get("count", total)
        for p in d["positions"]: found[p["id"]] = p
        start += len(d["positions"])
        if total is not None and start >= total: break
        time.sleep(0.4)
    return found, total

def main():
    old = {}
    if OUT.exists():
        old = {j["id"]: j for j in json.loads(OUT.read_text()).get("jobs", []) if "id" in j}
    cand, senior_ids = {}, set()
    for k in KEYWORDS:
        res, total = search(k)
        print(f"{k!r}: {len(res)} fetched (portal count {total})")
        cand.update(res)
        for lvl in ("Director", "CXO"):                      # best-effort seniority filter
            sres, stotal = search(k, filter_seniority=lvl)
            if total and stotal is not None and stotal < total:   # only trust if filter really narrowed results
                senior_ids.update(sres)
    print(f"{len(cand)} unique candidates; {len(senior_ids)} flagged senior by portal filter")
    today, jobs = dt.date.today().isoformat(), []
    for pid, p in cand.items():
        if pid in old:
            j = old[pid]; j["senior"] = j["senior"] or pid in senior_ids; jobs.append(j); continue
        d = api(f"{SEARCH}/{pid}", domain="hsbc.com") or {}
        text = " ".join(str(x or "") for x in (p.get("name"), p.get("department"), p.get("business_unit"),
                                               d.get("job_description"), d.get("name")))
        text = re.sub(r"<[^>]+>", " ", text)
        matched = [k for k, pat in PATTERNS.items() if pat.search(text)]
        if not matched: continue
        loc = p.get("location") or (p.get("locations") or [""])[0]
        parts = [x.strip() for x in loc.split(",")]
        country = parts[-1] if parts else ""
        title = p.get("name") or p.get("posting_name") or ""
        created = p.get("t_create")
        jobs.append({"id": pid, "title": title, "url": p.get("canonicalPositionUrl") or f"{BASE}/careers/job/{pid}",
                     "location": loc, "city": parts[0], "country": country,
                     "region": REGION.get(country.lower(), "Other"),
                     "department": p.get("department") or "", "unit": p.get("business_unit") or "",
                     "posted": dt.datetime.fromtimestamp(created, dt.timezone.utc).strftime("%Y-%m-%d") if created else "",
                     "matched": matched,
                     "senior": pid in senior_ids or bool(SENIOR.search(title) and not JUNIOR.search(title)),
                     "first_seen": today})
        time.sleep(0.4)
    if not jobs and old:
        print("No results - keeping previous data"); return
    OUT.write_text(json.dumps({"updated": dt.datetime.now(dt.timezone.utc).isoformat(), "source": BASE,
                               "jobs": sorted(jobs, key=lambda j: j["posted"], reverse=True)}, indent=1))
    print(f"{len(jobs)} jobs written")

if __name__ == "__main__":
    main()
