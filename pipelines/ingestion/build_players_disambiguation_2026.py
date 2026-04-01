#!/usr/bin/env python3
"""Build disambiguation hints for 2026 unresolved players using PFR-only identity checks.

This script is conservative by design:
- Fills a row only when a name maps to exactly one PFR player slug.
- Leaves rows blank with reason codes when no unique identity is available.
"""

from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


@dataclass(frozen=True)
class Candidate:
    name: str
    slug: str
    url: str


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
    s = s.replace(".", "").replace(",", "").replace("'", "")
    s = re.sub(r"\s+", " ", s)
    return s


def load_pfr_index() -> dict[str, list[Candidate]]:
    by_name: dict[str, list[Candidate]] = {}
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        html = fetch(f"https://www.pro-football-reference.com/players/{ch}/")
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select('div#div_players p a[href^="/players/"]'):
            href = a.get("href", "")
            m = re.match(r"/players/[A-Z]/([A-Za-z0-9]+)\.htm", href)
            if not m:
                continue
            name = a.get_text(" ", strip=True)
            if not name:
                continue
            slug = m.group(1)
            url = f"https://www.pro-football-reference.com/players/{slug[0]}/{slug}.htm"
            key = norm_name(name)
            by_name.setdefault(key, []).append(Candidate(name=name, slug=slug, url=url))
    return by_name


def parse_player_profile(url: str) -> tuple[str, str, str]:
    html = fetch(url)
    soup = BeautifulSoup(html, "html.parser")

    txt = soup.get_text(" ", strip=True)
    pos = ""
    m_pos = re.search(r"Position:\s*([A-Za-z/ ]+)", txt)
    if m_pos:
        pos = m_pos.group(1).split("/")[0].split(" and ")[0].split()[0].upper()

    college = ""
    c = soup.select_one('[data-stat="college"]')
    if c:
        college = c.get_text(" ", strip=True)

    dob = ""
    b = soup.select_one("span#necro-birth")
    if b and b.get("data-birth"):
        dob = (b.get("data-birth") or "").strip()

    return pos, college, dob


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

    pfr_blocked = False
    try:
        by_name = load_pfr_index()
    except (HTTPError, URLError):
        by_name = {}
        pfr_blocked = True

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

        if pfr_blocked:
            out.append(
                {
                    "player": player,
                    "team": team,
                    "pfr_url_or_slug": "",
                    "position_hint": "",
                    "college_hint": "",
                    "dob_hint": "",
                    "notes": "insufficient_evidence:pfr_access_blocked",
                }
            )
            continue

        candidates = by_name.get(norm_name(player), [])
        if not candidates:
            out.append(
                {
                    "player": player,
                    "team": team,
                    "pfr_url_or_slug": "",
                    "position_hint": "",
                    "college_hint": "",
                    "dob_hint": "",
                    "notes": "no_match_found",
                }
            )
            continue

        unique_slugs = sorted({c.slug for c in candidates})
        if len(unique_slugs) != 1:
            out.append(
                {
                    "player": player,
                    "team": team,
                    "pfr_url_or_slug": "",
                    "position_hint": "",
                    "college_hint": "",
                    "dob_hint": "",
                    "notes": f"ambiguous_name:{len(unique_slugs)}_candidates",
                }
            )
            continue

        cand = candidates[0]
        pos, college, dob = parse_player_profile(cand.url)
        out.append(
            {
                "player": player,
                "team": team,
                "pfr_url_or_slug": cand.slug,
                "position_hint": pos,
                "college_hint": college,
                "dob_hint": dob,
                "notes": "auto_resolved_unique_pfr_name",
            }
        )

    # Keep row parity with unresolved input.
    if len(out) != len(unresolved):
        raise RuntimeError("row parity failed")

    write_rows(args.template, out)
    print(f"rows={len(out)}")


if __name__ == "__main__":
    main()
