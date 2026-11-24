"""
Regressions for the errors of 2026-11-24 in the main cycle (runs #124 and #125).

1. GitHub Pages: deploy-pages looked the artifact up in the run's artifact list right after
   upload-pages-artifact finalized it. The list had not caught up yet (2 of the 3 artifacts were
   listed), so the deploy failed with 'No artifacts named "github-pages" were found' and the run was
   marked failed although the paper-trading job had succeeded. The job now waits until the run lists
   the artifact and retries the deploy once.
2. Telegram: the daily settlement summary put game ids (ESPN_401910036_2026-11-24_MEM_AT_CHA) and
   market names (total_points) outside Markdown entities. Their '_' shifted the italics pairing and
   left the footer's closing '_' open, so the Bot API answered HTTP 400 "Can't find end of the entity
   starting at byte offset 925" and the summary was resent without formatting.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from src.reporting.telegram_bot import TelegramAlertBot, escape_markdown

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONTROL = b"_*`["


def telegram_legacy_markdown(text: str) -> str:
    """
    Port of the Bot API parser for parse_mode="Markdown" (legacy): a backslash escapes a control
    character outside an entity; an entity's text runs to the next end character and is read literally
    (entities do not nest). Returns the rendered text, or raises ValueError with the Bot API's message.
    """
    data = text.encode("utf-8")
    out = bytearray()
    i, n = 0, len(data)
    while i < n:
        ch = data[i]
        if ch == ord("\\") and i + 1 < n and data[i + 1] in _CONTROL:
            out.append(data[i + 1])
            i += 2
            continue
        if ch not in _CONTROL:
            out.append(ch)
            i += 1
            continue
        begin = i
        i += 1
        if ch == ord("`") and data[i : i + 2] == b"``":
            end = data.find(b"```", i + 2)
            if end < 0:
                raise ValueError(f"Can't find end of the entity starting at byte offset {begin}")
            out += data[i + 2 : end]
            i = end + 3
            continue
        end_char = ord("]") if ch == ord("[") else ch
        end = data.find(bytes([end_char]), i)
        if end < 0:
            raise ValueError(f"Can't find end of the entity starting at byte offset {begin}")
        out += data[i:end]
        i = end + 1
        if ch == ord("[") and data[i : i + 1] == b"(":
            close = data.find(b")", i)
            if close < 0:
                raise ValueError(f"Can't find end of a URL at byte offset {i}")
            i = close + 1
    return out.decode("utf-8")


def _bot(tmp_path: Path) -> TelegramAlertBot:
    return TelegramAlertBot(bot_token="fake_token", chat_id="1", alerts_log_path=tmp_path / "alerts.json")


def _settlement_summary(
    bot: TelegramAlertBot,
    bets: list[dict[str, Any]],
    props: list[dict[str, Any]] | None = None,
    parlays: list[dict[str, Any]] | None = None,
) -> str:
    return bot.format_daily_settlement_report(
        matchday_date="2026-11-24",
        settled_bets=bets,
        settled_props=props or [],
        current_bankroll_pen=97.97,
        initial_bankroll_pen=100.0,
        peak_bankroll_pen=101.93,
        cppi_multiplier=1.0,
        parlay_bankroll_state={"settled_bankroll_pen": 50.0, "cumulative_net_profit_pen": 0.0, "roi_pct": 0.0},
        settled_parlays=parlays or [],
    )


# --- 2. Telegram Markdown ---------------------------------------------------------------------------


def test_parser_port_reproduces_the_bot_api_error() -> None:
    # The game id's 5 underscores pair up as italics, the 5th pairs with the footer's opening '_', and
    # the footer's closing '_' (the last byte) is left open: the error the Bot API returned.
    text = "  1. ❌ ESPN_401910036_2026-11-24_MEM_AT_CHA moneyline HOME (S/ -1.01)\n🔒 _Historial auditado._"
    with pytest.raises(ValueError, match=f"byte offset {len(text.encode('utf-8')) - 1}$"):
        telegram_legacy_markdown(text)


def test_escape_markdown_escapes_only_control_characters() -> None:
    assert escape_markdown("ESPN_1 *x* `y` [z]") == "ESPN\\_1 \\*x\\* \\`y\\` \\[z]"
    assert telegram_legacy_markdown(escape_markdown("a_b*c`d[e]")) == "a_b*c`d[e]"
    assert escape_markdown(229.5) == "229.5"


def test_settlement_summary_of_2026_11_24_is_valid_markdown(tmp_path: Path) -> None:
    bet = {
        "game_id": "ESPN_401910036_2026-11-24_MEM_AT_CHA",
        "market": "moneyline",
        "selection": "HOME",
        "status": "LOST",
        "net_profit_pen": -1.01,
        "stake_pen": 1.01,
    }
    rendered = telegram_legacy_markdown(_settlement_summary(_bot(tmp_path), [bet]))
    assert "ESPN_401910036_2026-11-24_MEM_AT_CHA moneyline HOME" in rendered
    assert rendered.endswith("Historial y balance auditado e inmutable en SQLite (Dual Bankroll: S/100 + S/50).")


def test_settlement_summary_with_totals_props_and_parlays_is_valid_markdown(tmp_path: Path) -> None:
    bets = [
        {
            "game_id": "ESPN_401910040_2026-11-24_BOS_AT_GSW",
            "market": "total_points",
            "selection": "UNDER",
            "line_value": 229.5,
            "status": "WON",
            "net_profit_pen": 1.20,
            "stake_pen": 1.31,
        },
        {
            "game_id": "ESPN_401910036_2026-11-24_MEM_AT_CHA",
            "market": "moneyline",
            "selection": "HOME",
            "status": "LOST",
            "net_profit_pen": -1.01,
            "stake_pen": 1.01,
        },
    ]
    props = [
        {
            "player_name": "Ernest Udeh Jr.",
            "prop_category": "points_rebounds",
            "selection": "OVER",
            "line_value": 12.5,
            "status": "WON",
            "net_profit_pen": 0.90,
            "stake_pen": 1.00,
        }
    ]
    parlays = [{"parlay_id": "SGP_1", "summary": "MEM_AT_CHA ML + total_points", "status": "LOST", "net_profit_pen": -1.0}]
    rendered = telegram_legacy_markdown(_settlement_summary(_bot(tmp_path), bets, props, parlays))
    assert "ESPN_401910040_2026-11-24_BOS_AT_GSW total_points UNDER" in rendered
    assert "points_rebounds OVER 12.5" in rendered
    assert "MEM_AT_CHA ML + total_points" in rendered


def test_empty_settlement_summary_is_valid_markdown(tmp_path: Path) -> None:
    telegram_legacy_markdown(_settlement_summary(_bot(tmp_path), []))


def test_alerts_with_provider_labels_and_categories_are_valid_markdown(tmp_path: Path) -> None:
    bot = _bot(tmp_path)
    surebet = telegram_legacy_markdown(
        bot.format_surebet_alert(
            {
                "book_a": "Te Apuesto Perú [LIVE_API]",
                "selection_a": "HOME",
                "odds_a": 2.10,
                "stake_a_pen": 5.0,
                "book_b": "Pinnacle [LIVE_API]",
                "selection_b": "AWAY",
                "odds_b": 2.05,
                "stake_b_pen": 5.1,
            }
        )
    )
    assert "Te Apuesto Perú [LIVE_API]" in surebet and "Pinnacle [LIVE_API]" in surebet

    sgp = telegram_legacy_markdown(
        bot.format_sgp_parlay_alert(
            {
                "legs": [{"player_name": "Ernest Udeh Jr.", "category": "points_rebounds", "selection": "OVER", "line": 12.5}],
                "offered_sgp_odds": 3.2,
                "p_joint": 0.35,
                "p_independent": 0.30,
                "fair_sgp_odds": 2.9,
                "ev_pct": 5.0,
                "kelly_stake_pen": 1.0,
            }
        )
    )
    assert "Ernest Udeh Jr. points_rebounds OVER 12.5" in sgp

    high_prob = telegram_legacy_markdown(
        bot.format_high_prob_parlay_alert(
            {
                "legs": [{"desc": "MEM_AT_CHA moneyline HOME", "prob": 0.80, "odds": 1.30}],
                "decimal_odds": 1.69,
                "p_joint": 0.64,
                "ev_pct": 3.0,
                "stake_pen": 1.0,
            }
        )
    )
    assert "MEM_AT_CHA moneyline HOME" in high_prob


# --- 1. GitHub Pages deploy -------------------------------------------------------------------------


def test_pages_deploy_waits_for_the_artifact_and_retries_once() -> None:
    wf = yaml.safe_load((PROJECT_ROOT / ".github" / "workflows" / "nba_cloud_automation.yml").read_text(encoding="utf-8"))
    job = wf["jobs"]["deploy-pages"]
    steps = job["steps"]
    uses = [str(s.get("uses", "")) for s in steps]
    upload = next(i for i, u in enumerate(uses) if u.startswith("actions/upload-pages-artifact"))
    deploys = [i for i, u in enumerate(uses) if u.startswith("actions/deploy-pages")]
    wait = next(i for i, s in enumerate(steps) if "artifacts?name=github-pages" in str(s.get("run", "")))
    assert len(deploys) == 2
    assert upload < wait < deploys[0] < deploys[1]

    first, retry = steps[deploys[0]], steps[deploys[1]]
    assert first["id"] == "deployment" and first.get("continue-on-error") is True
    assert retry["id"] == "deployment_retry"
    assert retry["if"] == "steps.deployment.outcome == 'failure'"
    assert "steps.deployment_retry.outputs.page_url" in job["environment"]["url"]
    # The wait step lists the run's artifacts, which needs read access to Actions on a private
    # repository (the full least-privilege set is pinned by test_t018_workflows_least_privilege_and_ci_branch_gate).
    assert job["permissions"].get("actions") == "read"
