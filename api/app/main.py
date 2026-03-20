#!/usr/bin/env python3
"""HTTP endpoint for counterfactual scenario simulation."""

from __future__ import annotations

import argparse
import json
from urllib.parse import parse_qs, urlparse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from api.app.counterfactual_service import CounterfactualService


SERVICE = CounterfactualService()


def _parse_payload(payload: dict[str, Any]) -> dict[str, Any]:
    required = ["team_id", "season", "scenario_id"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"missing required fields: {missing}")

    season = int(payload["season"])
    week = payload.get("week")
    week_int = int(week) if week is not None else None
    moves = payload.get("applied_moves", [])
    if not isinstance(moves, list):
        raise ValueError("applied_moves must be a list")

    return {
        "team_id": str(payload["team_id"]).strip(),
        "season": season,
        "week": week_int,
        "scenario_id": str(payload["scenario_id"]).strip(),
        "moves": moves,
    }


class CounterfactualHandler(BaseHTTPRequestHandler):
    """Handler for counterfactual simulation endpoint."""

    server_version = "nflanalysis-counterfactual/0.1"

    def _write_json(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return
        if parsed.path == "/v1/dashboard/overview":
            try:
                params = parse_qs(parsed.query)
                season_raw = params.get("season", [None])[0]
                if season_raw is None:
                    season = max(int(row["nfl_season"]) for row in SERVICE.model_rows)
                else:
                    season = int(season_raw)
                payload = SERVICE.build_overview_payload(season=season)
                self._write_json(HTTPStatus.OK, payload)
                return
            except Exception as exc:  # pylint: disable=broad-except
                self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
        self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/counterfactual/simulate":
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length)
            payload = json.loads(raw_body.decode("utf-8"))
            args = _parse_payload(payload)
            response = SERVICE.simulate(
                team_id=args["team_id"],
                season=args["season"],
                week=args["week"],
                scenario_id=args["scenario_id"],
                moves=args["moves"],
            )
            self._write_json(HTTPStatus.OK, response)
        except Exception as exc:  # pylint: disable=broad-except
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run counterfactual API server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8080, help="Bind port")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), CounterfactualHandler)
    print(f"Serving counterfactual API on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
