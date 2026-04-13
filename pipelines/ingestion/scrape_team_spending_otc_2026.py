#!/usr/bin/env python3
"""Collect and resolve OTC 2026 team spending data.

Phase 1: Write evidence rows from OTC salary-cap team pages.
Phase 2: Resolve into final resolved/unresolved outputs with strict gates.
"""

from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TEAM_TO_SLUG = {
    "ARI": "arizona-cardinals",
    "ATL": "atlanta-falcons",
    "BAL": "baltimore-ravens",
    "BUF": "buffalo-bills",
    "CAR": "carolina-panthers",
    "CHI": "chicago-bears",
    "CIN": "cincinnati-bengals",
    "CLE": "cleveland-browns",
    "DAL": "dallas-cowboys",
    "DEN": "denver-broncos",
    "DET": "detroit-lions",
    "GB": "green-bay-packers",
    "HOU": "houston-texans",
    "IND": "indianapolis-colts",
    "JAX": "jacksonville-jaguars",
    "KC": "kansas-city-chiefs",
    "LV": "las-vegas-raiders",
    "LAC": "los-angeles-chargers",
    "LAR": "los-angeles-rams",
    "MIA": "miami-dolphins",
    "MIN": "minnesota-vikings",
    "NE": "new-england-patriots",
    "NO": "new-orleans-saints",
    "NYG": "new-york-giants",
    "NYJ": "new-york-jets",
    "PHI": "philadelphia-eagles",
    "PIT": "pittsburgh-steelers",
    "SEA": "seattle-seahawks",
    "SF": "san-francisco-49ers",
    "TB": "tampa-bay-buccaneers",
    "TEN": "tennessee-titans",
    "WAS": "washington-commanders",
}

