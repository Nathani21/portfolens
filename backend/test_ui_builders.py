import json

import pytest

from portfolio import Holding, Quote, portfolio_summary
from ui_builders import (
    BASIC_CATALOG_ID,
    check_components,
    create_dashboard_messages,
    dashboard_components,
    dashboard_data_model,
    format_change,
    format_money,
    format_pct,
    format_shares,
    update_dashboard_message,
)

HOLDINGS = [Holding("AAPL", 10, 150), Holding("MSFT", 6, 250), Holding("TSLA", 1, 200)]
QUOTES = {
    "AAPL": Quote(price=200, prev_close=190),
    "MSFT": Quote(price=400, prev_close=410),
}
SUMMARY = portfolio_summary(HOLDINGS, QUOTES)


def component_by_id(components):
    """Map id -> component, for easy lookups in tests."""
    return {c["id"]: c for c in components}


def bound_paths(components):
    """Every {"@path": ...} used in the components."""
    paths = []
    for component in components:
        for value in component.values():
            if isinstance(value, dict) and "@path" in value:
                paths.append(value["@path"])
    return paths


def resolve(data, pointer):
    """Follow a JSON Pointer like /totals/value through nested dicts."""
    for part in pointer.strip("/").split("/"):
        data = data[part]
    return data


# --- formatting ---

@pytest.mark.parametrize(
    "amount, expected",
    [(1234.5, "$1,234.50"), (0, "$0.00"), (-60, "-$60.00"), (1_000_000, "$1,000,000.00")],
)
def test_format_money(amount, expected):
    assert format_money(amount) == expected


@pytest.mark.parametrize("pct, expected", [(2.5, "+2.50%"), (-2.439, "-2.44%"), (0, "+0.00%"), (None, "—")])
def test_format_pct(pct, expected):
    assert format_pct(pct) == expected


def test_format_change():
    assert format_change(40, 40 / 4360 * 100) == "+$40.00 (+0.92%)"
    assert format_change(-60, -2.439) == "-$60.00 (-2.44%)"


@pytest.mark.parametrize("shares, expected", [(10.0, "10 shares"), (1.0, "1 share"), (1.5, "1.5 shares")])
def test_format_shares(shares, expected):
    assert format_shares(shares) == expected


# --- data model ---

def test_data_model_totals_and_positions():
    model = dashboard_data_model(SUMMARY, "demo")
    assert model["totals"] == {
        "value": "$4,400.00",
        "day": "+$40.00 (+0.92%)",
        "pnl": "+$1,400.00 (+46.67%)",
    }
    assert [p["ticker"] for p in model["positions"]] == ["MSFT", "AAPL"]
    assert model["positions"][0] == {
        "ticker": "MSFT",
        "shares": "6 shares",
        "value": "$2,400.00",
        "day": "-$60.00 (-2.44%)",
        "weight": "54.55%",
    }


def test_data_model_notes():
    assert dashboard_data_model(SUMMARY, "demo")["mode_note"].startswith("Demo prices")
    assert dashboard_data_model(SUMMARY, "live")["mode_note"] == "Live prices"
    assert dashboard_data_model(SUMMARY, "demo")["missing_note"] == "No price for TSLA"


def test_data_model_no_missing():
    summary = portfolio_summary(HOLDINGS[:2], QUOTES)
    assert dashboard_data_model(summary, "demo")["missing_note"] == ""


def test_data_model_empty_portfolio():
    model = dashboard_data_model(portfolio_summary(HOLDINGS, {}), "demo")
    assert model["totals"]["value"] == "$0.00"
    assert model["totals"]["pnl"] == "+$0.00 (—)"
    assert model["positions"] == []


# --- components ---

def test_dashboard_components_pass_the_checks():
    check_components(dashboard_components())


def test_every_absolute_binding_exists_in_the_data_model():
    model = dashboard_data_model(SUMMARY, "demo")
    for path in bound_paths(dashboard_components()):
        if path.startswith("/"):
            resolve(model, path)  # raises KeyError if the path is wrong


def test_template_bindings_exist_on_each_position():
    model = dashboard_data_model(SUMMARY, "demo")
    relative = [p for p in bound_paths(dashboard_components()) if not p.startswith("/")]
    assert relative  # the template does bind to item fields
    for position in model["positions"]:
        for path in relative:
            assert path in position


def test_holdings_use_a_template_over_positions():
    holdings = component_by_id(dashboard_components())["holdings"]
    assert holdings["children"] == {"path": "/positions", "componentId": "position_row"}


# --- messages ---

def test_create_dashboard_messages():
    messages = create_dashboard_messages(SUMMARY, "demo")
    assert len(messages) == 1
    message = messages[0]
    assert message["version"] == "1.0"
    surface = message["createSurface"]
    assert surface["surfaceId"] == "portfolio_dashboard"
    assert surface["catalogId"] == BASIC_CATALOG_ID
    assert surface["dataModel"]["totals"]["value"] == "$4,400.00"
    assert set(message) == {"version", "createSurface"}  # exactly one message key


def test_messages_are_json_serialisable():
    json.dumps(create_dashboard_messages(SUMMARY, "live"))
    json.dumps(update_dashboard_message(SUMMARY, "live"))


def test_update_dashboard_message_replaces_whole_model():
    message = update_dashboard_message(SUMMARY, "live", surface_id="s1")
    update = message["updateDataModel"]
    assert message["version"] == "1.0"
    assert update["surfaceId"] == "s1"
    assert update["path"] == "/"
    assert update["value"] == dashboard_data_model(SUMMARY, "live")


# --- check_components ---

def valid():
    """A minimal valid component list."""
    return [
        {"id": "root", "component": "Column", "children": ["a"]},
        {"id": "a", "component": "Text", "text": "hi"},
    ]


def test_check_components_accepts_minimal():
    check_components(valid())


@pytest.mark.parametrize(
    "components, message",
    [
        ([], "non-empty list"),
        ("root", "non-empty list"),
        (["root"], "must be an object"),
        ([{"id": "a", "component": "Text", "text": "x"}], 'id "root"'),
        ([{"id": "user-card", "component": "Text", "text": "x"}], "Invalid component id"),
        ([{"id": "1abc", "component": "Text", "text": "x"}], "Invalid component id"),
        ([{"component": "Text", "text": "x"}], "Invalid component id"),
        (
            [{"id": "root", "component": "Text", "text": "x"}, {"id": "root", "component": "Text", "text": "y"}],
            "Duplicate component id: root",
        ),
        ([{"id": "root", "component": "Surface"}], "unknown component type 'Surface'"),
        ([{"id": "root", "component": "Column", "children": ["ghost"]}], "child 'ghost' doesn't exist"),
        ([{"id": "root", "component": "Card", "child": "ghost"}], "child 'ghost' doesn't exist"),
        ([{"id": "root", "component": "Column", "children": [{"x": 1}]}], "doesn't exist"),
        (
            [{"id": "root", "component": "Column", "children": {"componentId": "root"}}],
            "template needs a string path",
        ),
        (
            [{"id": "root", "component": "Column", "children": {"path": "/x", "componentId": "ghost"}}],
            "child 'ghost' doesn't exist",
        ),
    ],
)
def test_check_components_rejects(components, message):
    with pytest.raises(ValueError, match=message):
        check_components(components)
