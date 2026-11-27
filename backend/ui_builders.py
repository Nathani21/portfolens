"""Build A2UI v1.0 messages for the portfolio dashboard. Pure functions, no web imports.

Layout lives in components; numbers live in the data model. Components bind to
the data model with {"@path": "/..."}, so price updates only need a new data
model, not a new layout.

Spec: https://a2ui.org/specification/v1.0-a2ui/
"""

import re

A2UI_VERSION = "1.0"
BASIC_CATALOG_ID = "https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json"
DEFAULT_SURFACE_ID = "portfolio_dashboard"

# Components from the basic catalog that our layouts use.
KNOWN_COMPONENTS = {"Text", "Row", "Column", "Card", "Divider", "List"}

# Enum values allowed by the v1.0 basic catalog (checked against catalog.json).
# v1.0 Text has no heading variants: emphasis comes from `weight` instead.
ALLOWED_VALUES = {
    "Text": {"variant": {"caption", "body"}},
    "Row": {
        "justify": {"start", "center", "end", "spaceBetween", "spaceAround", "spaceEvenly", "stretch"},
        "align": {"start", "center", "end", "stretch"},
    },
    "Column": {
        "justify": {"start", "center", "end", "spaceBetween", "spaceAround", "spaceEvenly", "stretch"},
        "align": {"start", "center", "end", "stretch"},
    },
}

TITLE_WEIGHT = 700
EMPHASIS_WEIGHT = 600

# UAX #31-style identifier: letters, digits and underscores, not starting with a digit.
ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


# --- Formatting (the data model holds display strings) ---

def format_money(amount):
    """1234.5 -> "$1,234.50"; negative amounts get a minus sign."""
    sign = "-" if amount < 0 else ""
    return f"{sign}${abs(amount):,.2f}"


def format_signed_money(amount):
    """Like format_money, but always shows + or - (zero shows +)."""
    sign = "-" if amount < 0 else "+"
    return f"{sign}${abs(amount):,.2f}"


def format_pct(pct):
    """2.5 -> "+2.50%"; None (division by zero) -> "—"."""
    if pct is None:
        return "—"
    sign = "-" if pct < 0 else "+"
    return f"{sign}{abs(pct):.2f}%"


def format_change(amount, pct):
    """Money change with its percentage: "+$40.00 (+0.92%)"."""
    return f"{format_signed_money(amount)} ({format_pct(pct)})"


def format_shares(shares):
    """10.0 -> "10 shares", 1.5 -> "1.5 shares", 1.0 -> "1 share"."""
    text = f"{shares:g}"
    return f"{text} share" if shares == 1 else f"{text} shares"


# --- Data model ---

def dashboard_data_model(summary, mode):
    """Turn portfolio_summary() output into the data model the dashboard binds to.

    `mode` is "demo" or "live" (from the price service).
    """
    missing = summary["missing"]
    return {
        "mode_note": (
            "Live prices" if mode == "live" else "Demo prices, not real market data"
        ),
        "totals": {
            "value": format_money(summary["total_value"]),
            "day": format_change(summary["day_change"], summary["day_change_pct"]),
            "pnl": format_change(summary["pnl"], summary["pnl_pct"]),
        },
        "positions": [
            {
                "ticker": p["ticker"],
                "shares": format_shares(p["shares"]),
                "value": format_money(p["value"]),
                "day": format_change(p["day_change"], p["day_change_pct"]),
                "weight": format_pct(p["weight_pct"]).lstrip("+"),
            }
            for p in summary["positions"]
        ],
        "missing_note": f"No price for {', '.join(missing)}" if missing else "",
    }


# --- Components ---

def _text(component_id, text, variant=None, weight=None):
    """A Text component; `text` is a literal string or {"@path": ...}.

    `variant` is "caption" or "body"; `weight` is a font weight like 600.
    """
    component = {"id": component_id, "component": "Text", "text": text}
    if variant:
        component["variant"] = variant
    if weight:
        component["weight"] = weight
    return component


def _bind(path):
    """A data binding to a JSON Pointer path."""
    return {"@path": path}


def _kpi_card(name, label, path):
    """A Card with a caption label above a bound value. Returns 4 components."""
    return [
        {"id": f"kpi_{name}", "component": "Card", "child": f"kpi_{name}_body"},
        {
            "id": f"kpi_{name}_body",
            "component": "Column",
            "children": [f"kpi_{name}_label", f"kpi_{name}_value"],
        },
        _text(f"kpi_{name}_label", label, "caption"),
        _text(f"kpi_{name}_value", _bind(path), weight=EMPHASIS_WEIGHT),
    ]


