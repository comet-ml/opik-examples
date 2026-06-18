"""
[Example title]

[One sentence: what this demonstrates.]

Run without credentials for a dry-run that prints output locally.
Set OPIK_API_KEY and OPIK_WORKSPACE to send data to Opik.
"""

import os

# ── Credentials ───────────────────────────────────────────────────────────────
OPIK_API_KEY   = os.environ.get("OPIK_API_KEY")
OPIK_WORKSPACE = os.environ.get("OPIK_WORKSPACE")
OPIK_URL       = os.environ.get("OPIK_URL_OVERRIDE", "https://www.comet.com/opik/api")

DRY_RUN = not (OPIK_API_KEY and OPIK_WORKSPACE)


# ── Your code ─────────────────────────────────────────────────────────────────

def main() -> None:
    if DRY_RUN:
        print("[DRY RUN] No credentials set — printing output locally.")
        print("Set OPIK_API_KEY and OPIK_WORKSPACE to send data to Opik.")

    # TODO: implement the example


if __name__ == "__main__":
    main()
