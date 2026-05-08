#!/usr/bin/env python3
"""Fetch offseason raw tables for a requested NFL season.

# USAGE
# Step 1: Fetch raw data for a season
#   python3 scripts/fetch_season_data.py --season 2025
#
# Step 2: Run the ingestion pipeline (existing)
#   bash run_final.sh
#
# To fetch all historical seasons at once:
#   bash scripts/fetch_all_seasons.sh
"""

from __future__ import annotations

import argparse
import csv
import io
import gzip
import re
from html.parser import HTMLParser
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from urllib import error, request


CURRENT_SEASON = 2026
CONTRACTS_URL = "https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.csv.gz"
_CONTRACT_ROWS_CACHE: list[dict[str, str]] | None = None

PLAYERS_FIELDS = [
    "player",
    "position",
    "team",
    "from_team",
    "contract_aav",
    "contract_total",
    "contract_years",
    "age",
    "height",
    "weight",
    "experience",
    "college",
    "draft_year",
    "draft_round",
    "draft_pick",
    "pfr_slug",
    "source_url",
    "import_method",
    "imported_at",
]

TEAM_SPENDING_FIELDS = [
    "team",
    "total_fa_spending",
    "cap_space",
    "dead_money",
    "source_url",
    "import_method",
    "imported_at",
]

WIN_TOTALS_FIELDS = [
    "team",
    "wins",
    "losses",
    "ties",
    "win_pct",
    "point_diff_per_game",
    "games_played",
    "source",
    "win_total",
    "provider",
    "captured_at",
]

NFL_TEAMS = [
    "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
    "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
    "LV", "LAC", "LAR", "MIA", "MIN", "NE", "NO", "NYG",
    "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS",
]

TEAM_ALIASES = {
    "arizona": "ARI",
    "cardinals": "ARI",
    "atlanta": "ATL",
    "falcons": "ATL",
    "baltimore": "BAL",
    "ravens": "BAL",
    "buffalo": "BUF",
    "bills": "BUF",
    "carolina": "CAR",
    "panthers": "CAR",
    "chicago": "CHI",
    "bears": "CHI",
    "cincinnati": "CIN",
    "bengals": "CIN",
    "cleveland": "CLE",
    "browns": "CLE",
    "dallas": "DAL",
    "cowboys": "DAL",
    "denver": "DEN",
    "broncos": "DEN",
    "detroit": "DET",
    "lions": "DET",
    "green bay": "GB",
    "packers": "GB",
    "houston": "HOU",
    "texans": "HOU",
    "indianapolis": "IND",
    "colts": "IND",
    "jacksonville": "JAX",
    "jaguars": "JAX",
    "kansas city": "KC",
    "chiefs": "KC",
    "las vegas": "LV",
    "raiders": "LV",
    "los angeles chargers": "LAC",
    "chargers": "LAC",
    "los angeles rams": "LAR",
    "rams": "LAR",
    "miami": "MIA",
    "dolphins": "MIA",
    "minnesota": "MIN",
    "vikings": "MIN",
    "new england": "NE",
    "patriots": "NE",
    "new orleans": "NO",
    "saints": "NO",
    "new york giants": "NYG",
    "giants": "NYG",
    "new york jets": "NYJ",
    "jets": "NYJ",
    "philadelphia": "PHI",
    "eagles": "PHI",
    "pittsburgh": "PIT",
    "steelers": "PIT",
    "seattle": "SEA",
    "seahawks": "SEA",
    "san francisco": "SF",
    "49ers": "SF",
    "tampa bay": "TB",
    "buccaneers": "TB",
    "tennessee": "TEN",
    "titans": "TEN",
    "washington": "WAS",
    "commanders": "WAS",
}

