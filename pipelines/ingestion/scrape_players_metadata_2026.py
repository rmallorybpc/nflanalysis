#!/usr/bin/env python3
"""Resolve 2026 player metadata from PFR using (player, team) transaction pairs."""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup


TEAM_TO_PFR = {
    "ARI": "crd",
    "ATL": "atl",
    "BAL": "rav",
    "BUF": "buf",
    "CAR": "car",
    "CHI": "chi",
    "CIN": "cin",
    "CLE": "cle",
    "DAL": "dal",
    "DEN": "den",
    "DET": "det",
    "GB": "gnb",
    "HOU": "htx",
    "IND": "clt",
    "JAX": "jax",
    "KC": "kan",
    "LV": "rai",
    "LAC": "sdg",
    "LAR": "ram",
    "MIA": "mia",
    "MIN": "min",
    "NE": "nwe",
    "NO": "nor",
    "NYG": "nyg",
    "NYJ": "nyj",
    "PHI": "phi",
    "PIT": "pit",
    "SEA": "sea",
    "SF": "sfo",
    "TB": "tam",
    "TEN": "oti",
    "WAS": "was",
}

POS_MAP = {
    "QB": "QB",
    "RB": "RB",
    "WR": "WR",
    "TE": "TE",
    "OT": "OT",
    "G": "G",
    "C": "C",
    "EDGE": "EDGE",
    "DT": "DT",
    "LB": "LB",
    "CB": "CB",
    "S": "S",
    "K": "K",
    "P": "P",
    "LS": "LS",
    "DE": "EDGE",
    "OLB": "EDGE",
    "NT": "DT",
    "T": "OT",
    "FB": "RB",
}

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

