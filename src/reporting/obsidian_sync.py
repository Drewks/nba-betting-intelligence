"""
Synchronizes the dedicated Obsidian vault with rich markdown notes, DataviewJS dashboards, and provenance metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import load_config
from src.ingestion.sportradar import resolve_nba_season_year
from src.reporting.slate_intelligence import _fmt


def sync_obsidian_vault(
    vault_root: str | Path,
    daily_report_md: str,
    weekly_report_md: str,
    audit_report_md: str,
    metrics: dict[str, Any],
    environment_status: dict[str, Any],
    target_date: str,
) -> dict[str, str]:
    """Populates the dedicated Obsidian vault (`NBA/00-Inbox` through `NBA/09-Reports`)."""
    root = Path(vault_root)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cfg = load_config()
    risk_cfg = cfg.risk
    src_cfg = cfg.sources
    season_yr = resolve_nba_season_year()
    synergy_note = (
        "y la telemetría de posesiones y jugadas de **Synergy Basketball NBA API** (`/synergy/basketball/nba/games` y `/events`)"
        if src_cfg.sportradar_synergy_enabled
        else "(Synergy Basketball desactivado por configuración: `sportradar_synergy_enabled: false`)"
    )
    sr_heading = (
        "## 2. Sportradar NBA API v8 & Synergy Basketball NBA API (`SportradarAdapter`)\n"
        if src_cfg.sportradar_synergy_enabled
        else "## 2. Sportradar NBA API v8 (`SportradarAdapter`)\n"
    )
    min_ev_pct = float(risk_cfg.min_ev_threshold) * 100.0
    max_sel = int(risk_cfg.max_selections_per_matchday)
    if str(risk_cfg.staking_mode).lower() == "fractional_kelly":
        kelly_pct = round(float(risk_cfg.kelly_fraction) * 100.0)
        staking_desc = f"Kelly Fraccional ({kelly_pct}%)"
    else:
        staking_desc = f"Stake fijo S/{float(risk_cfg.base_stake_pen):.2f}"

    active_model_id = str((metrics.get("run_manifest") or {}).get("model_version_id") or load_config().model.version_id)
    files_to_write: dict[str, str] = {
        "00-Inbox/00-System-Status.md": (
            f"---\ndate_generated: {now_str}\nstatus: PAPER_TRADING_ACTIVE\nbankroll_initial: 100.00\n"
            f"current_bankroll_pen: {metrics['current_settled_bankroll_pen']:.2f}\n"
            f"net_profit_pen: {metrics['net_profit_pen']:.2f}\n"
            f"roi_pct: {metrics['roi_pct']:.2f}\n"
            f"mean_clv_pct: {_fmt(metrics.get('mean_clv_pct'), '.2f')}\n"
            f"brier_score: {_fmt(metrics.get('overall_brier_score'))}\n"
            f"market_brier_score: {_fmt(metrics.get('market_brier_score'))}\n"
            f"settled_bets: {metrics['settled_bets_count']}\n---\n"
            "# NBA Betting Intelligence — Inbox Operativo\n\n"
            f"- **Última sincronización**: `{now_str}`\n"
            f"- **Bankroll virtual actual**: `S/{metrics['current_settled_bankroll_pen']:.2f} PEN`\n"
            f"- **Dictamen del auditor**: `{metrics['exit_gates_evaluation']['recommendation']}`\n"
            "- **Dashboard Cuantitativo DataviewJS**: [[01-Dataview-Quant-Dashboard]]\n"
            "- **SGP 'Crea tu Apuesta' RETAbet**: [[02-SGP-Correlated-Parlays]]\n"
        ),
        "00-Inbox/02-SGP-Correlated-Parlays.md": (
            f"---\ndate_generated: {now_str}\ndashboard_type: retabet_sgp_copula_v8\n---\n"
            "# 🎰 Apuestas Correlacionadas SGP (Crea tu Apuesta — RETAbet Perú)\n\n"
            "> [!NOTE] Simulación de Cópula Student-t Multivariada (V8 Fase 3)\n"
            "> Modela la interdependencia estocástica entre resultados de equipo y props de jugadores (PTS, REB, AST, PRA) "
            "para explotar tablas de correlación rígidas en **RETAbet Perú**.\n\n"
            "```dataview\n"
            "TABLE bookmaker AS Casa, game_selection AS Partido, player_name AS Jugador, prop_category AS Mercado, fair_sgp_odds AS \"Cuota Justa\", offered_sgp_odds AS \"Cuota RETAbet\", ev_pct AS \"EV (%)\", kelly_stake_pen AS \"Stake (S/.)\"\n"
            "FROM \"00-Inbox\" OR \"04-Predictions\"\n"
            "SORT ev_pct DESC\n"
            "```\n"
        ),
        "00-Inbox/01-Dataview-Quant-Dashboard.md": (
            f"---\ndate_generated: {now_str}\ndashboard_type: obsidian_dataview_quant_v8\n"
            f"current_bankroll_pen: {metrics['current_settled_bankroll_pen']:.2f}\n"
            f"roi_pct: {metrics['roi_pct']:.2f}\n"
            f"brier_score: {_fmt(metrics.get('overall_brier_score'))}\n---\n"
            "# 📊 Centro de Comando Cuantitativo (Obsidian DataviewJS & Tracker)\n\n"
            "> [!TIP] Plugins recomendados en Obsidian\n"
            "> Instala **Dataview** (habilitando `Enable JavaScript Queries`), **Tracker**, **Charts** y **Obsidian Git** para visualizar las tablas y curvas en tiempo real.\n\n"
            "## 1. KPIs del Portafolio en Soles (DataviewJS)\n\n"
            "```dataviewjs\n"
            "const statusPage = dv.page('00-Inbox/00-System-Status');\n"
            "if (statusPage) {\n"
            "  dv.table(\n"
            "    ['Bankroll (S/.)', 'Beneficio Neto', 'ROI (%)', 'CLV Medio (%)', 'Brier Score', 'Liquidadas'],\n"
            "    [[\n"
            "      'S/ ' + statusPage.current_bankroll_pen,\n"
            "      'S/ ' + statusPage.net_profit_pen,\n"
            "      statusPage.roi_pct + '%',\n"
            "      statusPage.mean_clv_pct + '%',\n"
            "      statusPage.brier_score,\n"
            "      statusPage.settled_bets\n"
            "    ]]\n"
            "  );\n"
            "}\n"
            "```\n\n"
            "## 2. Auditoría de Informes y Modelos (Dataview DQL)\n\n"
            "```dataview\n"
            "TABLE report_type AS Tipo, date_generated AS Fecha, settled_predictions AS Liquidadas, final_verdict AS Dictamen\n"
            "FROM \"09-Reports\" OR \"08-Calibration\"\n"
            "SORT date_generated DESC\n"
            "```\n\n"
            "## 3. Seguimiento Temporal de Calibración y Bankroll (Obsidian Tracker)\n\n"
            "```tracker\n"
            "searchType: frontmatter\n"
            "searchTarget: current_bankroll_pen, roi_pct\n"
            "folder: 00-Inbox\n"
            "line:\n"
            "    title: Evolución del Bankroll (S/. PEN) & ROI (%)\n"
            "    yAxisLabel: Soles (PEN)\n"
            "    lineColor: '#10b981, #38bdf8'\n"
            "```\n"
        ),
        "01-Sources/Data-Sources-and-Limitations.md": (
            f"---\ndate_generated: {now_str}\ncomponent: nba_data_scout\n---\n"
            "# Evaluación de Fuentes de Estadísticas y Cuotas NBA\n\n"
            "## 1. ESPN Public API (`site.api.espn.com`) — Activa sin Credenciales\n"
            "- Proporciona calendario oficial, estados de partido (`SCHEDULED`, `FINAL`), estadísticas de equipo y cuotas pre-partido de `DraftKings` (`moneyline` y `total_points`).\n"
            "- Limitación histórica: en partidos históricos finalizados, `pickcenter` refleja la línea archivada sin historial tick-a-tick; por ello el sistema exige `captured_at < game_start_time` para toda captura en vivo.\n\n"
            f"{sr_heading}"
            f"- Estado: `{environment_status.get('sportradar_status', 'Adaptador implementado; verificar SPORTRADAR_API_KEY en runtime')}`.\n"
            f"- Sincroniza el parte médico oficial de la liga (`league/injuries.json`) y los splits tácticos de los 30 equipos (`seasons/{season_yr}/REG/standings.json`) {synergy_note} usando `SPORTRADAR_API_KEY`.\n\n"
            "## 3. TheOddsAPI Multi-Bookmaker Line Shopping (`TheOddsAPIAdapter`)\n"
            f"- Escanea casas activas en región `{src_cfg.the_odds_api_regions}` y mercados `{src_cfg.the_odds_api_markets}` (`Pinnacle`, `Matchbook`, `Betfair`, `Coolbet`, `Marathon Bet`, `888sport`, complementado con `DraftKings` vía ESPN y caché TTL de `{src_cfg.the_odds_api_cache_ttl_seconds}s`) para elegir la mejor cuota disponible.\n\n"
            "## 4. Playwright + PixelRAG (`visual_researcher`)\n"
            f"- Playwright: `{environment_status.get('playwright_status', 'Verificar estado en runtime')}`.\n"
            f"- PixelRAG: `{environment_status.get('pixelrag_status', 'Pipeline tabular/RAG local (verificar estado en runtime)')}`.\n"
        ),
        "02-Teams/NBA-30-Canonical-Teams.md": (
            f"---\ndate_generated: {now_str}\ntotal_teams: 30\n---\n"
            "# Registro Canónico de Equipos NBA\n\n"
            "Los 30 equipos de la NBA están normalizados a códigos de 3 letras (`ATL`, `BOS`, `BKN`, ..., `WAS`) en `src/ingestion/normalizer.py`.\n"
        ),
        f"03-Games/Matchday-{target_date}.md": (
            f"---\ndate_generated: {now_str}\nmatchday: {target_date}\n---\n"
            f"# Registro de Partidos — Jornada {target_date}\n\n"
            "Consulte el detalle de partidos evaluados y predicciones en `09-Reports/`.\n"
        ),
        f"04-Predictions/Predictions-Summary-{target_date}.md": (
            f"---\ndate_generated: {now_str}\nmodel_versions: [{active_model_id}, model_b_elo_v8, model_c_point_margin_v8, model_d_total_points_v8, model_e_lightgbm_v8, model_g_ml_montecarlo_v8]\n---\n"
            "# Historial Auditable de Predicciones\n\n"
            "- Todas las predicciones están protegidas mediante triggers `BEFORE UPDATE` y `BEFORE DELETE` en SQLite (`data/nba_intelligence.sqlite3`).\n"
            "- Prohibido sobrescribir predicciones o cuotas originales.\n"
        ),
        "05-Paper-Trading/Virtual-Bankroll-Ledger.md": (
            f"---\ndate_generated: {now_str}\ninitial_bankroll_pen: 100.00\ncurrent_bankroll_pen: {metrics['current_settled_bankroll_pen']:.2f}\n---\n"
            "# Libro Mayor de Paper Trading (S/100.00 PEN Virtuales)\n\n"
            f"- **Saldo inicial**: `S/100.00 PEN`\n"
            f"- **Saldo liquidado actual**: `S/{metrics['current_settled_bankroll_pen']:.2f} PEN`\n"
            f"- **Beneficio neto acumulado**: `S/{metrics['net_profit_pen']:+.2f} PEN`\n"
            f"- **Exposición pendiente**: `S/{metrics.get('pending_exposure_pen', 0.0):.2f} PEN`\n"
            f"- **Apuestas liquidadas**: `{metrics['settled_bets_count']}`\n"
            f"- **Reglas activas**: {staking_desc}, máx {max_sel} selecciones/jornada, EV >= {min_ev_pct:.1f}%.\n"
        ),
        "06-Models/Model-Catalog-and-Versions.md": (
            f"---\ndate_generated: {now_str}\n---\n"
            "# Catálogo de Modelos Cuantitativos (Modelos A–G)\n\n"
            "1. **Modelo A (`model_a_baseline_v1`)**: Frecuencia histórica de victoria local y media/desviación de puntos totales.\n"
            "2. **Modelo B (`model_b_elo_v8`)**: Sistema Elo secuencial con ajuste por localía (+65 Elo) y descanso (+12 Elo/día).\n"
            "3. **Modelo C (`model_c_point_margin_v8`)**: Regresión Ridge sobre `Offensive Rating`, `Defensive Rating`, `Net Rating`, `Pace`, descanso y forma reciente.\n"
            "4. **Modelo D (`model_d_total_points_v8`)**: Distribución normal con **covarianza explícita entre marcadores** ($\\text{Var}(H+A) = \\text{Var}(H) + \\text{Var}(A) + 2\\text{Cov}(H,A)$).\n"
            "5. **Modelo E (`model_e_lightgbm_v8`)**: `LightGBM` evaluado estrictamente fuera de muestra mediante validación walk-forward.\n"
            f"6. **Modelo F (`{str((metrics.get('run_manifest') or {}).get('model_version_id') or load_config().model.version_id)}`)**: Meta-Ensemble de Sindicato que combina Modelos B, C, D, E y G en escala log-odds.\n"
            "7. **Modelo G (`model_g_ml_montecarlo_v8`)**: **Simulador Híbrido ML + 10,000 Partidos Monte Carlo por Posesión** (modela `Q1–Q3`, desaceleración por `Blowout/Garbage-Time` en `Q4`, faltas intencionales en los últimos 90s `Clutch Fouling` y prórrogas iterativas `Overtime` + percentiles de simulación `[Q10, Q90]`).\n"
        ),
        "07-Backtesting/Walk-Forward-Backtest-Results.md": weekly_report_md,
        "08-Calibration/Calibration-and-Reliability.md": (
            f"---\ndate_generated: {now_str}\nbrier_score: {_fmt(metrics.get('overall_brier_score'))}\nlog_loss: {_fmt(metrics.get('overall_log_loss'))}\n---\n"
            "# Seguimiento de Calibración Probabilística (`model_calibrator`)\n\n"
            f"- **Brier Score combinado (ensemble calibrado)**: `{_fmt(metrics.get('overall_brier_score'), '.5f', 'n/d')}` (Baseline ingenuo: `{_fmt(metrics.get('baseline_brier_score'), '.5f', 'n/d')}`)\n"
            f"- **Log Loss combinado (ensemble calibrado)**: `{_fmt(metrics.get('overall_log_loss'), '.5f', 'n/d')}` (Baseline ingenuo: `{_fmt(metrics.get('baseline_log_loss'), '.5f', 'n/d')}`)\n"
            f"- **Frente al mercado sin margen (mismos partidos)**: modelo `{_fmt(metrics.get('model_brier_on_market_subset'), '.5f', 'n/d')}` vs mercado `{_fmt(metrics.get('market_brier_score'), '.5f', 'n/d')}`\n"
            "- **Política de recalibración**: Calibración logística (`N >= 30`) e isotónica (`N >= 100`) entrenadas exclusivamente con partidos finalizados antes del timestamp de corte.\n"
        ),
        f"09-Reports/Daily-Report-{target_date}.md": daily_report_md,
        f"09-Reports/Weekly-Report-{target_date}.md": weekly_report_md,
        "09-Reports/Independent-Audit-Report.md": audit_report_md,
    }

    for subdir, prefix in [
        ("03-Games", "Matchday-"),
        ("04-Predictions", "Predictions-Summary-"),
        ("09-Reports", "Daily-Report-"),
        ("09-Reports", "Weekly-Report-"),
    ]:
        folder = root / subdir
        if folder.exists():
            for old_file in folder.glob(f"{prefix}*.md"):
                if old_file.name != f"{prefix}{target_date}.md":
                    old_file.unlink(missing_ok=True)

    written_paths: dict[str, str] = {}
    for rel_path, content in files_to_write.items():
        full_path = root / rel_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        written_paths[rel_path] = str(full_path)

    return written_paths