def dashboard_components():
    """The default dashboard layout: header, three KPI cards, one row per holding.

    Holding rows use a template, so the layout doesn't change with the number
    of holdings. Paths inside the template are relative to each position.
    """
    return [
        {
            "id": "root",
            "component": "Column",
            "children": ["header", "kpi_row", "holdings_title", "holdings", "missing"],
        },
        {"id": "header", "component": "Column", "children": ["title", "mode_note"]},
        _text("title", "Portfolio", weight=TITLE_WEIGHT),
        _text("mode_note", _bind("/mode_note"), "caption"),
        {
            "id": "kpi_row",
            "component": "Row",
            "children": ["kpi_value", "kpi_day", "kpi_pnl"],
            "justify": "spaceBetween",
        },
        *_kpi_card("value", "Total value", "/totals/value"),
        *_kpi_card("day", "Today", "/totals/day"),
        *_kpi_card("pnl", "Total gain/loss", "/totals/pnl"),
        _text("holdings_title", "Holdings", weight=EMPHASIS_WEIGHT),
        {
            "id": "holdings",
            "component": "Column",
            "children": {"path": "/positions", "componentId": "position_row"},
        },
        {
            "id": "position_row",
            "component": "Row",
            "children": ["position_name", "position_numbers"],
            "justify": "spaceBetween",
            "align": "center",
        },
        {
            "id": "position_name",
            "component": "Column",
            "children": ["position_ticker", "position_shares"],
        },
        _text("position_ticker", _bind("ticker"), weight=EMPHASIS_WEIGHT),
        _text("position_shares", _bind("shares"), "caption"),
        {
            "id": "position_numbers",
            "component": "Column",
            "children": ["position_value", "position_day", "position_weight"],
            "align": "end",
        },
        _text("position_value", _bind("value")),
        _text("position_day", _bind("day"), "caption"),
        _text("position_weight", _bind("weight"), "caption"),
        _text("missing", _bind("/missing_note"), "caption"),
    ]


# --- Messages ---

def create_dashboard_messages(summary, mode, surface_id=DEFAULT_SURFACE_ID):
    """A2UI messages that draw the dashboard: one createSurface with everything."""
    components = dashboard_components()
    check_components(components)
    return [
        {
            "version": A2UI_VERSION,
            "createSurface": {
                "surfaceId": surface_id,
                "catalogId": BASIC_CATALOG_ID,
                "components": components,
                "dataModel": dashboard_data_model(summary, mode),
            },
        }
    ]


def update_dashboard_message(summary, mode, surface_id=DEFAULT_SURFACE_ID):
    """One updateDataModel message that replaces all numbers but keeps the layout."""
    return {
        "version": A2UI_VERSION,
        "updateDataModel": {
            "surfaceId": surface_id,
            "path": "/",
            "value": dashboard_data_model(summary, mode),
        },
    }


# --- Structural checks ---

def _child_ids(component):
    """IDs this component points to: `child`, a `children` list, or a template."""
    if "child" in component:
        return [component["child"]]
    children = component.get("children")
    if isinstance(children, list):
        return list(children)
    if isinstance(children, dict):
        return [children.get("componentId")]
    return []


def check_components(components):
    """Check the rules A2UI renderers rely on. Raises ValueError on the first problem.

    - every component has a valid, unique id and a known component type
    - enum properties (Text variant, Row/Column justify and align) use allowed values
    - exactly one component has the id "root"
    - every child id points to a component that exists
    - templates have a string path and a componentId

    This is a structural check, not full JSON Schema validation against the catalog.
    """
    if not isinstance(components, list) or not components:
        raise ValueError("Components must be a non-empty list.")

    ids = set()
    for component in components:
        if not isinstance(component, dict):
            raise ValueError("Every component must be an object.")
        component_id = component.get("id")
        if not isinstance(component_id, str) or not ID_PATTERN.match(component_id):
            raise ValueError(f"Invalid component id: {component_id!r}.")
        if component_id in ids:
            raise ValueError(f"Duplicate component id: {component_id}.")
        component_type = component.get("component")
        if not isinstance(component_type, str) or component_type not in KNOWN_COMPONENTS:
            raise ValueError(f"{component_id}: unknown component type {component_type!r}.")
        for prop, allowed in ALLOWED_VALUES.get(component_type, {}).items():
            value = component.get(prop)
            if prop in component and (not isinstance(value, str) or value not in allowed):
                raise ValueError(
                    f"{component_id}: {prop} {value!r} isn't allowed "
                    f"for {component_type}."
                )
        ids.add(component_id)

    if "root" not in ids:
        raise ValueError('There must be a component with the id "root".')

    for component in components:
        children = component.get("children")
        if isinstance(children, dict) and not isinstance(children.get("path"), str):
            raise ValueError(f"{component['id']}: template needs a string path.")
        for child_id in _child_ids(component):
            if not isinstance(child_id, str) or child_id not in ids:
                raise ValueError(f"{component['id']}: child {child_id!r} doesn't exist.")
