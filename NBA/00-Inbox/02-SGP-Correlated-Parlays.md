---
date_generated: 2026-11-10T14:07:27Z
dashboard_type: retabet_sgp_copula_v8
---
# 🎰 Apuestas Correlacionadas SGP (Crea tu Apuesta — RETAbet Perú)

> [!NOTE] Simulación de Cópula Gaussiana Bivariada (V8 Fase 3)
> Modela la interdependencia estocástica entre resultados de equipo y props de jugadores (PTS, REB, AST, PRA) para explotar tablas de correlación rígidas en **RETAbet Perú**.

```dataview
TABLE bookmaker AS Casa, game_selection AS Partido, player_name AS Jugador, prop_category AS Mercado, fair_sgp_odds AS "Cuota Justa", offered_sgp_odds AS "Cuota RETAbet", ev_pct AS "EV (%)", kelly_stake_pen AS "Stake (S/.)"
FROM "00-Inbox" OR "04-Predictions"
SORT ev_pct DESC
```
