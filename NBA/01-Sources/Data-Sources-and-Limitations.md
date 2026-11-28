---
date_generated: 2026-11-28T15:52:54Z
component: nba_data_scout
---
# Evaluación de Fuentes de Estadísticas y Cuotas NBA

## 1. ESPN Public API (`site.api.espn.com`) — Activa sin Credenciales
- Proporciona calendario oficial, estados de partido (`SCHEDULED`, `FINAL`), estadísticas de equipo y cuotas pre-partido de `DraftKings` (`moneyline` y `total_points`).
- Limitación histórica: en partidos históricos finalizados, `pickcenter` refleja la línea archivada sin historial tick-a-tick; por ello el sistema exige `captured_at < game_start_time` para toda captura en vivo.

## 2. Sportradar NBA API v8 (`SportradarAdapter`)
- Estado: `OPERATIONAL_LIVE_NBA_V8 (97 injury docs + 30 teams tactical splits)`.
- Sincroniza el parte médico oficial de la liga (`league/injuries.json`) y los splits tácticos de los 30 equipos (`seasons/2026/REG/standings.json`) (Synergy Basketball desactivado por configuración: `sportradar_synergy_enabled: false`) usando `SPORTRADAR_API_KEY`.

## 3. TheOddsAPI Multi-Bookmaker Line Shopping (`TheOddsAPIAdapter`)
- Escanea casas activas en región `eu` y mercados `h2h,totals` (`Pinnacle`, `Matchbook`, `Betfair`, `Coolbet`, `Marathon Bet`, `888sport`, complementado con `DraftKings` vía ESPN y caché TTL de `300s`) para elegir la mejor cuota disponible.

## 4. Playwright + PixelRAG (`visual_researcher`)
- Playwright: `READY_FOR_BROWSER_INSTALL`.
- PixelRAG: `OPERATIONAL_NATIVE_TABULAR_RAG (BROWSERBASE_CLOUD_CDP, 123 docs indexed)`.
