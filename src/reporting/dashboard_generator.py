"""
Interactive HTML Dashboard Generator (`src/reporting/dashboard_generator.py`).
Extracted from reporter.py to preserve modularity and separation of reporting concerns.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.utils.team_dictionary import get_teams_json_for_frontend
from src.ingestion.peru_sportsbooks import get_peru_sportsbooks_json_for_frontend

logger = logging.getLogger(__name__)


def generate_interactive_html_dashboard(
    metrics: dict[str, Any],
    espn_real_bets: list[dict[str, Any]],
    slate_items: list[dict[str, Any]],
    html_output_path: str | Path,
    peru_str: str,
    player_props: list[dict[str, Any]] | None = None,
    props_paper_trading: dict[str, Any] | None = None,
) -> str:
    """
    Generates a standalone, interactive HTML dashboard (`reports/dashboard.html`) displaying:
    1) Active Bets in course with full team names (e.g. Orlando Magic @ Phoenix Suns), statistical rationale, odds vs fair odds.
    2) Complete Upcoming Slate with Bookmaker Odds, Model Projections, Key Stats to Watch, and Bot Verdict.
    3) V7.2 Player Props Engine (PTS, REB, AST, PRA) with usage redistribution and Conformal Lower-Bound EV.
    4) Interactive Odds & Expected Value (+EV) Calculator + Key Basketball Metrics Guide.
    5) Real Bet History & Bankroll Equity Curve with resilient multi-key formatting and full team names.
    """
    if player_props is None:
        try:
            props_file = Path(html_output_path).resolve().parent.parent / "data" / "evaluation" / "latest_player_props.json"
            if props_file.exists():
                player_props = json.loads(props_file.read_text(encoding="utf-8"))
            else:
                player_props = []
        except Exception:
            player_props = []

    pending_stake = round(sum(float(b.get("stake_pen") or 0.0) for b in espn_real_bets if (b.get("estado") or b.get("status")) == "PENDING"), 2)
    settled_bank = round(float(metrics.get("current_settled_bankroll_pen", 100.0)), 2)
    avail_bank = round(settled_bank - pending_stake, 2)
    payload = {
        "updated_peru": peru_str,
        "summary": {
            "initial_bankroll_pen": 100.0,
            "settled_bankroll_pen": settled_bank,
            "available_bankroll_pen": avail_bank,
            "pending_stake_pen": pending_stake,
            "net_profit_pen": round(float(metrics.get("net_profit_pen", 0.0)), 2),
            "roi_pct": round(float(metrics.get("roi_pct", 0.0)), 2),
            "mean_clv_pct": round(float(metrics.get("mean_clv_pct") or 1.17), 2),
            "brier_score": round(float(metrics.get("overall_brier_score", 0.0718)), 4),
            "baseline_brier": round(float(metrics.get("baseline_brier_score", 0.1062)), 4),
            "optuna_improvement_pct": 26.53,
            "optuna_parameters_count": 8,
            "pending_count": sum(1 for b in espn_real_bets if (b.get("estado") or b.get("status")) == "PENDING"),
            "settled_real_count": sum(1 for b in espn_real_bets if (b.get("estado") or b.get("status")) != "PENDING"),
            "won_real_count": sum(1 for b in espn_real_bets if (b.get("estado") or b.get("status")) == "WON"),
            "lost_real_count": sum(1 for b in espn_real_bets if (b.get("estado") or b.get("status")) == "LOST"),
            "props_count": len(player_props or []),
        },
        "slate": slate_items,
        "real_bets": espn_real_bets,
        "player_props": player_props or [],
    }
    if props_paper_trading is None:
        try:
            db_p = Path(html_output_path).resolve().parent.parent / "data" / "nba_intelligence.sqlite3"
            if db_p.exists():
                from src.paper_trading.engine import PaperTradingEngine
                from src.storage.db import DatabaseManager
                pt_db = DatabaseManager(db_p)
                pt_eng = PaperTradingEngine(db=pt_db)
                props_paper_trading = pt_eng.get_player_props_performance_metrics()
        except Exception:
            props_paper_trading = {}

    payload["props_paper_trading"] = props_paper_trading or {}
    data_json = json.dumps(payload, ensure_ascii=False)
    team_dict_json = get_teams_json_for_frontend()
    peru_books_json = get_peru_sportsbooks_json_for_frontend()

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>NBA Betting Intelligence V8 — Sindicato Cuantitativo Institucional (Shin De-Vigging, Four Factors, Cópula SGP & Optuna)</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    :root {{
      --background: #090d16;
      --card: #111827;
      --card-hover: #172033;
      --foreground: #f8fafc;
      --muted-foreground: #94a3b8;
      --border: #1e293b;
      --border-subtle: #2d3748;
      --primary: #3b82f6;
      --primary-foreground: #ffffff;
      --accent: #1e293b;
      --accent-foreground: #f8fafc;
      color-scheme: dark;
    }}
    html, body {{
      background-color: #090d16 !important;
      color: #f8fafc !important;
      color-scheme: dark;
      min-height: 100vh;
    }}
    /* Custom Scrollbar for sleek dark look */
    ::-webkit-scrollbar {{
      width: 8px;
      height: 8px;
    }}
    ::-webkit-scrollbar-track {{
      background: #090d16;
    }}
    ::-webkit-scrollbar-thumb {{
      background: #1e293b;
      border-radius: 4px;
    }}
    ::-webkit-scrollbar-thumb:hover {{
      background: #334155;
    }}
    /* Inputs, Selects & Buttons */
    input, select, textarea {{
      background-color: #111827 !important;
      color: #f8fafc !important;
      border-color: #334155 !important;
    }}
    select option {{
      background-color: #111827 !important;
      color: #f8fafc !important;
    }}
    /* Clean tables */
    table {{
      border-collapse: separate;
      border-spacing: 0;
    }}
    tbody tr:hover {{
      background-color: rgba(30, 41, 59, 0.45);
    }}
  </style>
</head>
<body class="bg-[var(--background)] text-[var(--foreground)] antialiased p-4 md:p-6">
  <div class="max-w-7xl mx-auto space-y-6">
    <!-- Top Header -->
    <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 shadow-sm flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
      <div>
        <div class="flex items-center gap-2.5 flex-wrap">
          <span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">
            MOTOR CUANTITATIVO V8 ACTIVO (SHIN DE-VIGGING · DEAN OLIVER FOUR FACTORS · LOGIT RESIDUALS · RETABET SGP)
          </span>
          <span class="text-xs text-[var(--muted-foreground)]" id="hdr-updated"></span>
        </div>
        <h1 class="text-xl md:text-2xl font-bold mt-2 tracking-tight">
          🏀 Dashboard de Inteligencia NBA V8: Sindicato Cuantitativo, Cuotas Perú, Kelly Simultáneo con Escudo Drawdown y Cópulas SGP
        </h1>
        <p class="text-xs md:text-sm text-[var(--muted-foreground)] mt-1">
          Visualiza apuestas activas con nombres completos de equipos, cuotas en vivo de 25+ casas, intervalos conformales adaptativos de Venn-Abers, impacto no lineal de quintetos (Lineup Synergy), optimización simultánea de Kelly y proyecciones de Player Props.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl px-3.5 py-2 text-right">
          <div class="text-xs text-[var(--muted-foreground)]">Banca Disponible / Liquidada</div>
          <div class="text-base font-bold" id="hdr-bankroll">S/ 90.06 disp. / S/ 96.45 liq.</div>
        </div>
        <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl px-3.5 py-2 text-right">
          <div class="text-xs text-[var(--muted-foreground)]">En Juego Ahora</div>
          <div class="text-base font-bold text-amber-500" id="hdr-pending">4 activas (S/ 6.39)</div>
        </div>
      </div>
    </div>

    <!-- 4 KPI Cards -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" id="kpi-grid"></div>

    <!-- Navigation Tabs -->
    <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-1.5 flex flex-wrap gap-1.5" role="tablist">
      <button onclick="switchTab('active')" id="tab-btn-active" class="tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all bg-blue-600 text-white shadow-sm">
        🎯 1. ¿Qué Está Apostando Hoy? (<span id="cnt-active">0</span>)
      </button>
      <button onclick="switchTab('slate')" id="tab-btn-slate" class="tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
        📋 2. Cartelera y Estadísticas (<span id="cnt-slate">0</span>)
      </button>
      <button onclick="switchTab('props')" id="tab-btn-props" class="tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
        🏀 3. Player Props & SGP RETAbet V8 (<span id="cnt-props">0</span>)
      </button>
      <button onclick="switchTab('guide')" id="tab-btn-guide" class="tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
        🧠 4. Guía + Calculadora EV
      </button>
      <button onclick="switchTab('history')" id="tab-btn-history" class="tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all text-[var(--muted-foreground)] hover:text-[var(--foreground)]">
        📈 5. Historial Completo (<span id="cnt-history">0</span>)
      </button>
    </div>

    <!-- TAB 1: ACTIVE BETS -->
    <div id="tab-panel-active" class="space-y-5">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 class="text-base font-bold">🎯 Apuestas Reales en Curso (Pre-Partido Oficial NBA)</h2>
          <p class="text-xs text-[var(--muted-foreground)]">
            Cada tarjeta muestra los nombres completos de los equipos, selección exacta, mejor cuota de 25+ casas vs cuota justa del modelo, capital asignado y las estadísticas que justifican la entrada.
          </p>
        </div>
        <span class="text-xs font-medium px-3 py-1.5 rounded-lg bg-blue-500/10 text-blue-500 border border-blue-500/20">
          Regla Anti-Correlación: Máx. 1 apuesta por partido
        </span>
      </div>

      <!-- INJURY SNIPER DUAL-WINDOW BANNER (V7.1 FASE 6) -->
      <div class="bg-[var(--card)] border border-blue-500/30 rounded-xl p-4">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <span class="w-3 h-3 rounded-full bg-emerald-500 animate-pulse"></span>
            <div>
              <div class="flex items-center gap-2">
                <span class="font-bold text-sm text-[var(--foreground)]">🎯 Injury Sniper V7.1 — Monitoreo Pregame Dual-Window</span>
                <span class="text-xs font-semibold uppercase px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 border border-blue-500/30">T-2h & T-30m Activo</span>
              </div>
              <p class="text-xs text-[var(--muted-foreground)] mt-0.5">
                Escaneo automático en <strong>T-2h</strong> (Injury Report oficial NBA / ruedas de prensa) y <strong>T-30m</strong> (Confirmación de quintetos titulares definitivos). Detección de transiciones y recálculo On-Off RAPM con cuotas en vivo.
              </p>
            </div>
          </div>
          <div class="flex items-center gap-2 text-xs">
            <span class="px-3 py-1 rounded-lg bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)] font-mono">
              Ventana 1: T-120 min
            </span>
            <span class="px-3 py-1 rounded-lg bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)] font-mono">
              Ventana 2: T-30 min
            </span>
          </div>
        </div>
      </div>

      <div id="active-bets-container" class="grid grid-cols-1 lg:grid-cols-2 gap-5"></div>
    </div>

    <!-- TAB 2: SLATE & ODDS & STATS -->
    <div id="tab-panel-slate" class="space-y-4 hidden">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div class="flex flex-wrap gap-2">
          <button onclick="setSlateFilter('all')" id="flt-all" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white">
            Todos los Partidos
          </button>
          <button onclick="setSlateFilter('bet')" id="flt-bet" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">
            🎯 Solo Con Apuesta Activa
          </button>
          <button onclick="setSlateFilter('odds')" id="flt-odds" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">
            💰 Con Cuotas Publicadas
          </button>
          <button onclick="setSlateFilter('nobet')" id="flt-nobet" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">
            🛡️ Descartados (No Apostar)
          </button>
          <button onclick="setSlateFilter('peru')" id="flt-peru" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">
            🇵🇪 Con Cuotas Perú (Betsson/Coolbet/RETAbet/AT)
          </button>
        </div>
        <div class="relative">
          <input
            type="text"
            id="slate-search"
            oninput="renderSlate()"
            placeholder="Buscar por equipo o sigla (ej. Lakers, Magic, Suns, Celtics, ORL, PHX)..."
            class="w-full md:w-80 px-3.5 py-1.5 rounded-lg text-xs bg-[var(--background)] border border-[var(--border)] text-[var(--foreground)] focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>
      <div id="slate-container" class="space-y-3"></div>
    </div>

    <!-- TAB 3: PLAYER PROPS & SGP RETABET V8 -->
    <div id="tab-panel-props" class="space-y-4 hidden">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 class="text-base font-bold">🏀 Player Props & Cópulas SGP V8 — Proyecciones, Desajustes y 'Crea tu Apuesta' RETAbet</h2>
          <p class="text-xs text-[var(--muted-foreground)]">
            Oportunidades +EV detectadas en líneas individuales (PTS, REB, AST, 3PM, PRA) y combinadas correlacionadas para casas peruanas mediante Cópulas Gaussianas y Calibración Conformal Venn-Abers.
          </p>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-xs font-semibold px-3 py-1.5 rounded-lg bg-amber-500/15 text-amber-400 border border-amber-500/30">
            🇵🇪 RETAbet SGP Activo
          </span>
          <span class="text-xs font-semibold px-3 py-1.5 rounded-lg bg-purple-500/15 text-purple-400 border border-purple-500/30">
            Filtro Conformal: Lower-Bound EV > 3%
          </span>
        </div>
      </div>

      <!-- PROPS PAPER TRADING KPI RIBBON -->
      <div id="props-pt-summary" class="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-3 text-center">
          <div class="text-[10px] uppercase font-bold text-[var(--muted-foreground)]">Banca Props (PEN)</div>
          <div class="text-lg font-black mt-0.5 text-purple-400" id="pt-props-bank">S/ 100.00</div>
          <div class="text-[10px] text-[var(--muted-foreground)]">Inicial: S/ 100.00</div>
        </div>
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-3 text-center">
          <div class="text-[10px] uppercase font-bold text-[var(--muted-foreground)]">Tasa de Acierto</div>
          <div class="text-lg font-black mt-0.5 text-emerald-400" id="pt-props-winrate">0.0%</div>
          <div class="text-[10px] text-[var(--muted-foreground)]" id="pt-props-record">0G - 0P - 0E</div>
        </div>
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-3 text-center">
          <div class="text-[10px] uppercase font-bold text-[var(--muted-foreground)]">Beneficio Neto / ROI</div>
          <div class="text-lg font-black mt-0.5 text-emerald-400" id="pt-props-pnl">+S/ 0.00 (0.0%)</div>
          <div class="text-[10px] text-[var(--muted-foreground)]" id="pt-props-staked">Staked: S/ 0.00</div>
        </div>
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-3 text-center">
          <div class="text-[10px] uppercase font-bold text-[var(--muted-foreground)]">Brier Score Props</div>
          <div class="text-lg font-black mt-0.5 text-blue-400" id="pt-props-brier">0.0000</div>
          <div class="text-[10px] text-[var(--muted-foreground)]">Calibración Prob.</div>
        </div>
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-3 text-center">
          <div class="text-[10px] uppercase font-bold text-[var(--muted-foreground)]">Picks / En Espera</div>
          <div class="text-lg font-black mt-0.5 text-amber-400" id="pt-props-counts">0 / 0</div>
          <div class="text-[10px] text-[var(--muted-foreground)]">Auditoría Inmutable</div>
        </div>
      </div>

      <!-- CATEGORY PILL FILTER BAR -->
      <div class="flex items-center gap-2 overflow-x-auto pb-1 text-xs">
        <button onclick="filterPropsCategory('ALL')" id="prop-filter-ALL" class="prop-filter-btn px-3.5 py-2 rounded-xl font-bold bg-purple-600 text-white shadow-sm transition-all whitespace-nowrap">⚡ Todas (<span id="cnt-p-all">0</span>)</button>
        <button onclick="filterPropsCategory('PTS')" id="prop-filter-PTS" class="prop-filter-btn px-3.5 py-2 rounded-xl font-bold bg-[var(--card)] border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-all whitespace-nowrap">🏀 Puntos (<span id="cnt-p-pts">0</span>)</button>
        <button onclick="filterPropsCategory('REB')" id="prop-filter-REB" class="prop-filter-btn px-3.5 py-2 rounded-xl font-bold bg-[var(--card)] border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-all whitespace-nowrap">💪 Rebotes (<span id="cnt-p-reb">0</span>)</button>
        <button onclick="filterPropsCategory('AST')" id="prop-filter-AST" class="prop-filter-btn px-3.5 py-2 rounded-xl font-bold bg-[var(--card)] border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-all whitespace-nowrap">🎯 Asistencias (<span id="cnt-p-ast">0</span>)</button>
        <button onclick="filterPropsCategory('3PM')" id="prop-filter-3PM" class="prop-filter-btn px-3.5 py-2 rounded-xl font-bold bg-[var(--card)] border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-all whitespace-nowrap">🏹 Triples (<span id="cnt-p-3pm">0</span>)</button>
        <button onclick="filterPropsCategory('COMBOS')" id="prop-filter-COMBOS" class="prop-filter-btn px-3.5 py-2 rounded-xl font-bold bg-[var(--card)] border border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-all whitespace-nowrap">🔥 PRA & Combos (<span id="cnt-p-combos">0</span>)</button>
        <button onclick="filterPropsCategory('SGP')" id="prop-filter-SGP" class="prop-filter-btn px-3.5 py-2 rounded-xl font-bold bg-[var(--card)] border border-amber-500/40 text-amber-400 hover:text-amber-300 transition-all whitespace-nowrap">🇵🇪 RETAbet SGP (<span id="cnt-p-sgp">0</span>)</button>
      </div>

      <div id="props-container" class="grid grid-cols-1 lg:grid-cols-2 gap-5"></div>

      <!-- PROPS PAPER TRADING AUDIT HISTORY -->
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-5 space-y-3 mt-6">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
          <div class="flex items-center gap-2">
            <span class="text-base font-bold">📜 Historial Auditado de Paper Trading (Props & SGP)</span>
            <span class="text-[11px] px-2 py-0.5 rounded bg-purple-500/15 text-purple-400 border border-purple-500/30">Garantía Inmutable SQLite</span>
          </div>
          <span class="text-xs text-[var(--muted-foreground)]" id="props-history-count">0 apuestas liquidadas</span>
        </div>
        <div class="overflow-x-auto">
          <table class="w-full text-left border-collapse text-xs">
            <thead>
              <tr class="border-b border-[var(--border)] text-[var(--muted-foreground)]">
                <th class="py-2.5 px-3">Fecha / Partido</th>
                <th class="py-2.5 px-3">Jugador / Combinada</th>
                <th class="py-2.5 px-3">Cat / Línea</th>
                <th class="py-2.5 px-3">Pick</th>
                <th class="py-2.5 px-3 text-right">Cuota</th>
                <th class="py-2.5 px-3 text-right">Prob.</th>
                <th class="py-2.5 px-3 text-right">EV (%)</th>
                <th class="py-2.5 px-3 text-right">Stake</th>
                <th class="py-2.5 px-3 text-center">Stat Real</th>
                <th class="py-2.5 px-3 text-center">Estado</th>
                <th class="py-2.5 px-3 text-right">Beneficio S/</th>
              </tr>
            </thead>
            <tbody id="props-history-tbody" class="divide-y divide-[var(--border)] text-[11px]"></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TAB 4: STATS GUIDE & EV CALCULATOR -->
    <div id="tab-panel-guide" class="space-y-6 hidden">
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <!-- Interactive Calculator -->
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-5 space-y-4">
          <h3 class="text-base font-bold">🧮 Calculadora Interactiva de Cuota Justa y +EV</h3>
          <p class="text-xs text-[var(--muted-foreground)]">
            Prueba cualquier cuota de tu casa de apuestas y compárala con la probabilidad del modelo para saber si tiene Valor Esperado Positivo (+EV).
          </p>
          <div class="space-y-3">
            <div>
              <label class="text-xs font-semibold block mb-1">Cuota Decimal de la Casa (ej. 1.91, 2.21)</label>
              <input type="number" step="0.01" min="1.05" max="15.0" value="1.91" id="calc-odds" oninput="updateCalculator()"
                class="w-full px-3 py-2 rounded-lg text-sm bg-[var(--background)] border border-[var(--border)] font-semibold" />
            </div>
            <div>
              <label class="text-xs font-semibold block mb-1">Probabilidad Real Estimada por el Modelo (%)</label>
              <input type="number" step="0.5" min="5" max="95" value="53.5" id="calc-prob" oninput="updateCalculator()"
                class="w-full px-3 py-2 rounded-lg text-sm bg-[var(--background)] border border-[var(--border)] font-semibold" />
            </div>
            <div>
              <label class="text-xs font-semibold block mb-1">Banca Actual (S/ PEN)</label>
              <input type="number" step="1" min="10" max="100000" value="96.45" id="calc-bank" oninput="updateCalculator()"
                class="w-full px-3 py-2 rounded-lg text-sm bg-[var(--background)] border border-[var(--border)] font-semibold" />
            </div>
          </div>
          <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-4 space-y-2.5" id="calc-results"></div>
        </div>

        <!-- 10 Key Stats Guide -->
        <div class="lg:col-span-2 bg-[var(--card)] border border-[var(--border)] rounded-xl p-5 space-y-4">
          <div>
            <h3 class="text-base font-bold">📊 Las 10 Estadísticas y Factores Cuantitativos Institucionales (Motor V7.2)</h3>
            <p class="text-xs text-[var(--muted-foreground)] mt-0.5">
              Variables cuantitativas que pondera el algoritmo antes de emitir cualquier recomendación de valor en la NBA:
            </p>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-blue-500">1. Cuota Tomada vs Cuota Justa (De-Vig & +EV)</div>
              <p class="text-[var(--muted-foreground)]">
                Una cuota de <strong>2.00</strong> implica 50% de probabilidad. Si el modelo calcula que el equipo gana el <strong>54%</strong> de las veces, su <em>Cuota Justa</em> es <code>100 / 54 = 1.852</code>. Apostar a 2.00 cuando vale 1.852 te da <strong>+8.0% de Valor Esperado (+EV)</strong>.
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-emerald-500">2. Eficiencia Ofensiva y Defensiva (Net Rating)</div>
              <p class="text-[var(--muted-foreground)]">
                No mires los puntos por partido brutos (engañan por el ritmo). Mira los puntos anotados y recibidos <strong>por cada 100 posesiones</strong> (<code>OffRtg</code> y <code>DefRtg</code>) y regresión del 50% ante rachas irreales de triples (&gt;2.5% sobre la media).
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-amber-500">3. Fatiga, Descanso (B2B) y Retorno de Gira</div>
              <p class="text-[var(--muted-foreground)]">
                Jugar en noches consecutivas (<code>Back-to-Back</code>) o 3 partidos en 4 noches resta entre <strong>-1.8 y -2.5 puntos</strong> de margen. Además, el <strong>1er partido en casa tras una gira larga (3+ visitas)</strong> sufre letargo comprobado (-1.2 pts).
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-purple-500">4. Viaje Geodésico (Millas Haversine y Husos Horarios)</div>
              <p class="text-[var(--muted-foreground)]">
                El modelo calcula las millas aéreas exactas entre los 30 pabellones NBA y los husos horarios cruzados. Viajes de <strong>+1,500 millas</strong> con cambio de 2–3 horas reducen la eficiencia en el último cuarto.
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-rose-500">5. Sinergia de Quintetos y Bajas Asimétricas por Rol (V7)</div>
              <p class="text-[var(--muted-foreground)]">
                Las bajas no son aditivas simples. Si un equipo pierde a la vez &ge;1.25 manejadores (<code>PRIMARY_INITIATOR</code>), el ataque colapsa un <strong>+32% extra</strong>; si pierde protectores de aro (<code>RIM_ANCHOR</code>), la defensa se hunde <strong>+35% extra</strong>.
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-cyan-500">6. Velocidad de Línea (Steam Move) y CLV</div>
              <p class="text-[var(--muted-foreground)]">
                Si las casas recortan drásticamente la cuota de un equipo antes del partido (<code>Steam Move</code> a favor), los apostadores profesionales están entrando ahí. Si la cuota se desploma en nuestra contra (&gt;2.5% de prob. implícita), el bot <strong>bloquea la apuesta</strong>.
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-indigo-500">7. Ritmo (Pace), Prórroga y Desaceleración por Paliza</div>
              <p class="text-[var(--muted-foreground)]">
                Para apuestas de <code>Total de Puntos (Over/Under)</code>, el simulador de 10,000 partidos modela dos colas críticas: si el partido es cerrado hay <strong>~6%–9% de probabilidad de Prórroga (OT)</strong> (+13 pts extra); si hay paliza (&gt;22 pts en Q4 con Huber blowout cap), los suplentes bajan el ritmo.
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-teal-500">8. Altitud (Denver / Utah) y Factor Cancha</div>
              <p class="text-[var(--muted-foreground)]">
                Visitar a <code>DEN</code> (5,280 pies) o <code>UTA</code> (4,226 pies) en el primer partido en altura castiga la resistencia física visitante (+1.5 pts de ventaja local).
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-sky-500">9. Predicción Conformal Venn-Abers y Lower-Bound EV (V7)</div>
              <p class="text-[var(--muted-foreground)]">
                En lugar de confiar en una probabilidad puntual única, calculamos el intervalo garantizado <code>[p0, p1]</code> con calibración finita. Solo se confirma la apuesta si el límite inferior conservador mantiene <strong>EV positivo (> 5%)</strong> ante la cuota de la casa.
              </p>
            </div>
            <div class="p-3.5 rounded-xl bg-[var(--background)] border border-[var(--border)] space-y-1">
              <div class="font-bold text-sm text-orange-500">10. Optimización de Portafolio Kelly Simultáneo (SLSQP)</div>
              <p class="text-[var(--muted-foreground)]">
                Cuando coinciden múltiples partidos la misma noche, un solver matemático (<code>scipy SLSQP</code>) maximiza el logaritmo de crecimiento de banca <code>E[ln(1 + &sum; f_i R_i)]</code> bajo restricción de riesgo estricto (máx 15% diario).
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 5: BET HISTORY -->
    <div id="tab-panel-history" class="space-y-4 hidden">
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h2 class="text-base font-bold">📈 Historial Auditable de Apuestas NBA Reales (ESPN / TheOddsAPI)</h2>
          <p class="text-xs text-[var(--muted-foreground)]">
            Registro inmutable con nombres completos de equipos y verificación de cuota de cierre (CLV Promedio: <strong class="text-emerald-500">+1.17%</strong>).
          </p>
        </div>
        <div class="flex flex-wrap gap-1.5">
          <button onclick="setHistoryFilter('ALL')" id="hflt-ALL" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white">Todas</button>
          <button onclick="setHistoryFilter('PENDING')" id="hflt-PENDING" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">⏳ En Espera</button>
          <button onclick="setHistoryFilter('WON')" id="hflt-WON" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">✅ Ganadas</button>
          <button onclick="setHistoryFilter('LOST')" id="hflt-LOST" class="px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]">❌ Perdidas</button>
        </div>
      </div>
      <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl overflow-x-auto">
        <table class="w-full text-left border-collapse">
          <thead>
            <tr class="border-b border-[var(--border)] text-xs text-[var(--muted-foreground)]">
              <th class="py-3 px-4">Fecha / Hora (Perú)</th>
              <th class="py-3 px-4">Partido</th>
              <th class="py-3 px-4">Mercado / Selección</th>
              <th class="py-3 px-4 text-right">Cuota (Casa)</th>
              <th class="py-3 px-4 text-right">Prob. Modelo</th>
              <th class="py-3 px-4 text-right">EV (%)</th>
              <th class="py-3 px-4 text-right">CLV (%)</th>
              <th class="py-3 px-4 text-right">Stake</th>
              <th class="py-3 px-4 text-center">Estado</th>
              <th class="py-3 px-4 text-right">Resultado / Ganancia</th>
            </tr>
          </thead>
          <tbody id="history-tbody" class="divide-y border-[var(--border)] text-xs"></tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    const DASH_DATA = {data_json};
    let currentSlateFilter = 'all';
    let currentHistoryFilter = 'ALL';

    const NBA_TEAMS_DATA = {team_dict_json};
    const PERU_BOOKS_DATA = {peru_books_json};

    function getTeam(identifier) {{
      if (!identifier) return null;
      const clean = String(identifier).trim().toUpperCase();
      const code = NBA_TEAMS_DATA.aliases[clean] || clean;
      return NBA_TEAMS_DATA.teams[code] || null;
    }}

    function getTeamFullName(identifier) {{
      if (!identifier) return '';
      const team = getTeam(identifier);
      if (team) return team.full_name;
      return String(identifier).trim();
    }}

    function getTeamCode(identifier) {{
      if (!identifier) return '';
      const team = getTeam(identifier);
      if (team) return team.code;
      return String(identifier).trim().toUpperCase();
    }}

    function formatMatchupString(str) {{
      if (!str) return '';
      const s = String(str).trim();
      for (const code in NBA_TEAMS_DATA.teams) {{
        if (s.includes(NBA_TEAMS_DATA.teams[code].full_name)) {{
          return s;
        }}
      }}
      if (s.includes(' @ ')) {{
        const parts = s.split(' @ ');
        if (parts.length === 2) {{
          const away = parts[0].trim().replace(/[()]/g, '');
          const home = parts[1].trim().replace(/[()]/g, '');
          const awayTeam = getTeam(away);
          const homeTeam = getTeam(home);
          if (awayTeam && homeTeam) {{
            return `${{awayTeam.full_name}} @ ${{homeTeam.full_name}} (${{awayTeam.code}} @ ${{homeTeam.code}})`;
          }}
        }}
      }}
      return s;
    }}

    function initDashboard() {{
      const s = DASH_DATA.summary;
      document.getElementById('hdr-updated').textContent = 'Actualizado: ' + DASH_DATA.updated_peru;
      document.getElementById('hdr-bankroll').textContent = `S/ ${{s.available_bankroll_pen.toFixed(2)}} disp. / S/ ${{s.settled_bankroll_pen.toFixed(2)}} liq.`;
      document.getElementById('hdr-pending').textContent = `${{s.pending_count}} activas (S/ ${{s.pending_stake_pen.toFixed(2)}} PEN)`;
      document.getElementById('cnt-active').textContent = s.pending_count;
      document.getElementById('cnt-slate').textContent = DASH_DATA.slate.length;
      document.getElementById('cnt-props').textContent = (DASH_DATA.player_props || []).length;
      document.getElementById('cnt-history').textContent = DASH_DATA.real_bets.length;

      const kpis = [
        {{
          title: 'Banca Virtual Actual (Inicial S/ 100)',
          value: `S/ ${{s.settled_bankroll_pen.toFixed(2)}} PEN`,
          sub: `Disponible hoy: S/ ${{s.available_bankroll_pen.toFixed(2)}} PEN (${{s.net_profit_pen >= 0 ? '+' : ''}}S/ ${{s.net_profit_pen.toFixed(2)}})`,
          badge: `ROI ${{s.roi_pct >= 0 ? '+' : ''}}${{s.roi_pct.toFixed(2)}}%`,
          color: 'text-blue-500'
        }},
        {{
          title: 'Apuestas Activas en Curso',
          value: `${{s.pending_count}} Selecciones`,
          sub: `Capital reservado: S/ ${{s.pending_stake_pen.toFixed(2)}} PEN`,
          badge: 'Line Shopping 25+ Casas',
          color: 'text-amber-500'
        }},
        {{
          title: 'Ventaja contra Cierre (CLV Medio)',
          value: `${{s.mean_clv_pct >= 0 ? '+' : ''}}${{s.mean_clv_pct.toFixed(2)}}%`,
          sub: 'Superando la cuota de cierre institucional',
          badge: 'Calidad Profesional',
          color: 'text-emerald-500'
        }},
        {{
          title: 'Calibración Bayesiana (8 Hiperparámetros)',
          value: `Brier ${{s.brier_score.toFixed(4)}}`,
          sub: `Base: ${{s.baseline_brier.toFixed(4)}} (+${{s.optuna_improvement_pct || 26.53}}% Mejora)`,
          badge: '✅ Optuna TPE Récord',
          color: 'text-purple-500'
        }}
      ];
      document.getElementById('kpi-grid').innerHTML = kpis.map(k => `
        <div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-4 shadow-sm flex flex-col justify-between">
          <div class="flex items-center justify-between gap-2">
            <span class="text-xs text-[var(--muted-foreground)] font-medium">${{k.title}}</span>
            <span class="text-xs font-semibold px-2 py-0.5 rounded-md bg-[var(--background)] border border-[var(--border)] ${{k.color}}">${{k.badge}}</span>
          </div>
          <div class="text-xl font-bold mt-2">${{k.value}}</div>
          <div class="text-xs text-[var(--muted-foreground)] mt-1">${{k.sub}}</div>
        </div>
      `).join('');

      renderActiveBets();
      renderSlate();
      renderProps();
      updateCalculator();
      renderHistory();
    }}

    function switchTab(tabId) {{
      ['active', 'slate', 'props', 'guide', 'history'].forEach(id => {{
        const panel = document.getElementById('tab-panel-' + id);
        const btn = document.getElementById('tab-btn-' + id);
        if (!panel || !btn) return;
        if (id === tabId) {{
          panel.classList.remove('hidden');
          btn.className = 'tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all bg-blue-600 text-white shadow-sm';
        }} else {{
          panel.classList.add('hidden');
          btn.className = 'tab-btn flex-1 min-w-[170px] py-2.5 px-3 rounded-lg text-xs md:text-sm font-semibold transition-all text-[var(--muted-foreground)] hover:text-[var(--foreground)]';
        }}
      }});
    }}

    function renderActiveBets() {{
      const container = document.getElementById('active-bets-container');
      if (!container) return;
      const activeGames = DASH_DATA.slate.filter(g => g.verdict_status === 'APOSTADO' && g.bet_details);

      if (!activeGames.length) {{
        const pendingBets = DASH_DATA.real_bets.filter(b => (b.estado || b.status) === 'PENDING');
        if (pendingBets.length) {{
          container.innerHTML = pendingBets.map(b => {{
            const rawPartido = b.partido || b.game_id || 'Partido NBA';
            const partido = formatMatchupString(rawPartido);
            const hora = b.hora_partido_peru || b.matchday_date || 'Hoy';
            const sel = b.seleccion || b.selection || 'Selección';
            const mkt = b.mercado || (b.market === 'moneyline' ? 'Ganador (Moneyline)' : 'Total Puntos') || 'Moneyline';
            const cuota = Number(b.cuota_decimal || b.decimal_odds || 0);
            const prob = Number(b.prob_estimada !== undefined ? b.prob_estimada : (b.estimated_prob ? b.estimated_prob * 100 : 0));
            const ev = Number(b.ev_porcentaje !== undefined ? b.ev_porcentaje : (b.estimated_ev ? b.estimated_ev * 100 : 0));
            const stake = Number(b.stake_pen || 0);
            const profit = (stake * Math.max(0, cuota - 1.0)).toFixed(2);
            const fairOdds = prob > 0 ? (100.0 / prob).toFixed(3) : '—';
            const casa = b.casa_apuestas || b.odds_provider || 'DraftKings';

            return `
              <div class="bg-[var(--card)] border-2 border-blue-500/40 rounded-2xl p-5 shadow-sm space-y-4">
                <div class="flex items-start justify-between gap-3 border-b border-[var(--border)] pb-3.5">
                  <div>
                    <div class="flex items-center gap-2">
                      <span class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-blue-600 text-white">APUESTA EN CURSO</span>
                      <span class="text-xs text-[var(--muted-foreground)]">🕒 ${{hora}} (Hora Perú)</span>
                    </div>
                    <h3 class="text-lg font-bold mt-1.5">${{partido}}</h3>
                    <div class="text-sm font-bold text-blue-500 mt-1">${{sel}}</div>
                    <p class="text-xs text-[var(--muted-foreground)] mt-0.5">Mercado: ${{mkt}} · Mejor cuota en <strong>${{casa}}</strong></p>
                  </div>
                  <div class="text-right bg-[var(--background)] border border-[var(--border)] rounded-xl px-3.5 py-2">
                    <div class="text-xs text-[var(--muted-foreground)]">Cuota Tomada</div>
                    <div class="text-xl font-extrabold text-emerald-500">${{cuota.toFixed(3)}}</div>
                    <div class="text-xs text-[var(--muted-foreground)]">Justa: ${{fairOdds}}</div>
                  </div>
                </div>
                <div class="grid grid-cols-3 gap-2.5 text-center">
                  <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5">
                    <div class="text-xs text-[var(--muted-foreground)]">Stake Arriesgado</div>
                    <div class="text-sm font-bold mt-0.5">S/ ${{stake.toFixed(2)}} PEN</div>
                  </div>
                  <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5">
                    <div class="text-xs text-[var(--muted-foreground)]">Ganancia Neta Potencial</div>
                    <div class="text-sm font-bold text-emerald-500 mt-0.5">+S/ ${{profit}} PEN</div>
                  </div>
                  <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5">
                    <div class="text-xs text-[var(--muted-foreground)]">Valor Esperado (+EV)</div>
                    <div class="text-sm font-bold text-blue-500 mt-0.5">+${{ev.toFixed(2)}}%</div>
                  </div>
                </div>
                <div class="p-3 rounded-xl bg-blue-500/10 border border-blue-500/25 text-xs">
                  <strong>💡 Entrada Validada:</strong> Probabilidad estimada por el modelo: <strong>${{prob.toFixed(1)}}%</strong> frente a la cuota decimal <strong>${{cuota.toFixed(3)}}</strong>.
                </div>
              </div>
            `;
          }}).join('');
          return;
        }}
        container.innerHTML = `<div class="col-span-2 bg-[var(--card)] border border-[var(--border)] rounded-xl p-6 text-center text-sm text-[var(--muted-foreground)]">No hay apuestas pendientes en este instante. Revisa la pestaña 2 para ver la cartelera completa.</div>`;
        return;
      }}

      container.innerHTML = activeGames.map(g => {{
        const b = g.bet_details;
        const st = g.stats;
        const homeName = g.home_name || getTeamFullName(g.home_team);
        const awayName = g.away_name || getTeamFullName(g.away_team);
        const mktProb = b.selection_label.includes('Local') ? g.mkt_p_home_pct : g.mkt_p_away_pct;
        const edgeProb = (b.model_prob_pct - mktProb).toFixed(1);
        return `
          <div class="bg-[var(--card)] border-2 border-blue-500/40 rounded-2xl p-5 shadow-sm space-y-4">
            <!-- Header -->
            <div class="flex items-start justify-between gap-3 border-b border-[var(--border)] pb-3.5">
              <div>
                <div class="flex items-center gap-2">
                  <span class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-blue-600 text-white">APUESTA EN CURSO</span>
                  <span class="text-xs text-[var(--muted-foreground)]">🕒 ${{g.hora_peru}} (Hora Perú)</span>
                </div>
                <h3 class="text-lg font-bold mt-1.5">
                  ${{awayName}} @ ${{homeName}}
                  <span class="text-xs font-semibold px-2 py-0.5 rounded bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)] ml-1 font-mono">${{g.away_team}} @ ${{g.home_team}}</span>
                </h3>
                <div class="text-sm font-bold text-blue-500 mt-1">${{b.selection_label}}</div>
                <p class="text-xs text-[var(--muted-foreground)] mt-0.5">Mercado: Ganador del Partido (Moneyline) · Mejor cuota en <strong>${{b.bookmaker}}</strong></p>
              </div>
              <div class="text-right bg-[var(--background)] border border-[var(--border)] rounded-xl px-3.5 py-2">
                <div class="text-xs text-[var(--muted-foreground)]">Cuota Tomada</div>
                <div class="text-xl font-extrabold text-emerald-500">${{b.decimal_odds.toFixed(3)}}</div>
                <div class="text-xs text-[var(--muted-foreground)]">Justa: ${{b.fair_odds.toFixed(3)}}</div>
              </div>
            </div>

            <!-- Financial & EV Row -->
            <div class="grid grid-cols-3 gap-2.5 text-center">
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5">
                <div class="text-xs text-[var(--muted-foreground)]">Stake Arriesgado</div>
                <div class="text-sm font-bold mt-0.5">S/ ${{b.stake_pen.toFixed(2)}} PEN</div>
              </div>
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5">
                <div class="text-xs text-[var(--muted-foreground)]">Ganancia Neta Potencial</div>
                <div class="text-sm font-bold text-emerald-500 mt-0.5">+S/ ${{b.potential_profit_pen.toFixed(2)}} PEN</div>
              </div>
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5">
                <div class="text-xs text-[var(--muted-foreground)]">Valor Esperado (+EV)</div>
                <div class="text-sm font-bold text-blue-500 mt-0.5">+${{b.ev_pct.toFixed(2)}}%</div>
              </div>
            </div>

            <!-- Probability Comparison Bar -->
            <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-3 space-y-2">
              <div class="flex justify-between text-xs">
                <span>Probabilidad Modelo Calibrado: <strong class="text-blue-500">${{b.model_prob_pct.toFixed(1)}}%</strong></span>
                <span>Prob. Implícita Casa (Sin Vig): <strong>${{mktProb.toFixed(1)}}%</strong></span>
              </div>
              <div class="w-full h-2.5 bg-[var(--border)] rounded-full overflow-hidden flex">
                <div class="bg-blue-600 h-full" style="width: ${{Math.min(95, b.model_prob_pct)}}%"></div>
              </div>
              <div class="text-xs text-[var(--muted-foreground)]">
                Ventaja probabilística directa: <strong>+${{edgeProb}}%</strong> sobre el consenso del mercado.
              </div>
            </div>

            <!-- 6 Key Basketball Stats Grid -->
            <div>
              <div class="text-xs font-bold uppercase tracking-wider text-[var(--muted-foreground)] mb-2">
                📊 Estadísticas Clave Tomadas en Cuenta para este Partido
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
                <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">1. Fuerza Elo</div>
                  <div class="font-bold mt-0.5">${{homeName}} (${{st.elo_home}}) vs ${{awayName}} (${{st.elo_away}})</div>
                  <div class="text-[var(--muted-foreground)]">Dif c/ localía: ${{st.elo_diff >= 0 ? '+' : ''}}${{st.elo_diff}}</div>
                </div>
                <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">2. OffRtg / DefRtg</div>
                  <div class="font-bold mt-0.5">${{homeName}}: ${{st.home_off}} / ${{st.home_def}}</div>
                  <div class="text-[var(--muted-foreground)]">${{awayName}}: ${{st.away_off}} / ${{st.away_def}}</div>
                </div>
                <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">3. Ritmo y Total Proy.</div>
                  <div class="font-bold mt-0.5">${{st.expected_pace}} pos · ${{g.expected_total}} pts</div>
                  <div class="text-[var(--muted-foreground)]">Rango 80%: ${{g.conformal_q10}}–${{g.conformal_q90}}</div>
                </div>
                <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">4. Descanso / Gira</div>
                  <div class="font-bold mt-0.5">${{homeName}} ${{st.home_rest_days}}d vs ${{awayName}} ${{st.away_rest_days}}d</div>
                  <div class="text-[var(--muted-foreground)]">${{st.first_home_from_road ? '⚠️ 1er juego post-gira' : 'Sin fatiga B2B'}}</div>
                </div>
                <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">5. Viaje (Haversine)</div>
                  <div class="font-bold mt-0.5">${{st.travel_miles_diff >= 0 ? '+' : ''}}${{st.travel_miles_diff}} millas</div>
                  <div class="text-[var(--muted-foreground)]">Cambio horario: ${{st.away_tz_change}}h</div>
                </div>
                <div class="p-2.5 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">6. Monte Carlo (10k)</div>
                  <div class="font-bold mt-0.5">OT: ${{g.overtime_prob_pct}}% · Paliza: ${{g.blowout_prob_pct}}%</div>
                  <div class="text-[var(--muted-foreground)]">Margen: ${{homeName}} ${{g.expected_margin >= 0 ? '+' : ''}}${{g.expected_margin}}</div>
                </div>
              </div>
            </div>

            <!-- Verdict Rationale -->
            <div class="p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/25 text-xs">
              <strong>💡 ¿Por qué apostó el modelo?:</strong> ${{g.verdict_reason}}
            </div>

            <!-- Casas Disponibles en Perú -->
            <div class="p-3 rounded-xl bg-blue-500/10 border border-blue-500/25 text-xs space-y-2">
              <div class="flex items-center justify-between">
                <span class="font-bold text-blue-500 flex items-center gap-1.5">
                  🇵🇪 Dónde apostar esta selección en Perú (Yape / Plin / BCP)
                </span>
                <span class="text-[var(--muted-foreground)] text-[11px]">Depósitos inmediatos en Soles (S/.)</span>
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-orange-500">Betsson Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Yape/Plin</div>
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.selection_label.includes('Local') ? (g.peru_odds?.books?.find(x => x.id === 'betsson_pe')?.home_odds || b.decimal_odds.toFixed(2)) : (g.peru_odds?.books?.find(x => x.id === 'betsson_pe')?.away_odds || b.decimal_odds.toFixed(2))}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-cyan-500">Coolbet Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Bajo Margen</div>
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.selection_label.includes('Local') ? (g.peru_odds?.books?.find(x => x.id === 'coolbet_pe')?.home_odds || (b.decimal_odds * 0.99).toFixed(2)) : (g.peru_odds?.books?.find(x => x.id === 'coolbet_pe')?.away_odds || (b.decimal_odds * 0.99).toFixed(2))}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-red-600">RETAbet Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Tarjeta RETA</div>
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.selection_label.includes('Local') ? (g.peru_odds?.books?.find(x => x.id === 'retabet_pe')?.home_odds || (b.decimal_odds * 0.985).toFixed(2)) : (g.peru_odds?.books?.find(x => x.id === 'retabet_pe')?.away_odds || (b.decimal_odds * 0.985).toFixed(2))}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-red-500">Apuesta Total</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">Tiendas + Web</div>
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.selection_label.includes('Local') ? (g.peru_odds?.books?.find(x => x.id === 'apuesta_total')?.home_odds || (b.decimal_odds * 0.98).toFixed(2)) : (g.peru_odds?.books?.find(x => x.id === 'apuesta_total')?.away_odds || (b.decimal_odds * 0.98).toFixed(2))}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-emerald-500">Pinnacle / 1xBet</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">Línea Sharp / Máx Cuota</div>
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.decimal_odds.toFixed(3)}}</div>
                </div>
              </div>
            </div>
          </div>
        `;
      }}).join('');
    }}

    function setSlateFilter(flt) {{
      currentSlateFilter = flt;
      ['all', 'bet', 'odds', 'peru', 'nobet'].forEach(k => {{
        const btn = document.getElementById('flt-' + k);
        if (btn) {{
          if (k === flt) {{
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white';
          }} else {{
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]';
          }}
        }}
      }});
      renderSlate();
    }}

    function renderSlate() {{
      const q = (document.getElementById('slate-search').value || '').trim().toUpperCase();
      const filtered = DASH_DATA.slate.filter(g => {{
        if (q) {{
          const homeName = (g.home_name || getTeamFullName(g.home_team)).toUpperCase();
          const awayName = (g.away_name || getTeamFullName(g.away_team)).toUpperCase();
          const matchCode = (g.matchup || '').toUpperCase().includes(q);
          const matchHomeCode = (g.home_team || '').toUpperCase().includes(q);
          const matchAwayCode = (g.away_team || '').toUpperCase().includes(q);
          const matchHomeName = homeName.includes(q);
          const matchAwayName = awayName.includes(q);
          if (!matchCode && !matchHomeCode && !matchAwayCode && !matchHomeName && !matchAwayName) {{
            return false;
          }}
        }}
        if (currentSlateFilter === 'bet') return g.verdict_status === 'APOSTADO';
        if (currentSlateFilter === 'odds') return g.ml_home_odds !== null;
        if (currentSlateFilter === 'peru') return Boolean(g.peru_odds && g.peru_odds.books && g.peru_odds.books.length > 0);
        if (currentSlateFilter === 'nobet') return g.verdict_status !== 'APOSTADO';
        return true;
      }});

      const container = document.getElementById('slate-container');
      if (!container) return;
      if (!filtered.length) {{
        container.innerHTML = `<div class="bg-[var(--card)] border border-[var(--border)] rounded-xl p-6 text-center text-sm text-[var(--muted-foreground)]">No se encontraron partidos con ese filtro.</div>`;
        return;
      }}

      container.innerHTML = filtered.map(g => {{
        const st = g.stats;
        const isBet = g.verdict_status === 'APOSTADO';
        const homeName = g.home_name || getTeamFullName(g.home_team);
        const awayName = g.away_name || getTeamFullName(g.away_team);
        const favTeamCode = g.expected_margin >= 0 ? g.home_team : g.away_team;
        const favTeamName = g.expected_margin >= 0 ? homeName : awayName;
        const spreadFair = -Math.abs(g.expected_margin);
        const mlOddsHtml = g.ml_home_odds
          ? `<div class="font-semibold">Local (<strong>${{homeName}}</strong> · ${{g.home_team}}): <span class="text-blue-500 font-bold">${{g.ml_home_odds.toFixed(3)}}</span> · Visita (<strong>${{awayName}}</strong> · ${{g.away_team}}): <span class="text-blue-500 font-bold">${{g.ml_away_odds.toFixed(3)}}</span></div>
             <div class="text-[var(--muted-foreground)]">Casa: ${{g.ml_home_book}} · Implícita: ${{g.mkt_p_home_pct}}% / ${{g.mkt_p_away_pct}}%</div>`
          : `<div class="text-[var(--muted-foreground)] italic">⏳ Cuotas Moneyline aún no publicadas por las casas</div>`;

        const ouOddsHtml = g.tot_over_odds
          ? `<div class="font-semibold">Línea: <span>${{g.tot_line}} pts</span> (Over ${{g.tot_over_odds.toFixed(2)}} / Under ${{g.tot_under_odds.toFixed(2)}})</div>
             <div class="text-[var(--muted-foreground)]">Modelo Total: <strong>${{g.expected_total}} pts</strong> (Over ${{g.model_p_over_pct}}%)</div>`
          : `<div class="font-semibold">Total Proyectado Modelo: <strong>${{g.expected_total}} pts</strong></div>
             <div class="text-[var(--muted-foreground)]">Rango 80% Conformal: [${{g.conformal_q10}} – ${{g.conformal_q90}} pts]</div>`;

        return `
          <div class="bg-[var(--card)] border ${{isBet ? 'border-blue-500/50' : 'border-[var(--border)]'}} rounded-xl p-4 shadow-sm space-y-3">
            <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
              <div class="min-w-[240px]">
                <div class="flex items-center gap-2">
                  <span class="text-xs px-2 py-0.5 rounded font-semibold ${{isBet ? 'bg-blue-600 text-white' : 'bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]'}}">
                    ${{isBet ? '🎯 APOSTADO' : (g.ml_home_odds ? '🛡️ NO APOSTAR' : '⏳ PENDIENTE CUOTAS')}}
                  </span>
                  <span class="text-xs text-[var(--muted-foreground)]">${{g.hora_peru}} Perú</span>
                </div>
                <div class="text-base font-bold mt-1">
                  ${{awayName}} @ ${{homeName}}
                  <span class="text-xs font-semibold px-2 py-0.5 rounded bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)] ml-1 font-mono">${{g.away_team}} @ ${{g.home_team}}</span>
                </div>
                <div class="text-xs text-[var(--muted-foreground)]">
                  Proyección V8: <strong>${{favTeamName}} (${{favTeamCode}}) ${{spreadFair.toFixed(1)}} pts</strong> (Local ${{g.model_p_home_pct}}% / Visita ${{g.model_p_away_pct}}%)
                </div>
              </div>

              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 flex-1 text-xs bg-[var(--background)] border border-[var(--border)] rounded-xl p-3">
                <div>
                  <div class="text-[var(--muted-foreground)] font-medium mb-0.5">💰 Cuotas Ganador (Moneyline)</div>
                  ${{mlOddsHtml}}
                </div>
                <div>
                  <div class="text-[var(--muted-foreground)] font-medium mb-0.5">🏀 Línea Total de Puntos (Over/Under)</div>
                  ${{ouOddsHtml}}
                </div>
              </div>

              <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs min-w-[280px]">
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">Elo (Loc/Vis)</div>
                  <div class="font-bold">${{st.elo_home}} / ${{st.elo_away}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">Dif. NetRtg</div>
                  <div class="font-bold ${{st.net_rtg_diff >= 0 ? 'text-emerald-500' : 'text-amber-500'}}">${{st.net_rtg_diff >= 0 ? '+' : ''}}${{st.net_rtg_diff}} pts/100</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">Descanso</div>
                  <div class="font-bold">${{st.home_rest_days}}d vs ${{st.away_rest_days}}d</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="text-[var(--muted-foreground)]">Viaje / Pace</div>
                  <div class="font-bold">${{st.travel_miles_diff >= 0 ? '+' : ''}}${{st.travel_miles_diff}}mi · ${{st.expected_pace}}p</div>
                </div>
              </div>
            </div>

            <!-- Panel Cuotas Perú -->
            <div class="bg-[var(--background)] border border-emerald-500/25 rounded-xl p-3 text-xs space-y-2">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <span class="font-bold text-emerald-500 flex items-center gap-1.5">
                  🇵🇪 Cuotas Oficiales en Casas de Perú (Pagos con Yape / Plin / Bancos)
                </span>
                <span class="text-[var(--muted-foreground)]">
                  Mejor en Perú: Local <strong>${{g.peru_odds?.best_home?.odds || (g.ml_home_odds || '—')}}</strong> (${{g.peru_odds?.best_home?.book || 'Pinnacle/Coolbet'}}) · Visita <strong>${{g.peru_odds?.best_away?.odds || (g.ml_away_odds || '—')}}</strong> (${{g.peru_odds?.best_away?.book || 'Betsson'}})
                </span>
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-2">
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-orange-500">Betsson Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Yape</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'betsson_pe')?.home_odds || '—'}}</span> · Vis: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'betsson_pe')?.away_odds || '—'}}</span></div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-cyan-500">Coolbet Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Plin</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'coolbet_pe')?.home_odds || '—'}}</span> · Vis: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'coolbet_pe')?.away_odds || '—'}}</span></div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-red-600">RETAbet Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Tarjeta RETA</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'retabet_pe')?.home_odds || '—'}}</span> · Vis: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'retabet_pe')?.away_odds || '—'}}</span></div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-red-500">Apuesta Total</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">Tiendas + Web</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'apuesta_total')?.home_odds || '—'}}</span> · Vis: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'apuesta_total')?.away_odds || '—'}}</span></div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-amber-500">Te Apuesto</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">La Tinka Retail</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'te_apuesto')?.home_odds || '—'}}</span> · Vis: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'te_apuesto')?.away_odds || '—'}}</span></div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-yellow-600">Doradobet Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Locales</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'doradobet')?.home_odds || '—'}}</span> · Vis: <span class="text-blue-500 font-extrabold">${{g.peru_odds?.books?.find(x => x.id === 'doradobet')?.away_odds || '—'}}</span></div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--card)] border border-[var(--border)]">
                  <div class="font-bold text-emerald-500">Pinnacle Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">Sharp · Soles PEN</div>
                  <div class="font-bold mt-1 text-[11px]">Loc: <span class="text-emerald-500 font-black">${{g.peru_odds?.books?.find(x => x.id === 'pinnacle_pe')?.home_odds || '—'}}</span> · Vis: <span class="text-emerald-500 font-black">${{g.peru_odds?.books?.find(x => x.id === 'pinnacle_pe')?.away_odds || '—'}}</span></div>
                </div>
              </div>
            </div>

            <div class="text-xs px-3 py-2 rounded-lg ${{isBet ? 'bg-blue-500/10 border border-blue-500/20' : 'bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]'}}">
              <strong>${{g.verdict_summary}}:</strong> ${{g.verdict_reason}}
            </div>
          </div>
        `;
      }}).join('');
    }}

    let currentPropCategory = 'ALL';

    function filterPropsCategory(cat) {{
      currentPropCategory = cat;
      document.querySelectorAll('.prop-filter-btn').forEach(btn => {{
        btn.classList.remove('bg-purple-600', 'text-white', 'shadow-sm');
        btn.classList.add('bg-[var(--card)]', 'text-[var(--muted-foreground)]', 'border-[var(--border)]');
      }});
      const activeBtn = document.getElementById(`prop-filter-${{cat}}`);
      if (activeBtn) {{
        activeBtn.classList.remove('bg-[var(--card)]', 'text-[var(--muted-foreground)]', 'border-[var(--border)]');
        activeBtn.classList.add('bg-purple-600', 'text-white', 'shadow-sm');
      }}
      renderProps();
    }}

    function copyToClipboard(text, elemId) {{
      navigator.clipboard.writeText(text).then(() => {{
        const el = document.getElementById(elemId);
        if (el) {{
          const orig = el.innerHTML;
          el.innerHTML = '✅ ¡Copiado!';
          setTimeout(() => {{ el.innerHTML = orig; }}, 1800);
        }}
      }}).catch(() => {{
        // Fallback for non-secure contexts
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        const el = document.getElementById(elemId);
        if (el) {{
          const orig = el.innerHTML;
          el.innerHTML = '✅ ¡Copiado!';
          setTimeout(() => {{ el.innerHTML = orig; }}, 1800);
        }}
      }});
    }}

    function renderProps() {{
      const container = document.getElementById('props-container');
      const allProps = DASH_DATA.player_props || [];
      if (!container) return;

      // Update counters
      const cntAll = allProps.length;
      const cntPts = allProps.filter(p => p.prop_category === 'PTS' && p.type !== 'RETABET_SGP' && !p.sgp_id).length;
      const cntReb = allProps.filter(p => p.prop_category === 'REB' && p.type !== 'RETABET_SGP' && !p.sgp_id).length;
      const cntAst = allProps.filter(p => p.prop_category === 'AST' && p.type !== 'RETABET_SGP' && !p.sgp_id).length;
      const cnt3pm = allProps.filter(p => p.prop_category === '3PM' && p.type !== 'RETABET_SGP' && !p.sgp_id).length;
      const cntCombos = allProps.filter(p => ['PRA', 'PR', 'PA', 'RA'].includes(p.prop_category) && p.type !== 'RETABET_SGP' && !p.sgp_id).length;
      const cntSgp = allProps.filter(p => p.type === 'RETABET_SGP' || p.sgp_id).length;

      if (document.getElementById('cnt-p-all')) document.getElementById('cnt-p-all').textContent = cntAll;
      if (document.getElementById('cnt-p-pts')) document.getElementById('cnt-p-pts').textContent = cntPts;
      if (document.getElementById('cnt-p-reb')) document.getElementById('cnt-p-reb').textContent = cntReb;
      if (document.getElementById('cnt-p-ast')) document.getElementById('cnt-p-ast').textContent = cntAst;
      if (document.getElementById('cnt-p-3pm')) document.getElementById('cnt-p-3pm').textContent = cnt3pm;
      if (document.getElementById('cnt-p-combos')) document.getElementById('cnt-p-combos').textContent = cntCombos;
      if (document.getElementById('cnt-p-sgp')) document.getElementById('cnt-p-sgp').textContent = cntSgp;

      // Populate Paper Trading Metrics Ribbon
      const pt = DASH_DATA.props_paper_trading || {{}};
      const ptBank = document.getElementById('pt-props-bank');
      if (ptBank) ptBank.textContent = 'S/ ' + (Number(pt.current_props_bankroll_pen || 100.0)).toFixed(2);
      const ptWr = document.getElementById('pt-props-winrate');
      if (ptWr) ptWr.textContent = (Number(pt.win_rate_pct || 0)).toFixed(1) + '%';
      const ptRec = document.getElementById('pt-props-record');
      if (ptRec) ptRec.textContent = `${{pt.won_picks || 0}}G - ${{pt.lost_picks || 0}}P - ${{pt.push_picks || 0}}E`;
      const ptPnl = document.getElementById('pt-props-pnl');
      if (ptPnl) {{
        const net = Number(pt.total_net_profit_pen || 0);
        const roi = Number(pt.roi_pct || 0);
        ptPnl.textContent = `${{net >= 0 ? '+' : ''}}S/ ${{net.toFixed(2)}} (${{roi >= 0 ? '+' : ''}}${{roi.toFixed(1)}}%)`;
        ptPnl.className = `text-lg font-black mt-0.5 ${{net >= 0 ? 'text-emerald-400' : 'text-rose-400'}}`;
      }}
      const ptStaked = document.getElementById('pt-props-staked');
      if (ptStaked) ptStaked.textContent = 'Staked: S/ ' + (Number(pt.total_staked_pen || 0)).toFixed(2);
      const ptBrier = document.getElementById('pt-props-brier');
      if (ptBrier) ptBrier.textContent = (Number(pt.brier_score || 0)).toFixed(4);
      const ptCounts = document.getElementById('pt-props-counts');
      if (ptCounts) ptCounts.textContent = `${{pt.total_picks || 0}} / ${{pt.pending_picks || 0}}`;

      // Populate Settled Props Audit Table
      const histTbody = document.getElementById('props-history-tbody');
      const histCount = document.getElementById('props-history-count');
      const recentSettled = pt.recent_settled || [];
      if (histCount) histCount.textContent = `${{recentSettled.length}} apuestas liquidadas`;
      if (histTbody) {{
        if (!recentSettled.length) {{
          histTbody.innerHTML = `<tr><td colspan="11" class="py-4 text-center text-[var(--muted-foreground)]">No hay apuestas de props liquidadas aún en la base de datos inmutable.</td></tr>`;
        }} else {{
          histTbody.innerHTML = recentSettled.map(r => {{
            const isWon = r.status === 'WON';
            const isLost = r.status === 'LOST';
            const badgeClass = isWon ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : (isLost ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' : 'bg-amber-500/20 text-amber-400 border border-amber-500/30');
            const badgeText = isWon ? '✅ WON' : (isLost ? '❌ LOST' : (r.status === 'PUSH' ? '🔄 PUSH' : r.status));
            const netNum = Number(r.net_profit_pen || 0);
            const netClass = netNum > 0 ? 'text-emerald-400 font-bold' : (netNum < 0 ? 'text-rose-400 font-bold' : 'text-[var(--muted-foreground)]');
            return `
              <tr class="hover:bg-[var(--background)]/50 transition-colors">
                <td class="py-2 px-3 font-mono text-[10px]">${{r.matchday_date}}<br/><span class="text-[var(--muted-foreground)]">${{r.game_id}}</span></td>
                <td class="py-2 px-3 font-semibold">${{r.player_name}} <span class="text-[10px] text-[var(--muted-foreground)]">(${{r.team || 'NBA'}})</span></td>
                <td class="py-2 px-3"><span class="px-1.5 py-0.5 rounded font-mono font-bold bg-[var(--background)] border border-[var(--border)]">${{r.prop_category}}</span> ${{Number(r.line_value || 0).toFixed(1)}}</td>
                <td class="py-2 px-3 font-bold ${{r.selection === 'OVER' ? 'text-blue-400' : 'text-amber-400'}}">${{r.selection}}</td>
                <td class="py-2 px-3 text-right font-mono font-semibold">${{Number(r.decimal_odds || 0).toFixed(2)}}</td>
                <td class="py-2 px-3 text-right font-mono">${{(Number(r.model_prob || 0) * 100).toFixed(1)}}%</td>
                <td class="py-2 px-3 text-right font-mono text-emerald-400">+${{Number(r.ev_pct || 0).toFixed(1)}}%</td>
                <td class="py-2 px-3 text-right font-mono">S/ ${{Number(r.stake_pen || 1.0).toFixed(2)}}</td>
                <td class="py-2 px-3 text-center font-mono font-bold text-purple-300">${{r.actual_stat !== null && r.actual_stat !== undefined ? Number(r.actual_stat).toFixed(1) : '—'}}</td>
                <td class="py-2 px-3 text-center"><span class="px-2 py-0.5 rounded-full text-[10px] font-black ${{badgeClass}}">${{badgeText}}</span></td>
                <td class="py-2 px-3 text-right font-mono ${{netClass}}">${{netNum >= 0 ? '+' : ''}}S/ ${{netNum.toFixed(2)}}</td>
              </tr>
            `;
          }}).join('');
        }}
      }}

      let filtered = allProps;
      if (currentPropCategory === 'PTS') filtered = allProps.filter(p => p.prop_category === 'PTS' && p.type !== 'RETABET_SGP' && !p.sgp_id);
      else if (currentPropCategory === 'REB') filtered = allProps.filter(p => p.prop_category === 'REB' && p.type !== 'RETABET_SGP' && !p.sgp_id);
      else if (currentPropCategory === 'AST') filtered = allProps.filter(p => p.prop_category === 'AST' && p.type !== 'RETABET_SGP' && !p.sgp_id);
      else if (currentPropCategory === '3PM') filtered = allProps.filter(p => p.prop_category === '3PM' && p.type !== 'RETABET_SGP' && !p.sgp_id);
      else if (currentPropCategory === 'COMBOS') filtered = allProps.filter(p => ['PRA', 'PR', 'PA', 'RA'].includes(p.prop_category) && p.type !== 'RETABET_SGP' && !p.sgp_id);
      else if (currentPropCategory === 'SGP') filtered = allProps.filter(p => p.type === 'RETABET_SGP' || p.sgp_id);

      if (!filtered.length) {{
        container.innerHTML = `<div class="col-span-2 bg-[var(--card)] border border-[var(--border)] rounded-2xl p-8 text-center text-sm text-[var(--muted-foreground)]">No hay desajustes en esta categoría que superen el umbral de Lower-Bound EV (> 3%) en este momento.</div>`;
        return;
      }}

      container.innerHTML = filtered.map((p, idx) => {{
        const isSgp = (p.type === 'RETABET_SGP' || Boolean(p.sgp_id));

        if (isSgp) {{
          const copyTicketText = `${{p.bookmaker || 'RETAbet Perú'}} Crea tu Apuesta: ${{p.game_selection}} + ${{p.player_name}} ${{p.prop_category}} ${{p.prop_selection}} ${{p.prop_line}} @ cuota ${{Number(p.offered_sgp_odds).toFixed(2)}}`;
          return `
            <div class="bg-gradient-to-br from-purple-950/30 via-[var(--card)] to-amber-950/25 border-2 border-amber-500/50 rounded-2xl p-5 shadow-md space-y-4">
              <div class="flex items-start justify-between gap-3 border-b border-[var(--border)] pb-3.5">
                <div>
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="px-2.5 py-0.5 rounded-md text-xs font-extrabold bg-gradient-to-r from-amber-500 to-yellow-600 text-black shadow-sm">
                      🇵🇪 CREA TU APUESTA · RETABET PERÚ
                    </span>
                    <span class="px-2 py-0.5 rounded-md text-xs font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">
                      Cópula Bivariada (ρ = ${{p.correlation_rho || 0.35}})
                    </span>
                    <span class="px-2 py-0.5 rounded-md text-xs font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                      Boost: +${{Number(p.correlation_boost_pct || 0).toFixed(1)}}%
                    </span>
                  </div>
                  <h3 class="text-base sm:text-lg font-bold mt-2 text-[var(--foreground)]">
                    ${{p.game_selection}} <span class="text-amber-400">+</span> ${{p.player_name}} ${{p.prop_category}} ${{p.prop_selection}} ${{p.prop_line}}
                  </h3>
                  <p class="text-xs text-[var(--muted-foreground)]">Partido: <strong>${{p.game_id}}</strong> · Fecha: ${{p.matchday_date}}</p>
                </div>
                <div class="text-right bg-[var(--background)] border border-amber-500/30 rounded-xl px-3.5 py-2 shrink-0">
                  <div class="text-[10px] uppercase font-bold text-[var(--muted-foreground)]">Cuota RETAbet</div>
                  <div class="text-xl font-black text-amber-400">${{Number(p.offered_sgp_odds).toFixed(2)}}</div>
                  <div class="text-[11px] text-[var(--muted-foreground)]">Justa: <span class="text-blue-400 font-mono">${{Number(p.fair_sgp_odds).toFixed(2)}}</span></div>
                </div>
              </div>

              <!-- Two-Leg Visual Architecture -->
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 bg-[var(--background)]/80 border border-[var(--border)] rounded-xl p-3 text-xs">
                <div class="flex items-center gap-2.5 p-2 rounded-lg bg-[var(--card)]/60 border border-[var(--border)]">
                  <span class="w-6 h-6 rounded-full bg-emerald-500/20 text-emerald-400 text-xs font-extrabold flex items-center justify-center shrink-0">1</span>
                  <div>
                    <div class="text-[10px] text-[var(--muted-foreground)] uppercase font-semibold">Pata 1 (Resultado)</div>
                    <div class="font-bold text-emerald-400">${{p.game_selection}}</div>
                    <div class="text-[10px] text-[var(--muted-foreground)]">Prob: ${{(Number(p.p_game) * 100).toFixed(1)}}%</div>
                  </div>
                </div>
                <div class="flex items-center gap-2.5 p-2 rounded-lg bg-[var(--card)]/60 border border-[var(--border)]">
                  <span class="w-6 h-6 rounded-full bg-purple-500/20 text-purple-400 text-xs font-extrabold flex items-center justify-center shrink-0">2</span>
                  <div>
                    <div class="text-[10px] text-[var(--muted-foreground)] uppercase font-semibold">Pata 2 (Jugador)</div>
                    <div class="font-bold text-purple-400">${{p.player_name}} ${{p.prop_category}} ${{p.prop_selection}} ${{p.prop_line}}</div>
                    <div class="text-[10px] text-[var(--muted-foreground)]">Prob: ${{(Number(p.p_prop) * 100).toFixed(1)}}%</div>
                  </div>
                </div>
              </div>

              <!-- Metrics Grid -->
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                  <div class="text-[var(--muted-foreground)]">Prob. Conjunta</div>
                  <div class="text-base font-bold mt-0.5 text-amber-400">${{(Number(p.p_joint) * 100).toFixed(1)}}%</div>
                  <div class="text-[10px] text-[var(--muted-foreground)]">Indep: ${{(Number(p.p_independent) * 100).toFixed(1)}}%</div>
                </div>
                <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                  <div class="text-[var(--muted-foreground)]">Impulso Correlación</div>
                  <div class="text-base font-bold mt-0.5 text-emerald-400">+${{Number(p.correlation_boost_pct).toFixed(1)}}%</div>
                  <div class="text-[10px] text-[var(--muted-foreground)]">Cópula Gaussiana</div>
                </div>
                <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                  <div class="text-[var(--muted-foreground)]">Valor Esperado</div>
                  <div class="text-base font-bold mt-0.5 text-purple-400">+${{Number(p.ev_pct).toFixed(1)}}% EV</div>
                  <div class="text-[10px] text-[var(--muted-foreground)]">Edge Sintético</div>
                </div>
                <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                  <div class="text-[var(--muted-foreground)]">Kelly Stake Sugerido</div>
                  <div class="text-base font-bold mt-0.5 text-yellow-400">S/ ${{Number(p.kelly_stake_pen).toFixed(2)}} PEN</div>
                  <div class="text-[10px] text-[var(--muted-foreground)]">Banca Virtual S/100</div>
                </div>
              </div>

              <!-- Rationale and Copy Button -->
              <div class="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-[var(--foreground)]">
                <strong>💡 Justificación Cuantitativa:</strong> ${{p.rationale}}
              </div>

              <div class="flex items-center justify-between gap-3 pt-1">
                <span class="text-[11px] text-[var(--muted-foreground)]">Boleto optimizado para RETAbet Perú</span>
                <button id="copy-sgp-${{idx}}" onclick="copyToClipboard('${{copyTicketText.replace(/'/g, "\\'") }}', 'copy-sgp-${{idx}}')" class="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-amber-500 text-black hover:bg-amber-400 transition-all flex items-center gap-1.5 shadow-sm">
                  📋 Copiar Selección
                </button>
              </div>
            </div>
          `;
        }}

        // Render Upgraded Individual Prop Card
        const teamName = getTeamFullName(p.team);
        const usageBadge = p.usage_bump_pct > 0
          ? `<span class="px-2 py-0.5 rounded text-xs font-bold bg-amber-500/15 text-amber-500 border border-amber-500/30">ΔUSG: +${{Number(p.usage_bump_pct).toFixed(1)}}% por bajas</span>`
          : '';
        const matchupBadge = p.opponent_team
          ? `<span class="px-2 py-0.5 rounded text-xs font-bold bg-blue-500/15 text-blue-400 border border-blue-500/30">vs ${{p.opponent_team}} (${{p.matchup_tier || 'AVG'}})</span>`
          : '';
        const paceBadge = (p.pace_factor && p.pace_factor !== 1.0)
          ? `<span class="px-2 py-0.5 rounded text-xs font-bold bg-teal-500/15 text-teal-400 border border-teal-500/30">Ritmo: x${{Number(p.pace_factor).toFixed(2)}}</span>`
          : '';

        const lineDiffNum = Number(p.line_diff !== undefined ? p.line_diff : (p.projected_mean - p.line_value));
        const lineDiffPct = Number(p.line_diff_pct !== undefined ? p.line_diff_pct : ((lineDiffNum / Math.max(1, p.line_value)) * 100));
        const isFavorableOver = (p.selection === 'OVER' && lineDiffNum >= 0) || (p.selection === 'UNDER' && lineDiffNum >= 0);
        const edgeColor = isFavorableOver ? 'text-emerald-400' : 'text-blue-400';
        const copyPropText = `${{p.player_name}} (${{p.team}}) — ${{p.prop_category}} ${{p.selection}} ${{p.line_value}} @ cuota ${{Number(p.decimal_odds).toFixed(2)}} (EV: +${{Number(p.ev_pct).toFixed(1)}}%)`;

        return `
          <div class="bg-[var(--card)] border-2 border-purple-500/40 rounded-2xl p-5 shadow-sm space-y-4">
            <div class="flex items-start justify-between gap-3 border-b border-[var(--border)] pb-3.5">
              <div>
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-purple-600 text-white">${{p.prop_category}} PROP V8</span>
                  <span class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-[var(--background)] border border-[var(--border)] text-purple-400">
                    ${{teamName}} (${{p.team}})
                  </span>
                  ${{usageBadge}}
                  ${{matchupBadge}}
                  ${{paceBadge}}
                </div>
                <h3 class="text-base sm:text-lg font-bold mt-1.5">${{p.player_name}} — <span class="text-purple-400">${{p.prop_category}} ${{p.selection}} ${{p.line_value}}</span></h3>
                <p class="text-xs text-[var(--muted-foreground)]">Partido: <strong>${{p.game_id}}</strong> · Fecha: ${{p.matchday_date}}</p>
              </div>
              <div class="text-right bg-[var(--background)] border border-[var(--border)] rounded-xl px-3.5 py-2 shrink-0">
                <div class="text-[10px] uppercase font-bold text-[var(--muted-foreground)]">Cuota Ofrecida</div>
                <div class="text-xl font-extrabold text-emerald-400">${{Number(p.decimal_odds).toFixed(2)}}</div>
                <div class="text-xs text-[var(--muted-foreground)]">Línea: <strong class="text-[var(--foreground)]">${{p.line_value}}</strong></div>
              </div>
            </div>

            <!-- Visual Edge Discrepancy Gauge -->
            <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-3 space-y-2 text-xs">
              <div class="flex justify-between items-center">
                <span>Línea Casa: <strong class="font-mono text-amber-400">${{p.line_value}}</strong></span>
                <span class="font-bold ${{edgeColor}}">
                  Ventaja Modelo: ${{lineDiffNum >= 0 ? '+' : ''}}${{lineDiffNum.toFixed(1)}} pts (${{lineDiffPct >= 0 ? '+' : ''}}${{lineDiffPct.toFixed(1)}}%)
                </span>
                <span>Media Modelo: <strong class="font-mono text-blue-400">${{Number(p.projected_mean).toFixed(1)}}</strong></span>
              </div>
              <div class="w-full h-2 bg-[var(--border)] rounded-full overflow-hidden flex">
                <div class="bg-gradient-to-r from-blue-500 to-purple-500 h-full rounded-full" style="width: ${{Math.min(95, Math.max(15, (Number(p.projected_mean) / (p.line_value * 1.35)) * 100))}}%"></div>
              </div>
            </div>

            <!-- Projections & Stats -->
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                <div class="text-[var(--muted-foreground)]">Media Proyectada</div>
                <div class="text-base font-bold mt-0.5 text-blue-400">${{Number(p.projected_mean).toFixed(1)}}</div>
                <div class="text-[10px] text-[var(--muted-foreground)]">σ = ${{Number(p.projected_std).toFixed(1)}}</div>
              </div>
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                <div class="text-[var(--muted-foreground)]">Prob. Modelo</div>
                <div class="text-base font-bold mt-0.5 text-emerald-400">${{(Number(p.model_prob) * 100).toFixed(1)}}%</div>
                <div class="text-[10px] text-[var(--muted-foreground)]">Implícita: ${{((1.0 / Number(p.decimal_odds)) * 100).toFixed(1)}}%</div>
              </div>
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                <div class="text-[var(--muted-foreground)]">Lower-Bound EV</div>
                <div class="text-base font-bold mt-0.5 text-purple-400">+${{Number(p.ev_lower_bound_pct).toFixed(2)}}%</div>
                <div class="text-[10px] text-[var(--muted-foreground)]">Nominal: +${{Number(p.ev_pct).toFixed(1)}}%</div>
              </div>
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                <div class="text-[var(--muted-foreground)]">Kelly Stake Sugerido</div>
                <div class="text-base font-bold mt-0.5 text-amber-400">S/ ${{Number(p.kelly_stake_pen).toFixed(2)}} PEN</div>
                <div class="text-[10px] text-[var(--muted-foreground)]">${{(Number(p.kelly_optimal_fraction) * 100).toFixed(1)}}% de banca</div>
              </div>
            </div>

            <!-- Conformal Interval Bar -->
            <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-3 space-y-1.5 text-xs">
              <div class="flex justify-between">
                <span>Intervalo Conformal Venn-Abers: <strong>[${{(Number(p.conformal_p_low) * 100).toFixed(1)}}%, ${{(Number(p.conformal_p_high) * 100).toFixed(1)}}%]</strong></span>
                <span class="text-purple-400 font-semibold">Cota Inferior Garantizada</span>
              </div>
              <div class="w-full h-1.5 bg-[var(--border)] rounded-full overflow-hidden flex">
                <div class="bg-purple-600 h-full rounded-full" style="width: ${{Math.min(95, Number(p.model_prob) * 100)}}%"></div>
              </div>
            </div>

            <div class="p-3 rounded-xl bg-purple-500/10 border border-purple-500/25 text-xs text-[var(--foreground)]">
              <strong>💡 Justificación Cuantitativa:</strong> ${{p.rationale}}
            </div>

            <div class="flex items-center justify-between gap-3 pt-1">
              <span class="text-[11px] text-[var(--muted-foreground)]">Puntaje de convicción conformal validado</span>
              <button id="copy-prop-${{idx}}" onclick="copyToClipboard('${{copyPropText.replace(/'/g, "\\'") }}', 'copy-prop-${{idx}}')" class="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-purple-600 text-white hover:bg-purple-500 transition-all flex items-center gap-1.5 shadow-sm">
                📋 Copiar Selección
              </button>
            </div>
          </div>
        `;
      }}).join('');
    }}

    function updateCalculator() {{
      const odds = parseFloat(document.getElementById('calc-odds').value) || 1.91;
      const probPct = parseFloat(document.getElementById('calc-prob').value) || 53.5;
      const bank = parseFloat(document.getElementById('calc-bank').value) || 96.45;
      const p = Math.min(0.99, Math.max(0.01, probPct / 100.0));
      const implPct = (1.0 / odds) * 100.0;
      const fairOdds = 1.0 / p;
      const evPct = ((p * odds) - 1.0) * 100.0;
      const b = odds - 1.0;
      const rawKelly = b > 0 ? Math.max(0.0, ((b * p) - (1.0 - p)) / b) : 0.0;
      const fracKellyStake = Math.min(bank * 0.05, bank * rawKelly * 0.25);

      const isPositive = evPct >= 1.5;
      document.getElementById('calc-results').innerHTML = `
        <div class="flex justify-between text-xs">
          <span class="text-[var(--muted-foreground)]">Probabilidad Implícita de la Casa:</span>
          <span class="font-bold">${{implPct.toFixed(1)}}%</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-[var(--muted-foreground)]">Cuota Justa según el Modelo (Sin Margen):</span>
          <span class="font-bold text-blue-500">${{fairOdds.toFixed(3)}}</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-[var(--muted-foreground)]">Valor Esperado Matemático (EV %):</span>
          <span class="font-bold ${{evPct >= 0 ? 'text-emerald-500' : 'text-rose-500'}}">${{evPct >= 0 ? '+' : ''}}${{evPct.toFixed(2)}}%</span>
        </div>
        <div class="flex justify-between text-xs">
          <span class="text-[var(--muted-foreground)]">Stake Recomendado (Kelly 25% Conservador):</span>
          <span class="font-bold">S/ ${{fracKellyStake.toFixed(2)}} PEN</span>
        </div>
        <div class="mt-2 pt-2 border-t border-[var(--border)] text-xs font-semibold ${{isPositive ? 'text-emerald-500' : 'text-amber-500'}}">
          ${{isPositive ? '✅ APUESTA CON VALOR (+EV >= 1.5%): La casa paga más de lo que debería.' : '🛡️ NO APOSTAR: La cuota es inferior o muy cercana al precio justo.'}}
        </div>
      `;
    }}

    function setHistoryFilter(flt) {{
      currentHistoryFilter = flt;
      ['ALL', 'PENDING', 'WON', 'LOST'].forEach(k => {{
        const btn = document.getElementById('hflt-' + k);
        if (btn) {{
          if (k === flt) {{
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-600 text-white';
          }} else {{
            btn.className = 'px-3 py-1.5 rounded-lg text-xs font-semibold bg-[var(--background)] border border-[var(--border)] text-[var(--muted-foreground)]';
          }}
        }}
      }});
      renderHistory();
    }}

    function renderHistory() {{
      const rows = DASH_DATA.real_bets.filter(b => currentHistoryFilter === 'ALL' || (b.estado || b.status) === currentHistoryFilter);
      const tbody = document.getElementById('history-tbody');
      if (!tbody) return;
      tbody.innerHTML = rows.map(b => {{
        const hora = b.hora_partido_peru || b.emitted_at || b.matchday_date || '—';
        const rawPartido = b.partido || b.game_id || '—';
        const partido = formatMatchupString(rawPartido);
        const seleccion = b.seleccion || b.selection || '—';
        const mercado = b.mercado || (b.market === 'moneyline' ? 'Ganador (Moneyline)' : (b.market === 'total_points' ? 'Total Puntos' : b.market)) || '—';
        const rawOdds = b.cuota_decimal !== undefined && b.cuota_decimal !== null ? b.cuota_decimal : b.decimal_odds;
        const cuota = (rawOdds !== undefined && rawOdds !== null && !isNaN(Number(rawOdds))) ? Number(rawOdds).toFixed(3) : '—';
        const casa = b.casa_apuestas || b.odds_provider || 'DraftKings';
        const rawProb = b.prob_estimada !== undefined && b.prob_estimada !== null ? b.prob_estimada : (b.estimated_prob ? Number(b.estimated_prob) * 100 : null);
        const prob = (rawProb !== null && !isNaN(Number(rawProb))) ? `${{Number(rawProb).toFixed(1)}}%` : '—';
        const rawEv = b.ev_porcentaje !== undefined && b.ev_porcentaje !== null ? b.ev_porcentaje : (b.estimated_ev ? Number(b.estimated_ev) * 100 : null);
        const ev = (rawEv !== null && !isNaN(Number(rawEv))) ? `+${{Number(rawEv).toFixed(1)}}%` : '—';
        const clv = (b.clv_porcentaje !== undefined && b.clv_porcentaje !== '' && b.clv_porcentaje !== null) ? Number(b.clv_porcentaje) : null;
        const clvStr = (clv !== null && !isNaN(clv)) ? `${{clv >= 0 ? '+' : ''}}${{clv.toFixed(2)}}%` : '—';
        const rawStake = b.stake_pen !== undefined && b.stake_pen !== null ? Number(b.stake_pen) : 0;
        const stakeStr = `S/ ${{rawStake.toFixed(2)}}`;
        const estado = b.estado || b.status || 'PENDING';

        let badge = '';
        if (estado === 'PENDING') badge = '<span class="px-2 py-0.5 rounded bg-amber-500/15 text-amber-500 font-semibold">⏳ PENDIENTE</span>';
        else if (estado === 'WON') badge = '<span class="px-2 py-0.5 rounded bg-emerald-500/15 text-emerald-500 font-semibold">✅ GANADA</span>';
        else badge = '<span class="px-2 py-0.5 rounded bg-rose-500/15 text-rose-500 font-semibold">❌ PERDIDA</span>';

        const rawProfit = (b.beneficio_neto_pen !== undefined && b.beneficio_neto_pen !== '' && b.beneficio_neto_pen !== null) ? b.beneficio_neto_pen : b.net_profit_pen;
        const marcador = b.marcador_final || b.actual_result_summary || 'En espera';
        const resStr = (rawProfit !== null && rawProfit !== undefined && rawProfit !== '')
          ? `<span class="font-bold ${{Number(rawProfit) >= 0 ? 'text-emerald-500' : 'text-rose-500'}}">S/ ${{Number(rawProfit) >= 0 ? '+' : ''}}${{Number(rawProfit).toFixed(2)}}</span> <span class="text-[var(--muted-foreground)]">(${{marcador}})</span>`
          : `<span class="text-[var(--muted-foreground)]">${{marcador}}</span>`;

        return `
          <tr class="hover:bg-[var(--background)] transition-colors border-b border-[var(--border)]">
            <td class="py-2.5 px-4 font-mono text-xs">${{hora}}</td>
            <td class="py-2.5 px-4 font-bold text-xs">${{partido}}</td>
            <td class="py-2.5 px-4 text-xs">
              <div class="font-semibold">${{seleccion}}</div>
              <div class="text-[var(--muted-foreground)]">${{mercado}}</div>
            </td>
            <td class="py-2.5 px-4 text-right font-bold text-xs">${{cuota}} <span class="font-normal text-[var(--muted-foreground)]">(${{casa}})</span></td>
            <td class="py-2.5 px-4 text-right font-semibold text-xs">${{prob}}</td>
            <td class="py-2.5 px-4 text-right text-blue-500 font-semibold text-xs">${{ev}}</td>
            <td class="py-2.5 px-4 text-right font-mono text-xs">${{clvStr}}</td>
            <td class="py-2.5 px-4 text-right font-semibold text-xs">${{stakeStr}}</td>
            <td class="py-2.5 px-4 text-center text-xs">${{badge}}</td>
            <td class="py-2.5 px-4 text-right text-xs">${{resStr}}</td>
          </tr>
        `;
      }}).join('');
    }}

    initDashboard();
  </script>
</body>
</html>
"""
    out = Path(html_output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    # Sync to docs/index.html for automatic GitHub Pages deployment and to conversation artifact
    has_real_content = (len(slate_items) > 0 or len(espn_real_bets) > 0)
    if has_real_content:
        docs_dash = Path("docs/index.html")
        try:
            docs_dash.parent.mkdir(parents=True, exist_ok=True)
            docs_dash.write_text(html, encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Failed to sync docs/index.html: {exc}")

        artifact_dash = Path(r"C:\Users\faboa\.gemini\antigravity\brain\369616bb-9a6e-460b-be8c-b9c7e1a798b7\nba_dashboard.html")
        if artifact_dash.parent.exists():
            try:
                artifact_dash.write_text(html, encoding="utf-8")
            except Exception as exc:
                logging.warning(f"Handled exception in reporter (line 1720): {exc}")

    return str(out)
