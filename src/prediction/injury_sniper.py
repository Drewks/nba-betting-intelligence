"""
V7.1 Injury Sniper Pregame Dual-Window Monitor (T-2h & T-30m):
Monitors real-time NBA injury reports and starting lineup confirmations at the two critical market windows:
  1. Window T-2h (90 to 150 minutes before tip-off): NBA official afternoon injury report & head coach press briefings.
  2. Window T-30m (15 to 45 minutes before tip-off): NBA official scorer's table active/inactive lists & starting five confirmation.

When a high-impact player status transition occurs (e.g., Questionable/GTD -> OUT, or Late Scratch):
  - Recalculates non-linear On/Off RAPM lineup synergy penalties (LineupSynergyEngine).
  - Recalculates win probability and Venn-Abers conformal prediction intervals [p0, p1].
  - Checks if Lower-Bound EV exceeds the syndicate hurdle (+5.0%) before bookmakers fully adjust lines.
  - Recommends simultaneous Kelly-sized stakes and logs immutable audit records to `sniper_alerts`.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import json
from typing import Any
import uuid

logger = logging.getLogger(__name__)

import numpy as np
from scipy.stats import norm

from src.calibration.calibrator import VennAbersConformalInterval
from src.config import load_config
from src.features.team_ratings import (
    PLAYER_ON_OFF_SYNERGY_PROFILES,
    compute_lineup_synergy_penalty,
)
from src.ingestion.adapters import ESPNPublicAdapter, PlaywrightAuthorizedScraper, SportradarAdapter
from src.prediction.ev_calculator import (
    compute_market_consensus,
    evaluate_market_opportunity,
    optimize_simultaneous_kelly_portfolio,
)
from src.storage.db import DatabaseManager
from src.validation.validator import parse_iso_utc


def classify_game_window(
    game_start_time_iso: str,
    reference_time_utc: datetime | None = None,
) -> tuple[str, float]:
    """
    Classifies a game's temporal status relative to tip-off into dual monitoring windows:
      - WINDOW_2H: 90 to 150 minutes before tip-off (T - 2 hours)
      - WINDOW_30M: 15 to 45 minutes before tip-off (T - 30 minutes)
      - TIPOFF_IMMINENT: 0 to 15 minutes before tip-off
      - IN_PROGRESS_OR_FINAL: Game already started (delta < 0)
      - UPCOMING_FUTURE: > 150 minutes before tip-off
    Returns: (window_type, delta_minutes)
    """
    ref_dt = reference_time_utc or datetime.now(timezone.utc)
    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=timezone.utc)

    game_dt = parse_iso_utc(game_start_time_iso)
    delta_seconds = (game_dt - ref_dt).total_seconds()
    delta_minutes = delta_seconds / 60.0

    if 90.0 <= delta_minutes <= 150.0:
        return "WINDOW_2H", round(delta_minutes, 1)
    elif 15.0 <= delta_minutes <= 45.0:
        return "WINDOW_30M", round(delta_minutes, 1)
    elif 0.0 <= delta_minutes < 15.0:
        return "TIPOFF_IMMINENT", round(delta_minutes, 1)
    elif delta_minutes < 0.0:
        return "IN_PROGRESS_OR_FINAL", round(delta_minutes, 1)
    else:
        return "UPCOMING_FUTURE", round(delta_minutes, 1)


def normalize_injury_status(raw_status: str) -> str:
    """Normalizes raw status strings into canonical categories."""
    s = str(raw_status or "").strip().lower()
    if any(k in s for k in ("out", "injured", "sidelined", "inactive")):
        return "OUT"
    if any(k in s for k in ("doubtful", "unlikely")):
        return "DOUBTFUL"
    if any(k in s for k in ("questionable", "gtd", "game-time", "day-to-day", "doubt")):
        return "QUESTIONABLE"
    if any(k in s for k in ("probable", "likely")):
        return "PROBABLE"
    if any(k in s for k in ("available", "active", "cleared", "starter", "starting")):
        return "AVAILABLE"
    return "UNKNOWN"


def detect_injury_status_transitions(
    cached_injuries: list[dict[str, Any]],
    live_injuries: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Compares prior known injury statuses with fresh live reports to detect market-moving transitions.
    Detects:
      - QUESTIONABLE / DOUBTFUL / GTD -> OUT (Confirmed Out / Scratch)
      - AVAILABLE / ACTIVE -> OUT (Late Scratch / Shock Out)
      - QUESTIONABLE / DOUBTFUL -> AVAILABLE (Confirmed Playing / Early Boost)
    """
    cached_map: dict[str, str] = {
        item["name"].strip(): normalize_injury_status(item.get("status", ""))
        for item in cached_injuries
        if item.get("name")
    }

    transitions: list[dict[str, Any]] = []

    for live in live_injuries:
        p_name = live.get("name", "").strip()
        if not p_name:
            continue
        new_status = normalize_injury_status(live.get("status", ""))
        old_status = cached_map.get(p_name, "AVAILABLE")

        if old_status != new_status:
            # Check tactical impact in Synergy Profiles
            synergy_profile = PLAYER_ON_OFF_SYNERGY_PROFILES.get(p_name)
            is_star = synergy_profile is not None
            impact_val = synergy_profile[0] if synergy_profile is not None else float(live.get("default_impact", 0.5))
            role = synergy_profile[4] if synergy_profile is not None else "ROTATION"

            severity = "LOW"
            if is_star and new_status == "OUT":
                severity = "CRITICAL"
            elif new_status == "OUT" and impact_val >= 2.0:
                severity = "HIGH"
            elif old_status in ("QUESTIONABLE", "DOUBTFUL") and new_status == "AVAILABLE" and impact_val >= 2.5:
                severity = "HIGH"
            elif is_star:
                severity = "MEDIUM"

            transitions.append({
                "player_name": p_name,
                "team": live.get("team", ""),
                "old_status": old_status,
                "new_status": new_status,
                "tactical_role": role,
                "base_impact": impact_val,
                "severity": severity,
                "is_synergy_star": is_star,
                "notes": live.get("notes", ""),
            })

    return transitions


