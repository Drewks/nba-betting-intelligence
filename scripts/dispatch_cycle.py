#!/usr/bin/env python3
"""
scripts/dispatch_cycle.py — Zero-Latency Workflow Dispatcher

Triggers the GitHub Actions stateful cloud cycle instantly via GitHub REST API,
bypassing the public GitHub Actions cron queue latency.
Works with zero third-party dependencies (Python 3 standard library only).

Usage:
  python scripts/dispatch_cycle.py --mode auto
  python scripts/dispatch_cycle.py --mode pregame
  python scripts/dispatch_cycle.py --mode settle_and_calibrate
  python scripts/dispatch_cycle.py --dry-run
  python scripts/dispatch_cycle.py --help
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

WORKFLOW_FILE = "nba_cloud_automation.yml"


def resolve_repository(explicit_repo: str | None = None) -> str:
    """Resolves owner/repo from explicit arg, env var, or local git remote."""
    if explicit_repo:
        return explicit_repo.strip()

    env_repo = os.getenv("GITHUB_REPOSITORY")
    if env_repo:
        return env_repo.strip()

    try:
        remote_url = (
            subprocess.check_output(
                ["git", "config", "--get", "remote.origin.url"],
                stderr=subprocess.DEVNULL,
            )
            .decode("utf-8")
            .strip()
        )
        # Parse https://github.com/owner/repo.git or git@github.com:owner/repo.git
        match = re.search(r"github\.com[:/]([^/]+/[^/.]+)(?:\.git)?", remote_url)
        if match:
            return match.group(1)
    except Exception:
        pass

    return "Drewks/nba-betting-intelligence"


def resolve_token(explicit_token: str | None = None) -> str | None:
    """Resolves GitHub authentication token from arg, env vars, or gh CLI."""
    if explicit_token:
        return explicit_token.strip()

    for var in ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT"):
        val = os.getenv(var)
        if val and val.strip():
            return val.strip()

    try:
        out = subprocess.check_output(["gh", "auth", "token"], stderr=subprocess.DEVNULL).decode("utf-8").strip()
        if out:
            return out
    except Exception:
        pass

    return None


def dispatch_workflow(
    repo: str,
    token: str,
    mode: str = "auto",
    ref: str = "main",
    dry_run: bool = False,
) -> bool:
    """Dispatches the workflow via GitHub API and returns True on success."""
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    payload = {
        "ref": ref,
        "inputs": {
            "cycle_mode": mode,
        },
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
        "User-Agent": "NBA-Betting-Intelligence-Dispatcher",
    }
    data_bytes = json.dumps(payload).encode("utf-8")

    masked_token = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "***"
    print(f"[*] Repositorio: {repo}")
    print(f"[*] Workflow:     {WORKFLOW_FILE}")
    print(f"[*] Rama/Ref:     {ref}")
    print(f"[*] Modo:         {mode}")
    print(f"[*] Token:        {masked_token}")
    print(f"[*] Endpoint:     POST {url}")

    if dry_run:
        print("\n[DRY RUN] Simulación activada. No se envió la petición HTTP.")
        print(f"Payload JSON:\n{json.dumps(payload, indent=2)}")
        print("\nComando equivalente cURL:")
        print(
            f"curl -X POST \\\n"
            f'  -H "Accept: application/vnd.github+json" \\\n'
            f'  -H "Authorization: Bearer <TU_GITHUB_TOKEN>" \\\n'
            f'  -H "X-GitHub-Api-Version: 2022-11-28" \\\n'
            f"  {url} \\\n"
            f"  -d '{json.dumps(payload)}'"
        )
        return True

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            if status in (204, 201, 200):
                print(f"\n[OK] ¡Disparo exitoso! HTTP {status} (Workflow encolado inmediatamente sin demora).")
                print(f"Ver ejecuciones en vivo: https://github.com/{repo}/actions/workflows/{WORKFLOW_FILE}")
                return True
            else:
                print(f"\n[!] Respuesta inesperada: HTTP {status}")
                return False
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        print(f"\n[ERROR] Falló el disparo: HTTP {exc.code} {exc.reason}")
        print(f"Detalle: {err_body}")
        if exc.code == 401:
            print("[AYUDA] El token no es válido o ha expirado.")
        elif exc.code == 404:
            print("[AYUDA] No se encontró el repositorio o el token no tiene permisos de 'workflow' / 'actions:write'.")
        return False
    except Exception as exc:
        print(f"\n[ERROR] Error de conexión: {exc}")
        return False


def wait_and_print_run_status(repo: str, token: str, max_wait_seconds: int = 30) -> None:
    """Polls runs endpoint briefly to show the URL of the newly created run."""
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/runs?per_page=1"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "NBA-Betting-Intelligence-Dispatcher",
    }
    req = urllib.request.Request(url, headers=headers)
    print("\nBuscando ID de ejecución iniciada...")
    time.sleep(4)

    start_time = time.time()
    while time.time() - start_time < max_wait_seconds:
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                runs = data.get("workflow_runs", [])
                if runs:
                    latest = runs[0]
                    created_at = latest.get("created_at")
                    html_url = latest.get("html_url")
                    status = latest.get("status")
                    print(f"[>] Run URL: {html_url}")
                    print(f"[>] Estado inicial: {status} (Creado: {created_at})")
                    return
        except Exception:
            pass
        time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Disparador externo de latencia cero para NBA Cloud Automation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/dispatch_cycle.py --mode pregame
  python scripts/dispatch_cycle.py --mode settle_and_calibrate
  python scripts/dispatch_cycle.py --dry-run
  python scripts/dispatch_cycle.py --wait
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["auto", "pregame", "settle_and_calibrate"],
        default="auto",
        help="Modo de ejecución del ciclo (por defecto: auto).",
    )
    parser.add_argument(
        "--ref",
        default="main",
        help="Rama o referencia de git en la que se ejecutará el workflow (por defecto: main).",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Repositorio en formato owner/repo (por defecto auto-detectado).",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="GitHub Personal Access Token con permiso 'actions:write' o 'repo' (o variable GITHUB_TOKEN).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simula la llamada y muestra el comando cURL equivalente sin enviar la petición.",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Espera unos segundos tras el disparo para obtener la URL directa de la ejecución.",
    )

    args = parser.parse_args()
    repo = resolve_repository(args.repo)
    token = resolve_token(args.token)

    if not token and not args.dry_run:
        print("[ERROR] No se encontró ningún token de GitHub.")
        print("Configura la variable de entorno GITHUB_TOKEN o pasa el parámetro --token <TU_PAT>.")
        print("Ejemplo en PowerShell:")
        print("  $env:GITHUB_TOKEN='ghp_xxxx'")
        print("  python scripts/dispatch_cycle.py --mode pregame\n")
        print("O usa --dry-run para ver el comando cURL:")
        print("  python scripts/dispatch_cycle.py --dry-run")
        sys.exit(1)

    effective_token = token or "DUMMY_TOKEN_FOR_DRY_RUN"
    success = dispatch_workflow(
        repo=repo,
        token=effective_token,
        mode=args.mode,
        ref=args.ref,
        dry_run=args.dry_run,
    )

    if success and args.wait and not args.dry_run and token:
        wait_and_print_run_status(repo, token)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
