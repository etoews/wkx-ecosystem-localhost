"""The pure ``parse_roadmap`` over synthetic GitHub Flavored Markdown.

Every fixture here is invented markdown, never captured. The parser counts
exactly GFM task items, skips fenced code blocks, and reads no heading or table
convention, so these pin each of those rules directly.
"""

from __future__ import annotations

import pytest

from wkx_ecosystem_localhost.collectors.roadmap import parse_roadmap


@pytest.mark.parametrize(
    "line",
    [
        "- [ ] dash unticked",
        "* [ ] star unticked",
        "+ [ ] plus unticked",
        "1. [ ] ordered dot unticked",
        "1) [ ] ordered paren unticked",
        "    - [ ] indented unticked",
        "\t- [ ] tab-indented unticked",
    ],
)
def test_a_single_unticked_task_item_counts_toward_total_only(line: str) -> None:
    progress = parse_roadmap(line + "\n")

    assert (progress.ticked, progress.total) == (0, 1)


@pytest.mark.parametrize(
    "line",
    [
        "- [x] lowercase ticked",
        "- [X] uppercase ticked",
        "3. [x] ordered ticked",
        "    * [X] indented uppercase ticked",
    ],
)
def test_a_single_ticked_task_item_counts_toward_both(line: str) -> None:
    progress = parse_roadmap(line + "\n")

    assert (progress.ticked, progress.total) == (1, 1)


@pytest.mark.parametrize(
    "line",
    [
        "# [ ] a heading, not a task",
        "- a plain list item, no checkbox",
        "text [ ] a checkbox mid-sentence, not at line start",
        "| [ ] | a table cell |",
        "-[ ] no space after the marker",
        "- [] an empty checkbox is not a task",
        "- [y] a non-x letter is not a checkbox",
        "> - [ ] inside a blockquote is not a bare list item",
        "",
    ],
)
def test_non_task_lines_are_ignored(line: str) -> None:
    progress = parse_roadmap(line + "\n")

    assert (progress.ticked, progress.total) == (0, 0)


def test_fenced_code_blocks_are_skipped() -> None:
    text = (
        "- [x] a real ticked task\n"
        "```markdown\n"
        "- [ ] this is a code sample, not a task\n"
        "- [x] neither is this\n"
        "```\n"
        "- [ ] a real unticked task\n"
    )

    progress = parse_roadmap(text)

    assert (progress.ticked, progress.total) == (1, 2)


def test_a_tilde_fence_also_skips_and_a_backtick_run_inside_it_does_not_close_it() -> None:
    text = (
        "~~~\n"
        "- [ ] inside a tilde fence\n"
        "```\n"
        "- [x] a backtick run does not close a tilde fence\n"
        "~~~\n"
        "- [ ] back outside, this counts\n"
    )

    progress = parse_roadmap(text)

    assert (progress.ticked, progress.total) == (0, 1)


def test_a_mixed_document_counts_only_the_task_items() -> None:
    text = (
        "# Roadmap\n"
        "\n"
        "Some prose describing the plan.\n"
        "\n"
        "## Milestone one\n"
        "- [x] done one\n"
        "- [X] done two\n"
        "- [ ] still open\n"
        "  - [x] a nested, ticked sub-task\n"
        "\n"
        "A table that must not be read as tasks:\n"
        "| item | state |\n"
        "| --- | --- |\n"
        "| foo | [ ] |\n"
        "\n"
        "```python\n"
        "checklist = ['- [ ] not a task']\n"
        "```\n"
        "\n"
        "1. [ ] an ordered open item\n"
        "2. [x] an ordered done item\n"
    )

    progress = parse_roadmap(text)

    # Ticked: done one, done two, nested sub-task, ordered done -> 4.
    # Total: those four plus "still open" and the ordered open item -> 6.
    assert (progress.ticked, progress.total) == (4, 6)


def test_an_empty_file_has_no_task_items() -> None:
    progress = parse_roadmap("")

    assert (progress.ticked, progress.total) == (0, 0)
