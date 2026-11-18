"""Create or update the Comet project view that shows training and downstream results together.

Usage: uv run --env-file .env python scripts/10_em_dashboard.py

The view holds a Python panel (panels/scorecard.py), a JavaScript panel
(panels/per_class_accuracy.js), the mAP curve and an experiment table with the mAP and opik_*
columns. Run it again after editing a panel file; the view is updated in place.
"""

from __future__ import annotations

from comet_ml import API

from roadwork_demo.config import exit_if_no_comet, get_settings
from roadwork_demo.dashboard import PANELS_DIR, VIEW_NAME, build_dashboard


def main() -> None:
    s = get_settings()
    exit_if_no_comet(s, f"create the project view '{VIEW_NAME}' in Comet project '{s.project}'")
    view = build_dashboard(
        (PANELS_DIR / "scorecard.py").read_text(), (PANELS_DIR / "per_class_accuracy.js").read_text()
    )
    api = API()
    existing = next((v for v in api.get_views(s.workspace, s.project) if v.name == VIEW_NAME), None)
    if existing is None:
        saved = api.create_view(s.workspace, s.project, view)
    else:
        view.template_id = existing.template_id
        saved = api.update_view(s.workspace, s.project, view)
    if saved is None:
        raise SystemExit(f"Comet did not save the view '{VIEW_NAME}'.")
    action = "Created" if existing is None else "Updated"
    print(f"{action} project view '{VIEW_NAME}' (id {saved.template_id}).")
    print(f"Open https://www.comet.com/{s.workspace}/{s.project} and pick it in the view selector.")


if __name__ == "__main__":
    main()
