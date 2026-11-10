"""
Generates the daily performance and prediction report for NBA operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.storage.db import DatabaseManager


def generate_daily_report(
    db: DatabaseManager,
    target_date: str,
    live_games_summary: dict[str, Any] | None = None,
) -> str:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    games = db.fetch_all("SELECT * FROM games WHERE matchday_date = ? ORDER BY game_start_time", (target_date,))
    preds = db.fetch_all(
        """
        SELECT p.*, g.home_team, g.away_team
        FROM predictions p
        JOIN games g ON p.game_id = g.game_id
        WHERE g.matchday_date = ?
        ORDER BY p.ev_pct DESC
        """,
        (target_date,),
    )
    decisions = db.fetch_all(
        "SELECT * FROM decision_log WHERE matchday_date = ? ORDER BY emitted_at",
        (target_date,),
    )
    bets = db.fetch_all(
        "SELECT * FROM v_observed_simulated_bets WHERE matchday_date = ? ORDER BY emitted_at",
        (target_date,),
    )
    pending_all = db.fetch_all("SELECT * FROM v_observed_simulated_bets WHERE status = 'PENDING'")

    discarded_games = live_games_summary.get("discarded_games", []) if live_games_summary else []
    no_bets = [d for d in decisions if d["decision_type"] == "NO_BET"]

    lines = [
        "---",
        f"date_generated: {now_str}",
        "report_type: daily_report",
        "model_versions: [model_c_point_margin_v1, model_d_total_points_v1]",
        f"period_evaluated: {target_date}",
        f"predictions_count: {len(preds)}",
        "simulation_only: true",
        "---",
        f"# Informe Diario NBA Betting Intelligence — {target_date}",
        "",
        "## 1. Metadatos de Ejecución",
        f"- **Fecha de generación (UTC)**: `{now_str}`",
        f"- **Jornada evaluada**: `{target_date}`",
        "- **Versiones de modelos activas**: `model_c_point_margin_v1` (Moneyline), `model_d_total_points_v1` (Total Points)",
        f"- **Partidos evaluados**: `{len(games)}`",
        f"- **Partidos descartados por falta de datos/cuotas**: `{len(discarded_games)}`",
        f"- **Predicciones emitidas**: `{len(preds)}`",
        f"- **Apuestas simuladas registradas en la jornada**: `{len(bets)}` (límite diario: 3, stake máx: S/1.00 PEN)",
        f"- **Decisiones NO_BET registradas**: `{len(no_bets)}`",
        f"- **Resultados pendientes globales**: `{len(pending_all)}`",
        "",
        "## 2. Partidos Descartados por Falta de Datos o Cuotas",
    ]

    if discarded_games:
        for dg in discarded_games:
            lines.append(f"- `{dg.get('game_id', 'UNKNOWN')}`: {dg.get('reason', 'Datos esenciales o cuotas no disponibles')}")
    else:
        lines.append("- Ningún partido descartado por falta de variables esenciales en el lote validado.")

    lines.extend([
        "",
        "## 3. Predicciones Disponibles, Cuotas y Valor Esperado (Top 10 por EV)",
        "",
        "| Partido | Mercado | Selección | Línea | Cuota Dec. | Prob. Implícita Bruta | Prob. Estimada (Cal.) | EV (%) | Proveedor |",
        "| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- |",
    ])

    for p in preds[:10]:
        match_label = f"{p['away_team']} @ {p['home_team']}"
        line_str = f"{p['line_value']}" if p["line_value"] is not None else "—"
        lines.append(
            f"| `{match_label}` | `{p['market']}` | **{p['selection']}** | {line_str} | "
            f"{p['decimal_odds_used']:.3f} | {p['implied_prob_gross']:.4f} | "
            f"{p['calibrated_probability']:.4f} | {p['ev_pct']:+.2f}% | `{p['odds_provider']}` |"
        )

    lines.extend([
        "",
        "## 4. Apuestas Simuladas (Paper Trading S/100 PEN) y Resultados Pendientes",
        "",
        "| Bet ID | Partido | Mercado | Selección | Cuota | Prob. Est. | EV (%) | Stake Virtual | Estado | Beneficio Neto |",
        "| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: | :--- | ---: |",
    ])

    if bets:
        for b in bets:
            prof_str = f"S/{b['net_profit_pen']:+.2f}" if b["net_profit_pen"] is not None else "PENDIENTE"
            lines.append(
                f"| `{b['bet_id']}` | `{b['game_id']}` | `{b['market']}` | **{b['selection']}** | "
                f"{b['decimal_odds']:.3f} | {b['estimated_prob']:.4f} | {b['estimated_ev'] * 100:+.2f}% | "
                f"S/{b['stake_pen']:.2f} | `{b['status']}` | {prof_str} |"
            )
    else:
        lines.append("| — | — | — | **NO BET** | — | — | — | S/0.00 | `NO_BET` | S/0.00 |")

    lines.extend([
        "",
        "## 5. Registro de Decisiones NO_BET (Muestra de Control)",
    ])
    for nb in no_bets[:8]:
        lines.append(
            f"- `{nb['game_id']}` (`{nb['market']}` - `{nb['selection']}`): **NO_BET** [{nb['reason_code']}] — {nb['reason_detail']}"
        )

    lines.extend([
        "",
        "## 6. Limitaciones Documentadas",
        "- Todas las operaciones son estrictamente simuladas sobre el bankroll virtual de **S/100.00 PEN**.",
        "- Cuando una fuente externa no proporciona cuota verificable antes del inicio del partido (`captured_at < game_start_time`), el sistema bloquea el cálculo de EV y registra `NO_BET`.",
    ])

    return "\n".join(lines) + "\n"
