from __future__ import annotations

from pathlib import Path

from execution_accelerator.adapters import PomMutationAdapter
from execution_accelerator.nodes import build_remediate_simple_node
from tests.conftest import seed_workspace_pom
from tests.test_remediation_nodes import build_state


def test_remediate_simple_node_preserves_existing_workspace_content(tmp_path) -> None:
    fixture_dir = Path(__file__).parents[1] / "fixtures"
    node = build_remediate_simple_node(
        PomMutationAdapter(
            fixture_before_path=fixture_dir / "pom_before.xml",
            fixture_after_path=fixture_dir / "pom_after.xml",
        )
    )
    state = build_state(tmp_path)
    workspace = Path(state.repo_map["payments-service"].local_path)
    pom_path = seed_workspace_pom(workspace, fixture_dir / "pom_before.xml")
    pom_path.write_text(pom_path.read_text().replace("<dependencies>", "<!-- DO NOT OVERWRITE --><dependencies>", 1))

    update = node(state)
    mutated_xml = Path(update["modified_files"][0]).read_text()

    assert "<!-- DO NOT OVERWRITE -->" in mutated_xml
    assert "1.2.4" in mutated_xml
    assert "1.2.3" not in mutated_xml
