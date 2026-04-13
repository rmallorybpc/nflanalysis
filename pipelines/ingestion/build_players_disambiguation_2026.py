#!/usr/bin/env python3
"""Build disambiguation hints for 2026 unresolved players using NFL.com evidence.

Safety rules:
- Never synthesize or guess a PFR slug.
- Only keep `pfr_url_or_slug` when already present in prior template.
- Add auditable NFL.com references in `notes`.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


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
ABBR_TO_TEAM_SLUG = {abbr: slug for slug, abbr in TEAM_SLUG_TO_ABBR.items()}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build players metadata disambiguation template for 2026")
    p.add_argument(
        "--unresolved",
        type=Path,
        default=Path("data/raw/offseason/players_metadata_2026_unresolved.csv"),
    )
    p.add_argument(
        "--template",
        type=Path,
        default=Path("data/raw/offseason/players_metadata_2026_disambiguation_template.csv"),
    )
    return p.parse_args()


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def norm_name(name: str) -> str:
    s = (name or "").lower().strip()
    s = unescape(s)
    s = s.replace(".", "").replace(",", "").replace("'", "")
    s = s.replace("-", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def roster_url_for_team(team: str) -> str:
    slug = ABBR_TO_TEAM_SLUG.get(team, "")
    if not slug:
        return ""
    return f"https://www.nfl.com/teams/{slug}/roster"


def load_team_roster_index(teams: set[str]) -> tuple[dict[tuple[str, str], list[str]], dict[str, str]]:
    by_team_name: dict[tuple[str, str], list[str]] = {}
    roster_urls: dict[str, str] = {}
    for team in sorted(teams):
        rurl = roster_url_for_team(team)
        roster_urls[team] = rurl
        if not rurl:
            continue
        try:
            html = fetch(rurl)
        except (HTTPError, URLError):
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select('a.nfl-o-roster__player-name[href^="/players/"]'):
            href = (a.get("href") or "").strip()
            name = a.get_text(" ", strip=True)
            if not href or not name:
                continue
            profile_url = f"https://www.nfl.com{href if href.startswith('/') else '/' + href}"
            key = (team, norm_name(name))
            by_team_name.setdefault(key, []).append(profile_url)
    return by_team_name, roster_urls


def load_global_roster_index() -> dict[str, list[str]]:
    by_name: dict[str, list[str]] = {}
    for team in sorted(ABBR_TO_TEAM_SLUG):
        rurl = roster_url_for_team(team)
        if not rurl:
            continue
        try:
            html = fetch(rurl)
        except (HTTPError, URLError):
            continue

        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select('a.nfl-o-roster__player-name[href^="/players/"]'):
            href = (a.get("href") or "").strip()
            name = a.get_text(" ", strip=True)
            if not href or not name:
                continue
            profile_url = f"https://www.nfl.com{href if href.startswith('/') else '/' + href}"
            key = norm_name(name)
            by_name.setdefault(key, []).append(profile_url)
    return by_name


def parse_profile_hints(html: str) -> tuple[str, str, str]:
    soup = BeautifulSoup(html, "html.parser")
    position = ""
    pos_el = soup.select_one("span.nfl-c-player-header__position")
    if pos_el:
        position = re.sub(r"\s+", " ", pos_el.get_text(" ", strip=True)).upper()

    birth_date = ""
    college = ""

    def iter_person_nodes(node: object) -> list[dict[str, object]]:
        found: list[dict[str, object]] = []
        if isinstance(node, dict):
            if str(node.get("@type", "")).lower() == "person":
                found.append(node)
            for v in node.values():
                found.extend(iter_person_nodes(v))
        elif isinstance(node, list):
            for item in node:
                found.extend(iter_person_nodes(item))
        return found

    for script in soup.select('script[type="application/ld+json"]'):
        raw = (script.string or "").strip()
        if not raw:
            continue
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError:
            continue
        nodes = doc if isinstance(doc, list) else [doc]
        for node in nodes:
            for person in iter_person_nodes(node):
                birth_date = str(person.get("birthDate") or "").strip()
                alumni = person.get("alumniOf")
                if isinstance(alumni, dict):
                    inner = alumni.get("alumniOf")
                    if isinstance(inner, dict):
                        college = str(inner.get("name") or "").strip()
                    else:
                        college = str(alumni.get("name") or "").strip()
                if birth_date or college:
                    break
            if birth_date or college:
                break
        if birth_date or college:
            break
    return position, college, birth_date


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    fields = ["player", "team", "pfr_url_or_slug", "position_hint", "college_hint", "dob_hint", "notes"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    args = parse_args()
    unresolved = read_rows(args.unresolved)
    existing = read_rows(args.template) if args.template.exists() else []

    existing_map = {(r.get("player", "").strip(), r.get("team", "").strip()): r for r in existing}
    team_set = {(r.get("team") or "").strip() for r in unresolved}
    by_team_name, roster_urls = load_team_roster_index(team_set)
    global_name_index = load_global_roster_index()
    profile_cache: dict[str, tuple[str, str, str]] = {}

    out: list[dict[str, str]] = []
    for row in unresolved:
        player = (row.get("player") or "").strip()
        team = (row.get("team") or "").strip()
        key = (player, team)

        prior = existing_map.get(key, {})
        prior_slug = (prior.get("pfr_url_or_slug") or "").strip()
        if prior_slug:
            out.append(
                {
                    "player": player,
                    "team": team,
                    "pfr_url_or_slug": prior_slug,
                    "position_hint": (prior.get("position_hint") or "").strip(),
                    "college_hint": (prior.get("college_hint") or "").strip(),
                    "dob_hint": (prior.get("dob_hint") or "").strip(),
                    "notes": (prior.get("notes") or "").strip() or "manual_or_prior_resolution",
                }
            )
            continue

        rurl = roster_urls.get(team, "")
        if not rurl:
            out.append(
                {
                    "player": player,
                    "team": team,
                    "pfr_url_or_slug": "",
                    "position_hint": "",
                    "college_hint": "",
                    "dob_hint": "",
                    "notes": "insufficient_evidence:unknown_team_slug",
                }
            )
            continue

        candidates = by_team_name.get((team, norm_name(player)), [])
        if not candidates:
            global_candidates = sorted(set(global_name_index.get(norm_name(player), [])))
            if len(global_candidates) == 1:
                profile_url = global_candidates[0]
                if profile_url not in profile_cache:
                    try:
                        profile_html = fetch(profile_url)
                        profile_cache[profile_url] = parse_profile_hints(profile_html)
                    except (HTTPError, URLError):
                        profile_cache[profile_url] = ("", "", "")
                pos, college, dob = profile_cache[profile_url]
                if not pos and not college and not dob:
                    note = f"insufficient_evidence:nfl_profile_parse_failed:{profile_url}"
                else:
                    note = f"matched_nfl_profile_global_roster:{profile_url}"
                out.append(
                    {
                        "player": player,
                        "team": team,
                        "pfr_url_or_slug": "",
                        "position_hint": pos,
                        "college_hint": college,
                        "dob_hint": dob,
                        "notes": note,
                    }
                )
                continue

            if len(global_candidates) > 1:
                out.append(
                    {
                        "player": player,
                        "team": team,
                        "pfr_url_or_slug": "",
                        "position_hint": "",
                        "college_hint": "",
                        "dob_hint": "",
                        "notes": f"ambiguous_global_nfl_roster_match:{len(global_candidates)}",
                    }
                )
                continue

            out.append(
                {
                    "player": player,
                    "team": team,
                    "pfr_url_or_slug": "",
                    "position_hint": "",
                    "college_hint": "",
                    "dob_hint": "",
                    "notes": f"no_nfl_team_roster_match:{rurl}",
                }
            )
            continue

        unique_urls = sorted(set(candidates))
        if len(unique_urls) != 1:
            out.append(
                {
                    "player": player,
                    "team": team,
                    "pfr_url_or_slug": "",
                    "position_hint": "",
                    "college_hint": "",
                    "dob_hint": "",
                    "notes": f"ambiguous_nfl_team_roster_match:{len(unique_urls)}:{rurl}",
                }
            )
            continue

        profile_url = unique_urls[0]
        if profile_url not in profile_cache:
            try:
                profile_html = fetch(profile_url)
                profile_cache[profile_url] = parse_profile_hints(profile_html)
            except (HTTPError, URLError):
                profile_cache[profile_url] = ("", "", "")
        pos, college, dob = profile_cache[profile_url]
        if not pos and not college and not dob:
            note = f"insufficient_evidence:nfl_profile_parse_failed:{profile_url}"
        else:
            note = f"matched_nfl_profile:{profile_url}"
        out.append(
            {
                "player": player,
                "team": team,
                "pfr_url_or_slug": "",
                "position_hint": pos,
                "college_hint": college,
                "dob_hint": dob,
                "notes": note,
            }
        )

    # Keep row parity with unresolved input.
    if len(out) != len(unresolved):
        raise RuntimeError("row parity failed")

    write_rows(args.template, out)
    print(f"rows={len(out)}")


if __name__ == "__main__":
    main()