MONEY_PATTERN = re.compile(r"\(?\$-?[0-9][0-9,]*(?:\.[0-9]+)?\)?")
ROW_PATTERN = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
TEAM_LINK_PATTERN = re.compile(r'team-link\s+([A-Z]{2,3})\b', re.I)
TABLE_PATTERN = re.compile(r"<table[^>]*>(.*?)</table>", re.I | re.S)
TD_PATTERN = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
FREE_AGENCY_URL = "https://overthecap.com/free-agency-spending"
CAP_SPACE_URL = "https://overthecap.com/salary-cap-space"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape OTC 2026 team spending and resolve outputs")
    p.add_argument(
        "--evidence",
        type=Path,
        default=Path("data/raw/offseason/team_spending_otc_2026_evidence_template.csv"),
    )
    p.add_argument(
        "--resolved",
        type=Path,
        default=Path("data/raw/offseason/team_spending_otc_2026.csv"),
    )
    p.add_argument(
        "--unresolved",
        type=Path,
        default=Path("data/raw/offseason/team_spending_otc_2026_unresolved.csv"),
    )
    p.add_argument(
        "--resolve-only",
        action="store_true",
        help="Do not scrape OTC; resolve only from existing evidence CSV.",
    )
    return p.parse_args()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def clean_money(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    neg = s.startswith("(") and s.endswith(")")
    s = s.replace("$", "").replace(",", "").replace("(", "").replace(")", "")
    if not s:
        return ""
    try:
        v = int(float(s))
    except ValueError:
        return ""
    if neg:
        v = -abs(v)
    return str(v)


def first_money(text: str) -> str:
    m = MONEY_PATTERN.search(text)
    if not m:
        return ""
    return clean_money(m.group(0))


def extract_y2026_block(html: str) -> str:
    marker = 'id="y2026"'
    i = html.find(marker)
    if i == -1:
        return ""
    j = html.find('id="y2027"', i)
    if j == -1:
        return html[i : i + 150000]
    return html[i:j]


def extract_cap_space(y2026_block: str) -> str:
    if not y2026_block:
        return ""
    m = re.search(r"Team Cap Space:\s*([^<]+)", y2026_block, re.I)
    if not m:
        return ""
    return first_money(m.group(1))


def extract_dead_money(y2026_block: str, full_html: str) -> str:
    if y2026_block:
        m1 = re.search(r"Dead\s+Money:\s*([^<]+)", y2026_block, re.I)
        if m1:
            return first_money(m1.group(1))
        m2 = re.search(r"Dead\s+Cap:\s*([^<]+)", y2026_block, re.I)
        if m2:
            return first_money(m2.group(1))
    m3 = re.search(r"2026[^\n]{0,160}(Dead\s+Money|Dead\s+Cap)[^\n]{0,160}", full_html, re.I)
    if m3:
        return first_money(m3.group(0))
    return ""


def extract_total_fa_spending(y2026_block: str, full_html: str) -> str:
    if y2026_block:
        m1 = re.search(r"(Total\s+)?FA\s+Spending:\s*([^<]+)", y2026_block, re.I)
        if m1:
            return first_money(m1.group(0))
        m2 = re.search(r"Free\s+Agent\s+Spending:\s*([^<]+)", y2026_block, re.I)
        if m2:
            return first_money(m2.group(0))
    m3 = re.search(r"2026[^\n]{0,200}(FA\s+Spending|Free\s+Agent\s+Spending)[^\n]{0,200}", full_html, re.I)
    if m3:
        return first_money(m3.group(0))
    return ""


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def extract_team_money_rows(html: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in ROW_PATTERN.findall(html):
        team_match = TEAM_LINK_PATTERN.search(row)
        if not team_match:
            continue
        team = team_match.group(1).upper()
        money = [clean_money(m.group(0)) for m in MONEY_PATTERN.finditer(row)]
        money = [m for m in money if m]
        if money:
            out[team] = money
    return out


def extract_tables(html: str) -> list[str]:
    return TABLE_PATTERN.findall(html)


def strip_tags(raw: str) -> str:
    return re.sub(r"<[^>]+>", " ", raw)


def extract_free_agency_totals(y2026_html: str) -> dict[str, str]:
    totals: dict[str, str] = {}
    for table in extract_tables(y2026_html):
        if "Total Guarantees" not in table or "1st Year Cash" not in table:
            continue
        for row in ROW_PATTERN.findall(table):
            team_match = TEAM_LINK_PATTERN.search(row)
            if not team_match:
                continue
            cells = TD_PATTERN.findall(row)
            if len(cells) < 3:
                continue
            total = first_money(strip_tags(cells[2]))
            if total:
                totals[team_match.group(1).upper()] = total
        if totals:
            break
    return totals


def extract_cap_space_dead(y2026_html: str) -> tuple[dict[str, str], dict[str, str]]:
    cap_by_team: dict[str, str] = {}
    dead_by_team: dict[str, str] = {}
    for table in extract_tables(y2026_html):
        if "salary-cap-space-table" not in table and "Cap <br />Space" not in table:
            continue
        for row in ROW_PATTERN.findall(table):
            team_match = TEAM_LINK_PATTERN.search(row)
            if not team_match:
                continue
            cells = TD_PATTERN.findall(row)
            if len(cells) < 6:
                continue
            team = team_match.group(1).upper()
            cap = first_money(strip_tags(cells[1]))
            dead = first_money(strip_tags(cells[5]))
            if cap:
                cap_by_team[team] = cap
            if dead:
                dead_by_team[team] = dead
        if cap_by_team:
            break
    return cap_by_team, dead_by_team


def build_evidence() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    obs = now_iso()

    fa_by_team: dict[str, str] = {}
    cap_by_team: dict[str, str] = {}
    dead_by_team: dict[str, str] = {}

    try:
        fa_html = fetch(FREE_AGENCY_URL)
        fa_block = extract_y2026_block(fa_html) or fa_html
        fa_by_team = extract_free_agency_totals(fa_block)
    except Exception:  # pylint: disable=broad-except
        fa_by_team = {}

    try:
        cap_html = fetch(CAP_SPACE_URL)
        cap_block = extract_y2026_block(cap_html) or cap_html
        cap_by_team, dead_by_team = extract_cap_space_dead(cap_block)
    except Exception:  # pylint: disable=broad-except
        cap_by_team = {}
        dead_by_team = {}

    for team, slug in TEAM_TO_SLUG.items():
        url = f"{FREE_AGENCY_URL}|{CAP_SPACE_URL}|https://overthecap.com/salary-cap/{slug}"
        notes: list[str] = []
        fa = fa_by_team.get(team, "")
        cap = cap_by_team.get(team, "")
        dead = dead_by_team.get(team, "")

        if not fa:
            notes.append("missing_total_fa_spending")
        if not cap:
            notes.append("missing_cap_space")
        if not dead:
            notes.append("missing_dead_money")

        if not fa and not cap and not dead:
            notes.append("no_2026_data")

        rows.append(
            {
                "team": team,
                "total_fa_spending": fa,
                "cap_space": cap,
                "dead_money": dead,
                "source_url": url,
                "observed_at": obs,
                "notes": "|".join(notes),
            }
        )
    return rows


def reason_for(evidence_row: dict[str, str]) -> str:
    notes = evidence_row.get("notes", "")
    fa = (evidence_row.get("total_fa_spending") or "").strip()
    cap = (evidence_row.get("cap_space") or "").strip()
    dead = (evidence_row.get("dead_money") or "").strip()

    if not fa and not cap and not dead:
        return "no_2026_data"
    if "no_2026_data" in notes:
        return "no_2026_data"
    if not cap:
        return "missing_cap_space"
    if not dead:
        return "missing_dead_money"
    if not fa:
        return "missing_total_fa_spending"
    if "parse_error" in notes:
        return "parse_error"
    return "parse_error"


def resolve(evidence_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    imported_at = now_iso()
    resolved_rows: list[dict[str, str]] = []
    unresolved_rows: list[dict[str, str]] = []

    for team in TEAM_TO_SLUG:
        team_rows = [r for r in evidence_rows if r["team"] == team]
        team_rows.sort(key=lambda r: r.get("observed_at", ""), reverse=True)
        chosen = team_rows[0] if team_rows else None
        if not chosen:
            unresolved_rows.append(
                {
                    "team": team,
                    "reason": "no_2026_data",
                    "source_url": f"https://overthecap.com/salary-cap/{TEAM_TO_SLUG[team]}",
                }
            )
            continue

        fa = chosen.get("total_fa_spending", "").strip()
        cap = chosen.get("cap_space", "").strip()
        dead = chosen.get("dead_money", "").strip()

        if fa and cap and dead:
            resolved_rows.append(
                {
                    "team": team,
                    "total_fa_spending": fa,
                    "cap_space": cap,
                    "dead_money": dead,
                    "source_url": chosen["source_url"],
                    "import_method": "scraped",
                    "imported_at": imported_at,
                }
            )
        else:
            unresolved_rows.append(
                {
                    "team": team,
                    "reason": reason_for(chosen),
                    "attempted_sources": chosen["source_url"],
                }
            )

    return resolved_rows, unresolved_rows


def main() -> None:
    args = parse_args()
    if args.resolve_only:
        with args.evidence.open(newline="", encoding="utf-8") as f:
            evidence = list(csv.DictReader(f))
    else:
        evidence = build_evidence()
        write_csv(
            args.evidence,
            ["team", "total_fa_spending", "cap_space", "dead_money", "source_url", "observed_at", "notes"],
            evidence,
        )

    resolved_rows, unresolved_rows = resolve(evidence)

    if len(resolved_rows) + len(unresolved_rows) != 32:
        raise RuntimeError("coverage gate failed for otc outputs")

    write_csv(
        args.resolved,
        ["team", "total_fa_spending", "cap_space", "dead_money", "source_url", "import_method", "imported_at"],
        resolved_rows,
    )
    write_csv(args.unresolved, ["team", "reason", "attempted_sources"], unresolved_rows)

    print(
        f"evidence={len(evidence)} resolved={len(resolved_rows)} unresolved={len(unresolved_rows)}"
    )


if __name__ == "__main__":
    main()
