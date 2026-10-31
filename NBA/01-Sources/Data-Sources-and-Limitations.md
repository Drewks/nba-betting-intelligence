---
date_generated: 2026-10-31T01:30:11Z
component: nba_data_scout
---
# Evaluación de Fuentes de Estadísticas y Cuotas NBA

## 1. ESPN Public API (`site.api.espn.com`) — Activa sin Credenciales
- Proporciona calendario oficial, estados de partido (`SCHEDULED`, `FINAL`), estadísticas de equipo y cuotas pre-partido de `DraftKings` (`moneyline` y `total_points`).
- Limitación histórica: en partidos históricos finalizados, `pickcenter` refleja la línea archivada sin historial tick-a-tick; por ello el sistema exige `captured_at < game_start_time` para toda captura en vivo.

## 2. Sportradar NBA API v8 & Synergy Basketball NBA API (`SportradarAdapter`)
- Estado: `OPERATIONAL_LIVE_NBA_V8_AND_SYNERGY (28 teams injuries + 30 teams tactical splits + 30 Synergy NBA teams + 60 Synergy possession events)`.
- Sincroniza el parte médico oficial de la liga (`league/injuries.json`), los splits tácticos de los 30 equipos (`seasons/2026/REG/standings.json`) y la telemetría de posesiones y jugadas de **Synergy Basketball NBA API** (`/synergy/basketball/nba/games` y `/events`) usando `SPORTRADAR_API_KEY`.

## 3. TheOddsAPI Multi-Bookmaker Line Shopping (`TheOddsAPIAdapter`)
- Escanea en tiempo real hasta 25+ casas de apuestas (`Pinnacle`, `DraftKings`, `FanDuel`, `BetMGM`, `Coolbet`, `Matchbook`, `GTbets`, etc.) para elegir siempre la cuota máxima disponible.

## 4. Playwright + PixelRAG (`visual_researcher`)
- Playwright: `OPERATIONAL`.
- PixelRAG: `OPERATIONAL_NATIVE_TABULAR_RAG (PLAYWRIGHT_CHROMIUM_HEADLESS, 122 docs indexed)` indexando lesiones oficiales de Sportradar, perfiles tácticos de Synergy Basketball NBA y tablas DOM de ESPN.
