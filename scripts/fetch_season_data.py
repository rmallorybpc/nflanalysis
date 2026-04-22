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

PLAYERS_FIELDS = [
    "player",
    "position",
    "team",
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


def build_players_metadata(season: int, imported_at: str) -> list[dict[str, str]]:
    trades_url = "https://github.com/nflverse/nflverse-data/releases/download/trades/trades.csv"

    roster_idx = load_roster_index(season)

    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []

    for row in fetch_pfr_free_agency_rows(season, imported_at):
        key = (row["player"].lower(), row["team"])
        if key in seen:
            continue
        seen.add(key)
        out.append(row)

    reader, used_url, headers, _size = csv_rows_from_url(trades_url, "transactions")
    if reader is None:
        out.sort(key=lambda r: (r["team"], r["player"]))
        return out

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

        out.append(
            {
                "player": player,
                "position": position,
                "team": team,
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

    out.sort(key=lambda r: (r["team"], r["player"]))
    return out


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

    wins = {team: 0.0 for team in NFL_TEAMS}
    games_played = {team: 0 for team in NFL_TEAMS}

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
            kept += 1

            if away_score > home_score:
                wins[away] += 1.0
            elif home_score > away_score:
                wins[home] += 1.0
            else:
                wins[away] += 0.5
                wins[home] += 0.5

        print(f"[INFO] games: {used_url} fetched_rows={fetched} kept_rows={kept}")
        used = used_url
        break

    if not used:
        print("[WARN] games: no usable source. Writing sparse win_totals output.")

    win_pct_values: list[float] = []
    rows: list[dict[str, str]] = []
    for team in NFL_TEAMS:
        gp = games_played.get(team, 0)
        wt = wins.get(team, 0.0)
        win_pct = (wt / gp) if gp else 0.0
        win_pct_values.append(win_pct)
        rows.append(
            {
                "team": team,
                "win_total": f"{wt:.1f}",
                "provider": "nflverse_games",
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


def maybe_write(path: Path, fields: list[str], rows: list[dict[str, str]], force: bool) -> bool:
    if path.exists() and not force:
        print(f"[WARN] {path} exists. Skipping write (use --force to overwrite).")
        return False
    write_csv(path, fields, rows)
    print(f"[WRITE] {path} rows={len(rows)}")
    return True


def main() -> None:
    args = parse_args()

    if args.season < 2022 or args.season > 2026:
        print(f"[WARN] season {args.season} is outside recommended range 2022-2026")

    imported_at = now_iso()
    output_dir = Path(args.output_dir)

    players_path = output_dir / f"players_metadata_{args.season}.csv"
    spending_path = output_dir / f"team_spending_otc_{args.season}.csv"
    wins_path = output_dir / f"win_totals_{args.season}.csv"

    print(f"[INFO] fetching season={args.season} output_dir={output_dir}")
    players = build_players_metadata(args.season, imported_at)
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

    maybe_write(players_path, PLAYERS_FIELDS, players, args.force)
    maybe_write(spending_path, TEAM_SPENDING_FIELDS, spending, args.force)
    maybe_write(wins_path, WIN_TOTALS_FIELDS, wins, args.force)


if __name__ == "__main__":
    main()
