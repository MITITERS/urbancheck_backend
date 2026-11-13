"""C-16: Dependabot abre sus PR contra ``develop``, no contra ``main``.

``main`` recibe solo releases; un PR de dependencias contra ``main`` se saltea
``develop`` y su CI.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_every_update_targets_develop():
    config = yaml.safe_load((ROOT / ".github" / "dependabot.yml").read_text())

    for update in config["updates"]:
        assert update.get("target-branch") == "develop", update["package-ecosystem"]
