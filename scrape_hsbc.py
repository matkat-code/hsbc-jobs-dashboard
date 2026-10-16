"""Scrape apply.careers.hsbc.com (SAP SuccessFactors) for Securities Services-type roles -> jobs.json"""
import re, json, time, pathlib, datetime as dt
import requests
from bs4 import BeautifulSoup

BASE = "https://apply.careers.hsbc.com"
KEYWORDS = ["custody", "fund accounting", "fund administration", "MSS", "FSS", "Asset Servicing",
            "transfer agency", "Securities Services", "digital assets", "transaction bank",
            "fund services", "capital markets", "COO", "Asset Owner", "ETF Servicing"]
HDR = {"User-Agent": "Mozilla/5.0 (compatible; JobDashboard/1.0)"}
OUT = pathlib.Path(__file__).with_name("jobs.json")

# Seniority: "Director and above" if title matches SENIOR and not JUNIOR
SENIOR = re.compile(r"\b(managing director|director|head of|global head|regional head|country head|chief|"
                    r"ceo|cfo|cro|general manager|md)\b", re.I)
JUNIOR = re.compile(r"\b(associate|assistant|deputy)\s+director\b", re.I)

CC = {  # code: (country, region)
 "SG":("Singapore","APAC"),"HK":("Hong Kong","APAC"),"CN":("China","APAC"),"IN":("India","APAC"),
 "AU":("Australia","APAC"),"MY":("Malaysia","APAC"),"ID":("Indonesia","APAC"),"TH":("Thailand","APAC"),
 "VN":("Vietnam","APAC"),"PH":("Philippines","APAC"),"TW":("Taiwan","APAC"),"KR":("South Korea","APAC"),
 "JP":("Japan","APAC"),"LK":("Sri Lanka","APAC"),"BD":("Bangladesh","APAC"),"NZ":("New Zealand","APAC"),
 "GB":("United Kingdom","Europe"),"UK":("United Kingdom","Europe"),"FR":("France","Europe"),
 "DE":("Germany","Europe"),"LU":("Luxembourg","Europe"),"IE":("Ireland","Europe"),"MT":("Malta","Europe"),
 "PL":("Poland","Europe"),"GR":("Greece","Europe"),"CH":("Switzerland","Europe"),"IT":("Italy","Europe"),
 "ES":("Spain","Europe"),"TR":("Turkey","Europe"),"AE":("UAE","MENA"),"SA":("Saudi Arabia","MENA"),
 "QA":("Qatar","MENA"),"BH":("Bahrain","MENA"),"KW":("Kuwait","MENA"),"OM":("Oman","MENA"),
 "EG":("Egypt","MENA"),"US":("United States","Americas"),"CA":("Canada","Americas"),
 "MX":("Mexico","Americas"),"BR":("Brazil","Americas"),"AR":("Argentina","Americas"),
}

def rx(k):  # acronyms case-sensitive, phrases case-insensitive
    return re.compile(r"\b" + re.escape(k) + r"\b", 0 if k.isupper() else re.I)
PATTERNS = {k: rx(k) for k in KEYWORDS}

def get(url, **kw):
    for i in range(3):
        try:
            r = requests.get(url, headers=HDR, timeout=30, **kw); r.raise_for_status(); return r
        except requests.RequestException:
            time.sleep(2 * (i + 1))
    return None

def search(keyword):
    rows, start = {}, 0
    while True:
        r = get(f"{BASE}/search/", params={"q": keyword, "sortColumn": "referencedate",
                                           "sortDirection": "desc", "startrow": start})
        if not r: break
        trs = BeautifulSoup(r.text, "html.parser").select("tr.data-row")
        if not trs: break
        for tr in trs:
            a = tr.select_one("a.jobTitle-link")
            if not a: continue
            loc = tr.select_one("span.jobLocation")
            d = tr.select_one("span.jobDate")
            url = BASE + a["href"]
            rows[url] = {"title": a.get_text(strip=True), "location": loc.get_text(strip=True) if loc else "",
                         "posted": d.get_text(strip=True) if d else ""}
        start += len(trs)
        time.sleep(0.5)
    return rows

def main():
    old = {}
    if OUT.exists():
        old = {j["url"]: j for j in json.loads(OUT.read_text()).get("jobs", [])}
    found = {}
    for k in KEYWORDS:
        found.update(search(k))
    today = dt.date.today().isoformat()
    jobs = []
    for url, row in found.items():
        if url in old:                       # reuse, avoid refetching detail pages
            j = old[url]; j.update(posted=row["posted"] or j["posted"]); jobs.append(j); continue
        r = get(url)
        text = row["title"]
        if r:
            s = BeautifulSoup(r.text, "html.parser")
            d = s.select_one("span.jobdescription") or s.body
            text += " " + d.get_text(" ", strip=True)
        matched = [k for k, p in PATTERNS.items() if p.search(text)]
        if not matched: continue             # search hit but phrase not really in the role
        parts = [p.strip() for p in row["location"].split(",")]
        code = next((p for p in parts[1:] if len(p) == 2 and p.isupper()), "")
        country, region = CC.get(code, (parts[-1] if parts else "", "Other"))
        jobs.append({"title": row["title"], "url": url, "location": row["location"], "city": parts[0],
                     "country": country, "region": region, "posted": row["posted"], "matched": matched,
                     "senior": bool(SENIOR.search(row["title"]) and not JUNIOR.search(row["title"])),
                     "first_seen": today})
        time.sleep(0.5)
    if not jobs and old:
        print("No results - keeping previous data (portal layout may have changed)"); return
    OUT.write_text(json.dumps({"updated": dt.datetime.now(dt.timezone.utc).isoformat(),
                               "source": BASE, "jobs": sorted(jobs, key=lambda j: j["first_seen"], reverse=True)},
                              indent=1))
    print(f"{len(jobs)} jobs written")

if __name__ == "__main__":
    main()
