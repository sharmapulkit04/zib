"""Exhaustive unit tests for parse_diff_counts — the gateway diff-counting rule.

Pure function: input string in, ``(files, insertions, deletions)`` out. The load-
bearing subtlety is not miscounting the ``+++``/``---`` file headers as content.
"""

from __future__ import annotations

from zib.core.gateways.git.notes.rules.diff_stats import parse_diff_counts

# A realistic two-file unified diff. One file edited (1 add, 1 delete) and one
# file added (3 adds). The +++/--- headers must NOT be counted as +/- content.
SAMPLE_DIFF = """\
diff --git a/README.md b/README.md
index 1111111..2222222 100644
--- a/README.md
+++ b/README.md
@@ -1,3 +1,3 @@
 title
-old line
+new line
 footer
diff --git a/new.txt b/new.txt
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/new.txt
@@ -0,0 +1,3 @@
+first
+second
+third
"""


def test_sample_diff_exact_counts() -> None:
    # 2 files, 4 insertions (1 + 3), 1 deletion. +++/--- excluded.
    assert parse_diff_counts(SAMPLE_DIFF) == (2, 4, 1)


def test_empty_diff_is_all_zero() -> None:
    assert parse_diff_counts("") == (0, 0, 0)


def test_file_headers_not_counted_as_content() -> None:
    # Only the +++/--- file headers and the diff header — zero real content lines.
    only_headers = (
        "diff --git a/f b/f\n"
        "index aaa..bbb 100644\n"
        "--- a/f\n"
        "+++ b/f\n"
    )
    assert parse_diff_counts(only_headers) == (1, 0, 0)


def test_pure_insertions() -> None:
    diff = (
        "diff --git a/a b/a\n"
        "--- a/a\n"
        "+++ b/a\n"
        "@@ -0,0 +1,2 @@\n"
        "+alpha\n"
        "+beta\n"
    )
    assert parse_diff_counts(diff) == (1, 2, 0)


def test_pure_deletions() -> None:
    diff = (
        "diff --git a/a b/a\n"
        "--- a/a\n"
        "+++ b/a\n"
        "@@ -1,2 +0,0 @@\n"
        "-alpha\n"
        "-beta\n"
    )
    assert parse_diff_counts(diff) == (1, 0, 2)


def test_three_files_changed() -> None:
    diff = (
        "diff --git a/one b/one\n"
        "--- a/one\n"
        "+++ b/one\n"
        "@@ -1 +1 @@\n"
        "-x\n"
        "+y\n"
        "diff --git a/two b/two\n"
        "--- a/two\n"
        "+++ b/two\n"
        "@@ -1 +1 @@\n"
        "-a\n"
        "+b\n"
        "diff --git a/three b/three\n"
        "--- a/three\n"
        "+++ b/three\n"
        "@@ -0,0 +1 @@\n"
        "+c\n"
    )
    assert parse_diff_counts(diff) == (3, 3, 2)


def test_context_and_hunk_lines_ignored() -> None:
    # Context lines (leading space), @@ hunk headers, and index lines are not +/-.
    diff = (
        "diff --git a/f b/f\n"
        "index 111..222 100644\n"
        "--- a/f\n"
        "+++ b/f\n"
        "@@ -1,4 +1,4 @@\n"
        " unchanged-1\n"
        " unchanged-2\n"
        "-removed\n"
        "+added\n"
        " unchanged-3\n"
    )
    assert parse_diff_counts(diff) == (1, 1, 1)
