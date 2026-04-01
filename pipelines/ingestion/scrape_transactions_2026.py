#!/usr/bin/env python3
"""Scrape NFL.com league transaction pages into canonical offseason CSV.

The scraper enforces deterministic normalization and coverage rules for the
2026 offseason transaction seed file.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


TEAM_SLUG_TO_ABBR = {
    "arizona-cardinals": "ARI",
    "atlanta-falcons": "ATL",
    "baltimore-ravens": "BAL",
    "buffalo-bills": "BUF",
    "carolina-panthers": "CAR",
    "chicago-bears": "CHI",
    "cincinnati-bengals": "CIN",
    "cleveland-browns": "CLE",
    "dallas-cowboys": "DAL",
    "denver-broncos": "DEN",
    "detroit-lions": "DET",
    "green-bay-packers": "GB",
    "houston-texans": "HOU",
    "indianapolis-colts": "IND",
    "jacksonville-jaguars": "JAX",
    "kansas-city-chiefs": "KC",
    "las-vegas-raiders": "LV",
    "los-angeles-chargers": "LAC",
    "los-angeles-rams": "LAR",
    "miami-dolphins": "MIA",
    "minnesota-vikings": "MIN",
    "new-england-patriots": "NE",
    "new-orleans-saints": "NO",
    "new-york-giants": "NYG",
    "new-york-jets": "NYJ",
    "philadelphia-eagles": "PHI",
    "pittsburgh-steelers": "PIT",
    "seattle-seahawks": "SEA",
    "san-francisco-49ers": "SF",
    "tampa-bay-buccaneers": "TB",
    "tennessee-titans": "TEN",
    "washington-commanders": "WAS",
}

EXCLUDE_KEYWORDS = (
    "practice squad",
    "reserve/future",
    "reserve/futures",
    "futures contract",
    "international exemption",
    "roster exemption",
)

OUTPUT_FIELDS = [
    "team",
    "player",
    "transaction_type",
    "transaction_date",
    "notes",
    "source_url",
    "import_method",
    "imported_at",
]

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"


@dataclass(frozen=True)
class RawTransaction:
    source_type: str
    from_team: str
    to_team: str
    date_text: str
    player: str
    txn_text: str
    source_url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape NFL.com offseason transactions")
    parser.add_argument("--season", type=int, default=2026)
    parser.add_argument("--output", type=Path, default=Path("data/raw/offseason/transactions_raw_2026.csv"))
    parser.add_argument("--imported-at", default="2026-03-26T00:00:00Z")
    parser.add_argument("--max-page", type=int, default=200)
    return parser.parse_args()


def fetch_html(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def extract_team_abbr(cell: BeautifulSoup) -> str:
    link = cell.find("a", href=True)
    if not link:
        return ""
    m = re.search(r"/teams/([^/]+)/", link["href"])
    if not m:
        return ""
    return TEAM_SLUG_TO_ABBR.get(m.group(1), "")


def parse_page(source_type: str, source_url: str, html: str) -> list[RawTransaction]:
    soup = BeautifulSoup(html, "html.parser")
    tbody = soup.find("tbody")
    if not tbody:
        return []

    rows: list[RawTransaction] = []
    for tr in tbody.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 6:
            continue

        from_team = extract_team_abbr(tds[0])
        to_team = extract_team_abbr(tds[1])
        date_text = tds[2].get_text(" ", strip=True)
        player = tds[3].get_text(" ", strip=True)
        txn_text = tds[5].get_text(" ", strip=True)

        if not player or not txn_text or not date_text:
            continue

        rows.append(
            RawTransaction(
                source_type=source_type,
                from_team=from_team,
                to_team=to_team,
                date_text=date_text,
                player=player,
                txn_text=txn_text,
                source_url=source_url,
            )
        )

    return rows


def to_iso_date(value: str, season: int) -> str:
    dt = datetime.strptime(f"{season}/{value}", "%Y/%m/%d")
    return dt.date().isoformat()


def normalize_type(raw: RawTransaction) -> str:
    text = raw.txn_text.lower()

    if "activated" in text or "designated for return" in text:
        return "Activated"
    if "injured reserve" in text or "placed on ir" in text:
        return "PlacedOnIR"

    if raw.source_type == "signings":
        if any(k in text for k in ("re-sign", "re signed", "extension", "contract extension")):
            return "Re-signed"
        return "Signed"

    if raw.source_type == "releases":
        if any(k in text for k in ("waived", "waiver", "waived/injured", "waived injured")):
            return "Waived"
        return "Released"

    if raw.source_type == "trades":
        return "Traded"

    return "Signed"


def should_exclude(raw: RawTransaction) -> bool:
    text = raw.txn_text.lower()
    return any(k in text for k in EXCLUDE_KEYWORDS)


def select_team(raw: RawTransaction) -> str:
    if raw.source_type == "releases":
        return raw.from_team or raw.to_team
    if raw.source_type == "trades":
        return raw.to_team or raw.from_team
    return raw.to_team or raw.from_team


def scrape_transactions(season: int, max_page: int) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    # NFL exposes 2026 player exits under "terminations" and "waivers".
    source_jobs = [
        ("signings", "signings"),
        ("releases", "releases"),
        ("releases", "terminations"),
        ("releases", "waivers"),
        ("trades", "trades"),
    ]

    for source_type, source_path in source_jobs:
        for month in range(1, 13):
            seen_hashes: set[str] = set()
            for page in range(1, max_page + 1):
                url = f"https://www.nfl.com/transactions/league/{source_path}/{season}/{month}?page={page}"
                try:
                    html = fetch_html(url)
                except HTTPError as exc:
                    if exc.code == 404:
                        break
                    raise
                except URLError:
                    break

                digest = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()
                if digest in seen_hashes:
                    break
                seen_hashes.add(digest)

                parsed = parse_page(source_type, url, html)
                if not parsed:
                    break

                for raw in parsed:
                    if should_exclude(raw):
                        continue

                    team = select_team(raw)
                    if team not in TEAM_SLUG_TO_ABBR.values():
                        continue

                    try:
                        iso_date = to_iso_date(raw.date_text, season)
                    except ValueError:
                        continue

                    out.append(
                        {
                            "team": team,
                            "player": raw.player,
                            "transaction_type": normalize_type(raw),
                            "transaction_date": iso_date,
                            "notes": raw.txn_text,
                            "source_url": raw.source_url,
                        }
                    )

    return out


def dedupe(rows: list[dict[str, str]], imported_at: str) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    unique: list[dict[str, str]] = []

    for row in rows:
        key = (
            row["team"],
            row["player"],
            row["transaction_type"],
            row["transaction_date"],
            row["source_url"],
        )
        if key in seen:
            continue
        seen.add(key)

        out = {
            "team": row["team"],
            "player": row["player"],
            "transaction_type": row["transaction_type"],
            "transaction_date": row["transaction_date"],
            "notes": row["notes"],
            "source_url": row["source_url"],
            "import_method": "scraped",
            "imported_at": imported_at,
        }
        unique.append(out)

    unique.sort(key=lambda r: (r["transaction_date"], r["team"], r["player"], r["transaction_type"]))
    return unique


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    args = parse_args()
    rows = scrape_transactions(args.season, args.max_page)
    unique_rows = dedupe(rows, args.imported_at)
    write_csv(args.output, unique_rows)
    print(f"Wrote {len(unique_rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
