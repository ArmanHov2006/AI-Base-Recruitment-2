"""Tests for C1: @mention notifications in notes."""
import re

from app.notes.router import _MENTION_RE


def test_mention_regex_extracts_handles() -> None:
    text = "Hey @john.doe please review this candidate, also cc @jane"
    handles = _MENTION_RE.findall(text)
    assert "john.doe" in handles
    assert "jane" in handles


def test_mention_regex_no_handles() -> None:
    assert _MENTION_RE.findall("No mentions here.") == []


def test_mention_regex_email_style() -> None:
    handles = _MENTION_RE.findall("Ping @arman+test")
    assert "arman" in handles or "arman+test" in handles


def test_mention_re_pattern_compiled() -> None:
    assert isinstance(_MENTION_RE, type(re.compile("")))
