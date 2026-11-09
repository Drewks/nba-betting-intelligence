---
date_generated: 2026-11-09T06:28:34Z
dashboard_type: obsidian_dataview_quant_v8
current_bankroll_pen: 103.63
roi_pct: 9.24
brier_score: 0.20568
---
# 📊 Centro de Comando Cuantitativo (Obsidian DataviewJS & Tracker)

> [!TIP] Plugins recomendados en Obsidian
> Instala **Dataview** (habilitando `Enable JavaScript Queries`), **Tracker**, **Charts** y **Obsidian Git** para visualizar las tablas y curvas en tiempo real.

## 1. KPIs del Portafolio en Soles (DataviewJS)

```dataviewjs
const statusPage = dv.page('00-Inbox/00-System-Status');
if (statusPage) {
  dv.table(
    ['Bankroll (S/.)', 'Beneficio Neto', 'ROI (%)', 'CLV Medio (%)', 'Brier Score', 'Liquidadas'],
    [[
      'S/ ' + statusPage.current_bankroll_pen,
      'S/ ' + statusPage.net_profit_pen,
      statusPage.roi_pct + '%',
      statusPage.mean_clv_pct + '%',
      statusPage.brier_score,
      statusPage.settled_bets
    ]]
  );
}
```

## 2. Auditoría de Informes y Modelos (Dataview DQL)

```dataview
TABLE report_type AS Tipo, date_generated AS Fecha, settled_predictions AS Liquidadas, final_verdict AS Dictamen
FROM "09-Reports" OR "08-Calibration"
SORT date_generated DESC
```

## 3. Seguimiento Temporal de Calibración y Bankroll (Obsidian Tracker)

```tracker
searchType: frontmatter
searchTarget: current_bankroll_pen, roi_pct
folder: 00-Inbox
line:
    title: Evolución del Bankroll (S/. PEN) & ROI (%)
    yAxisLabel: Soles (PEN)
    lineColor: '#10b981, #38bdf8'
```
