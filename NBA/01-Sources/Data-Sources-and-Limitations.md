---
date_generated: 2026-10-29T22:42:03Z
component: nba_data_scout
---
# Evaluación de Fuentes de Estadísticas y Cuotas NBA

## 1. ESPN Public API (`site.api.espn.com`) — Activa sin Credenciales
- Proporciona calendario oficial, estados de partido (`SCHEDULED`, `FINAL`), estadísticas de equipo y cuotas pre-partido de `DraftKings` (`moneyline` y `total_points`).
- Limitación histórica: en partidos históricos finalizados, `pickcenter` refleja la línea archivada sin historial tick-a-tick; por ello el sistema exige `captured_at < game_start_time` para toda captura en vivo.

## 2. Sportradar NBA API v8 (`SportradarAdapter`)
- Estado: Adaptador intercambiable implementado (`src/ingestion/adapters.py`).
- Requiere `SPORTRADAR_API_KEY` en `.env`. Las cuotas históricas requieren licencia adicional de Odds Comparison.

## 3. NBA.com/stats (`NBAStatsAdapter`)
- Estado: Adaptador implementado con cabeceras oficiales y circuit-breaker.
- Limitación: `stats.nba.com` bloquea peticiones directas por huella TLS Akamai (timeout) y **no proporciona cuotas históricas de apuestas**.

## 4. PixelRAG (`visual_researcher`)
- Estado: No existe servidor MCP de PixelRAG instalado en `%APPDATA%` / `.gemini/config/mcp_config.json`.
- El agente `visual_researcher` documenta explícitamente `PIXELRAG_NOT_INSTALLED` y opera sobre el pipeline estructurado sin inventar respuestas.
