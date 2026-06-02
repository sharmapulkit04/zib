"""Lifecycle tests for NotesProcess — the outbound notes gateway interaction.

Proves the process assembles a domain Delta correctly from the git port: diff
text, commit log, magnitude (driven by churn against the from-side tree), and the
optional annotated-tag notes. Driven by the validated FakeGitPort double.
"""

from __future__ import annotations

from zib.core.entities.shared.value_objects import CommitSha, TreeEntry
from zib.core.gateways.git.notes.process.notes_process import NotesProcess
from zib.core.gateways.git.port.git_port import GitCommit
from zib.core.rules.computation.delta.delta import Magnitude
from tests.gateways.git.port.fake_git_port import FakeGitPort

SOURCE = "github.com/acme/specs"
FROM_HEX = "a" * 40
TO_HEX = "b" * 40

SAMPLE_DIFF = """\
diff --git a/README.md b/README.md
--- a/README.md
+++ b/README.md
@@ -1,2 +1,2 @@
-old
+new
"""


def _file(path: str, line_count: int) -> TreeEntry:
    # A blob with exactly `line_count` newline-terminated lines.
    body = "".join(f"line{i}\n" for i in range(line_count)).encode()
    return TreeEntry(path=path, mode=0o100644, blob=body)


def _make_port(diff: str, from_tree: list[TreeEntry]) -> FakeGitPort:
    port = FakeGitPort()
    port.add_rev(SOURCE, FROM_HEX)
    port.add_rev(SOURCE, TO_HEX)
    port.set_tree(SOURCE, FROM_HEX, from_tree)
    port.set_diff(SOURCE, FROM_HEX, TO_HEX, diff)
    return port


def test_delta_carries_diff_text_and_commits() -> None:
    port = _make_port(SAMPLE_DIFF, [_file("README.md", 200)])
    commits = [
        GitCommit(commit=CommitSha(TO_HEX), subject="fix typo", body="body text"),
    ]
    port.set_log(SOURCE, FROM_HEX, TO_HEX, commits)

    process = NotesProcess(port)
    delta = process.delta(SOURCE, CommitSha(FROM_HEX), CommitSha(TO_HEX), None)

    assert delta.diff_text == SAMPLE_DIFF
    assert len(delta.commits) == 1
    assert delta.commits[0].subject == "fix typo"
    assert delta.commits[0].body == "body text"


def test_small_diff_against_large_tree_is_incremental() -> None:
    # 1 insertion + 1 deletion = churn 2 / 200 = 0.01, well below 0.5 threshold.
    port = _make_port(SAMPLE_DIFF, [_file("README.md", 200)])
    process = NotesProcess(port)

    delta = process.delta(SOURCE, CommitSha(FROM_HEX), CommitSha(TO_HEX), None)

    assert delta.magnitude is Magnitude.INCREMENTAL


def test_high_churn_diff_against_tiny_tree_is_rewrite() -> None:
    # A big diff (many +/-) against a 2-line baseline: churn far above threshold.
    big_diff = "diff --git a/f b/f\n--- a/f\n+++ b/f\n@@ @@\n" + (
        "-old\n" * 5 + "+new\n" * 5
    )
    # churn = (5 + 5) / 2 = 5.0 >= 0.5 -> REWRITE
    port = _make_port(big_diff, [_file("f", 2)])
    process = NotesProcess(port)

    delta = process.delta(SOURCE, CommitSha(FROM_HEX), CommitSha(TO_HEX), None)

    assert delta.magnitude is Magnitude.REWRITE


def test_tag_notes_present_when_to_tag_given() -> None:
    port = _make_port(SAMPLE_DIFF, [_file("README.md", 200)])
    port.set_tag_message(SOURCE, "v2.0.0", "Release 2.0.0 — breaking changes")
    process = NotesProcess(port)

    delta = process.delta(
        SOURCE, CommitSha(FROM_HEX), CommitSha(TO_HEX), None, to_tag="v2.0.0"
    )

    assert delta.tag_notes == "Release 2.0.0 — breaking changes"


def test_tag_notes_absent_when_no_to_tag() -> None:
    port = _make_port(SAMPLE_DIFF, [_file("README.md", 200)])
    port.set_tag_message(SOURCE, "v2.0.0", "should not appear")
    process = NotesProcess(port)

    delta = process.delta(SOURCE, CommitSha(FROM_HEX), CommitSha(TO_HEX), None)

    assert delta.tag_notes is None


def test_tag_notes_none_when_tag_unannotated() -> None:
    # to_tag given but no message registered -> port.tag_message returns None.
    port = _make_port(SAMPLE_DIFF, [_file("README.md", 200)])
    process = NotesProcess(port)

    delta = process.delta(
        SOURCE, CommitSha(FROM_HEX), CommitSha(TO_HEX), None, to_tag="v2.0.0"
    )

    assert delta.tag_notes is None


def test_empty_from_tree_makes_any_change_a_rewrite() -> None:
    # lines_before = 0 -> max(0,1)=1 denominator; any non-zero churn >= 0.5.
    port = _make_port(SAMPLE_DIFF, [])
    process = NotesProcess(port)

    delta = process.delta(SOURCE, CommitSha(FROM_HEX), CommitSha(TO_HEX), None)

    # SAMPLE_DIFF has 1 insertion + 1 deletion = churn 2/1 = 2.0 -> REWRITE
    assert delta.magnitude is Magnitude.REWRITE


def test_lines_before_sums_newlines_across_blobs() -> None:
    # Two files: 10 + 30 = 40 lines before. Diff churn = 2/40 = 0.05 -> INCREMENTAL.
    port = _make_port(SAMPLE_DIFF, [_file("a.md", 10), _file("b.md", 30)])
    process = NotesProcess(port)

    delta = process.delta(SOURCE, CommitSha(FROM_HEX), CommitSha(TO_HEX), None)

    assert delta.magnitude is Magnitude.INCREMENTAL
