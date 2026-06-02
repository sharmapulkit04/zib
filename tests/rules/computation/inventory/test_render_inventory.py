"""Exhaustive unit tests for the inventory render rule.

Pure function: items in, markdown body out. Every assertion is on a CONCRETE substring
the agent relies on (name, role, resolved pin, on-disk path, the pending marker), or on
exact ordering. No fakes, no I/O.
"""

from __future__ import annotations

from zib.core.rules.computation.inventory.render_inventory import (
    InventoryItem,
    render_inventory,
)


def _item(
    name: str,
    role: str = "json-mapping",
    ref_type: str = "semver",
    resolved: str = "v1.2.3",
    description: str | None = "maps JSON to domain types",
    owed_delta: bool = False,
) -> InventoryItem:
    return InventoryItem(
        name=name,
        role=role,
        ref_type=ref_type,
        resolved=resolved,
        description=description,
        owed_delta=owed_delta,
    )


def test_single_item_renders_name_role_resolved_and_path() -> None:
    body = render_inventory([_item("openspec", role="spec-driven", resolved="v0.5.0")])
    assert "openspec · spec-driven" in body
    assert "v0.5.0" in body
    assert ".zib/references/openspec/" in body


def test_single_item_renders_its_description() -> None:
    body = render_inventory([_item("openspec", description="how we drive specs")])
    assert "how we drive specs" in body


def test_ref_type_is_shown_alongside_resolved() -> None:
    body = render_inventory([_item("otlp", ref_type="branch", resolved="main@abc1234")])
    assert "main@abc1234 (branch)" in body


def test_owed_delta_true_renders_pending_marker_with_diff_command() -> None:
    body = render_inventory([_item("otlp", owed_delta=True)])
    assert "UPDATE PENDING" in body
    assert "`zib diff otlp`" in body
    assert "`zib confirm otlp`" in body


def test_owed_delta_false_renders_no_pending_marker() -> None:
    body = render_inventory([_item("otlp", owed_delta=False)])
    assert "UPDATE PENDING" not in body
    assert "zib diff" not in body


def test_pending_marker_only_for_the_owed_item() -> None:
    body = render_inventory(
        [
            _item("alpha", owed_delta=False),
            _item("beta", owed_delta=True),
        ]
    )
    assert "`zib diff beta`" in body
    assert "`zib diff alpha`" not in body
    assert body.count("UPDATE PENDING") == 1


def test_empty_list_renders_stable_no_references_body() -> None:
    body = render_inventory([])
    assert body == (
        "## Managed references (zib)\n"
        "\n"
        "No references are pinned yet. Run `zib add <name> --role <role> --git <repo>` to add one."
    )


def test_items_are_sorted_by_name_regardless_of_input_order() -> None:
    body = render_inventory(
        [
            _item("zeta"),
            _item("alpha"),
            _item("mike"),
        ]
    )
    assert body.index("zeta") > body.index("mike") > body.index("alpha")


def test_none_description_falls_back_to_name_and_role() -> None:
    body = render_inventory([_item("otlp", role="tracing", description=None)])
    assert "otlp · tracing" in body
    # the fallback "<name> · <role>" line is present as the description too
    assert body.count("otlp · tracing") == 2


def test_empty_string_description_falls_back_to_name_and_role() -> None:
    body = render_inventory([_item("otlp", role="tracing", description="")])
    assert body.count("otlp · tracing") == 2


def test_body_has_header_and_selection_guidance() -> None:
    body = render_inventory([_item("openspec")])
    assert body.startswith("## Managed references (zib)")
    assert "`zib cat <name>`" in body


def test_body_does_not_end_with_trailing_blank_line() -> None:
    body = render_inventory([_item("alpha"), _item("beta")])
    assert not body.endswith("\n")
    assert "\n\n\n" not in body


def test_each_item_renders_its_own_content_path() -> None:
    body = render_inventory([_item("alpha"), _item("beta")])
    assert ".zib/references/alpha/" in body
    assert ".zib/references/beta/" in body


def test_inventory_item_is_frozen() -> None:
    item = _item("alpha")
    try:
        item.name = "changed"  # type: ignore[misc]
    except Exception as exc:  # FrozenInstanceError subclasses Exception
        assert "cannot assign" in str(exc).lower() or "frozen" in type(exc).__name__.lower()
    else:
        raise AssertionError("InventoryItem must be frozen/immutable")
