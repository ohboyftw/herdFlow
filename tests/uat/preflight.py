"""UAT Pre-flight checks for HerdFlow ADK+LiveKit e2e test.

Validates all prerequisites before the manual e2e session.
Run: uv run python tests/uat/preflight.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Results collector
results: list[dict] = []


def check(test_id: str, title: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    icon = "\u2705" if passed else "\u274c"
    results.append({"id": test_id, "title": title, "status": status, "detail": detail})
    print(f"  {icon} {test_id}: {title}" + (f" — {detail}" if detail else ""))


def main() -> None:
    print("\n=== HerdFlow E2E Pre-flight Checks ===\n")

    project_root = Path(__file__).parent.parent.parent

    # --- Environment ---
    print("[ENV]")
    env_path = project_root / ".env"
    check("PRE-001", ".env file exists", env_path.exists())

    if env_path.exists():
        env_content = env_path.read_text()
        check("PRE-002", "LIVEKIT_URL configured", "LIVEKIT_URL=" in env_content and "wss://" in env_content)
        check("PRE-003", "LIVEKIT_API_KEY configured", "LIVEKIT_API_KEY=" in env_content and len([l for l in env_content.splitlines() if l.startswith("LIVEKIT_API_KEY=") and len(l.split("=", 1)[1]) > 5]) > 0)
        check("PRE-004", "LIVEKIT_API_SECRET configured", "LIVEKIT_API_SECRET=" in env_content and len([l for l in env_content.splitlines() if l.startswith("LIVEKIT_API_SECRET=") and len(l.split("=", 1)[1]) > 5]) > 0)
        check("PRE-005", "GOOGLE_API_KEY configured", "GOOGLE_API_KEY=" in env_content and len([l for l in env_content.splitlines() if l.startswith("GOOGLE_API_KEY=") and len(l.split("=", 1)[1]) > 5]) > 0,
              "Needed for Gemini Live API")

    # --- Credentials ---
    print("\n[CREDENTIALS]")
    creds_path = project_root / "credentials.json"
    check("PRE-006", "credentials.json exists", creds_path.exists())
    if creds_path.exists():
        try:
            creds = json.loads(creds_path.read_text())
            check("PRE-007", "credentials.json is valid JSON", True, f"type={creds.get('type', '?')}")
        except json.JSONDecodeError:
            check("PRE-007", "credentials.json is valid JSON", False, "Invalid JSON")

    # --- Video ---
    print("\n[VIDEO]")
    video_path = project_root / "demo_videos" / "yt_cattle_farm_720p.mp4"
    check("PRE-008", "Demo video exists", video_path.exists(),
          f"{video_path.stat().st_size // (1024*1024)}MB" if video_path.exists() else str(video_path))

    # --- Dependencies ---
    print("\n[DEPS]")
    try:
        import supervision  # noqa: F401
        check("PRE-009", "supervision importable", True)
    except ImportError:
        check("PRE-009", "supervision importable", False, "Run: uv sync --extra dev")

    try:
        import rfdetr  # noqa: F401
        check("PRE-010", "rfdetr importable", True)
    except ImportError:
        check("PRE-010", "rfdetr importable", False)

    try:
        from google.adk.agents import Agent  # noqa: F401
        check("PRE-011", "google-adk importable", True)
    except ImportError:
        check("PRE-011", "google-adk importable", False)

    try:
        from google.genai import types  # noqa: F401
        check("PRE-012", "google-genai importable", True)
    except ImportError:
        check("PRE-012", "google-genai importable", False)

    try:
        from livekit.agents import AgentServer  # noqa: F401
        check("PRE-013", "livekit-agents importable", True)
    except ImportError:
        check("PRE-013", "livekit-agents importable", False)

    try:
        from PIL import Image  # noqa: F401
        check("PRE-014", "Pillow importable", True)
    except ImportError:
        check("PRE-014", "Pillow importable", False)

    # --- Agent import chain (must run from project root) ---
    print("\n[AGENT]")
    import subprocess
    try:
        result = subprocess.run(
            [sys.executable, "-c", "from agent.main import server; print('OK')"],
            capture_output=True, text=True, cwd=str(project_root), timeout=15,
        )
        ok = result.returncode == 0
        check("PRE-015", "agent.main imports cleanly", ok,
              result.stderr.strip().split("\n")[-1][:100] if not ok else "")
    except Exception as e:
        check("PRE-015", "agent.main imports cleanly", False, str(e)[:100])

    try:
        result = subprocess.run(
            [sys.executable, "-c", "from agent.adk_agents import herd_tools; print(len(herd_tools))"],
            capture_output=True, text=True, cwd=str(project_root), timeout=15,
        )
        ok = result.returncode == 0
        detail = f"{result.stdout.strip()} tools" if ok else result.stderr.strip().split("\n")[-1][:100]
        check("PRE-016", "ADK tools available", ok, detail)
    except Exception as e:
        check("PRE-016", "ADK tools available", False, str(e)[:100])

    # --- Token freshness ---
    print("\n[TOKEN]")
    test_html = project_root / "frontend" / "public" / "test.html"
    if test_html.exists():
        import base64
        content = test_html.read_text()
        # Extract JWT token
        import re
        token_match = re.search(r"const TOKEN = '([^']+)'", content)
        if token_match:
            token = token_match.group(1)
            try:
                payload = json.loads(base64.b64decode(token.split(".")[1] + "=="))
                exp = payload.get("exp", 0)
                exp_dt = datetime.fromtimestamp(exp, tz=UTC)
                now = datetime.now(tz=UTC)
                is_valid = exp_dt > now
                check("PRE-017", "test.html token not expired", is_valid,
                      f"expires {exp_dt.isoformat()}" if is_valid else f"EXPIRED {exp_dt.isoformat()}")
            except Exception:
                check("PRE-017", "test.html token not expired", False, "Could not decode JWT")
        else:
            check("PRE-017", "test.html token not expired", False, "No TOKEN found in test.html")
    else:
        check("PRE-017", "test.html token not expired", False, "test.html not found")

    # --- Summary ---
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(f"\n{'='*50}")
    print(f"  {passed} passed, {failed} failed out of {len(results)} checks")

    if failed > 0:
        print(f"\n  BLOCKERS:")
        for r in results:
            if r["status"] == "FAIL":
                print(f"    {r['id']}: {r['title']}" + (f" — {r['detail']}" if r['detail'] else ""))

    critical_ids = {"PRE-001", "PRE-002", "PRE-003", "PRE-004", "PRE-006", "PRE-011", "PRE-013", "PRE-015"}
    critical_fails = [r for r in results if r["status"] == "FAIL" and r["id"] in critical_ids]

    if critical_fails:
        print(f"\n  VERDICT: BLOCKED — {len(critical_fails)} critical pre-flight failures")
        sys.exit(1)
    elif failed > 0:
        print(f"\n  VERDICT: PROCEED WITH CAUTION — non-critical issues")
        sys.exit(0)
    else:
        print(f"\n  VERDICT: ALL CLEAR — ready for e2e test")
        sys.exit(0)


if __name__ == "__main__":
    main()
