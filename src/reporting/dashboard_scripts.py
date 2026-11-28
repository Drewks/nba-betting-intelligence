"""
Client-side script builder for the NBA Betting Intelligence interactive HTML dashboard.
"""

from __future__ import annotations

from src.reporting.dashboard_props_script import render_props_dashboard_script


def render_dashboard_scripts(
    *,
    data_json: str,
    team_dict_json: str,
    peru_books_json: str,
    settled_bank: float,
    min_ev_pct: float,
    kelly_pct: int | float,
) -> str:
    """Renders the closing `<script>` tag and closing HTML body/document tags."""
    props_js = render_props_dashboard_script()
    return f"""
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
          title: 'CLV vs. cierre sin margen',
          value: s.mean_clv_pct === null ? '—' : `${{s.mean_clv_pct >= 0 ? '+' : ''}}${{s.mean_clv_pct.toFixed(2)}}%`,
          sub: `Muestra: ${{s.clv_sample_size}} apuestas con cierre observado`,
          badge: s.clv_sample_size >= 200 ? 'Muestra útil' : 'Muestra insuficiente',
          color: 'text-emerald-500'
        }},
        {{
          title: 'Modelo vs. Mercado (Brier)',
          value: s.brier_score === null ? '—' : `Modelo ${{s.brier_score.toFixed(4)}}`,
          sub: s.market_brier === null ? 'Sin cuotas observadas suficientes' : `Mercado: ${{s.market_brier.toFixed(4)}} (N=${{s.market_sample_size}})`,
          badge: (s.brier_score !== null && s.market_brier !== null && s.brier_score <= s.market_brier) ? 'No peor que el mercado' : 'Sin ventaja demostrada',
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
                  <div class="text-[var(--muted-foreground)]">Simulación 80% (Q10–Q90): ${{g.simulation_q10 ?? g.projections?.simulation_q10_total ?? '—'}}–${{g.simulation_q90 ?? g.projections?.simulation_q90_total ?? '—'}}</div>
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
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.selection_label.includes('Local') ? (g.peru_odds?.books?.find(x => x.id === 'betsson_pe')?.home_odds || '—') : (g.peru_odds?.books?.find(x => x.id === 'betsson_pe')?.away_odds || '—')}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-cyan-500">Coolbet Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Bajo Margen</div>
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.selection_label.includes('Local') ? (g.peru_odds?.books?.find(x => x.id === 'coolbet_pe')?.home_odds || '—') : (g.peru_odds?.books?.find(x => x.id === 'coolbet_pe')?.away_odds || '—')}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-red-600">RETAbet Perú</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">MINCETUR · Tarjeta RETA</div>
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.selection_label.includes('Local') ? (g.peru_odds?.books?.find(x => x.id === 'retabet_pe')?.home_odds || '—') : (g.peru_odds?.books?.find(x => x.id === 'retabet_pe')?.away_odds || '—')}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-red-500">Apuesta Total</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">Tiendas + Web</div>
                  <div class="font-extrabold text-sm text-[var(--foreground)] mt-0.5">${{b.selection_label.includes('Local') ? (g.peru_odds?.books?.find(x => x.id === 'apuesta_total')?.home_odds || '—') : (g.peru_odds?.books?.find(x => x.id === 'apuesta_total')?.away_odds || '—')}}</div>
                </div>
                <div class="p-2 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                  <div class="font-bold text-emerald-500">Cuota observada</div>
                  <div class="text-[var(--muted-foreground)] text-[10px]">${{b.bookmaker || 'Casa registrada'}}</div>
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
             <div class="text-[var(--muted-foreground)]">Intervalo Simulación MC 80% (sin garantía conformal): [${{g.simulation_q10 ?? g.projections?.simulation_q10_total ?? '—'}} – ${{g.simulation_q90 ?? g.projections?.simulation_q90_total ?? '—'}} pts]</div>`;

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
                  Mejor cuota observada: Local <strong>${{g.peru_odds?.best_home?.odds || (g.ml_home_odds || '—')}}</strong> (${{g.peru_odds?.best_home?.book || g.ml_home_book || '—'}}) · Visita <strong>${{g.peru_odds?.best_away?.odds || (g.ml_away_odds || '—')}}</strong> (${{g.peru_odds?.best_away?.book || g.ml_away_book || '—'}})
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

{props_js}

    function updateCalculator() {{
      const odds = parseFloat(document.getElementById('calc-odds').value) || 1.91;
      const probPct = parseFloat(document.getElementById('calc-prob').value) || 53.5;
      const bank = parseFloat(document.getElementById('calc-bank').value) || {settled_bank:.2f};
      const p = Math.min(0.99, Math.max(0.01, probPct / 100.0));
      const implPct = (1.0 / odds) * 100.0;
      const fairOdds = 1.0 / p;
      const evPct = ((p * odds) - 1.0) * 100.0;
      const b = odds - 1.0;
      const rawKelly = b > 0 ? Math.max(0.0, ((b * p) - (1.0 - p)) / b) : 0.0;
      const fracKellyStake = Math.min(bank * 0.05, bank * rawKelly * 0.25);

      const isPositive = evPct >= {min_ev_pct:.1f};
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
          <span class="text-[var(--muted-foreground)]">Stake Recomendado (Kelly {kelly_pct}% Conservador):</span>
          <span class="font-bold">S/ ${{fracKellyStake.toFixed(2)}} PEN</span>
        </div>
        <div class="mt-2 pt-2 border-t border-[var(--border)] text-xs font-semibold ${{isPositive ? 'text-emerald-500' : 'text-amber-500'}}">
          ${{isPositive ? '✅ APUESTA CON VALOR (+EV >= {min_ev_pct:.1f}%): La casa paga más de lo que debería.' : '🛡️ NO APOSTAR: La cuota es inferior o muy cercana al precio justo.'}}
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
