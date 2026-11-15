"""
HTML markup builder for the NBA Betting Intelligence interactive dashboard.
"""

from __future__ import annotations


def render_dashboard_markup(
    *,
    avail_bank: float,
    settled_bank: float,
    pending_cnt: int,
    pending_stake: float,
    min_ev_pct: float,
) -> str:
    """Renders the HTML document shell, theme styles, header, KPI grid, and tab panels."""
    return f"""<!DOCTYPE html>
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
          <div class="text-base font-bold" id="hdr-bankroll">S/ {avail_bank:.2f} disp. / S/ {settled_bank:.2f} liq.</div>
        </div>
        <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl px-3.5 py-2 text-right">
          <div class="text-xs text-[var(--muted-foreground)]">En Juego Ahora</div>
          <div class="text-base font-bold text-amber-500" id="hdr-pending">{pending_cnt} activas (S/ {pending_stake:.2f})</div>
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
            Oportunidades +EV detectadas en líneas individuales (PTS, REB, AST, 3PM, PRA) y combinadas correlacionadas para casas peruanas mediante Cópulas Elípticas Student-t y Calibración Conformal Venn-Abers.
          </p>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <span class="text-xs font-semibold px-3 py-1.5 rounded-lg bg-amber-500/15 text-amber-400 border border-amber-500/30">
            🇵🇪 Análisis SGP RETAbet (Simulación)
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
              <input type="number" step="1" min="10" max="100000" value="{settled_bank:.2f}" id="calc-bank" oninput="updateCalculator()"
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
                En lugar de confiar en una probabilidad puntual única, calculamos el intervalo garantizado <code>[p0, p1]</code> con calibración finita. Solo se confirma la apuesta si el límite inferior conservador mantiene <strong>EV positivo (>= {min_ev_pct:.1f}%)</strong> ante la cuota de la casa.
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
"""
