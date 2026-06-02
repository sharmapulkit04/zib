"""content_hash rule — exhaustive unit tests (pure function: trees in, hash out).

Covers every property the pin's reproducibility leans on: order-independence,
path/mode/content sensitivity, symlink-by-target, NFC normalization, empty trees, and
the output shape.
"""

from __future__ import annotations

import unicodedata

from zib.core.entities.shared.value_objects import SYMLINK_MODE, ContentHash, TreeEntry
from zib.core.rules.computation.content_hash.content_hash import compute_content_hash

REG = 0o100644
EXE = 0o100755


def _f(path: str, blob: bytes, mode: int = REG) -> TreeEntry:
    return TreeEntry(path=path, mode=mode, blob=blob)


def test_returns_well_formed_content_hash():
    result = compute_content_hash([_f("a.md", b"hello")])
    assert isinstance(result, ContentHash)
    assert result.value.startswith("sha256:")
    assert len(result.value) == len("sha256:") + 64


def test_deterministic_for_same_tree():
    tree = [_f("a.md", b"x"), _f("b/c.md", b"y")]
    assert compute_content_hash(tree) == compute_content_hash(list(tree))


def test_independent_of_input_order():
    a = compute_content_hash([_f("a.md", b"x"), _f("b.md", b"y")])
    b = compute_content_hash([_f("b.md", b"y"), _f("a.md", b"x")])
    assert a == b


def test_content_change_changes_hash():
    assert compute_content_hash([_f("a.md", b"x")]) != compute_content_hash([_f("a.md", b"y")])


def test_path_change_changes_hash():
    assert compute_content_hash([_f("a.md", b"x")]) != compute_content_hash([_f("b.md", b"x")])


def test_mode_change_changes_hash():
    # Same path + content, different mode (exec bit) → different hash.
    assert compute_content_hash([_f("s.sh", b"x", REG)]) != compute_content_hash(
        [_f("s.sh", b"x", EXE)]
    )


def test_framing_prevents_path_content_collision():
    # Without length-framing, ("ab","c") could collide with ("a","bc"). It must not.
    one = compute_content_hash([_f("ab", b"c")])
    two = compute_content_hash([_f("a", b"bc")])
    assert one != two


def test_symlink_hashed_by_target_not_dereferenced():
    # A symlink entry carries its target as the blob; a regular file with the same bytes
    # but a normal mode must hash differently (mode participates).
    link = compute_content_hash([_f("link", b"target/path", SYMLINK_MODE)])
    file = compute_content_hash([_f("link", b"target/path", REG)])
    assert link != file


def test_nfc_normalization_makes_equivalent_paths_equal():
    # "é" composed (NFC) vs decomposed (NFD) name the same file; hashes must match.
    nfc = unicodedata.normalize("NFC", "café.md")
    nfd = unicodedata.normalize("NFD", "café.md")
    assert nfc != nfd  # different byte sequences pre-normalization
    assert compute_content_hash([_f(nfc, b"x")]) == compute_content_hash([_f(nfd, b"x")])


def test_empty_tree_is_stable():
    assert compute_content_hash([]) == compute_content_hash([])
    # Adding any file moves it off the empty value.
    assert compute_content_hash([]) != compute_content_hash([_f("a", b"")])


def test_empty_file_distinct_from_absent_file():
    assert compute_content_hash([_f("a", b"")]) != compute_content_hash(
        [_f("a", b""), _f("b", b"")]
    )