RES_FIELDS = [
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

UNRES_FIELDS = ["player", "team", "reason", "notes"]


@dataclass(frozen=True)
class Pair:
    player: str
    team: str


@dataclass(frozen=True)
class DisambiguationHint:
    slug: str
    source_url: str
    position_hint: str
    college_hint: str
    dob_hint: str
    nfl_profile_url: str


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape players metadata for 2026")
    p.add_argument("--input", type=Path, default=Path("data/raw/offseason/transactions_raw_2026.csv"))
    p.add_argument("--output", type=Path, default=Path("data/raw/offseason/players_metadata_2026.csv"))
    p.add_argument(
        "--unresolved",
        type=Path,
        default=Path("data/raw/offseason/players_metadata_2026_unresolved.csv"),
    )
    p.add_argument(
        "--disambiguation",
        type=Path,
        default=Path("data/raw/offseason/players_metadata_2026_disambiguation_template.csv"),
    )
    p.add_argument("--imported-at", default="2026-03-26T00:00:00Z")
    return p.parse_args()


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def normalize_name(name: str) -> str:
    s = name.lower().strip()
    s = s.replace(".", "").replace(",", "")
    s = re.sub(r"\s+", " ", s)
    return s


def extract_slug(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    m = re.search(r"/players/[A-Z]/([A-Za-z0-9]+)\.htm", raw)
    if m:
        return m.group(1)
    m2 = re.fullmatch(r"[A-Za-z0-9]+", raw)
    if m2:
        return raw
    return ""


def extract_nfl_profile_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    m = re.search(r"https://www\.nfl\.com/players/[^\s|]+/?", raw)
    return m.group(0) if m else ""


def roster_candidates(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for a in soup.select('a[href^="/players/"]'):
        href = a.get("href", "")
        m = re.match(r"/players/[A-Z]/([A-Za-z0-9]+)\.htm", href)
        if not m:
            continue
        name = a.get_text(" ", strip=True)
        if not name:
            continue
        item = (name, m.group(1))
        if item in seen:
            continue
        seen.add(item)
        rows.append(item)
    return rows


def parse_player_page(html: str, slug: str, imported_at: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    def data_stat(name: str) -> str:
        tag = soup.select_one(f'[data-stat="{name}"]')
        return tag.get_text(" ", strip=True) if tag else ""

    pos = data_stat("pos")
    if not pos:
        txt = soup.get_text(" ", strip=True)
        m = re.search(r"Position:\s*([A-Za-z/ ]+)", txt)
        if m:
            pos = m.group(1)

    token = ""
    if pos:
        token = pos.split("/")[0].split(" and ")[0].split()[0].upper()
    position = POS_MAP.get(token, token)

    txt = soup.get_text(" ", strip=True)
    age = ""
    m_age = re.search(r"Age:\s*(\d+)", txt)
    if m_age:
        age = m_age.group(1)

    height = data_stat("height")
    weight = data_stat("weight")

    exp_raw = data_stat("experience")
    if exp_raw == "Rook":
        exp = "0"
    else:
        m_exp = re.search(r"\d+", exp_raw)
        exp = m_exp.group(0) if m_exp else ""

    college = data_stat("college")

    draft_year = ""
    draft_round = ""
    draft_pick = ""
    m_d = re.search(r"Draft:\s*(.*?)(?:\.|Height:|Weight:|College:|High School:)", txt)
    if m_d:
        d = m_d.group(1)
        if "Undrafted" not in d:
            y = re.search(r"(19|20)\d{2}", d)
            r = re.search(r"round\s*(\d+)", d, re.I)
            pk = re.search(r"pick\s*(\d+)", d, re.I)
            if y and r and pk:
                draft_year = y.group(0)
                draft_round = r.group(1)
                draft_pick = pk.group(1)

    return {
        "position": position,
        "age": age,
        "height": height,
        "weight": weight,
        "experience": exp,
        "college": college,
        "draft_year": draft_year,
        "draft_round": draft_round,
        "draft_pick": draft_pick,
        "pfr_slug": slug,
        "source_url": f"https://www.pro-football-reference.com/players/{slug[0]}/{slug}.htm",
        "import_method": "scraped",
        "imported_at": imported_at,
    }


def compute_age(dob_iso: str, imported_at: str) -> str:
    dob_raw = (dob_iso or "").strip()
    if not dob_raw:
        return ""
    try:
        dob = date.fromisoformat(dob_raw)
        as_of = date.fromisoformat((imported_at or "")[:10])
    except ValueError:
        return ""

    years = as_of.year - dob.year
    if (as_of.month, as_of.day) < (dob.month, dob.day):
        years -= 1
    return str(years if years >= 0 else "")


def parse_nfl_profile_page(html: str, imported_at: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")

    def value_for_key(key: str) -> str:
        for key_el in soup.select("div.nfl-c-player-info__key"):
            label = key_el.get_text(" ", strip=True).lower()
            if label != key.lower():
                continue
            parent = key_el.parent
            if not parent:
                continue
            val_el = parent.select_one("div.nfl-c-player-info__value")
            if val_el:
                return val_el.get_text(" ", strip=True)
        return ""

    position = ""
    pos_el = soup.select_one("span.nfl-c-player-header__position")
    if pos_el:
        token = pos_el.get_text(" ", strip=True).split("/")[0].split()[0].upper()
        position = POS_MAP.get(token, token)

    height = value_for_key("Height")
    weight = value_for_key("Weight")
    experience = value_for_key("Experience")
    if experience.lower() == "rook":
        experience = "0"

    college = value_for_key("College")
    birth_date = ""

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
                b = str(person.get("birthDate") or "").strip()
                if b:
                    birth_date = b
                alumni = person.get("alumniOf")
                if isinstance(alumni, dict):
                    inner = alumni.get("alumniOf")
                    if isinstance(inner, dict):
                        c = str(inner.get("name") or "").strip()
                        if c:
                            college = c
                    else:
                        c = str(alumni.get("name") or "").strip()
                        if c:
                            college = c
                if birth_date or college:
                    break
            if birth_date or college:
                break
        if birth_date or college:
            break

    age = compute_age(birth_date, imported_at)
    return {
        "position": position,
        "age": age,
        "height": height,
        "weight": weight,
        "experience": experience,
        "college": college,
        "dob": birth_date,
    }


def read_pairs(path: Path) -> list[Pair]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    seen: set[tuple[str, str]] = set()
    out: list[Pair] = []
    for r in rows:
        player = (r.get("player") or "").strip()
        team = (r.get("team") or "").strip()
        if not player or not team:
            continue
        key = (player, team)
        if key in seen:
            continue
        seen.add(key)
        out.append(Pair(player=player, team=team))
    return out


def read_disambiguation_hints(path: Path) -> dict[tuple[str, str], DisambiguationHint]:
    if not path.exists():
        return {}

    out: dict[tuple[str, str], DisambiguationHint] = {}
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        player = (row.get("player") or "").strip()
        team = (row.get("team") or "").strip()
        if not player or not team:
            continue

        slug = extract_slug(row.get("pfr_url_or_slug") or "")
        source_url = f"https://www.pro-football-reference.com/players/{slug[0]}/{slug}.htm" if slug else ""
        notes = row.get("notes") or ""
        nfl_profile_url = extract_nfl_profile_url(notes)

        out[(player, team)] = DisambiguationHint(
            slug=slug,
            source_url=source_url,
            position_hint=(row.get("position_hint") or "").strip(),
            college_hint=(row.get("college_hint") or "").strip(),
            dob_hint=(row.get("dob_hint") or "").strip(),
            nfl_profile_url=nfl_profile_url,
        )

    return out


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    args = parse_args()
    if not args.input.exists():
        raise FileNotFoundError(f"missing input: {args.input}")

    pairs = read_pairs(args.input)
    disambiguation_hints = read_disambiguation_hints(args.disambiguation)

    resolved: list[dict[str, str]] = []
    unresolved: list[dict[str, str]] = []

    roster_cache: dict[str, list[tuple[str, str]] | None] = {}
    player_cache: dict[str, dict[str, str]] = {}
    nfl_cache: dict[str, dict[str, str]] = {}
    used_slugs: set[str] = set()

    for pair in pairs:
        hint = disambiguation_hints.get((pair.player, pair.team))
        if hint:
            if not hint.slug:
                has_hint = bool(hint.position_hint or hint.college_hint or hint.dob_hint or hint.nfl_profile_url)
                if not has_hint:
                    unresolved.append({
                        "player": pair.player,
                        "team": pair.team,
                        "reason": "missing_disambiguation_hint",
                        "notes": "No PFR slug and no usable NFL hint",
                    })
                    continue

                nfl_meta = {
                    "position": hint.position_hint,
                    "age": compute_age(hint.dob_hint, args.imported_at),
                    "height": "",
                    "weight": "",
                    "experience": "",
                    "college": hint.college_hint,
                    "dob": hint.dob_hint,
                }

                if hint.nfl_profile_url:
                    if hint.nfl_profile_url not in nfl_cache:
                        try:
                            nfl_html = fetch(hint.nfl_profile_url)
                            nfl_cache[hint.nfl_profile_url] = parse_nfl_profile_page(nfl_html, args.imported_at)
                        except Exception:  # pylint: disable=broad-except
                            nfl_cache[hint.nfl_profile_url] = {}
                    if nfl_cache[hint.nfl_profile_url]:
                        for k, v in nfl_cache[hint.nfl_profile_url].items():
                            if k in nfl_meta and v:
                                nfl_meta[k] = v

                if not nfl_meta["position"]:
                    unresolved.append({
                        "player": pair.player,
                        "team": pair.team,
                        "reason": "parse_error",
                        "notes": "NFL disambiguation fallback missing required position",
                    })
                    continue

                resolved.append(
                    {
                        "player": pair.player,
                        "position": nfl_meta["position"],
                        "team": pair.team,
                        "age": nfl_meta["age"],
                        "height": nfl_meta["height"],
                        "weight": nfl_meta["weight"],
                        "experience": nfl_meta["experience"],
                        "college": nfl_meta["college"],
                        "draft_year": "",
                        "draft_round": "",
                        "draft_pick": "",
                        "pfr_slug": "",
                        "source_url": hint.nfl_profile_url,
                        "import_method": "nfl_disambiguation_hint",
                        "imported_at": args.imported_at,
                    }
                )
                continue

            slug = hint.slug
            purl = hint.source_url

            if slug in used_slugs:
                unresolved.append({
                    "player": pair.player,
                    "team": pair.team,
                    "reason": "conflicting_identity",
                    "notes": f"pfr_slug already assigned to another row: {slug}",
                })
                continue

            if slug not in player_cache:
                try:
                    player_html = fetch(purl)
                    player_cache[slug] = parse_player_page(player_html, slug, args.imported_at)
                except Exception as exc:  # pylint: disable=broad-except
                    unresolved.append({
                        "player": pair.player,
                        "team": pair.team,
                        "reason": "parse_error",
                        "notes": f"Disambiguation slug failed: {type(exc).__name__}",
                    })
                    continue

            meta = dict(player_cache[slug])
            required = ["position", "age", "height", "weight", "experience", "college", "pfr_slug", "source_url", "import_method", "imported_at"]
            if any(not str(meta.get(k, "")).strip() for k in required):
                unresolved.append({
                    "player": pair.player,
                    "team": pair.team,
                    "reason": "parse_error",
                    "notes": "Missing required non-draft fields",
                })
                continue

            dy, dr, dp = meta["draft_year"], meta["draft_round"], meta["draft_pick"]
            if not ((not dy and not dr and not dp) or (dy.isdigit() and dr.isdigit() and dp.isdigit())):
                unresolved.append({
                    "player": pair.player,
                    "team": pair.team,
                    "reason": "parse_error",
                    "notes": "Invalid draft trio",
                })
                continue

            resolved.append(
                {
                    "player": pair.player,
                    "position": meta["position"],
                    "team": pair.team,
                    "age": meta["age"],
                    "height": meta["height"],
                    "weight": meta["weight"],
                    "experience": meta["experience"],
                    "college": meta["college"],
                    "draft_year": dy,
                    "draft_round": dr,
                    "draft_pick": dp,
                    "pfr_slug": meta["pfr_slug"],
                    "source_url": meta["source_url"],
                    "import_method": "manual_disambiguation",
                    "imported_at": meta["imported_at"],
                }
            )
            used_slugs.add(slug)
            continue

        tslug = TEAM_TO_PFR.get(pair.team)
        if not tslug:
            unresolved.append({"player": pair.player, "team": pair.team, "reason": "parse_error", "notes": "Unknown team abbreviation"})
            continue

        roster_url = f"https://www.pro-football-reference.com/teams/{tslug}/2026_roster.htm"
        if roster_url not in roster_cache:
            try:
                roster_html = fetch(roster_url)
                roster_cache[roster_url] = roster_candidates(roster_html)
            except HTTPError as exc:
                if exc.code == 404:
                    roster_cache[roster_url] = None
                else:
                    roster_cache[roster_url] = None
            except URLError:
                roster_cache[roster_url] = None

        cands = roster_cache.get(roster_url)
        if cands is None:
            unresolved.append({
                "player": pair.player,
                "team": pair.team,
                "reason": "missing_team_roster_page",
                "notes": f"Roster page unavailable: {roster_url}",
            })
            continue

        exact = [c for c in cands if c[0] == pair.player]
        if exact:
            matches = exact
        else:
            n = normalize_name(pair.player)
            matches = [c for c in cands if normalize_name(c[0]) == n]

        if not matches:
            unresolved.append({
                "player": pair.player,
                "team": pair.team,
                "reason": "not_found",
                "notes": f"No exact/normalized roster match on {roster_url}",
            })
            continue

        if len(matches) > 1:
            urls = [f"https://www.pro-football-reference.com/players/{slug[0]}/{slug}.htm" for _, slug in matches]
            unresolved.append({
                "player": pair.player,
                "team": pair.team,
                "reason": "ambiguous_match",
                "notes": "Candidates: " + " | ".join(urls),
            })
            continue

        _, slug = matches[0]
        purl = f"https://www.pro-football-reference.com/players/{slug[0]}/{slug}.htm"

        if slug in used_slugs:
            unresolved.append({
                "player": pair.player,
                "team": pair.team,
                "reason": "conflicting_identity",
                "notes": f"pfr_slug already assigned to another row: {slug}",
            })
            continue

        if slug not in player_cache:
            try:
                player_html = fetch(purl)
                player_cache[slug] = parse_player_page(player_html, slug, args.imported_at)
            except Exception as exc:  # pylint: disable=broad-except
                unresolved.append({
                    "player": pair.player,
                    "team": pair.team,
                    "reason": "parse_error",
                    "notes": f"Failed to parse player page: {type(exc).__name__}",
                })
                continue

        meta = dict(player_cache[slug])

        required = ["position", "age", "height", "weight", "experience", "college", "pfr_slug", "source_url", "import_method", "imported_at"]
        if any(not str(meta.get(k, "")).strip() for k in required):
            unresolved.append({
                "player": pair.player,
                "team": pair.team,
                "reason": "parse_error",
                "notes": "Missing required non-draft fields",
            })
            continue

        dy, dr, dp = meta["draft_year"], meta["draft_round"], meta["draft_pick"]
        if not ((not dy and not dr and not dp) or (dy.isdigit() and dr.isdigit() and dp.isdigit())):
            unresolved.append({
                "player": pair.player,
                "team": pair.team,
                "reason": "parse_error",
                "notes": "Invalid draft trio",
            })
            continue

        resolved.append(
            {
                "player": pair.player,
                "position": meta["position"],
                "team": pair.team,
                "age": meta["age"],
                "height": meta["height"],
                "weight": meta["weight"],
                "experience": meta["experience"],
                "college": meta["college"],
                "draft_year": dy,
                "draft_round": dr,
                "draft_pick": dp,
                "pfr_slug": meta["pfr_slug"],
                "source_url": meta["source_url"],
                "import_method": meta["import_method"],
                "imported_at": meta["imported_at"],
            }
        )
        used_slugs.add(slug)

    if len(resolved) + len(unresolved) != len(pairs):
        raise RuntimeError("Coverage gate failed")

    write_csv(args.output, RES_FIELDS, resolved)
    write_csv(args.unresolved, UNRES_FIELDS, unresolved)

    print(f"pairs={len(pairs)} resolved={len(resolved)} unresolved={len(unresolved)}")


if __name__ == "__main__":
    main()
