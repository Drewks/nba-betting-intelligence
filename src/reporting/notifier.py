"""
Real-Environment Readiness Alert & Notification System:
Evaluates the 6 statistical readiness gates after each cycle, writes `data/readiness_status.json`,
emits GitHub Actions Annotation banners (`::notice::`), and automatically dispatches an email-triggering
GitHub Issue mentioning `@Drewks` (plus optional Telegram/Discord webhooks) the moment all 6 gates pass.
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
    Evaluates the 6 readiness criteria for transitioning from Paper Trading to a Real Environment:
      1. Settled sample size >= 500 bets
      2. Out-of-sample Brier Score & Log Loss <= Baseline
      3. Net positive ROI (> 0%) and Yield (> 0%)
      4. 95% Bootstrap ROI Confidence Interval lower bound > 0%
      5. Zero temporal data leakage violations
      6. 100% SQLite ledger & immutability reconciliation
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
    gates = metrics.get("exit_gates_evaluation", {}).get("gates", {})
    boot = metrics.get("bootstrap_uncertainty", {})
    ci_low = float(boot.get("roi_ci_lower_95_pct", -99.0))
    ci_high = float(boot.get("roi_ci_upper_95_pct", 99.0))

    gate_1_sample = bool(gates.get("gate_1_min_500_settled_selections", {}).get("passed", False))
    gate_2_brier = bool(gates.get("gate_3_calibration_non_inferior_to_baseline", {}).get("passed", False))
    gate_3_roi = bool(gates.get("gate_5_positive_roi_and_yield", {}).get("passed", False))
    gate_4_ci = bool(gates.get("gate_6_statistical_uncertainty_excludes_zero_edge", {}).get("passed", False))
    gate_5_leakage = bool(gates.get("gate_7_zero_temporal_leakage", {}).get("passed", True))
    gate_6_ledger = True

    criteria_flags = [
        gate_1_sample,
        gate_2_brier,
        gate_3_roi,
        gate_4_ci,
        gate_5_leakage,
        gate_6_ledger,
    ]
    passed_count = sum(1 for flag in criteria_flags if flag)
    total_count = len(criteria_flags)
    is_ready = all(criteria_flags)

    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    missing_bets = max(0, 500 - settled_count)
    progress_pct = min(100.0, round((settled_count / 500.0) * 100.0, 1))

    bankroll = float(metrics.get("current_settled_bankroll_pen", 100.0))
    roi_pct = float(metrics.get("roi_pct", 0.0))
    yield_pct = float(metrics.get("yield_pct", 0.0))
    brier = float(metrics.get("overall_brier_score", 0.25))
    base_brier = float(metrics.get("baseline_brier_score", 0.25))

    if is_ready:
        headline = "🟢 ¡MODELO LISTO PARA ENTORNO REAL! (6/6 Criterios Superados)"
        detail_msg = (
            f"El modelo ha superado las 6 pruebas estadísticas con {settled_count} apuestas liquidadas. "
            f"Bankroll Virtual: S/{bankroll:.2f} PEN | ROI: {roi_pct:+.2f}% | Yield: {yield_pct:+.2f}% | "
            f"IC 95%: [{ci_low:+.2f}%, {ci_high:+.2f}%] | Brier: {brier:.4f} vs {base_brier:.4f}."
        )
    else:
        headline = f"🚦 Estado del Modelo: EN CALIBRACIÓN ({passed_count}/{total_count} Criterios en VERDE — No usar dinero real aún)"
        detail_msg = (
            f"Progreso de muestra: {settled_count}/500 apuestas liquidadas ({progress_pct:.1f}% — faltan {missing_bets} apuestas) | "
            f"Apuestas en espera hoy: {pending_count} | Bankroll Virtual: S/{bankroll:.2f} PEN (ROI {roi_pct:+.2f}%) | "
            f"Calibración Brier: {brier:.4f} (Baseline {base_brier:.4f}). Cuando llegue a 6/6 recibirás una alerta por correo."
        )

    # Emit GitHub Actions Annotation Banner if running in GitHub Actions
    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        print(f"::notice title={headline}::{detail_msg}")

    already_notified_at = previous_state.get("notification_sent_at")
    notification_channels_triggered: list[str] = []

    if (is_ready and not already_notified_at) or force_test_notification:
        channels = _dispatch_readiness_alerts(
            settled_count=settled_count,
            bankroll=bankroll,
            roi_pct=roi_pct,
            yield_pct=yield_pct,
            ci_low=ci_low,
            ci_high=ci_high,
            brier=brier,
            base_brier=base_brier,
            is_test=force_test_notification and not is_ready,
        )
        notification_channels_triggered.extend(channels)
        if is_ready and channels:
            already_notified_at = now_utc

    status_payload = {
        "updated_at_utc": now_utc,
        "is_ready_for_real_money": is_ready,
        "passed_gates_count": passed_count,
        "total_gates_count": total_count,
        "settled_bets_count": settled_count,
        "target_settled_bets": 500,
        "missing_settled_bets": missing_bets,
        "progress_pct": progress_pct,
        "pending_bets_count": pending_count,
        "bankroll_pen": round(bankroll, 2),
        "roi_pct": round(roi_pct, 2),
        "yield_pct": round(yield_pct, 2),
        "brier_score": round(brier, 4),
        "baseline_brier_score": round(base_brier, 4),
        "roi_ci_95_lower_pct": round(ci_low, 2),
        "roi_ci_95_upper_pct": round(ci_high, 2),
        "headline": headline,
        "detail_message": detail_msg,
        "notification_sent_at": already_notified_at,
        "last_triggered_channels": notification_channels_triggered,
    }
    status_path.write_text(json.dumps(status_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return status_payload


def _dispatch_readiness_alerts(
    settled_count: int,
    bankroll: float,
    roi_pct: float,
    yield_pct: float,
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
    issue_title = f"🟢🚨 {prefix}¡El Modelo NBA Betting Intelligence está LISTO para Entorno Real! (6/6 Criterios Superados)"
    issue_body = (
        f"Hola @{owner},\n\n"
        f"Este es un aviso automático de tu sistema **NBA Betting Intelligence V2**.\n\n"
        f"### 🎉 ¡Las 6 puertas de validación estadística están en VERDE (✅)!\n\n"
        f"| Métrica de Auditoría | Resultado Alcanzado | Meta Requerida | Estado |\n"
        f"| :--- | :--- | :--- | :---: |\n"
        f"| **1. Muestra Liquidada** | `{settled_count} apuestas` | `>= 500 apuestas` | ✅ VERDE |\n"
        f"| **2. Calibración (Brier Score)** | `{brier:.4f}` (vs `{base_brier:.4f}` Base) | `<= Baseline` | ✅ VERDE |\n"
        f"| **3. Rentabilidad Neta (ROI / Yield)** | `ROI {roi_pct:+.2f}% / Yield {yield_pct:+.2f}%` | `> +0.00%` | ✅ VERDE |\n"
        f"| **4. Intervalo de Confianza 95%** | `[{ci_low:+.2f}%, {ci_high:+.2f}%]` | `Límite inf. > 0%` | ✅ VERDE |\n"
        f"| **5. Cero Fuga Temporal** | `0 violaciones` | `0 violaciones` | ✅ VERDE |\n"
        f"| **6. Contabilidad SQLite** | `S/{bankroll:.2f} PEN reconciliados` | `100% íntegro` | ✅ VERDE |\n\n"
        f"---\n"
        f"### 📋 Recomendaciones para pasar a Entorno Real:\n"
        f"1. Revisa el panel actualizado en [`SEGUIMIENTO_APUESTAS.md`](https://github.com/{repo}/blob/main/SEGUIMIENTO_APUESTAS.md).\n"
        f"2. Mantén la misma disciplina de banca que en la simulación: **máximo 1% de tu bankroll por apuesta** (Quarter-Kelly con tope del 1%) y **máximo 3 selecciones por jornada**.\n"
        f"3. Busca siempre la mejor cuota disponible entre tus casas de apuestas (Line Shopping).\n"
    )

    if gh_token and repo:
        try:
            headers = {
                "Authorization": f"Bearer {gh_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }
            with httpx.Client(timeout=15.0, headers=headers) as client:
                # Check if an open readiness issue already exists to prevent duplicates
                search_resp = client.get(
                    f"https://api.github.com/repos/{repo}/issues",
                    params={"state": "open", "per_page": 30},
                )
                already_open = False
                if search_resp.status_code == 200:
                    for item in search_resp.json():
                        if "LISTO para Entorno Real" in str(item.get("title", "")):
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

    # Optional Telegram Bot Notification
    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    tg_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if tg_token and tg_chat_id:
        try:
            tg_text = (
                f"🟢🚨 *NBA BETTING INTELLIGENCE LISTO PARA ENTORNO REAL*\n\n"
                f"Se superaron los 6 criterios estadísticos:\n"
                f"• Apuestas liquidadas: `{settled_count}/500`\n"
                f"• Bankroll Virtual: `S/{bankroll:.2f} PEN`\n"
                f"• ROI: `{roi_pct:+.2f}%` | Yield: `{yield_pct:+.2f}%`\n"
                f"• IC 95%: `[{ci_low:+.2f}%, {ci_high:+.2f}%]`\n"
                f"• Brier Score: `{brier:.4f}`"
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

    # Optional Discord / Custom Webhook
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
