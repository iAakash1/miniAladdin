"""Every feature in the panel has a definition, and every definition is a feature."""

from src.quant.pit import rich_panel as R
from src.quant.pit.rich_panel_catalog import CATALOG, COMMON


def test_catalog_and_panel_features_are_one_to_one():
    assert set(CATALOG) == set(R.NEW_FEATURES) | set(R.CONTROL_FEATURES)
    assert set(R.FAMILY) == set(CATALOG)


def test_every_definition_has_a_formula_and_inputs():
    for name, (formula, inputs, _) in CATALOG.items():
        assert formula.strip() and inputs.strip(), name


def test_controls_are_marked_as_gated():
    for name in R.CONTROL_FEATURES:
        assert "gated" in CATALOG[name][2].lower() or "gate" in CATALOG[name][2].lower(), name


def test_common_rules_state_the_after_close_and_missing_policies():
    assert "16:00" in COMMON["timestamp_rule"] and "never zero" in COMMON["missing_policy"]