class InjurySniperMonitor:
    """
    Automated Pregame Dual-Window Monitor and Conformal +EV Sniper:
    Tracks scheduled matchups at T-2h and T-30m, detects injury delta, recalculates
    V7 non-linear synergy penalties and Venn-Abers conformal bounds, and emits high-EV alerts.

    Probability model: the de-vigged market probability is the prior; only NEW material injury
    transitions (vs. the previous stored snapshot) shift it, through a normal margin model.
    """

    MARGIN_SIGMA_PTS = 12.0

    def __init__(
        self,
        db: DatabaseManager,
        espn_adapter: ESPNPublicAdapter | None = None,
        playwright_scraper: PlaywrightAuthorizedScraper | None = None,
        sportradar_adapter: SportradarAdapter | None = None,
        min_ev_threshold: float = 0.05,
        max_stake_pen: float | None = None,
    ) -> None:
        self.db = db
        self.max_stake_pen = float(max_stake_pen if max_stake_pen is not None else load_config().risk.max_stake_pen)
        self.espn_adapter = espn_adapter or ESPNPublicAdapter()
        self.playwright_scraper = playwright_scraper or PlaywrightAuthorizedScraper()
        self.sportradar_adapter = sportradar_adapter
        self.min_ev_threshold = min_ev_threshold
        self.calibrator = VennAbersConformalInterval(window=1200)

    def evaluate_game_sniper_opportunity(
        self,
        game_id: str,
        matchday_date: str,
        game_start_time: str,
        home_team: str,
        away_team: str,
        live_injuries: list[dict[str, Any]],
        market_odds: list[dict[str, Any]],
        window_type: str,
        minutes_to_tipoff: float,
        cached_injuries: list[dict[str, Any]] | None = None,
        bankroll_pen: float = 100.0,
        max_conformal_width: float | None = None,
    ) -> list[dict[str, Any]]:
        """
        Evaluates pregame odds against recalculated synergy ratings and Venn-Abers conformal intervals.
        Generates actionable SniperAlert items if Lower-Bound EV exceeds the threshold.
        """
        # 1. Detect transitions vs. the previous snapshot. Long-known absences are already priced by the
        #    market: only NEW status changes can move the fair price.
        cached = cached_injuries or []
        transitions = detect_injury_status_transitions(cached, live_injuries)
        material = [t for t in transitions if t["severity"] in ("CRITICAL", "HIGH")]
        if not material:
            return []

        # 2. Incremental lineup penalty per team (current report minus previous report)
        def _team(items: list[dict[str, Any]], team: str) -> list[dict[str, Any]]:
            return [i for i in items if i.get("team") == team]

        home_syn = compute_lineup_synergy_penalty(_team(live_injuries, home_team))
        away_syn = compute_lineup_synergy_penalty(_team(live_injuries, away_team))
        home_prev = compute_lineup_synergy_penalty(_team(cached, home_team))
        away_prev = compute_lineup_synergy_penalty(_team(cached, away_team))
        delta_home = float(home_syn["total_net_penalty"] - home_prev["total_net_penalty"])
        delta_away = float(away_syn["total_net_penalty"] - away_prev["total_net_penalty"])
        # Net shift in points in favor of HOME (+ means home's relative strength increased)
        net_shift = delta_away - delta_home

        # 3. Anchor to the de-vigged market: p_new = Phi((sigma * Phi^-1(p_market) + shift) / sigma)
        consensus = compute_market_consensus([o for o in market_odds if o.get("market") == "moneyline"])
        mkt_entry = consensus.get(("moneyline", "HOME", None))
        if not mkt_entry:
            return []
        p_mkt_home = float(np.clip(mkt_entry["p_market"], 0.02, 0.98))
        sigma = self.MARGIN_SIGMA_PTS
        spread_mkt = sigma * float(norm.ppf(p_mkt_home))
        p_home_raw = float(np.clip(norm.cdf((spread_mkt + net_shift) / sigma), 0.02, 0.98))
        p_away_raw = 1.0 - p_home_raw

        # 5. Conformal Venn-Abers prediction interval calibration
        conf_home = self.calibrator.predict_interval(p_home_raw)
        conf_away = self.calibrator.predict_interval(p_away_raw)

        # 6. Evaluate market odds from provided snapshots
        alerts: list[dict[str, Any]] = []
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        for odds_rec in market_odds:
            if odds_rec.get("market") != "moneyline":
                continue
            sel = odds_rec.get("selection")
            dec_odds = float(odds_rec.get("decimal_odds") or 0.0)
            if dec_odds <= 1.0:
                continue

            point_p = p_home_raw if sel == "HOME" else p_away_raw
            conf_int = conf_home if sel == "HOME" else conf_away

            opp = evaluate_market_opportunity(
                estimated_prob=point_p,
                uncertainty_std=0.035,
                odds_record=odds_rec,
                game_start_time=game_start_time,
                model_version_id="model_v7_sniper_pregame",
                conformal_interval=conf_int,
                # p already contains the market; the injury-impact table is hand-made and uncalibrated,
                # so only half of the modeled shift is trusted.
                model_weight=0.50,
            )

            lb_ev_pct = float(opp.get("ev_lower_bound_pct", -100.0))
            ev_pct = float(opp.get("ev_pct", -100.0))
            conf_w = float(opp.get("conformal_width") or 0.10)

            # Sniper Trigger Gate: Positive Lower-Bound EV and reasonable uncertainty width
            max_w = max_conformal_width if max_conformal_width is not None else (0.22 if getattr(self.calibrator, "is_fitted", False) else 0.32)
            if lb_ev_pct >= (self.min_ev_threshold * 100.0) and conf_w <= max_w:
                # Calculate optimal Kelly stake
                cand_for_kelly = [{
                    "prediction_id": f"SNIPER_PRED_{uuid.uuid4().hex[:8]}",
                    "game_id": game_id,
                    "market": "moneyline",
                    "selection": sel,
                    "estimated_probability": point_p,
                    "calibrated_probability": opp.get("estimated_probability", point_p),
                    "decimal_odds_used": dec_odds,
                    "ev_unit": opp.get("ev_lower_bound", 0.05),
                }]
                kelly_res = optimize_simultaneous_kelly_portfolio(
                    cand_for_kelly,
                    bankroll_pen=bankroll_pen,
                    max_total_exposure_fraction=0.15,
                    max_individual_fraction=0.06,
                )
                recommended_frac = kelly_res[0]["kelly_optimal_fraction"]
                # Alerts never suggest more than the configured per-selection cap; zero if Kelly says no edge.
                recommended_stake = round(min(float(kelly_res[0]["kelly_recommended_stake_pen"]), self.max_stake_pen), 2)

                # Build rationale
                target_team = home_team if sel == "HOME" else away_team
                opp_team = away_team if sel == "HOME" else home_team
                crit_transitions = [t for t in transitions if t["severity"] in ("CRITICAL", "HIGH")]
                t_str = ", ".join(f"{t['player_name']} ({t['old_status']}->{t['new_status']})" for t in crit_transitions) or "Confirmed Lineup Shift"

                rational = (
                    f"[{window_type} at T-{minutes_to_tipoff:.0f}m] Injury sniper edge on {target_team} ML. "
                    f"Net synergy shift: {net_shift:+.1f} pts ({t_str}). "
                    f"Point prob: {point_p * 100:.1f}%, Venn-Abers conformal: [{conf_int['p0'] * 100:.1f}%, {conf_int['p1'] * 100:.1f}%]. "
                    f"Lower-Bound EV: {lb_ev_pct:+.2f}% vs book odds {dec_odds:.2f}. "
                    f"Recommended Kelly stake: S/ {recommended_stake:.2f} PEN ({recommended_frac * 100:.2f}%)."
                )

                alert = {
                    "alert_id": f"SNIPER_{game_id}_{sel}_{uuid.uuid4().hex[:6]}",
                    "game_id": game_id,
                    "matchday_date": matchday_date,
                    "window_type": window_type,
                    "minutes_to_tipoff": minutes_to_tipoff,
                    "selection": sel,
                    "target_team": target_team,
                    "opponent_team": opp_team,
                    "decimal_odds": dec_odds,
                    "point_prob": round(point_p, 4),
                    "calibrated_prob": round(float(opp.get("estimated_probability", point_p)), 4),
                    "conformal_p_low": round(float(conf_int["p0"]), 4),
                    "conformal_p_high": round(float(conf_int["p1"]), 4),
                    "conformal_width": round(conf_w, 4),
                    "ev_pct": round(ev_pct, 2),
                    "ev_lower_bound_pct": round(lb_ev_pct, 2),
                    "kelly_stake_pen": recommended_stake,
                    "kelly_optimal_fraction": recommended_frac,
                    "transitions": transitions,
                    "synergy_shift": round(net_shift, 2),
                    "home_synergy_penalty": round(home_syn["total_net_penalty"], 2),
                    "away_synergy_penalty": round(away_syn["total_net_penalty"], 2),
                    "market_p_home": round(p_mkt_home, 4),
                    "rational": rational,
                    "emitted_at": now_iso,
                }
                alerts.append(alert)

                # Persist to SQLite table sniper_alerts
                try:
                    self.db.execute_insert(
                        """
                        INSERT OR REPLACE INTO sniper_alerts (
                            alert_id, game_id, matchday_date, window_type, minutes_to_tipoff,
                            selection, decimal_odds, point_prob, conformal_p_low, conformal_p_high,
                            ev_pct, ev_lower_bound_pct, kelly_stake_pen, transitions_json,
                            synergy_shift, rational, emitted_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            alert["alert_id"],
                            alert["game_id"],
                            alert["matchday_date"],
                            alert["window_type"],
                            alert["minutes_to_tipoff"],
                            alert["selection"],
                            alert["decimal_odds"],
                            alert["point_prob"],
                            alert["conformal_p_low"],
                            alert["conformal_p_high"],
                            alert["ev_pct"],
                            alert["ev_lower_bound_pct"],
                            alert["kelly_stake_pen"],
                            json.dumps(transitions, ensure_ascii=False),
                            alert["synergy_shift"],
                            alert["rational"],
                            alert["emitted_at"],
                        ),
                    )
                except Exception as exc:
                    logger.warning(f"Failed to persist sniper alert for {alert.get('game_id')}: {exc}")

        return alerts

    def _latest_injury_snapshot(self, game_id: str) -> list[dict[str, Any]] | None:
        row = self.db.fetch_one(
            "SELECT MAX(captured_at) AS ts FROM injury_status_snapshots WHERE game_id = ?", (game_id,)
        )
        if not row or not row.get("ts"):
            return None
        rows = self.db.fetch_all(
            "SELECT team, player_name, status FROM injury_status_snapshots WHERE game_id = ? AND captured_at = ?",
            (game_id, row["ts"]),
        )
        return [{"team": r["team"], "name": r["player_name"], "status": r["status"]} for r in rows if r["player_name"]]

    def _store_injury_snapshot(self, game_id: str, captured_at: str, injuries: list[dict[str, Any]]) -> None:
        with self.db.connect() as conn:
            if not injuries:
                # Explicit "empty report" marker so a later report with new absences is a real transition
                conn.execute(
                    "INSERT OR IGNORE INTO injury_status_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f"INJ_{game_id}_{captured_at}_EMPTY", game_id, captured_at, "", "", "NONE", "espn_summary"),
                )
                return
            for inj in injuries:
                conn.execute(
                    "INSERT OR IGNORE INTO injury_status_snapshots VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        f"INJ_{game_id}_{captured_at}_{inj.get('team')}_{inj.get('name')}",
                        game_id,
                        captured_at,
                        str(inj.get("team") or ""),
                        str(inj.get("name") or ""),
                        str(inj.get("status") or ""),
                        "espn_summary",
                    ),
                )

    def scan_pregame_slate(
        self,
        reference_time_utc: datetime | None = None,
        force_scan_all: bool = False,
    ) -> dict[str, Any]:
        """
        Scans all scheduled games today, filters those matching T-2h or T-30m monitoring windows,
        fetches fresh injury reports, evaluates synergy and conformal EV, and records alerts.
        """
        ref_dt = reference_time_utc or datetime.now(timezone.utc)
        if ref_dt.tzinfo is None:
            ref_dt = ref_dt.replace(tzinfo=timezone.utc)

        scheduled_games = self.db.fetch_all(
            """
            SELECT game_id, matchday_date, game_start_time, home_team, away_team, status
            FROM games
            WHERE status = 'SCHEDULED'
            ORDER BY game_start_time ASC
            """
        )

        scanned_games_summary: list[dict[str, Any]] = []
        all_generated_alerts: list[dict[str, Any]] = []

        for game in scheduled_games:
            g_id = game["game_id"]
            m_date = game["matchday_date"]
            start_iso = game["game_start_time"]
            h_team = game["home_team"]
            a_team = game["away_team"]

            window, delta_min = classify_game_window(start_iso, ref_dt)
            is_active_window = force_scan_all or window in ("WINDOW_2H", "WINDOW_30M")

            game_summary: dict[str, Any] = {
                "game_id": g_id,
                "matchup": f"{a_team} @ {h_team}",
                "game_start_time": start_iso,
                "window": window,
                "minutes_to_tipoff": delta_min,
                "monitored": is_active_window,
                "alerts_count": 0,
            }

            if not is_active_window:
                scanned_games_summary.append(game_summary)
                continue

            # Fetch current live odds snapshots
            odds_rows = self.db.fetch_all(
                """
                SELECT odds_id, game_id, provider, market, selection, line_value, decimal_odds,
                       counterpart_decimal_odds, captured_at
                FROM v_observed_odds_snapshots
                WHERE game_id = ? AND market = 'moneyline'
                """,
                (g_id,),
            )

            # Strict Data Integrity: If no genuine observed market odds exist, do not snipe
            if not odds_rows:
                logger.info(f"Skipping sniper scan for game {g_id}: no observed odds found in database.")
                continue

            # Ingest the live ESPN injury report for both teams
            live_injuries: list[dict[str, Any]] = []
            fetched = False
            try:
                espn_id = g_id.split("_")[1] if g_id.startswith("ESPN_") else g_id
                event_ctx = self.espn_adapter._fetch_event_summary_context(espn_id)
                reports = event_ctx.get("injury_reports") or {}
                for t_code in (h_team, a_team):
                    live_injuries.extend(reports.get(t_code, []))
                fetched = bool(event_ctx.get("fetch_ok", False))
            except Exception as exc:
                logger.warning("Injury report fetch failed for %s: %s", g_id, exc)

            if not fetched:
                game_summary["note"] = "NO_INJURY_REPORT"
                scanned_games_summary.append(game_summary)
                continue

            # Previous snapshot = baseline. The first observation of a game only records the baseline:
            # without a previous state there is no "transition", hence no alert.
            cached_injuries = self._latest_injury_snapshot(g_id)
            self._store_injury_snapshot(g_id, ref_dt.strftime("%Y-%m-%dT%H:%M:%SZ"), live_injuries)
            if cached_injuries is None:
                game_summary["note"] = "BASELINE_SNAPSHOT_RECORDED"
                scanned_games_summary.append(game_summary)
                continue

            # Evaluate sniper opportunities
            game_alerts = self.evaluate_game_sniper_opportunity(
                game_id=g_id,
                matchday_date=m_date,
                game_start_time=start_iso,
                home_team=h_team,
                away_team=a_team,
                live_injuries=live_injuries,
                cached_injuries=cached_injuries,
                market_odds=odds_rows,
                window_type=window if not force_scan_all else (window if window in ("WINDOW_2H", "WINDOW_30M") else "FORCE"),
                minutes_to_tipoff=delta_min,
                bankroll_pen=100.0,
            )

            game_summary["alerts_count"] = len(game_alerts)
            scanned_games_summary.append(game_summary)
            all_generated_alerts.extend(game_alerts)

        return {
            "scanned_at_utc": ref_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "total_scheduled": len(scheduled_games),
            "games_in_2h_window": sum(1 for g in scanned_games_summary if g["window"] == "WINDOW_2H"),
            "games_in_30m_window": sum(1 for g in scanned_games_summary if g["window"] == "WINDOW_30M"),
            "total_alerts_emitted": len(all_generated_alerts),
            "games": scanned_games_summary,
            "alerts": all_generated_alerts,
        }
