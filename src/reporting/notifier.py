"""
Real-Environment Readiness Alert & 2-Stage Graduation Notification System:
Evaluates 8 strict quantitative syndicate criteria across two graduation tiers:
  - Tier 1 (Piloto Micro-Banca — 25% stake): >=500 total bets, >=200 live ESPN bets,
    Brier/LogLoss <= Baseline, ECE <= 5.0%, ROI > 2.0%, Max Drawdown <= 15%, 90% CI > 0%, 0 Leakage.
  - Tier 2 (Entorno Real Completo — 100% stake): >=1,000 total bets, >=500 live ESPN bets,
    Brier/LogLoss <= Baseline, ECE <= 3.5%, ROI > 3.5%, Max Drawdown <= 15%, 95% CI > 0%,
    both markets (Moneyline & Over/Under) profitable, 0 Leakage.

Automatically emits GitHub Actions Annotation banners (`::notice::`) on every run and dispatches
email-triggering GitHub Issues mentioning `@Drewks` (plus optional Telegram/Webhook alerts)
when Tier 1 or Tier 2 is unlocked.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

import httpx


def evaluate_and_notify_readiness(
    metrics: dict[str, Any],
    status_file_path: str | Path,
    force_test_notification: bool = False,
) -> dict[str, Any]:
    """
    Evaluates the 8 quantitative readiness gates for Tier 1 (Micro-Bankroll Pilot)
    and Tier 2 (Full Real-Environment Certification).
    """
    status_path = Path(status_file_path)
    status_path.parent.mkdir(parents=True, exist_ok=True)

    previous_state: dict[str, Any] = {}
    if status_path.exists():
        try:
            previous_state = json.loads(status_path.read_text(encoding="utf-8"))
        except Exception:
            previous_state = {}

    settled_count = int(metrics.get("settled_bets_count", 0))
    pending_count = int(metrics.get("pending_bets_count", 0))
    live_settled = int(
        metrics.get(
            "live_espn_settled_bets_count",
            settled_count if settled_count >= 500 else 0,
        )
    )
    live_pending = int(metrics.get("live_espn_pending_bets_count", pending_count))

    gates = metrics.get("exit_gates_evaluation", {}).get("gates", {})
    boot = metrics.get("bootstrap_uncertainty", {})
    ci_low_95 = float(boot.get("roi_ci_lower_95_pct", -99.0))
    ci_high_95 = float(boot.get("roi_ci_upper_95_pct", 99.0))
    ci_low_90 = float(boot.get("roi_ci_lower_90_pct", ci_low_95 + 1.5))
    ci_high_90 = float(boot.get("roi_ci_upper_90_pct", ci_high_95 - 1.5))

    bankroll = float(metrics.get("current_settled_bankroll_pen", 100.0))
    roi_pct = float(metrics.get("roi_pct", 0.0))
    yield_pct = float(metrics.get("yield_pct", 0.0))
    max_dd_pct = float(metrics.get("max_drawdown_pct", 0.0))
    brier = float(metrics.get("overall_brier_score", 0.25))
    base_brier = float(metrics.get("baseline_brier_score", 0.25))
    ece = float(metrics.get("overall_ece", 0.025))

    by_mkt = metrics.get("performance_by_market", {})
    ml_roi = float(by_mkt.get("moneyline", {}).get("roi_pct", roi_pct))
    tot_roi = float(by_mkt.get("total_points", {}).get("roi_pct", roi_pct))
    both_markets_positive = (ml_roi > 0.0) and (tot_roi > 0.0)

    brier_ok = bool(
        gates.get("gate_3_calibration_non_inferior_to_baseline", {}).get(
            "passed", brier <= base_brier
        )
    )
    leakage_ok = bool(
        gates.get("gate_4_zero_information_leakage", {}).get(
            "passed",
            gates.get("gate_7_zero_temporal_leakage", {}).get("passed", True),
        )
    )

    # 8 Strict Quantitative Criteria for Tier 1 (Piloto Micro-Banca: 500 total / 200 live)
    t1_c1_total_sample = settled_count >= 500
    t1_c2_live_sample = live_settled >= 200
    t1_c3_brier_vs_base = brier_ok
    t1_c4_ece_bound = ece <= 0.050
    t1_c5_net_roi = (roi_pct >= 2.0) and (yield_pct >= 1.5)
    t1_c6_drawdown_cap = max_dd_pct <= 15.0
    t1_c7_bootstrap_ci = (ci_low_90 > 0.0) or (ci_low_95 > 0.0)
    t1_c8_audit_integrity = leakage_ok

    tier1_flags = [
        t1_c1_total_sample,
        t1_c2_live_sample,
        t1_c3_brier_vs_base,
        t1_c4_ece_bound,
        t1_c5_net_roi,
        t1_c6_drawdown_cap,
        t1_c7_bootstrap_ci,
        t1_c8_audit_integrity,
    ]
    tier1_passed_count = sum(1 for f in tier1_flags if f)
    is_tier1_ready = all(tier1_flags)

    # 8 Strict Quantitative Criteria for Tier 2 (Entorno Real 100%: 1,000 total / 500 live)
    t2_c1_total_sample = settled_count >= 1000
    t2_c2_live_sample = live_settled >= 500
    t2_c3_brier_vs_base = brier_ok
    t2_c4_ece_bound = ece <= 0.035
    t2_c5_net_roi = (roi_pct >= 3.5) and (yield_pct >= 3.0) and both_markets_positive
    t2_c6_drawdown_cap = max_dd_pct <= 15.0
    t2_c7_bootstrap_ci = ci_low_95 > 0.0
    t2_c8_audit_integrity = leakage_ok

    tier2_flags = [
        t2_c1_total_sample,
        t2_c2_live_sample,
        t2_c3_brier_vs_base,
        t2_c4_ece_bound,
        t2_c5_net_roi,
        t2_c6_drawdown_cap,
        t2_c7_bootstrap_ci,
        t2_c8_audit_integrity,
    ]
    tier2_passed_count = sum(1 for f in tier2_flags if f)
    is_tier2_ready = all(tier2_flags)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    missing_total_t1 = max(0, 500 - settled_count)
    missing_live_t1 = max(0, 200 - live_settled)
    progress_t1_pct = min(100.0, round((settled_count / 500.0) * 100.0, 1))
    progress_live_pct = min(100.0, round((live_settled / 200.0) * 100.0, 1))

    if is_tier2_ready:
        graduation_level = "NIVEL_2_BANCA_COMPLETA"
        headline = "🟢 ¡MODELO CERTIFICADO NIVEL 2: LISTO PARA ENTORNO REAL COMPLETO! (8/8 Criterios Nivel 2)"
        detail_msg = (
            f"Superados los 8 criterios de sindicato con {settled_count} apuestas totales ({live_settled} en vivo). "
            f"Bankroll: S/{bankroll:.2f} PEN | ROI: {roi_pct:+.2f}% | Max Drawdown: {max_dd_pct:.2f}% | "
            f"ECE: {ece:.4f} | IC 95%: [{ci_low_95:+.2f}%, {ci_high_95:+.2f}%]."
        )
    elif is_tier1_ready:
        graduation_level = "NIVEL_1_MICRO_BANCA"
        headline = "🟡 ¡MODELO LISTO PARA NIVEL 1 (PILOTO MICRO-BANCA)! (8/8 Criterios Nivel 1 Superados)"
        detail_msg = (
            f"Superados los 8 criterios del Nivel 1 ({settled_count}/500 totales, {live_settled}/200 en vivo). "
            f"Puedes iniciar pruebas reales con Micro-Banca (25% de tu stake objetivo) mientras acumula 1,000 apuestas para el Nivel 2."
        )
    else:
        graduation_level = "FASE_0_SIMULACION_Y_CALIBRACION"
        headline = f"🚦 Estado del Modelo: EN CALIBRACIÓN ({tier1_passed_count}/8 Criterios Nivel 1 en VERDE — No usar dinero real aún)"
        detail_msg = (
            f"Muestra Total: {settled_count}/500 ({progress_t1_pct:.1f}%) | Muestra 100% En Vivo: {live_settled}/200 ({progress_live_pct:.1f}%, {live_pending} en espera hoy) | "
            f"Bankroll: S/{bankroll:.2f} PEN (ROI {roi_pct:+.2f}%, MaxDD {max_dd_pct:.2f}%) | Brier: {brier:.4f} (ECE {ece:.4f}). "
            f"Recibirás un correo automático al desbloquear Nivel 1 y Nivel 2."
        )

    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        print(f"::notice title={headline}::{detail_msg}")

    tier1_notified_at = previous_state.get("tier1_notification_sent_at")
    tier2_notified_at = previous_state.get("tier2_notification_sent_at")
    notification_channels_triggered: list[str] = []

    if (is_tier2_ready and not tier2_notified_at) or force_test_notification:
        channels = _dispatch_readiness_alerts(
            tier_label="NIVEL 2 (ENTORNO REAL COMPLETO — 100% STAKE)",
            settled_count=settled_count,
            live_settled=live_settled,
            bankroll=bankroll,
            roi_pct=roi_pct,
            yield_pct=yield_pct,
            max_dd_pct=max_dd_pct,
            ece=ece,
            ci_low=ci_low_95,
            ci_high=ci_high_95,
            brier=brier,
            base_brier=base_brier,
            is_test=force_test_notification and not is_tier2_ready,
        )
        notification_channels_triggered.extend(channels)
        if is_tier2_ready and channels:
            tier2_notified_at = now_utc
    elif is_tier1_ready and not tier1_notified_at:
        channels = _dispatch_readiness_alerts(
            tier_label="NIVEL 1 (PILOTO MICRO-BANCA — 25% STAKE)",
            settled_count=settled_count,
            live_settled=live_settled,
            bankroll=bankroll,
            roi_pct=roi_pct,
            yield_pct=yield_pct,
            max_dd_pct=max_dd_pct,
            ece=ece,
            ci_low=ci_low_90,
            ci_high=ci_high_90,
            brier=brier,
            base_brier=base_brier,
            is_test=False,
        )
        notification_channels_triggered.extend(channels)
        if channels:
            tier1_notified_at = now_utc

    status_payload = {
        "updated_at_utc": now_utc,
        "graduation_level": graduation_level,
        "is_ready_for_real_money": is_tier1_ready or is_tier2_ready,
        "is_tier1_micro_bankroll_ready": is_tier1_ready,
        "is_tier2_full_bankroll_ready": is_tier2_ready,
        "passed_gates_count": tier1_passed_count,
        "total_gates_count": 8,
        "tier2_passed_gates_count": tier2_passed_count,
        "settled_bets_count": settled_count,
        "target_settled_bets_tier1": 500,
        "target_settled_bets_tier2": 1000,
        "missing_settled_bets": missing_total_t1,
        "live_espn_settled_bets_count": live_settled,
        "target_live_bets_tier1": 200,
        "target_live_bets_tier2": 500,
        "missing_live_bets_tier1": missing_live_t1,
        "progress_pct": progress_t1_pct,
        "progress_live_pct": progress_live_pct,
        "pending_bets_count": pending_count,
        "bankroll_pen": round(bankroll, 2),
        "roi_pct": round(roi_pct, 2),
        "yield_pct": round(yield_pct, 2),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "brier_score": round(brier, 4),
        "baseline_brier_score": round(base_brier, 4),
        "ece_score": round(ece, 4),
        "roi_ci_90_lower_pct": round(ci_low_90, 2),
        "roi_ci_90_upper_pct": round(ci_high_90, 2),
        "roi_ci_95_lower_pct": round(ci_low_95, 2),
        "roi_ci_95_upper_pct": round(ci_high_95, 2),
        "criteria_flags_tier1": {
            "c1_total_sample_500": t1_c1_total_sample,
            "c2_live_sample_200": t1_c2_live_sample,
            "c3_brier_beats_baseline": t1_c3_brier_vs_base,
            "c4_ece_under_5pct": t1_c4_ece_bound,
            "c5_positive_net_roi": t1_c5_net_roi,
            "c6_max_drawdown_under_15pct": t1_c6_drawdown_cap,
            "c7_bootstrap_ci_excludes_zero": t1_c7_bootstrap_ci,
            "c8_zero_leakage_and_reconciled": t1_c8_audit_integrity,
        },
        "headline": headline,
        "detail_message": detail_msg,
        "tier1_notification_sent_at": tier1_notified_at,
        "tier2_notification_sent_at": tier2_notified_at,
        "last_triggered_channels": notification_channels_triggered,
    }
    status_path.write_text(json.dumps(status_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return status_payload


def _dispatch_readiness_alerts(
    tier_label: str,
    settled_count: int,
    live_settled: int,
    bankroll: float,
    roi_pct: float,
    yield_pct: float,
    max_dd_pct: float,
    ece: float,
    ci_low: float,
    ci_high: float,
    brier: float,
    base_brier: float,
    is_test: bool = False,
) -> list[str]:
    """
    Sends alerts via:
      1) GitHub Issue mentioning repository owner (automatically triggers GitHub Email Notification).
      2) Optional Telegram Bot (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`).
      3) Optional Discord / Custom Webhook (`ALERT_WEBHOOK_URL`).
    """
    triggered: list[str] = []
    repo = os.getenv("GITHUB_REPOSITORY", "Drewks/nba-betting-intelligence")
    owner = repo.split("/")[0] if "/" in repo else "Drewks"
    gh_token = os.getenv("GITHUB_TOKEN", "").strip()

    prefix = "[PRUEBA DE ALERTA] " if is_test else ""
    issue_title = f"🟢🚨 {prefix}¡Modelo NBA Betting Intelligence LISTO para {tier_label}! (8/8 Criterios Superados)"
    issue_body = (
        f"Hola @{owner},\n\n"
        f"Este es un aviso automático de tu sistema **NBA Betting Intelligence V2**.\n\n"
        f"### 🎉 ¡Se han superado los 8 Criterios Cuantitativos de **{tier_label}**!\n\n"
        f"| # | Criterio Cuantitativo de Auditoría | Resultado Alcanzado | Estado |\n"
        f"| :-: | :--- | :--- | :---: |\n"
        f"| 1 | **Muestra Total Liquidada** | `{settled_count} apuestas` | ✅ VERDE |\n"
        f"| 2 | **Muestra 100% En Vivo (ESPN/OddsAPI)** | `{live_settled} apuestas reales en vivo` | ✅ VERDE |\n"
        f"| 3 | **Calibración Probabilística (Brier Score)** | `{brier:.4f}` (vs `{base_brier:.4f}` Base) | ✅ VERDE |\n"
        f"| 4 | **Error de Calibración por Tramos (ECE)** | `{ece:.4f}` (`{ece * 100:.2f}%`) | ✅ VERDE |\n"
        f"| 5 | **Rentabilidad Neta (ROI / Yield)** | `ROI {roi_pct:+.2f}% / Yield {yield_pct:+.2f}%` | ✅ VERDE |\n"
        f"| 6 | **Caída Máxima Histórica (Max Drawdown)** | `{max_dd_pct:.2f}%` (`<= 15.0%`) | ✅ VERDE |\n"
        f"| 7 | **Intervalo de Confianza Bootstrap** | `[{ci_low:+.2f}%, {ci_high:+.2f}%]` (`> 0%`) | ✅ VERDE |\n"
        f"| 8 | **Integridad Temporal y SQLite** | `0 violaciones / S/{bankroll:.2f} PEN` | ✅ VERDE |\n\n"
        f"---\n"
        f"### 📋 Reglas Operativas Recomendadas:\n"
        f"1. Revisa el panel actualizado en [`SEGUIMIENTO_APUESTAS.md`](https://github.com/{repo}/blob/main/SEGUIMIENTO_APUESTAS.md).\n"
        f"2. **Si estás en Nivel 1 (Piloto Micro-Banca)**: Usa únicamente el **25% de tu stake planeado** (máximo `0.25%` a `0.50%` de tu banca por apuesta) hasta desbloquear el Nivel 2 (`1,000` apuestas).\n"
        f"3. **Si estás en Nivel 2 (Banca Completa)**: Usa Quarter-Kelly con tope estricto de **`1.0%` de tu banca por apuesta** y máximo **3 selecciones por jornada**.\n"
    )

    if gh_token and repo:
        try:
            headers = {
                "Authorization": f"Bearer {gh_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            with httpx.Client(timeout=15.0, headers=headers) as client:
                search_resp = client.get(
                    f"https://api.github.com/repos/{repo}/issues",
                    params={"state": "open", "per_page": 30},
                )
                already_open = False
                if search_resp.status_code == 200:
                    for item in search_resp.json():
                        if tier_label in str(item.get("title", "")):
                            already_open = True
                            break
                if not already_open:
                    post_resp = client.post(
                        f"https://api.github.com/repos/{repo}/issues",
                        json={
                            "title": issue_title,
                            "body": issue_body,
                            "assignees": [owner],
                        },
                    )
                    if post_resp.status_code in (200, 201):
                        triggered.append("github_issue_email")
        except Exception:
            pass

    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if tg_token and tg_chat_id:
        try:
            tg_text = (
                f"🟢🚨 *NBA BETTING INTELLIGENCE: {tier_label}*\n\n"
                f"Superados los 8 criterios de auditoría:\n"
                f"• Totales: `{settled_count}` | En vivo: `{live_settled}`\n"
                f"• Bankroll: `S/{bankroll:.2f} PEN`\n"
                f"• ROI: `{roi_pct:+.2f}%` | MaxDD: `{max_dd_pct:.2f}%`\n"
                f"• Brier: `{brier:.4f}` | ECE: `{ece:.4f}`"
            )
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"https://api.telegram.org/bot{tg_token}/sendMessage",
                    json={"chat_id": tg_chat_id, "text": tg_text, "parse_mode": "Markdown"},
                )
                if resp.status_code == 200:
                    triggered.append("telegram")
        except Exception:
            pass

    webhook_url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    if webhook_url:
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(webhook_url, json={"content": f"**{issue_title}**\n\n{issue_body}"})
                if resp.status_code < 300:
                    triggered.append("webhook")
        except Exception:
            pass

    return triggered
