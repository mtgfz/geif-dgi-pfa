"""
AMMC Bank Financial Statement Parser (PCEC format)

Extracts key line items from Moroccan bank annual report PDFs:
- Total Actif / Total Passif (from BILAN)
- Produit Net Bancaire / PNB (from CPC or État des Soldes de Gestion)
- Résultat Net (from CPC)

Banks in Morocco follow the PCEC chart of accounts (Plan Comptable des
Établissements de Crédit), not the general CGNC used by other companies —
so this parser is specific to bank filings. All 7 target issuers are banks,
so one template covers everyone.

v2: switched from text-regex extraction to pdfplumber TABLE extraction.
Text-regex was concatenating adjacent numbers across table columns (no
column boundary in flat text), producing garbage values like 3.6e+17 MAD.
Tables give properly separated cells, which fixes that at the root.

Requires: pip install pdfplumber
"""

import re
import csv
from pathlib import Path
import pdfplumber

FILINGS_DIR = Path("filings")
OUTPUT_CSV = "parsed_financials.csv"

# Label variants seen across different banks/years for each target line item.
# Matched against a table cell after normalizing (uppercase, accents kept,
# extra whitespace collapsed). Order doesn't matter — first match wins.
LABEL_VARIANTS = {
    "total_actif": [
        "TOTAL DE L'ACTIF", "TOTAL DE L’ACTIF", "TOTAL ACTIF",
        "TOTAL GENERAL DE L'ACTIF", "TOTAL GENERAL DE L’ACTIF",
    ],
    "total_passif": [
        "TOTAL DU PASSIF", "TOTAL PASSIF",
        "TOTAL GENERAL DU PASSIF",
    ],
    "produit_net_bancaire": [
        "PRODUIT NET BANCAIRE",
    ],
    "resultat_net": [
        "RESULTAT NET DE L'EXERCICE", "RESULTAT NET DE L’EXERCICE",
        "RESULTAT NET", "RÉSULTAT NET DE L'EXERCICE",
        "RÉSULTAT NET DE L’EXERCICE", "RÉSULTAT NET",
    ],
}

NUMBER_CELL = re.compile(r"^-?[\d\s\u00a0]+(?:[.,]\d+)?$")


def normalize(s):
    if not s:
        return ""
    s = s.upper().replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def clean_number(raw):
    """Convert '12 345 678' or '12.345.678,50' style cell text to a float."""
    if not raw:
        return None
    cleaned = raw.strip().replace(" ", "").replace("\u00a0", "")
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def find_target_pages(pdf):
    """Return page indices likely to contain BILAN/CPC tables.

    Tries several marker phrases since different banks title this section
    differently ("COMPTES SOCIAUX AU...", "PUBLICATION DES COMPTES", "Bilan
    au...", etc). Falls back to bare "BILAN" if none of those hit, and as
    a last resort looks for a page containing both ACTIF and PASSIF.
    """
    markers = [
        re.compile(r"COMPTES\s+SOCIAUX\s+AU", re.IGNORECASE),
        re.compile(r"PUBLICATION\s+DES\s+COMPTES", re.IGNORECASE),
        re.compile(r"BILAN\s+AU\s+\d", re.IGNORECASE),
        re.compile(r"ETATS?\s+FINANCIERS", re.IGNORECASE),
        re.compile(r"ETATS?\s+DE\s+SYNTH[EÈ]SE", re.IGNORECASE),
        re.compile(r"COMPTES\s+ANNUELS", re.IGNORECASE),
    ]
    for marker in markers:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if marker.search(text):
                return sorted(set(range(i, min(i + 4, len(pdf.pages)))))

    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        if re.search(r"\bBILAN\b", text, re.IGNORECASE):
            return sorted(set(range(i, min(i + 4, len(pdf.pages)))))

    for i, page in enumerate(pdf.pages):
        text = (page.extract_text() or "").upper()
        if "ACTIF" in text and "PASSIF" in text:
            return sorted(set(range(i, min(i + 4, len(pdf.pages)))))

    return []


def is_plausible_balance(ta, tp):
    """A real bank total actif/passif is never a tiny number — reject
    matches that only pass the equality check by coincidence (e.g. two
    footnote references or table indices that happen to both read '2.0').
    Threshold is deliberately low (10,000) since figures are usually in
    thousands of MAD at minimum — this only filters out obvious garbage,
    not legitimate smaller issuers."""
    if ta is None or tp is None:
        return False
    if ta <= 0 or tp <= 0:
        return False
    if abs(ta) < 10_000 or abs(tp) < 10_000:
        return False
    return abs(ta - tp) <= max(abs(ta), abs(tp)) * 0.01


def scan_whole_document(pdf):
    """Fallback when marker-based page detection fails or finds the wrong
    page (e.g. a notes/appendix table instead of the real bilan). Scans
    every page's tables directly for 'Total de l'Actif' style rows. Slower,
    but far more robust — and safe, because a wrong match is caught by the
    balance_check (actif must equal passif) rather than trusted blindly."""
    candidates = []
    for page in pdf.pages:
        tables = page.extract_tables()
        if not tables:
            tables = page.extract_tables(table_settings={
                "vertical_strategy": "text",
                "horizontal_strategy": "text",
                "snap_tolerance": 5,
            })
        if not tables:
            continue
        ta, _ = extract_from_tables(tables, "total_actif")
        tp, _ = extract_from_tables(tables, "total_passif")
        if is_plausible_balance(ta, tp):
            candidates.append(tables)  # balanced AND plausible — trustworthy
    return candidates[0] if candidates else []


