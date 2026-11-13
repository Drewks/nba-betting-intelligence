"""
Official NBA League Injury Report ingestion & PDF parser.

Fetches the public hourly/half-hourly NBA Injury Report PDFs hosted at
`https://ak-static.cms.nba.com/referee/injury/Injury-Report_YYYY-MM-DD_HH_MMPM.pdf`
using standard HTTP requests (no anti-bot bypass or evasion) and extracts normalized
per-player availability rows using geometric PDF coordinate clustering.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import io
import logging
import re
from typing import Any

import httpx
from pypdf import PdfReader

from src.ingestion.normalizer import normalize_team_code

logger = logging.getLogger(__name__)

NBA_INJURY_PDF_URL_TEMPLATE = (
    "https://ak-static.cms.nba.com/referee/injury/Injury-Report_{date_et}_{slot_et}.pdf"
)

# Standard ET publication cadence across NBA game days (15-min/30-min/hourly slots)
DEFAULT_ET_SLOTS: tuple[str, ...] = (
    "11_30PM",
    "11_00PM",
    "10_30PM",
    "10_00PM",
    "09_30PM",
    "09_00PM",
    "08_30PM",
    "08_00PM",
    "07_30PM",
    "07_00PM",
    "06_30PM",
    "06_00PM",
    "05_30PM",
    "05_00PM",
    "04_30PM",
    "04_00PM",
    "03_30PM",
    "03_00PM",
    "02_30PM",
    "02_00PM",
    "01_30PM",
    "01_00PM",
    "12_30PM",
    "12_00PM",
    "11_30AM",
    "11_00AM",
    "10_30AM",
    "10_00AM",
    "09_30AM",
    "09_00AM",
    "08_30AM",
)

# Default column x-cutoffs matching official NBA PDF table layout (landscape)
DEFAULT_COL_BOUNDARIES: tuple[float, float, float, float, float, float] = (
    110.0,
    195.0,
    260.0,
    420.0,
    580.0,
    660.0,
)

# ET fixed offset (-05:00 standard / UTC-5 matches NBA injury filename clock during regular season)
ET_FIXED_OFFSET = timezone(timedelta(hours=-5))


def canonicalize_nba_player_name(raw_name: str) -> str:
    """Converts `'Last, First'` NBA PDF names into canonical `'First Last'` form."""
    cleaned = re.sub(r"\s+", " ", str(raw_name or "")).strip()
    if not cleaned:
        return ""
    # Rejoin hyphenated names wrapped at PDF line breaks (e.g., "Jackson- Davis" -> "Jackson-Davis")
    cleaned = re.sub(r"([A-Za-z])-\s+", r"\1-", cleaned)
    if "," in cleaned:
        last_part, first_part = cleaned.split(",", 1)
        first = first_part.strip()
        last = last_part.strip()
        if first and last:
            return f"{first} {last}"
    return cleaned


def _normalize_reason(raw_reason: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(raw_reason or "")).strip()
    cleaned = re.sub(r"([A-Za-z])-\s+", r"\1-", cleaned)
    return cleaned


def _detect_column_boundaries(header_tokens: list[tuple[float, float, str]]) -> tuple[float, ...]:
    """Derives exact column x-cutoffs from detected header labels if present."""
    anchors: dict[str, float] = {}
    for x, _y, txt in header_tokens:
        low = txt.lower()
        if low == "date" or (low == "game" and x < 80 and "date" not in anchors):
            anchors.setdefault("date", x)
        elif low == "time" or (low == "game" and 90 <= x < 170):
            anchors["time"] = min(anchors.get("time", x), x)
        elif "matchup" in low:
            anchors["matchup"] = x
        elif low == "team":
            anchors["team"] = x
        elif "player" in low:
            anchors["player"] = x
        elif low in ("current", "status"):
            anchors["status"] = min(anchors.get("status", x), x)
        elif "reason" in low:
            anchors["reason"] = x

    required = ("time", "matchup", "team", "player", "status", "reason")
    if all(k in anchors for k in required):
        return (
            anchors["time"] - 5.0,
            anchors["matchup"] - 5.0,
            anchors["team"] - 5.0,
            anchors["player"] - 5.0,
            anchors["status"] - 5.0,
            anchors["reason"] - 5.0,
        )
    return DEFAULT_COL_BOUNDARIES


def _cluster_tokens_by_y(
    tokens: list[tuple[float, float, str]],
    *,
    y_tolerance: float = 4.0,
) -> list[tuple[float, list[tuple[float, str]]]]:
    """Groups PDF text tokens into horizontal visual lines."""
    if not tokens:
        return []
    ordered = sorted(tokens, key=lambda item: (item[1], item[0]))
    clusters: list[tuple[float, list[tuple[float, str]]]] = []
    for x, y, text in ordered:
        if clusters and abs(clusters[-1][0] - y) <= y_tolerance:
            clusters[-1][1].append((x, text))
        else:
            clusters.append((y, [(x, text)]))
    return clusters


def parse_nba_injury_pdf_bytes(
    pdf_bytes: bytes,
    *,
    report_url: str | None = None,
    captured_at: str | None = None,
) -> dict[str, Any]:
    """
    Parses an official NBA Injury Report PDF payload into normalized player records.

    Returns a dictionary containing `players`, `by_team`, and `not_yet_submitted_teams`.
    """
    if not pdf_bytes:
        raise ValueError("Empty NBA injury report PDF payload.")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    captured_iso = captured_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    records: list[dict[str, Any]] = []
    not_yet_submitted: list[str] = []
    seen_pending_teams: set[str] = set()

    cur_date = ""
    cur_time = ""
    cur_matchup = ""
    cur_team_code = ""
    cur_team_raw = ""
    boundaries: tuple[float, ...] = DEFAULT_COL_BOUNDARIES

    for page in reader.pages:
        tokens: list[tuple[float, float, str]] = []

        def _visitor(
            text: str,
            _cm: Any,
            tm: list[float],
            _font_dict: Any,
            _font_size: Any,
            *,
            _tokens: list[tuple[float, float, str]] = tokens,
        ) -> None:
            stripped = str(text or "").strip()
            if stripped:
                _tokens.append((round(float(tm[4]), 1), round(float(tm[5]), 1), stripped))

        page.extract_text(visitor_text=_visitor)
        clusters = _cluster_tokens_by_y(tokens)
        if not clusters:
            continue

        # Locate column header row, top report title, and bottom page footer separately
        header_idx: int | None = None
        skip_indices: set[int] = set()
        page_footer_indices: set[int] = set()
        for idx, (_y, line_toks) in enumerate(clusters):
            joined = " ".join(t for _x, t in sorted(line_toks)).strip()
            if "Matchup" in joined and "Player" in joined and "Status" in joined:
                header_idx = idx
                boundaries = _detect_column_boundaries(
                    [(x, _y, t) for x, t in line_toks]
                )
            elif re.match(r"^Page\s+\d+\s+of\s+\d+$", joined):
                page_footer_indices.add(idx)
                skip_indices.add(idx)
            elif joined.startswith("Injury Report:"):
                skip_indices.add(idx)

        if header_idx is not None and page_footer_indices and min(page_footer_indices) < header_idx:
            clusters = list(reversed(clusters))
            header_idx = None
            skip_indices = set()
            for idx, (_y, line_toks) in enumerate(clusters):
                joined = " ".join(t for _x, t in sorted(line_toks)).strip()
                if "Matchup" in joined and "Player" in joined and "Status" in joined:
                    header_idx = idx
                elif re.match(r"^Page\s+\d+\s+of\s+\d+$", joined) or joined.startswith("Injury Report:"):
                    skip_indices.add(idx)

        b_time, b_matchup, b_team, b_player, b_status, b_reason = boundaries
        page_records: list[tuple[float, dict[str, Any], list[tuple[float, str]]]] = []
        orphan_reasons: list[tuple[float, str]] = []
        orphan_players: list[tuple[float, str]] = []

        for idx, (row_y, line_toks) in enumerate(clusters):
            if idx in skip_indices:
                continue
            if header_idx is not None and idx <= header_idx:
                continue

            cols: dict[str, list[str]] = defaultdict(list)
            for x, tok in sorted(line_toks):
                if x < b_time:
                    cols["date"].append(tok)
                elif x < b_matchup:
                    cols["time"].append(tok)
                elif x < b_team:
                    cols["matchup"].append(tok)
                elif x < b_player:
                    cols["team"].append(tok)
                elif x < b_status:
                    cols["player"].append(tok)
                elif x < b_reason:
                    cols["status"].append(tok)
                else:
                    cols["reason"].append(tok)

            date_val = " ".join(cols["date"]).strip()
            time_val = " ".join(cols["time"]).strip()
            matchup_val = " ".join(cols["matchup"]).strip()
            team_val = " ".join(cols["team"]).strip()
            player_val = " ".join(cols["player"]).strip()
            status_val = " ".join(cols["status"]).strip()
            reason_val = _normalize_reason(" ".join(cols["reason"]))

            if date_val:
                cur_date = date_val
            if time_val:
                cur_time = time_val
            if matchup_val:
                cur_matchup = matchup_val
            if team_val:
                cur_team_raw = team_val
                try:
                    cur_team_code = normalize_team_code(team_val)
                except ValueError:
                    cur_team_code = ""
                    logger.debug("Skipping unrecognized team name in NBA injury PDF: %r", team_val)

            if "NOT YET SUBMITTED" in reason_val.upper() or "NOT YET SUBMITTED" in status_val.upper():
                if cur_team_code and cur_team_code not in seen_pending_teams:
                    seen_pending_teams.add(cur_team_code)
                    not_yet_submitted.append(cur_team_code)
                continue

            if player_val and status_val:
                canon_name = canonicalize_nba_player_name(player_val)
                if cur_team_code and canon_name:
                    rec = {
                        "name": canon_name,
                        "raw_name": player_val,
                        "team": cur_team_code,
                        "team_name": cur_team_raw,
                        "status": status_val,
                        "notes": "",
                        "game_date": cur_date,
                        "game_time_et": cur_time,
                        "matchup": cur_matchup,
                        "source": "nba_official_injury_report",
                        "report_url": report_url,
                        "captured_at": captured_iso,
                    }
                    reason_parts = [(row_y, reason_val)] if reason_val else []
                    page_records.append((row_y, rec, reason_parts))
            else:
                if reason_val:
                    orphan_reasons.append((row_y, reason_val))
                if player_val and not status_val:
                    orphan_players.append((row_y, player_val))

        # Associate vertically-centered wrapped reason/player fragments with nearest row on this page
        if page_records:
            for r_y, r_txt in orphan_reasons:
                nearest_idx = min(
                    range(len(page_records)),
                    key=lambda i: abs(page_records[i][0] - r_y),
                )
                if abs(page_records[nearest_idx][0] - r_y) <= 22.0:
                    page_records[nearest_idx][2].append((r_y, r_txt))

            for p_y, p_txt in orphan_players:
                nearest_idx = min(
                    range(len(page_records)),
                    key=lambda i: abs(page_records[i][0] - p_y),
                )
                if abs(page_records[nearest_idx][0] - p_y) <= 18.0:
                    target_rec = page_records[nearest_idx][1]
                    if p_y < page_records[nearest_idx][0]:
                        merged_raw = f"{p_txt} {target_rec['raw_name']}".strip()
                    else:
                        merged_raw = f"{target_rec['raw_name']} {p_txt}".strip()
                    target_rec["raw_name"] = merged_raw
                    target_rec["name"] = canonicalize_nba_player_name(merged_raw)

            for _ry, rec, reason_parts in page_records:
                reason_parts.sort(key=lambda item: item[0])
                rec["notes"] = _normalize_reason(" ".join(part for _py, part in reason_parts))
                records.append(rec)

    by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        by_team[str(rec["team"])].append(rec)

    return {
        "source": "nba_official_injury_report",
        "report_url": report_url,
        "captured_at": captured_iso,
        "player_count": len(records),
        "players": records,
        "by_team": dict(by_team),
        "not_yet_submitted_teams": not_yet_submitted,
    }


@dataclass
class NBAOfficialInjuryFeed:
    """Client to fetch and parse the latest official NBA Injury Report PDF."""

    timeout_seconds: float = 12.0
    max_probe_slots: int = 16

    @staticmethod
    def _et_now(as_of_utc: datetime | None = None) -> datetime:
        base = as_of_utc or datetime.now(timezone.utc)
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        return base.astimezone(ET_FIXED_OFFSET)

    @classmethod
    def candidate_report_urls(
        cls,
        target_date_et: str | None = None,
        as_of_utc: datetime | None = None,
    ) -> list[str]:
        """Builds candidate official NBA PDF URLs from newest plausible slot backward."""
        now_et = cls._et_now(as_of_utc)
        date_str = target_date_et or now_et.strftime("%Y-%m-%d")

        # Prioritize half-hour slots near or before current ET time if fetching today's slate
        if date_str == now_et.strftime("%Y-%m-%d"):
            minute_bucket = 30 if now_et.minute >= 30 else 0
            cursor_dt = now_et.replace(minute=minute_bucket, second=0, microsecond=0)
            ordered_slots: list[str] = []
            for step in range(28):
                cand = cursor_dt - timedelta(minutes=30 * step)
                if cand.strftime("%Y-%m-%d") != date_str:
                    break
                slot = cand.strftime("%I_%M%p")
                if slot not in ordered_slots:
                    ordered_slots.append(slot)
            for s in DEFAULT_ET_SLOTS:
                if s not in ordered_slots:
                    ordered_slots.append(s)
        else:
            ordered_slots = list(DEFAULT_ET_SLOTS)

        return [
            NBA_INJURY_PDF_URL_TEMPLATE.format(date_et=date_str, slot_et=slot)
            for slot in ordered_slots
        ]

    def fetch_latest_report(
        self,
        *,
        target_date_et: str | None = None,
        as_of_utc: datetime | None = None,
        direct_url: str | None = None,
    ) -> dict[str, Any]:
        """Fetches and parses the freshest available official NBA Injury Report PDF."""
        now_utc = (as_of_utc or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
        candidates = (
            [direct_url]
            if direct_url
            else self.candidate_report_urls(target_date_et=target_date_et, as_of_utc=as_of_utc)[: self.max_probe_slots]
        )

        headers = {"User-Agent": "Mozilla/5.0 (compatible; NBA-Intelligence/1.0)", "Accept": "application/pdf"}
        last_error: str | None = None

        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
                for url in candidates:
                    try:
                        resp = client.get(url)
                        if resp.status_code == 200 and resp.content.startswith(b"%PDF"):
                            parsed = parse_nba_injury_pdf_bytes(
                                resp.content,
                                report_url=url,
                                captured_at=now_utc,
                            )
                            return {
                                "fetch_ok": True,
                                **parsed,
                            }
                        last_error = f"HTTP {resp.status_code} at {url}"
                    except Exception as exc:
                        last_error = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"

        return {
            "fetch_ok": False,
            "source": "nba_official_injury_report",
            "report_url": None,
            "captured_at": now_utc,
            "player_count": 0,
            "players": [],
            "by_team": {},
            "not_yet_submitted_teams": [],
            "error": last_error or "No available NBA injury report PDF found",
        }


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name or "").lower())


def merge_official_and_espn_injuries(
    official_by_team: dict[str, list[dict[str, Any]]],
    espn_reports: dict[str, list[dict[str, Any]]],
    teams: tuple[str, ...],
) -> list[dict[str, Any]]:
    """
    Merges official NBA Injury Report entries with ESPN event summary entries.

    Official NBA entries take precedence for player status and reason while inheriting
    optional metadata (such as `default_impact`) from matching ESPN rows.
    """
    merged: list[dict[str, Any]] = []
    for t_code in teams:
        off_rows = official_by_team.get(t_code, []) or []
        espn_rows = espn_reports.get(t_code, []) or []

        espn_by_key: dict[str, dict[str, Any]] = {}
        for er in espn_rows:
            k = _name_key(str(er.get("name") or ""))
            if k:
                espn_by_key[k] = er

        seen_keys: set[str] = set()
        for off in off_rows:
            item = dict(off)
            item.setdefault("source", "nba_official_injury_report")
            k = _name_key(str(item.get("name") or ""))
            if k:
                seen_keys.add(k)
                espn_match = espn_by_key.get(k)
                if espn_match and "default_impact" in espn_match and "default_impact" not in item:
                    item["default_impact"] = espn_match["default_impact"]
            merged.append(item)

        for er in espn_rows:
            k = _name_key(str(er.get("name") or ""))
            if k and k in seen_keys:
                continue
            fallback_item = dict(er)
            fallback_item.setdefault("source", "espn_summary")
            merged.append(fallback_item)

    return merged
