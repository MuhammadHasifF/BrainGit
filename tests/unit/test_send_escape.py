from __future__ import annotations

from brainbot.telegram.send import confirmation_buttons, escape_md


def test_escape_md_escapes_specials() -> None:
    assert escape_md("hello.world") == r"hello\.world"
    assert escape_md("a_b*c") == r"a\_b\*c"
    assert escape_md("(brackets)") == r"\(brackets\)"


def test_escape_md_leaves_plain_text() -> None:
    assert escape_md("plain text 123") == "plain text 123"


def test_confirmation_buttons_layout() -> None:
    rows = confirmation_buttons("delete_email_abc")
    assert len(rows) == 1
    labels = [lbl for lbl, _ in rows[0]]
    assert "✅ Yes" in labels[0]
    assert "❌ No" in labels[1]
    assert rows[0][0][1].endswith(":yes")
    assert rows[0][1][1].endswith(":no")
