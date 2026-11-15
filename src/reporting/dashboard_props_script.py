"""
Client-side JS snippet for rendering the quarantined Player Props & SGP tab.
"""

from __future__ import annotations


def render_props_dashboard_script() -> str:
    """Returns JS functions handling props category filters, clipboard copy, and props cards."""
    return """    let currentPropCategory = 'ALL';

    function filterPropsCategory(cat) {
      currentPropCategory = cat;
      document.querySelectorAll('.prop-filter-btn').forEach(btn => {
        btn.classList.remove('bg-purple-600', 'text-white', 'shadow-sm');
        btn.classList.add('bg-[var(--card)]', 'text-[var(--muted-foreground)]', 'border-[var(--border)]');
      });
      const activeBtn = document.getElementById(`prop-filter-${cat}`);
      if (activeBtn) {
        activeBtn.classList.remove('bg-[var(--card)]', 'text-[var(--muted-foreground)]', 'border-[var(--border)]');
        activeBtn.classList.add('bg-purple-600', 'text-white', 'shadow-sm');
      }
      renderProps();
    }

    function copyToClipboard(text, elemId) {
      navigator.clipboard.writeText(text).then(() => {
        const el = document.getElementById(elemId);
        if (el) {
          const orig = el.innerHTML;
          el.innerHTML = '✅ ¡Copiado!';
          setTimeout(() => { el.innerHTML = orig; }, 1800);
        }
      }).catch(() => {
        // Fallback for non-secure contexts
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        const el = document.getElementById(elemId);
        if (el) {
          const orig = el.innerHTML;
          el.innerHTML = '✅ ¡Copiado!';
          setTimeout(() => { el.innerHTML = orig; }, 1800);
        }
      });
    }

    function renderProps() {
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
      const pt = DASH_DATA.props_paper_trading || {};
      const ptBank = document.getElementById('pt-props-bank');
      if (ptBank) ptBank.textContent = 'S/ ' + (Number(pt.current_props_bankroll_pen || 100.0)).toFixed(2);
      const ptWr = document.getElementById('pt-props-winrate');
      if (ptWr) ptWr.textContent = (Number(pt.win_rate_pct || 0)).toFixed(1) + '%';
      const ptRec = document.getElementById('pt-props-record');
      if (ptRec) ptRec.textContent = `${pt.won_picks || 0}G - ${pt.lost_picks || 0}P - ${pt.push_picks || 0}E`;
      const ptPnl = document.getElementById('pt-props-pnl');
      if (ptPnl) {
        const net = Number(pt.total_net_profit_pen || 0);
        const roi = Number(pt.roi_pct || 0);
        ptPnl.textContent = `${net >= 0 ? '+' : ''}S/ ${net.toFixed(2)} (${roi >= 0 ? '+' : ''}${roi.toFixed(1)}%)`;
        ptPnl.className = `text-lg font-black mt-0.5 ${net >= 0 ? 'text-emerald-400' : 'text-rose-400'}`;
      }
      const ptStaked = document.getElementById('pt-props-staked');
      if (ptStaked) ptStaked.textContent = 'Staked: S/ ' + (Number(pt.total_staked_pen || 0)).toFixed(2);
      const ptBrier = document.getElementById('pt-props-brier');
      if (ptBrier) ptBrier.textContent = (Number(pt.brier_score || 0)).toFixed(4);
      const ptCounts = document.getElementById('pt-props-counts');
      if (ptCounts) ptCounts.textContent = `${pt.total_picks || 0} / ${pt.pending_picks || 0}`;

      // Populate Settled Props Audit Table
      const histTbody = document.getElementById('props-history-tbody');
      const histCount = document.getElementById('props-history-count');
      const recentSettled = (pt.recent_settled || []).filter(r => ['WON', 'LOST', 'PUSH'].includes(r.status));
      if (histCount) histCount.textContent = `${recentSettled.length} apuestas resueltas verificadas`;
      if (histTbody) {
        if (!recentSettled.length) {
          histTbody.innerHTML = `<tr><td colspan="11" class="py-4 text-center text-[var(--muted-foreground)]">No hay apuestas de props liquidadas aún en la base de datos inmutable.</td></tr>`;
        } else {
          histTbody.innerHTML = recentSettled.map(r => {
            const isWon = r.status === 'WON';
            const isLost = r.status === 'LOST';
            const badgeClass = isWon ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : (isLost ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' : 'bg-amber-500/20 text-amber-400 border border-amber-500/30');
            const badgeText = isWon ? '✅ WON' : (isLost ? '❌ LOST' : (r.status === 'PUSH' ? '🔄 PUSH' : r.status));
            const netNum = Number(r.net_profit_pen || 0);
            const netClass = netNum > 0 ? 'text-emerald-400 font-bold' : (netNum < 0 ? 'text-rose-400 font-bold' : 'text-[var(--muted-foreground)]');
            return `
              <tr class="hover:bg-[var(--background)]/50 transition-colors">
                <td class="py-2 px-3 font-mono text-[10px]">${r.matchday_date}<br/><span class="text-[var(--muted-foreground)]">${r.game_id}</span></td>
                <td class="py-2 px-3 font-semibold">${r.player_name} <span class="text-[10px] text-[var(--muted-foreground)]">(${r.team || 'NBA'})</span></td>
                <td class="py-2 px-3"><span class="px-1.5 py-0.5 rounded font-mono font-bold bg-[var(--background)] border border-[var(--border)]">${r.prop_category}</span> ${Number(r.line_value || 0).toFixed(1)}</td>
                <td class="py-2 px-3 font-bold ${r.selection === 'OVER' ? 'text-blue-400' : 'text-amber-400'}">${r.selection}</td>
                <td class="py-2 px-3 text-right font-mono font-semibold">${Number(r.decimal_odds || 0).toFixed(2)}</td>
                <td class="py-2 px-3 text-right font-mono">${(Number(r.model_prob || 0) * 100).toFixed(1)}%</td>
                <td class="py-2 px-3 text-right font-mono text-emerald-400">+${Number(r.ev_pct || 0).toFixed(1)}%</td>
                <td class="py-2 px-3 text-right font-mono">S/ ${Number(r.stake_pen || 1.0).toFixed(2)}</td>
                <td class="py-2 px-3 text-center font-mono font-bold text-purple-300">${r.actual_stat !== null && r.actual_stat !== undefined ? Number(r.actual_stat).toFixed(1) : '—'}</td>
                <td class="py-2 px-3 text-center"><span class="px-2 py-0.5 rounded-full text-[10px] font-black ${badgeClass}">${badgeText}</span></td>
                <td class="py-2 px-3 text-right font-mono ${netClass}">${netNum >= 0 ? '+' : ''}S/ ${netNum.toFixed(2)}</td>
              </tr>
            `;
          }).join('');
        }
      }

      let filtered = allProps;
      if (currentPropCategory === 'PTS') filtered = allProps.filter(p => p.prop_category === 'PTS' && p.type !== 'RETABET_SGP' && !p.sgp_id);
      else if (currentPropCategory === 'REB') filtered = allProps.filter(p => p.prop_category === 'REB' && p.type !== 'RETABET_SGP' && !p.sgp_id);
      else if (currentPropCategory === 'AST') filtered = allProps.filter(p => p.prop_category === 'AST' && p.type !== 'RETABET_SGP' && !p.sgp_id);
      else if (currentPropCategory === '3PM') filtered = allProps.filter(p => p.prop_category === '3PM' && p.type !== 'RETABET_SGP' && !p.sgp_id);
      else if (currentPropCategory === 'COMBOS') filtered = allProps.filter(p => ['PRA', 'PR', 'PA', 'RA'].includes(p.prop_category) && p.type !== 'RETABET_SGP' && !p.sgp_id);
      else if (currentPropCategory === 'SGP') filtered = allProps.filter(p => p.type === 'RETABET_SGP' || p.sgp_id);

      if (!filtered.length) {
        container.innerHTML = `<div class="col-span-2 bg-[var(--card)] border border-[var(--border)] rounded-2xl p-8 text-center text-sm text-[var(--muted-foreground)]">No hay desajustes en esta categoría que superen el umbral de Lower-Bound EV (> 3%) en este momento.</div>`;
        return;
      }

      container.innerHTML = filtered.map((p, idx) => {
        const isSgp = (p.type === 'RETABET_SGP' || Boolean(p.sgp_id));

        if (isSgp) {
          const copyTicketText = `${p.bookmaker || 'RETAbet Perú'} Crea tu Apuesta: ${p.game_selection} + ${p.player_name} ${p.prop_category} ${p.prop_selection} ${p.prop_line} @ cuota ${Number(p.offered_sgp_odds).toFixed(2)}`;
          return `
            <div class="bg-gradient-to-br from-purple-950/30 via-[var(--card)] to-amber-950/25 border-2 border-amber-500/50 rounded-2xl p-5 shadow-md space-y-4">
              <div class="flex items-start justify-between gap-3 border-b border-[var(--border)] pb-3.5">
                <div>
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="px-2.5 py-0.5 rounded-md text-xs font-extrabold bg-gradient-to-r from-amber-500 to-yellow-600 text-black shadow-sm">
                      🇵🇪 CREA TU APUESTA · RETABET PERÚ
                    </span>
                    <span class="px-2 py-0.5 rounded-md text-xs font-bold bg-amber-500/15 text-amber-400 border border-amber-500/30">
                      Cópula Bivariada (ρ = ${p.correlation_rho || 0.35})
                    </span>
                    <span class="px-2 py-0.5 rounded-md text-xs font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                      Boost: +${Number(p.correlation_boost_pct || 0).toFixed(1)}%
                    </span>
                  </div>
                  <h3 class="text-base sm:text-lg font-bold mt-2 text-[var(--foreground)]">
                    ${p.game_selection} <span class="text-amber-400">+</span> ${p.player_name} ${p.prop_category} ${p.prop_selection} ${p.prop_line}
                  </h3>
                  <p class="text-xs text-[var(--muted-foreground)]">Partido: <strong>${p.game_id}</strong> · Fecha: ${p.matchday_date}</p>
                </div>
                <div class="text-right bg-[var(--background)] border border-amber-500/30 rounded-xl px-3.5 py-2 shrink-0">
                  <div class="text-[10px] uppercase font-bold text-[var(--muted-foreground)]">Cuota RETAbet</div>
                  <div class="text-xl font-black text-amber-400">${Number(p.offered_sgp_odds).toFixed(2)}</div>
                  <div class="text-[11px] text-[var(--muted-foreground)]">Justa: <span class="text-blue-400 font-mono">${Number(p.fair_sgp_odds).toFixed(2)}</span></div>
                </div>
              </div>

              <!-- Two-Leg Visual Architecture -->
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5 bg-[var(--background)]/80 border border-[var(--border)] rounded-xl p-3 text-xs">
                <div class="flex items-center gap-2.5 p-2 rounded-lg bg-[var(--card)]/60 border border-[var(--border)]">
                  <span class="w-6 h-6 rounded-full bg-emerald-500/20 text-emerald-400 text-xs font-extrabold flex items-center justify-center shrink-0">1</span>
                  <div>
                    <div class="text-[10px] text-[var(--muted-foreground)] uppercase font-semibold">Pata 1 (Resultado)</div>
                    <div class="font-bold text-emerald-400">${p.game_selection}</div>
                    <div class="text-[10px] text-[var(--muted-foreground)]">Prob: ${(Number(p.p_game) * 100).toFixed(1)}%</div>
                  </div>
                </div>
                <div class="flex items-center gap-2.5 p-2 rounded-lg bg-[var(--card)]/60 border border-[var(--border)]">
                  <span class="w-6 h-6 rounded-full bg-purple-500/20 text-purple-400 text-xs font-extrabold flex items-center justify-center shrink-0">2</span>
                  <div>
                    <div class="text-[10px] text-[var(--muted-foreground)] uppercase font-semibold">Pata 2 (Jugador)</div>
                    <div class="font-bold text-purple-400">${p.player_name} ${p.prop_category} ${p.prop_selection} ${p.prop_line}</div>
                    <div class="text-[10px] text-[var(--muted-foreground)]">Prob: ${(Number(p.p_prop) * 100).toFixed(1)}%</div>
                  </div>
                </div>
              </div>

              <!-- Metrics Grid -->
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                  <div class="text-[var(--muted-foreground)]">Prob. Conjunta</div>
                  <div class="text-base font-bold mt-0.5 text-amber-400">${(Number(p.p_joint) * 100).toFixed(1)}%</div>
                  <div class="text-[10px] text-[var(--muted-foreground)]">Indep: ${(Number(p.p_independent) * 100).toFixed(1)}%</div>
                </div>
                <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                  <div class="text-[var(--muted-foreground)]">Impulso Correlación</div>
                  <div class="text-base font-bold mt-0.5 text-emerald-400">+${Number(p.correlation_boost_pct).toFixed(1)}%</div>
                  <div class="text-[10px] text-[var(--muted-foreground)]">Cópula Student-t</div>
                </div>
                <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                  <div class="text-[var(--muted-foreground)]">Valor Esperado</div>
                  <div class="text-base font-bold mt-0.5 text-purple-400">+${Number(p.ev_pct).toFixed(1)}% EV</div>
                  <div class="text-[10px] text-[var(--muted-foreground)]">Edge Simulado (Student-t)</div>
                </div>
                <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                  <div class="text-[var(--muted-foreground)]">Kelly Stake Sugerido</div>
                  <div class="text-base font-bold mt-0.5 text-yellow-400">S/ ${Number(p.kelly_stake_pen).toFixed(2)} PEN</div>
                  <div class="text-[10px] text-[var(--muted-foreground)]">Banca Virtual S/100</div>
                </div>
              </div>

              <!-- Rationale and Copy Button -->
              <div class="p-3 rounded-xl bg-amber-500/10 border border-amber-500/20 text-xs text-[var(--foreground)]">
                <strong>💡 Justificación Cuantitativa:</strong> ${p.rationale}
              </div>

              <div class="flex items-center justify-between gap-3 pt-1">
                <span class="text-[11px] text-[var(--muted-foreground)]">Boleto optimizado para RETAbet Perú</span>
                <button id="copy-sgp-${idx}" onclick="copyToClipboard('${copyTicketText.replace(/'/g, "\\'") }', 'copy-sgp-${idx}')" class="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-amber-500 text-black hover:bg-amber-400 transition-all flex items-center gap-1.5 shadow-sm">
                  📋 Copiar Selección
                </button>
              </div>
            </div>
          `;
        }

        // Render Upgraded Individual Prop Card
        const teamName = getTeamFullName(p.team);
        const usageBadge = p.usage_bump_pct > 0
          ? `<span class="px-2 py-0.5 rounded text-xs font-bold bg-amber-500/15 text-amber-500 border border-amber-500/30">ΔUSG: +${Number(p.usage_bump_pct).toFixed(1)}% por bajas</span>`
          : '';
        const matchupBadge = p.opponent_team
          ? `<span class="px-2 py-0.5 rounded text-xs font-bold bg-blue-500/15 text-blue-400 border border-blue-500/30">vs ${p.opponent_team} (${p.matchup_tier || 'AVG'})</span>`
          : '';
        const paceBadge = (p.pace_factor && p.pace_factor !== 1.0)
          ? `<span class="px-2 py-0.5 rounded text-xs font-bold bg-teal-500/15 text-teal-400 border border-teal-500/30">Ritmo: x${Number(p.pace_factor).toFixed(2)}</span>`
          : '';

        const lineDiffNum = Number(p.line_diff !== undefined ? p.line_diff : (p.projected_mean - p.line_value));
        const lineDiffPct = Number(p.line_diff_pct !== undefined ? p.line_diff_pct : ((lineDiffNum / Math.max(1, p.line_value)) * 100));
        const isFavorableOver = (p.selection === 'OVER' && lineDiffNum >= 0) || (p.selection === 'UNDER' && lineDiffNum >= 0);
        const edgeColor = isFavorableOver ? 'text-emerald-400' : 'text-blue-400';
        const copyPropText = `${p.player_name} (${p.team}) — ${p.prop_category} ${p.selection} ${p.line_value} @ cuota ${Number(p.decimal_odds).toFixed(2)} (EV: +${Number(p.ev_pct).toFixed(1)}%)`;

        return `
          <div class="bg-[var(--card)] border-2 border-purple-500/40 rounded-2xl p-5 shadow-sm space-y-4">
            <div class="flex items-start justify-between gap-3 border-b border-[var(--border)] pb-3.5">
              <div>
                <div class="flex items-center gap-2 flex-wrap">
                  <span class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-purple-600 text-white">${p.prop_category} PROP V8</span>
                  <span class="px-2.5 py-0.5 rounded-md text-xs font-bold bg-[var(--background)] border border-[var(--border)] text-purple-400">
                    ${teamName} (${p.team})
                  </span>
                  ${usageBadge}
                  ${matchupBadge}
                  ${paceBadge}
                </div>
                <h3 class="text-base sm:text-lg font-bold mt-1.5">${p.player_name} — <span class="text-purple-400">${p.prop_category} ${p.selection} ${p.line_value}</span></h3>
                <p class="text-xs text-[var(--muted-foreground)]">Partido: <strong>${p.game_id}</strong> · Fecha: ${p.matchday_date}</p>
              </div>
              <div class="text-right bg-[var(--background)] border border-[var(--border)] rounded-xl px-3.5 py-2 shrink-0">
                <div class="text-[10px] uppercase font-bold text-[var(--muted-foreground)]">Cuota Ofrecida</div>
                <div class="text-xl font-extrabold text-emerald-400">${Number(p.decimal_odds).toFixed(2)}</div>
                <div class="text-xs text-[var(--muted-foreground)]">Línea: <strong class="text-[var(--foreground)]">${p.line_value}</strong></div>
              </div>
            </div>

            <!-- Visual Edge Discrepancy Gauge -->
            <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-3 space-y-2 text-xs">
              <div class="flex justify-between items-center">
                <span>Línea Casa: <strong class="font-mono text-amber-400">${p.line_value}</strong></span>
                <span class="font-bold ${edgeColor}">
                  Ventaja Modelo: ${lineDiffNum >= 0 ? '+' : ''}${lineDiffNum.toFixed(1)} pts (${lineDiffPct >= 0 ? '+' : ''}${lineDiffPct.toFixed(1)}%)
                </span>
                <span>Media Modelo: <strong class="font-mono text-blue-400">${Number(p.projected_mean).toFixed(1)}</strong></span>
              </div>
              <div class="w-full h-2 bg-[var(--border)] rounded-full overflow-hidden flex">
                <div class="bg-gradient-to-r from-blue-500 to-purple-500 h-full rounded-full" style="width: ${Math.min(95, Math.max(15, (Number(p.projected_mean) / (p.line_value * 1.35)) * 100))}%"></div>
              </div>
            </div>

            <!-- Projections & Stats -->
            <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                <div class="text-[var(--muted-foreground)]">Media Proyectada</div>
                <div class="text-base font-bold mt-0.5 text-blue-400">${Number(p.projected_mean).toFixed(1)}</div>
                <div class="text-[10px] text-[var(--muted-foreground)]">σ = ${Number(p.projected_std).toFixed(1)}</div>
              </div>
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                <div class="text-[var(--muted-foreground)]">Prob. Modelo</div>
                <div class="text-base font-bold mt-0.5 text-emerald-400">${(Number(p.model_prob) * 100).toFixed(1)}%</div>
                <div class="text-[10px] text-[var(--muted-foreground)]">Implícita: ${((1.0 / Number(p.decimal_odds)) * 100).toFixed(1)}%</div>
              </div>
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                <div class="text-[var(--muted-foreground)]">Lower-Bound EV</div>
                <div class="text-base font-bold mt-0.5 text-purple-400">+${Number(p.ev_lower_bound_pct).toFixed(2)}%</div>
                <div class="text-[10px] text-[var(--muted-foreground)]">Nominal: +${Number(p.ev_pct).toFixed(1)}%</div>
              </div>
              <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-2.5 text-center">
                <div class="text-[var(--muted-foreground)]">Kelly Stake Sugerido</div>
                <div class="text-base font-bold mt-0.5 text-amber-400">S/ ${Number(p.kelly_stake_pen).toFixed(2)} PEN</div>
                <div class="text-[10px] text-[var(--muted-foreground)]">${(Number(p.kelly_optimal_fraction) * 100).toFixed(1)}% de banca</div>
              </div>
            </div>

            <!-- Calibration / Uncertainty Interval Bar -->
            <div class="bg-[var(--background)] border border-[var(--border)] rounded-xl p-3 space-y-1.5 text-xs">
              <div class="flex justify-between">
                <span>${p.calibration_is_conformal ? 'Intervalo Conformal Venn-Abers:' : 'Intervalo Fallback (Sin Calibración Conformal):'} <strong>[${(Number(p.conformal_p_low) * 100).toFixed(1)}%, ${(Number(p.conformal_p_high) * 100).toFixed(1)}%]</strong></span>
                <span class="${p.calibration_is_conformal ? 'text-purple-400' : 'text-amber-400'} font-semibold">${p.calibration_is_conformal ? 'Cobertura Venn-Abers Calibrada' : 'Sin Garantía Conformal'}</span>
              </div>
              <div class="w-full h-1.5 bg-[var(--border)] rounded-full overflow-hidden flex">
                <div class="bg-purple-600 h-full rounded-full" style="width: ${Math.min(95, Number(p.model_prob) * 100)}%"></div>
              </div>
            </div>

            <div class="p-3 rounded-xl bg-purple-500/10 border border-purple-500/25 text-xs text-[var(--foreground)]">
              <strong>💡 Justificación Cuantitativa:</strong> ${p.rationale}
            </div>

            <div class="flex items-center justify-between gap-3 pt-1">
              <span class="text-[11px] text-[var(--muted-foreground)]">${p.calibration_is_conformal ? 'Calibración conformal Venn-Abers fuera de muestra' : 'Calibrador sin ajuste suficiente (solo informativo)'}</span>
              <button id="copy-prop-${idx}" onclick="copyToClipboard('${copyPropText.replace(/'/g, "\\'") }', 'copy-prop-${idx}')" class="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-purple-600 text-white hover:bg-purple-500 transition-all flex items-center gap-1.5 shadow-sm">
                📋 Copiar Selección
              </button>
            </div>
          </div>
        `;
      }).join('');
    }"""
