---
date_generated: "{{date_generated}}"
report_type: "weekly_report"
model_version: "{{model_version}}"
period_evaluated: "{{period_evaluated}}"
predictions_count: "{{predictions_count}}"
simulation_only: true
---
# Informe Semanal NBA — {{period_evaluated}}

- **Bankroll inicial / actual**: S/100.00 PEN / S/{{current_bankroll}} PEN
- **ROI / Yield**: {{roi_pct}}% / {{yield_pct}}%
- **Brier Score / Log Loss**: {{brier_score}} / {{log_loss}}
- **Incertidumbre (Block Bootstrap 95% CI)**: {{bootstrap_ci}}
- **Decisiones de calibración**: {{calibration_decisions}}