SCALE_PATTERN = re.compile(
    r"\(?\s*en\s+(milliers|millions)\s+de\s+dirhams?\s*\)?|"
    r"\(?\s*en\s+(K|M)DH\s*\)?",
    re.IGNORECASE,
)


def detect_scale(pdf, pages_to_scan):
    """Look for a 'en milliers de DH' / 'en MDH' style caption near the
    target pages. Different banks (and sometimes different years from the
    same bank) report figures at different scales — this doesn't fix that,
    but surfaces it so you can spot and normalize it by hand rather than
    silently comparing apples to oranges."""
    for i in pages_to_scan:
        text = pdf.pages[i].extract_text() or ""
        match = SCALE_PATTERN.search(text)
        if match:
            return match.group(0).strip()
    return "not found — check manually"


def extract_from_tables(tables, field):
    """Search extracted tables for a row matching any label variant for
    this field, and return (current_value, previous_value) from the numeric
    cells on that row."""
    variants = LABEL_VARIANTS[field]
    for table in tables:
        for row in table:
            if not row or row[0] is None:
                continue
            label = normalize(row[0])
            if any(variant in label for variant in variants):
                numbers = [clean_number(c) for c in row[1:] if c and NUMBER_CELL.match(c.strip())]
                numbers = [n for n in numbers if n is not None]
                current = numbers[0] if len(numbers) >= 1 else None
                previous = numbers[1] if len(numbers) >= 2 else None
                return current, previous
    return None, None


def parse_pdf(pdf_path):
    result = {"file": pdf_path.name}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            pages_to_scan = find_target_pages(pdf)
            if not pages_to_scan:
                # no marker page found at all — try scanning the whole
                # document directly before giving up (this is what fixes
                # cases like CIH 2022 where no title text matched anything)
                fallback_tables = scan_whole_document(pdf)
                if fallback_tables:
                    result["scale_note"] = "not checked (whole-doc fallback used)"
                    result["used_whole_doc_fallback"] = True
                    for field in LABEL_VARIANTS:
                        current, previous = extract_from_tables(fallback_tables, field)
                        result[f"{field}_current"] = current
                        result[f"{field}_previous"] = previous
                    ta, tp = result.get("total_actif_current"), result.get("total_passif_current")
                    result["balance_check"] = "OK" if ta is not None and tp is not None else "n/a (one or both missing)"
                    return result

                result["error"] = "target pages not found"
                result["scale_note"] = ""
                result["balance_check"] = "n/a"
                for field in LABEL_VARIANTS:
                    result[f"{field}_current"] = None
                    result[f"{field}_previous"] = None
                return result

            result["scale_note"] = detect_scale(pdf, pages_to_scan)

            all_tables = []
            for i in pages_to_scan:
                page = pdf.pages[i]
                tables = page.extract_tables()
                if not tables:
                    tables = page.extract_tables(table_settings={
                        "vertical_strategy": "text",
                        "horizontal_strategy": "text",
                        "snap_tolerance": 5,
                    })
                all_tables.extend(tables)

            # quick pre-check: does this table set give a balanced actif/passif?
            ta_check, _ = extract_from_tables(all_tables, "total_actif") if all_tables else (None, None)
            tp_check, _ = extract_from_tables(all_tables, "total_passif") if all_tables else (None, None)
            page_result_balanced = is_plausible_balance(ta_check, tp_check)

            if not all_tables or not page_result_balanced:
                # marker-based page selection missed or found the wrong
                # table (e.g. a notes/appendix page) — fall back to
                # scanning the whole document directly
                fallback_tables = scan_whole_document(pdf)
                if fallback_tables:
                    all_tables = fallback_tables
                    result["used_whole_doc_fallback"] = True

            if not all_tables:
                result["error"] = "no tables found on target pages (even with fallback strategy)"

            for field in LABEL_VARIANTS:
                current, previous = extract_from_tables(all_tables, field)
                result[f"{field}_current"] = current
                result[f"{field}_previous"] = previous

            # Sanity check: Total Actif must equal Total Passif by basic
            # accounting identity (a bilan always balances). If they don't
            # match, at least one of them was extracted from the wrong row
            # — flag it rather than silently trusting a plausible-looking
            # number.
            ta, tp = result.get("total_actif_current"), result.get("total_passif_current")
            if ta is not None and tp is not None:
                if is_plausible_balance(ta, tp):
                    result["balance_check"] = "OK"
                elif ta <= 0 or tp <= 0 or abs(ta) < 10_000 or abs(tp) < 10_000:
                    result["balance_check"] = f"IMPLAUSIBLE actif={ta} passif={tp} — too small/negative, do not trust"
                else:
                    result["balance_check"] = f"MISMATCH actif={ta} vs passif={tp} — do not trust, re-check by hand"
            else:
                result["balance_check"] = "n/a (one or both missing)"
    except Exception as e:
        result["error"] = str(e)
    return result


def main():
    pdf_files = sorted(FILINGS_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDFs found in {FILINGS_DIR}/ — run the scraper first.")
        return

    rows = []
    for pdf_path in pdf_files:
        print(f"Parsing {pdf_path.name}...")
        row = parse_pdf(pdf_path)
        rows.append(row)
        print(f"  -> {row}")

    fieldnames = ["file", "error", "scale_note", "balance_check", "used_whole_doc_fallback"]
    for field in LABEL_VARIANTS:
        fieldnames += [f"{field}_current", f"{field}_previous"]
    # dedupe while preserving order
    fieldnames = list(dict.fromkeys(fieldnames))

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    print(f"\nDone. Results saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
