"""
AMMC Scraper — collects annual financial report (RFA) filings for a set of
target Moroccan listed companies from ammc.ma.

Strategy:
1. FAST PATH: try direct URL construction using the known pattern
   /fr/espace-emetteurs/etats-financiers/{slug}-rfa-{year}
   This works for most recent years (~2016-2025) for major issuers.
2. FALLBACK: walk the paginated master list
   /fr/liste-etats-financiers-emetteurs?page=N
   and keep any row matching a target company name. Use this to catch
   filings the fast path misses (older years, naming exceptions).

Run: python ammc_scraper.py
Output: ammc_filings.csv (metadata) + downloaded PDFs in ./filings/
"""

import re
import time
import csv
from pathlib import Path
import requests
from bs4 import BeautifulSoup

BASE = "https://www.ammc.ma"
LIST_URL = f"{BASE}/fr/liste-etats-financiers-emetteurs"
OUT_DIR = Path("filings")
OUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
}

# --- STEP 0: confirmed slugs -------------------------------------------------
# All verified directly by opening the URLs in browser (2026-08-08).
TARGET_COMPANIES = {
    "ATTIJARIWAFA BANK": "attijariwafa-bank",
    "Banque Centrale Populaire (BCP)": "bcp",
    "CIH Bank": "cih-bank",
    "Crédit du Maroc (CDM)": "credit-du-maroc",
    "Bank of Africa - Groupe BMCE (BOA)": "bank-africa",
    "BMCI": "bmci",
    "CDG capital": "cdg-capital",
}

YEARS = range(2016, 2026)  # adjust range as needed

session = requests.Session()
session.headers.update(HEADERS)


def try_fast_path():
    """Attempt direct URL construction for each company/year."""
    found = []
    for company, slug in TARGET_COMPANIES.items():
        for year in YEARS:
            url = f"{BASE}/fr/espace-emetteurs/etats-financiers/{slug}-rfa-{year}"
            r = session.get(url, timeout=15)
            if r.status_code == 200 and "Pièce jointe" in r.text:
                found.append((company, year, url))
                print(f"[OK]   {company} {year}")
            else:
                print(f"[miss] {company} {year} -> {r.status_code}")
            time.sleep(0.5)  # be polite, avoid hammering the server
    return found


def walk_master_list(max_pages=40):
    """Fallback: scan the paginated master list for target companies."""
    found = []
    company_names_lower = {c.lower(): c for c in TARGET_COMPANIES}

    for page in range(max_pages):
        url = f"{LIST_URL}?page={page}"
        r = session.get(url, timeout=15)
        if r.status_code != 200:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        rows = soup.select("table tr")
        if not rows:
            break

        for row in rows:
            link = row.find("a", href=re.compile(r"/fr/espace-emetteurs/etats-financiers/"))
            if not link:
                continue
            text = row.get_text(" ", strip=True).lower()
            for name_lower, name_orig in company_names_lower.items():
                if name_lower in text:
                    year_match = re.search(r"(20\d{2})", row.get_text())
                    year = year_match.group(1) if year_match else "?"
                    found.append((name_orig, year, BASE + link["href"]))
                    print(f"[list] {name_orig} {year}")
        time.sleep(0.5)

    return found


def scrape_detail(url):
    """Extract PDF link + metadata from a filing detail page."""
    r = session.get(url, timeout=15)
    if r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    pdf_link = soup.find("a", href=re.compile(r"\.pdf$"))
    if not pdf_link:
        return None
    return BASE + pdf_link["href"] if pdf_link["href"].startswith("/") else pdf_link["href"]


def download_pdf(pdf_url, company, year):
    safe_name = re.sub(r"[^\w\-]", "_", company)
    dest = OUT_DIR / f"{safe_name}_{year}.pdf"
    if dest.exists():
        return dest
    r = session.get(pdf_url, timeout=30)
    if r.status_code == 200:
        dest.write_bytes(r.content)
        print(f"  downloaded -> {dest}")
        return dest
    return None


def main():
    all_filings = try_fast_path()
    all_filings += walk_master_list(max_pages=40)

    # dedupe by (company, year)
    seen = set()
    rows = []
    for company, year, detail_url in all_filings:
        key = (company, str(year))
        if key in seen:
            continue
        seen.add(key)
        pdf_url = scrape_detail(detail_url)
        rows.append({
            "company": company,
            "year": year,
            "detail_url": detail_url,
            "pdf_url": pdf_url or "",
        })
        if pdf_url:
            download_pdf(pdf_url, company, year)
        time.sleep(0.5)

    with open("ammc_filings.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["company", "year", "detail_url", "pdf_url"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nDone. {len(rows)} filings found, saved to ammc_filings.csv")


if __name__ == "__main__":
    main()
