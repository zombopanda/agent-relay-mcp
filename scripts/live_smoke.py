"""Live provider smoke test for release gates.

This intentionally calls real external providers. It is not part of the unit
test suite because it costs money, depends on local auth, and may take seconds.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from agent_crossbar.server import review_sync


@dataclass(frozen=True)
class SmokeCase:
    profile: str
    sentinel: str
    model: str | None = None


CASES = (
    SmokeCase(profile="deepseek", model="deepseek-v4-flash", sentinel="DEEPSEEK_LIVE_SMOKE_OK"),
)


def main() -> int:
    failed = False
    for case in CASES:
        response = review_sync(
            profile=case.profile,
            model=case.model,
            prompt=f"Live release smoke test. Reply exactly: {case.sentinel}",
            timeout_sec=120,
            client_name="release-live-smoke",
        )
        output = response.get("output") or response.get("message") or ""
        selected = response.get("selected_candidate") or "none"
        ok = bool(response.get("ok")) and case.sentinel in output
        print(f"{case.profile}: ok={ok} selected={selected}")
        if not ok:
            failed = True
            print(output[-1000:], file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