TRANSACTION_TYPE_ALLOW = {
    "SIGNED_FA",
    "TRADED",
    "RELEASED",
    "SIGNED_PRACTICE_SQUAD",
}
TRANSACTION_TYPE_PLAYERS = {"SIGNED_FA", "TRADED"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch offseason source data for one NFL season")
    parser.add_argument("--season", required=True, type=int, help="Season year, e.g. 2025")
    parser.add_argument("--output-dir", default="data/raw/offseason/", help="Directory for output CSV files")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and validate only, do not write files")
    parser.add_argument("--force", action="store_true", help="Overwrite existing season files")
    parser.add_argument(
        "--spotrac",
        action="store_true",
        default=False,
        help="Fetch FA signing data from Spotrac (no extra dependencies required)",
    )
    return parser.parse_args()


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_team(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    up = raw.upper()
    if up in NFL_TEAMS:
        return up
    low = raw.lower()
    if low in TEAM_ALIASES:
        return TEAM_ALIASES[low]
    for key, team in TEAM_ALIASES.items():
        if key in low:
            return team
    return ""


def normalize_height(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    m = re.match(r"^(\d+)\D+(\d+)$", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    if text.isdigit() and len(text) in {2, 3}:
        if len(text) == 2:
            return f"{text[0]}-{text[1]}"
        return f"{text[:-1]}-{text[-1]}"
    return text


def parse_int(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except ValueError:
        return ""


def pfr_from_url(url: str) -> str:
    text = (url or "").strip()
    if not text:
        return ""
    m = re.search(r"/players/([A-Za-z])/([A-Za-z0-9]+)\.htm", text)
    if m:
        return m.group(2)
    return ""


def parse_float(value: str) -> float:
    text = (value or "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def csv_rows_from_url(url: str, source_name: str) -> tuple[Iterable[dict[str, str]] | None, str, str, int | None]:
    req = request.Request(url, headers={"User-Agent": "nflanalysis-fetch/1.0"})
    try:
        resp = request.urlopen(req, timeout=60)
    except error.HTTPError as exc:
        print(f"[WARN] {source_name}: {url} returned HTTP {exc.code}")
        return None, "", "", None
    except Exception as exc:  # pragma: no cover - network failures are environment dependent
        print(f"[WARN] {source_name}: failed to fetch {url}: {exc}")
        return None, "", "", None

    status = getattr(resp, "status", 200)
    if status != 200:
        print(f"[WARN] {source_name}: {url} returned non-200 status {status}")
        return None, "", "", None

    content_length = resp.headers.get("Content-Length")
    size = int(content_length) if content_length and content_length.isdigit() else None
    if size and size > 10 * 1024 * 1024:
        print(f"[INFO] {source_name}: streaming large CSV ({size} bytes)")

    if url.endswith(".csv.gz"):
        text_handle = io.TextIOWrapper(gzip.GzipFile(fileobj=resp), encoding="utf-8", newline="")
    else:
        text_handle = io.TextIOWrapper(resp, encoding="utf-8", newline="")

    reader = csv.DictReader(text_handle)
    return reader, url, ",".join(reader.fieldnames or []), size


def fetch_contracts(season: int) -> dict[str, dict[str, str]]:
    global _CONTRACT_ROWS_CACHE

    if _CONTRACT_ROWS_CACHE is None:
        reader, used_url, _headers, _size = csv_rows_from_url(CONTRACTS_URL, "contracts")
        if reader is None:
            print(f"[WARN] contracts: failed to fetch source at {CONTRACTS_URL}")
            _CONTRACT_ROWS_CACHE = []
        else:
            _CONTRACT_ROWS_CACHE = list(reader)

    by_name: dict[str, dict[str, str]] = {}
    kept = 0
    for row in _CONTRACT_ROWS_CACHE or []:
        year_signed = parse_int((row.get("year_signed") or "").strip())
        if not year_signed:
            continue

        years_raw = parse_int(row.get("years") or "")
        years_count = int(years_raw) if years_raw else 1
        contract_end_year = int(year_signed) + max(years_count, 1) - 1
        if not (int(year_signed) <= season <= contract_end_year):
            continue

        player_name = (row.get("player") or "").strip().lower()
        if not player_name:
            continue

        aav = parse_float(row.get("apy") or "")
        total_value = parse_float(row.get("value") or "")
        years = years_raw
        position = (row.get("position") or "").strip().upper()

        existing = by_name.get(player_name)
        if existing is None or aav > parse_float(existing.get("aav") or ""):
            by_name[player_name] = {
                "aav": str(int(round(aav))) if aav else "",
                "total_value": str(int(round(total_value))) if total_value else "",
                "years": years,
                "position": position,
            }
        kept += 1

    fetched = len(_CONTRACT_ROWS_CACHE or [])
    print(f"[INFO] contracts: {CONTRACTS_URL} fetched_rows={fetched} kept_for_{season}={kept}")
    return by_name


class PFRTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[dict[str, object]] = []
        self._table_stack: list[int] = []
        self._in_row = False
        self._in_cell = False
        self._cell_parts: list[str] = []
        self._current_row: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            attrs_map = {k: (v or "") for k, v in attrs}
            table_obj: dict[str, object] = {"id": attrs_map.get("id", ""), "rows": []}
            self.tables.append(table_obj)
            self._table_stack.append(len(self.tables) - 1)
            return

        if not self._table_stack:
            return

        if tag == "tr":
            self._in_row = True
            self._current_row = []
            return

        if self._in_row and tag in {"th", "td"}:
            self._in_cell = True
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            if self._table_stack:
                self._table_stack.pop()
            return

        if not self._table_stack:
            return

        if self._in_row and self._in_cell and tag in {"th", "td"}:
            cell = " ".join("".join(self._cell_parts).split()).strip()
            self._current_row.append(cell)
            self._in_cell = False
            self._cell_parts = []
            return

        if self._in_row and tag == "tr":
            if self._current_row:
                table_rows = self.tables[self._table_stack[-1]]["rows"]
                if isinstance(table_rows, list):
                    table_rows.append(self._current_row)
            self._in_row = False
            self._current_row = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)


def _header_index(headers: list[str], options: tuple[str, ...]) -> int:
    for idx, header in enumerate(headers):
        cleaned = re.sub(r"\s+", " ", header.strip().lower())
        if cleaned in options:
            return idx
    return -1


def parse_pfr_transactions_table(html: str) -> list[dict[str, str]] | None:
    parser = PFRTableParser()
    parser.feed(html)

    # Prefer the canonical transactions table id; if unavailable, try all parsed tables.
    candidates = [
        t for t in parser.tables
        if isinstance(t.get("id"), str) and t.get("id") == "transactions"
    ]
    if not candidates:
        candidates = parser.tables

    for table in candidates:
        rows = table.get("rows")
        if not isinstance(rows, list) or len(rows) < 2:
            continue

        header_row = next((r for r in rows if isinstance(r, list) and r), None)
        if not isinstance(header_row, list):
            continue
        headers = [str(h) for h in header_row]

        date_idx = _header_index(headers, ("date",))
        team_idx = _header_index(headers, ("team", "tm", "to"))
        tx_idx = _header_index(headers, ("transaction", "transaction description", "description", "type", "details", "detail"))
        player_idx = _header_index(headers, ("player", "name", "acquired"))

        if min(date_idx, team_idx, tx_idx, player_idx) < 0:
            continue

        parsed: list[dict[str, str]] = []
        header_found = False
        for row in rows:
            if not isinstance(row, list) or not row:
                continue
            if not header_found and row == header_row:
                header_found = True
                continue
            if len(row) <= max(date_idx, team_idx, tx_idx, player_idx):
                continue

            parsed.append(
                {
                    "date": row[date_idx].strip(),
                    "team": row[team_idx].strip(),
                    "transaction": row[tx_idx].strip(),
                    "player": row[player_idx].strip(),
                }
            )

        if parsed:
            return parsed

    return None


def fetch_pfr_free_agency_rows(season: int, imported_at: str) -> list[dict[str, str]]:
    url = f"https://www.pro-football-reference.com/years/{season}/transactions.htm"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; nflanalysis-research/1.0)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    req = request.Request(url, headers=headers)

    try:
        resp = request.urlopen(req, timeout=60)
    except error.HTTPError as exc:
        print(f"[WARN] pfr_transactions: {url} returned HTTP {exc.code}; continuing with trades-only")
        return []
    except Exception as exc:  # pragma: no cover - network failures are environment dependent
        print(f"[WARN] pfr_transactions: failed to fetch {url}: {exc}; continuing with trades-only")
        return []

    status = getattr(resp, "status", 200)
    if status != 200:
        print(f"[WARN] pfr_transactions: {url} returned non-200 status {status}; continuing with trades-only")
        return []

    html = io.TextIOWrapper(resp, encoding="utf-8", newline="").read()
    parsed = parse_pfr_transactions_table(html)
    if not parsed:
        print(f"[WARN] pfr_transactions: unable to parse transactions table from {url}; continuing with trades-only")
        return []

    fetched = len(parsed)
    kept = 0
    rows: list[dict[str, str]] = []
    for row in parsed:
        description = (row.get("transaction") or "").strip()
        desc_lower = description.lower()
        if "signed" not in desc_lower:
            continue
        if "practice squad" in desc_lower or "reserve" in desc_lower:
            continue

        player = (row.get("player") or "").strip()
        team = normalize_team(row.get("team", ""))
        if not player or not team:
            continue

        rows.append(
            {
                "player": player,
                "position": "",
                "team": team,
                "from_team": "",
                "age": "",
                "height": "",
                "weight": "",
                "experience": "",
                "college": "",
                "draft_year": "",
                "draft_round": "",
                "draft_pick": "",
                "pfr_slug": "",
                "source_url": url,
                "import_method": "pfr_transactions",
                "imported_at": imported_at,
            }
        )
        kept += 1

    print(f"[INFO] pfr_transactions: {url} fetched_rows={fetched} kept_rows={kept}")
    return rows


def fetch_spotrac_fa(season: int) -> list[dict[str, str]]:
    """
    Fetch all signed free agents from Spotrac for the given season.
    Uses urllib.request + html.parser - no third-party libraries.
    Returns list of dicts matching the players_metadata schema.
    """
    import urllib.request
    from html.parser import HTMLParser

    url = f"https://www.spotrac.com/nfl/free-agents/signed/_/year/{season}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; nflanalysis-research/1.0)",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"[WARN] spotrac_fa: failed to fetch {url}: {exc}")
        return []

    class SpotracParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.rows: list[dict[str, object]] = []
            self._in_tbody = False
            self._in_tr = False
            self._in_td = False
            self._in_span_d_none = False
            self._in_link = False
            self._current_row: list[str] = []
            self._current_td = ""
            self._current_spans: list[str] = []
            self._current_link = ""

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            attrs_dict = {k: (v or "") for k, v in attrs}
            if tag == "tbody":
                self._in_tbody = True
            elif tag == "tr" and self._in_tbody:
                self._in_tr = True
                self._current_row = []
                self._current_spans = []
                self._current_link = ""
            elif tag == "td" and self._in_tr:
                self._in_td = True
                self._current_td = ""
            elif tag == "span" and self._in_td:
                classes = attrs_dict.get("class", "")
                if "d-none" in classes:
                    self._in_span_d_none = True
            elif tag == "a" and self._in_td:
                classes = attrs_dict.get("class", "")
                if "link" in classes:
                    self._in_link = True

        def handle_endtag(self, tag: str) -> None:
            if tag == "tbody":
                self._in_tbody = False
            elif tag == "tr" and self._in_tr:
                self._in_tr = False
                if self._current_link:
                    from_team = ""
                    to_team = ""
                    if len(self._current_spans) >= 2:
                        from_team = self._current_spans[0]
                        to_team = self._current_spans[1]
                    elif len(self._current_spans) == 1:
                        from_team = self._current_spans[0]
                        to_team = self._current_spans[0]
                    elif len(self._current_row) > 4:
                        team_fallback = normalize_team(self._current_row[4])
                        if team_fallback:
                            from_team = team_fallback
                            to_team = team_fallback

                    if to_team:
                        self.rows.append(
                            {
                                "from_team": from_team,
                                "to_team": to_team,
                                "player": self._current_link,
                                "tds": list(self._current_row),
                            }
                        )
            elif tag == "td" and self._in_td:
                self._in_td = False
                self._current_row.append(self._current_td.strip())
                self._current_td = ""
            elif tag == "span" and self._in_span_d_none:
                self._in_span_d_none = False
            elif tag == "a" and self._in_link:
                self._in_link = False

        def handle_data(self, data: str) -> None:
            if self._in_span_d_none:
                text = data.strip()
                if text:
                    self._current_spans.append(text)
            elif self._in_link:
                text = data.strip()
                if text:
                    self._current_link += text
            elif self._in_td:
                self._current_td += data

    parser = SpotracParser()
    parser.feed(html)

    def parse_dollars(val: str) -> str:
        """Convert '$26,000,000' to integer string, empty if unparseable."""
        try:
            return str(int(val.replace("$", "").replace(",", "").strip()))
        except (ValueError, AttributeError):
            return ""

    def parse_years_to_int(val: str) -> int:
        text = (val or "").strip().lower()
        if not text:
            return 0
        m = re.search(r"(\d+)", text)
        if not m:
            return 0
        try:
            return int(m.group(1))
        except ValueError:
            return 0

    imported_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    results: list[dict[str, str]] = []
    for row in parser.rows:
        tds = row.get("tds", [])
        if not isinstance(tds, list):
            continue

        # td indices: [0]=from icon, [1]=arrow, [2]=to icon,
        # [3]=name, [4]=position, [5]=years, [6]=total,
        # [7]=aav, [8]=guaranteed, [9]=gtd@sign
        position = tds[4] if len(tds) > 4 else ""
        years = tds[5] if len(tds) > 5 else ""
        total_value = parse_dollars(tds[6]) if len(tds) > 6 else ""
        aav = parse_dollars(tds[7]) if len(tds) > 7 else ""

        # Alternate Spotrac table format:
        # [0]=player [1]=pos [2]=age [3]=experience [4]=team [5]=aav
        if len(tds) <= 8:
            position = tds[1] if len(tds) > 1 else position
            years = tds[3] if len(tds) > 3 else years
            total_value = ""
            aav = parse_dollars(tds[5]) if len(tds) > 5 else aav

        if not aav and total_value:
            years_count = parse_years_to_int(years)
            if years_count > 0:
                try:
                    aav = str(int(round(int(total_value) / years_count)))
                except ValueError:
                    aav = ""
        if not aav:
            aav = "0"

        from_team = normalize_team(str(row.get("from_team", "")))
        to_team = normalize_team(str(row.get("to_team", "")))
        if to_team and not from_team:
            from_team = to_team
        player = str(row.get("player", "")).strip()

        if not player or not to_team:
            continue

        results.append(
            {
                "player": player,
                "position": position,
                "team": to_team,
                "from_team": from_team,
                "age": "",
                "height": "",
                "weight": "",
                "experience": "",
                "college": "",
                "draft_year": "",
                "draft_round": "",
                "draft_pick": "",
                "pfr_slug": "",
                "contract_years": years,
                "contract_total": total_value,
                "contract_aav": aav,
                "source_url": url,
                "import_method": "spotrac_fa_scraper",
                "imported_at": imported_at,
            }
        )

    print(
        f"[INFO] spotrac_fa: {url} "
        f"fetched_rows={len(parser.rows)} "
        f"kept_rows={len(results)}"
    )
    return results


def load_roster_index(season: int) -> dict[str, dict[str, str]]:
    urls = [
        f"https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{season}.csv",
        "https://raw.githubusercontent.com/nflverse/nfldata/master/data/rosters.csv",
    ]

    for url in urls:
        reader, used_url, _headers, _size = csv_rows_from_url(url, "rosters")
        if reader is None:
            continue

        idx: dict[str, dict[str, str]] = {}
        fetched = 0
        kept = 0
        for row in reader:
            fetched += 1
            row_season = parse_int(row.get("season", ""))
            if row_season and int(row_season) != season:
                continue
            pid = (row.get("playerid") or row.get("pfr_id") or "").strip()
            if not pid:
                continue
            kept += 1
            idx[pid] = {
                "position": (row.get("position") or "").strip().upper(),
                "experience": (row.get("years") or row.get("years_exp") or "").strip(),
            }
        print(f"[INFO] rosters: {used_url} fetched_rows={fetched} kept_rows={kept}")
        return idx

    return {}


def build_players_metadata(season: int, imported_at: str, use_spotrac: bool = False) -> list[dict[str, str]]:
    trades_url = "https://github.com/nflverse/nflverse-data/releases/download/trades/trades.csv"

    roster_idx = load_roster_index(season)
    contracts_by_name = fetch_contracts(season)

    seen: set[tuple[str, str]] = set()
    nflverse_rows: list[dict[str, str]] = []

    if not use_spotrac:
        for row in fetch_pfr_free_agency_rows(season, imported_at):
            contract = contracts_by_name.get((row.get("player") or "").strip().lower(), {})
            key = (row["player"].lower(), row["team"])
            if key in seen:
                continue
            seen.add(key)
            row["contract_aav"] = contract.get("aav", "")
            row["contract_total"] = contract.get("total_value", "")
            row["contract_years"] = contract.get("years", "")
            nflverse_rows.append(row)

    reader, used_url, headers, _size = csv_rows_from_url(trades_url, "transactions")
    if reader is None:
        nflverse_rows.sort(key=lambda r: (r["team"], r["player"]))
        return nflverse_rows

    fetched = 0
    kept_scope = 0
    kept_output = 0

    header_set = {h.strip() for h in headers.split(",") if h.strip()}
    uses_trade_fallback = "trade_id" in header_set and "pfr_name" in header_set

    for row in reader:
        fetched += 1
        row_season = parse_int(row.get("season", ""))
        if not row_season or int(row_season) != season:
            continue

        if uses_trade_fallback:
            tx_type = "TRADED"
            player = (row.get("pfr_name") or "").strip()
            team = normalize_team(row.get("received", ""))
            from_team = normalize_team(row.get("gave", ""))
            position = ""
            pfr_slug = (row.get("pfr_id") or "").strip()
            source_url = used_url
            experience = ""
        else:
            tx_type = (row.get("transaction_type") or "").strip().upper()
            if tx_type not in TRANSACTION_TYPE_ALLOW:
                continue
            if tx_type != "TRADED":
                continue
            kept_scope += 1
            player = (row.get("player") or row.get("name") or "").strip()
            team = normalize_team(row.get("team", ""))
            from_team = normalize_team(
                row.get("trade_from_team") or row.get("from_team") or row.get("gave") or ""
            )
            position = (row.get("position") or "").strip().upper()
            pfr_slug = (row.get("pfr_id") or row.get("pfr_slug") or "").strip()
            source_url = (row.get("source_url") or used_url).strip()
            experience = ""

        if tx_type not in TRANSACTION_TYPE_PLAYERS:
            continue

        if not player:
            continue

        key = (player.lower(), team)
        if key in seen:
            continue
        seen.add(key)

        if pfr_slug in roster_idx:
            roster = roster_idx[pfr_slug]
            if not position:
                position = roster.get("position", "")
            if not experience:
                experience = roster.get("experience", "")

        if uses_trade_fallback:
            kept_scope += 1

        nflverse_rows.append(
            {
                "player": player,
                "position": position,
                "team": team,
                "from_team": from_team,
                "contract_aav": contracts_by_name.get(player.lower(), {}).get("aav", ""),
                "contract_total": contracts_by_name.get(player.lower(), {}).get("total_value", ""),
                "contract_years": contracts_by_name.get(player.lower(), {}).get("years", ""),
                "age": "",
                "height": "",
                "weight": "",
                "experience": experience,
                "college": "",
                "draft_year": "",
                "draft_round": "",
                "draft_pick": "",
                "pfr_slug": pfr_slug,
                "source_url": source_url,
                "import_method": "nflverse_trades_fallback" if uses_trade_fallback else "nflverse_transactions",
                "imported_at": imported_at,
            }
        )
        kept_output += 1

    print(
        f"[INFO] transactions: {used_url} fetched_rows={fetched} "
        f"rows_kept_scope={kept_scope} rows_kept_output={kept_output}"
    )

    if use_spotrac:
        spotrac_rows = fetch_spotrac_fa(season)
        merged: list[dict[str, str]] = []
        dedupe_seen: set[tuple[str, str]] = set()
        for row in nflverse_rows + spotrac_rows:
            key = (
                (row.get("player", "")).strip().lower(),
                (row.get("team", "")).strip().upper(),
            )
            if key in dedupe_seen:
                continue
            dedupe_seen.add(key)
            merged.append(row)
        print(
            f"[INFO] merged: trades={len(nflverse_rows)} "
            f"free_agency={len(spotrac_rows)} total={len(merged)}"
        )
        merged.sort(key=lambda r: (r["team"], r["player"]))
        return merged

    nflverse_rows.sort(key=lambda r: (r["team"], r["player"]))
    return nflverse_rows


def build_team_spending(season: int, imported_at: str) -> list[dict[str, str]]:
    contracts_url = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/contracts.csv"
    fallback_url = "https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.csv.gz"

    totals = {team: 0.0 for team in NFL_TEAMS}
    used_url = ""
    import_method = "empty_fallback"

    for url in (contracts_url, fallback_url):
        reader, ok_url, _headers, _size = csv_rows_from_url(url, "contracts")
        if reader is None:
            continue

        fetched = 0
        kept = 0
        for row in reader:
            fetched += 1
            year_signed = parse_int(row.get("year_signed") or row.get("season") or "")
            if not year_signed or int(year_signed) != season:
                continue

            team = normalize_team(row.get("team", ""))
            if not team:
                continue

            value = row.get("value") or row.get("apy") or ""
            amount = 0.0
            try:
                amount = float((value or "").strip()) if value else 0.0
            except ValueError:
                amount = 0.0

            totals[team] += amount
            kept += 1

        print(f"[INFO] contracts: {ok_url} fetched_rows={fetched} kept_rows={kept}")
        used_url = ok_url
        import_method = "nflverse_contracts"
        break

    if not used_url:
        print("[WARN] contracts: no usable source. Writing sparse team_spending output.")

    rows: list[dict[str, str]] = []
    for team in NFL_TEAMS:
        total = totals.get(team, 0.0)
        rows.append(
            {
                "team": team,
                "total_fa_spending": str(int(round(total))) if total > 0 else "",
                "cap_space": "",
                "dead_money": "",
                "source_url": used_url or fallback_url,
                "import_method": import_method,
                "imported_at": imported_at,
            }
        )

    return rows


def build_win_totals(season: int, imported_at: str) -> tuple[list[dict[str, str]], list[float]]:
    games_urls = [
        "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
        "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv",
    ]

    wins = {team: 0 for team in NFL_TEAMS}
    losses = {team: 0 for team in NFL_TEAMS}
    ties = {team: 0 for team in NFL_TEAMS}
    games_played = {team: 0 for team in NFL_TEAMS}
    point_diff_sum = {team: 0.0 for team in NFL_TEAMS}

    used = ""
    for url in games_urls:
        reader, used_url, _headers, _size = csv_rows_from_url(url, "games")
        if reader is None:
            continue

        fetched = 0
        kept = 0
        for row in reader:
            fetched += 1
            row_season = parse_int(row.get("season", ""))
            if not row_season or int(row_season) != season:
                continue
            if (row.get("game_type") or "").strip().upper() != "REG":
                continue

            away = normalize_team(row.get("away_team", ""))
            home = normalize_team(row.get("home_team", ""))
            if away not in wins or home not in wins:
                continue

            try:
                away_score = float((row.get("away_score") or "").strip())
                home_score = float((row.get("home_score") or "").strip())
            except ValueError:
                continue

            games_played[away] += 1
            games_played[home] += 1
            point_diff_sum[away] += away_score - home_score
            point_diff_sum[home] += home_score - away_score
            kept += 1

            if away_score > home_score:
                wins[away] += 1
                losses[home] += 1
            elif home_score > away_score:
                wins[home] += 1
                losses[away] += 1
            else:
                ties[away] += 1
                ties[home] += 1

        print(f"[INFO] games: {used_url} fetched_rows={fetched} kept_rows={kept}")
        used = used_url
        break

    if not used:
        print("[WARN] games: no usable source. Writing sparse win_totals output.")

    is_historical = season < CURRENT_SEASON
    source_value = "nflverse_games_actual" if is_historical else "nflverse_games_projected"
    provider_value = "nflverse_games_actual" if is_historical else "nflverse_games"

    win_pct_values: list[float] = []
    rows: list[dict[str, str]] = []
    for team in NFL_TEAMS:
        gp = games_played.get(team, 0)
        w = wins.get(team, 0)
        l = losses.get(team, 0)
        t = ties.get(team, 0)
        wt = float(w) + 0.5 * float(t)
        win_pct = (wt / gp) if gp else 0.0
        point_diff_per_game = (point_diff_sum.get(team, 0.0) / gp) if gp else 0.0
        win_pct_values.append(win_pct)
        rows.append(
            {
                "team": team,
                "wins": str(w),
                "losses": str(l),
                "ties": str(t),
                "win_pct": f"{win_pct:.4f}",
                "point_diff_per_game": f"{point_diff_per_game:.4f}",
                "games_played": str(gp),
                "source": source_value,
                "win_total": f"{wt:.1f}",
                "provider": provider_value,
                "captured_at": imported_at,
            }
        )

    return rows, win_pct_values


def check_columns(rows: list[dict[str, str]], required: list[str]) -> bool:
    if not rows:
        return True
    keys = set(rows[0].keys())
    return keys == set(required)


def print_validation(players: list[dict[str, str]], spending: list[dict[str, str]], wins: list[dict[str, str]], win_pcts: list[float]) -> None:
    print("[VALIDATION] players_metadata rows>=10:", "PASS" if len(players) >= 10 else "FAIL")
    print(
        "[VALIDATION] players_metadata required columns:",
        "PASS" if check_columns(players, PLAYERS_FIELDS) else "FAIL",
    )

    missing_name_and_source = sum(1 for r in players if not (r.get("player", "").strip() or r.get("source_url", "").strip()))
    print(
        "[VALIDATION] players_metadata no row missing both player and source_url:",
        "PASS" if missing_name_and_source == 0 else "FAIL",
    )

    print("[VALIDATION] team_spending_otc rows==32:", "PASS" if len(spending) == 32 else "FAIL")
    print(
        "[VALIDATION] team_spending_otc required columns:",
        "PASS" if check_columns(spending, TEAM_SPENDING_FIELDS) else "FAIL",
    )

    in_range = all(0.0 <= x <= 1.0 for x in win_pcts)
    print("[VALIDATION] win_totals rows==32:", "PASS" if len(wins) == 32 else "FAIL")
    print("[VALIDATION] derived win_pct between 0.0 and 1.0:", "PASS" if in_range else "FAIL")


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_manual_corrections(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("import_method") or "").strip() != "manual_correction":
                continue
            normalized = {field: (row.get(field) or "").strip() for field in PLAYERS_FIELDS}
            rows.append(normalized)
    return rows


def merge_manual_corrections(
    fetched_rows: list[dict[str, str]],
    manual_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    def key(row: dict[str, str]) -> tuple[str, str, str]:
        return (
            (row.get("player") or "").strip().lower(),
            (row.get("team") or "").strip().upper(),
            (row.get("from_team") or "").strip().upper(),
        )

    merged: dict[tuple[str, str, str], dict[str, str]] = {
        key({field: (row.get(field) or "") for field in PLAYERS_FIELDS}): {
            field: (row.get(field) or "") for field in PLAYERS_FIELDS
        }
        for row in fetched_rows
    }

    for row in manual_rows:
        merged[key(row)] = {field: (row.get(field) or "") for field in PLAYERS_FIELDS}

    out = list(merged.values())
    out.sort(key=lambda r: ((r.get("team") or ""), (r.get("player") or "")))
    return out


def maybe_write(path: Path, fields: list[str], rows: list[dict[str, str]], force: bool) -> bool:
    if path.exists() and not force:
        print(f"[WARN] {path} exists. Skipping write (use --force to overwrite).")
        return False
    write_csv(path, fields, rows)
    print(f"[WRITE] {path} rows={len(rows)}")
    return True


def _apply_blocklist_to_metadata(
    output_path: Path,
    blocklist_path: Path,
    season: int,
) -> int:
    """
    Remove rows from players_metadata where the player+team+season
    combination matches a blocklist entry. Returns count removed.
    """
    if not blocklist_path.exists():
        return 0

    with open(blocklist_path, newline="", encoding="utf-8") as f:
        blocked = [
            (r["player_name"].strip().lower(), r["team"].strip().upper())
            for r in csv.DictReader(f)
            if r.get("season", "").strip() == str(season)
        ]

    if not blocked:
        return 0

    with open(output_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    headers = list(rows[0].keys()) if rows else []
    clean = []
    removed = 0
    for row in rows:
        name = row.get("player", "").strip().lower()
        team = row.get("team", "").strip().upper()
        if any(name == b_name and (b_team == "" or team == b_team) for b_name, b_team in blocked):
            print(f"[BLOCKLIST] Removed from metadata: {row.get('player')} team={team} season={season}")
            removed += 1
        else:
            clean.append(row)

    if removed > 0:
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(clean)

    return removed


def main() -> None:
    args = parse_args()

    if args.season < 2022 or args.season > 2026:
        print(f"[WARN] season {args.season} is outside recommended range 2022-2026")

    imported_at = now_iso()
    output_dir = Path(args.output_dir)

    players_path = output_dir / f"players_metadata_{args.season}.csv"
    spending_path = output_dir / f"team_spending_otc_{args.season}.csv"
    wins_path = output_dir / f"win_totals_{args.season}.csv"

    manual_rows: list[dict[str, str]] = []
    if args.force:
        manual_rows = load_manual_corrections(players_path)
        if manual_rows:
            print(f"[INFO] preserving manual_correction rows from existing file: {len(manual_rows)}")

    print(f"[INFO] fetching season={args.season} output_dir={output_dir}")
    players = build_players_metadata(args.season, imported_at, use_spotrac=args.spotrac)
    if manual_rows:
        players = merge_manual_corrections(players, manual_rows)
        print(f"[INFO] reapplied manual_correction rows after fetch: {len(manual_rows)}")
    spending = build_team_spending(args.season, imported_at)
    wins, win_pcts = build_win_totals(args.season, imported_at)

    print(
        f"[INFO] row counts players_metadata={len(players)} "
        f"team_spending_otc={len(spending)} win_totals={len(wins)}"
    )
    print_validation(players, spending, wins, win_pcts)

    if args.dry_run:
        print("[INFO] dry-run mode enabled; no files written")
        return

    wrote_players = maybe_write(players_path, PLAYERS_FIELDS, players, args.force)
    if wrote_players:
        removed = _apply_blocklist_to_metadata(
            output_path=Path(f"data/raw/offseason/players_metadata_{args.season}.csv"),
            blocklist_path=Path("data/raw/offseason/player_blocklist.csv"),
            season=args.season,
        )
        if removed:
            print(f"[BLOCKLIST] Removed {removed} rows from players_metadata_{args.season}.csv")
    maybe_write(spending_path, TEAM_SPENDING_FIELDS, spending, args.force)
    maybe_write(wins_path, WIN_TOTALS_FIELDS, wins, args.force)


if __name__ == "__main__":
    main()
