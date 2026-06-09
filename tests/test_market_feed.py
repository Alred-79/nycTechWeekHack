"""
Unit tests for ui/feed_parse.parse_research_feed.

Covers: empty/None input, single item, max cap, category classification,
XSS escaping, markdown stripping, short-content filtering, delay ordering,
multi-heading documents, and the intro-paragraph edge case.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ui.feed_parse import parse_research_feed


# ── Null / empty inputs ────────────────────────────────────────────────────────

def test_empty_string_returns_empty():
    assert parse_research_feed("") == []


def test_whitespace_only_returns_empty():
    assert parse_research_feed("   \n\n\t  ") == []


def test_none_returns_empty():
    assert parse_research_feed(None) == []


def test_max_items_zero_returns_empty():
    assert parse_research_feed("- Meaningful insight about banking compliance.", max_items=0) == []


# ── Single item ────────────────────────────────────────────────────────────────

def test_single_plain_paragraph():
    result = parse_research_feed("Community banks face rising AML scrutiny from regulators.")
    assert len(result) == 1
    assert result[0]["text"] == "Community banks face rising AML scrutiny from regulators."


def test_single_bullet():
    result = parse_research_feed("- US community banks need better AML tooling urgently.")
    assert len(result) == 1


# ── Item cap ──────────────────────────────────────────────────────────────────

def test_default_cap_at_six():
    lines = "\n".join(f"- Item {i} about important banking compliance findings." for i in range(10))
    result = parse_research_feed(lines)
    assert len(result) == 6


def test_custom_max_items():
    lines = "\n".join(f"- Item {i} about important banking compliance findings." for i in range(10))
    result = parse_research_feed(lines, max_items=3)
    assert len(result) == 3


def test_max_items_one():
    lines = "\n".join(f"- Item {i} about important banking compliance findings." for i in range(5))
    result = parse_research_feed(lines, max_items=1)
    assert len(result) == 1


# ── Category classification ───────────────────────────────────────────────────

def test_buyer_keyword_classifies_correctly():
    result = parse_research_feed("Community bank buyers need better compliance tools.")
    assert result[0]["category"] == "BUYER INTEL"
    assert result[0]["color"] == "#5fd0e0"


def test_fincen_keyword_is_regulatory():
    result = parse_research_feed("FinCEN MPS 2024-01 cited three banks for AML failures.")
    assert result[0]["category"] == "REGULATORY"
    assert result[0]["color"] == "#ff5468"


def test_occ_consent_order_is_regulatory():
    result = parse_research_feed("OCC consent order AA-ENF-2025-21 mandated SAR lookback review.")
    assert result[0]["category"] == "REGULATORY"


def test_pain_keyword_classifies_correctly():
    result = parse_research_feed("Rules-based systems struggle to catch mule-ring patterns.")
    assert result[0]["category"] == "PAIN SIGNAL"
    assert result[0]["color"] == "#f7b733"


def test_why_now_keyword_classifies_correctly():
    result = parse_research_feed("Urgent mandate: all banks must comply by 2025.")
    assert result[0]["category"] == "WHY NOW"
    assert result[0]["color"] == "#34d6a4"


def test_unknown_keyword_falls_back_to_intelligence():
    result = parse_research_feed("An unusual finding with no category keywords at all here.")
    assert result[0]["category"] == "INTELLIGENCE"
    assert result[0]["color"] == "#8ab4ff"


def test_heading_section_title_informs_category():
    text = "## Regulatory Risk\n- Banks missed structuring patterns per peer review."
    result = parse_research_feed(text)
    assert result[0]["category"] == "REGULATORY"


def test_heading_buyer_segment():
    text = "## Buyer Segment\n- US community banks with 1B to 50B in assets are the target."
    result = parse_research_feed(text)
    assert result[0]["category"] == "BUYER INTEL"


# ── XSS and HTML safety ───────────────────────────────────────────────────────

def test_script_tag_is_escaped():
    result = parse_research_feed("- <script>alert('xss')</script> an important AML insight here.")
    assert len(result) == 1
    assert "<script>" not in result[0]["text"]
    assert "&lt;script&gt;" in result[0]["text"]


def test_html_angle_brackets_escaped():
    result = parse_research_feed("- Banks with assets <50B are at risk from AML examinations.")
    assert "<50B" not in result[0]["text"]
    assert "&lt;50B" in result[0]["text"]


def test_ampersand_escaped():
    result = parse_research_feed("- Structuring & layering patterns evade rules-based monitoring systems.")
    assert "&amp;" in result[0]["text"]


# ── Markdown stripping ────────────────────────────────────────────────────────

def test_bold_markers_stripped():
    result = parse_research_feed("**Community Banks**: Key target segment for AML compliance platform.")
    assert "**" not in result[0]["text"]
    assert "Community Banks" in result[0]["text"]


def test_italic_markers_stripped():
    # Use a mid-sentence italic so it's not consumed by the bullet regex
    result = parse_research_feed("The *key insight* is that penalty exposure is growing for banks.")
    assert "*" not in result[0]["text"]
    assert "key insight" in result[0]["text"]


# ── Short content filtering ───────────────────────────────────────────────────

def test_very_short_item_filtered():
    result = parse_research_feed("- Too short.")
    assert result == []


def test_exactly_15_chars_not_filtered():
    # "Exactly fifteen" = 15 chars → passes the < 15 filter
    result = parse_research_feed("- Exactly fifteen")
    assert len(result) == 1


def test_short_heading_with_long_bullet():
    text = "## OK\n- This bullet is long enough to pass the fifteen-character filter easily."
    result = parse_research_feed(text)
    assert len(result) == 1


# ── Delay ordering ────────────────────────────────────────────────────────────

def test_delays_start_at_zero():
    result = parse_research_feed("- A meaningful finding about compliance and risk exposure.")
    assert result[0]["delay"] == 0.0


def test_delays_monotonically_increasing():
    lines = "\n".join(f"- Item {i} about important banking compliance findings." for i in range(4))
    result = parse_research_feed(lines)
    delays = [r["delay"] for r in result]
    assert delays == sorted(delays)
    assert all(d >= 0 for d in delays)


def test_delay_field_always_present():
    result = parse_research_feed("- A meaningful finding about AML compliance risk today.")
    assert "delay" in result[0]


# ── Multi-section documents ───────────────────────────────────────────────────

def test_multiple_headings_produce_multiple_items():
    text = (
        "## Buyer Segment\n"
        "- US community banks with one to fifty billion in assets.\n\n"
        "## Regulatory Risk\n"
        "- FinCEN cited three institutions for missing ring patterns.\n"
    )
    result = parse_research_feed(text)
    assert len(result) == 2


def test_intro_paragraph_before_first_heading_captured():
    text = (
        "This is an important overview of the compliance landscape.\n\n"
        "## Buyer Segment\n"
        "- US community banks need better tooling for AML detection.\n"
    )
    result = parse_research_feed(text)
    assert len(result) == 2


def test_multiple_categories_across_headings():
    text = (
        "## Buyer Segment\n"
        "- Community banks and credit unions are the primary segment.\n\n"
        "## Regulatory Risk\n"
        "- FinCEN MPS 2024-01 cited three banks for missing ring patterns.\n\n"
        "## Pain Signal\n"
        "- Legacy systems struggle to detect cross-account layering schemes.\n"
    )
    result = parse_research_feed(text)
    cats = {r["category"] for r in result}
    assert "BUYER INTEL" in cats
    assert "REGULATORY" in cats
    assert "PAIN SIGNAL" in cats


# ── Return value structure ────────────────────────────────────────────────────

def test_item_has_all_required_keys():
    result = parse_research_feed("- A meaningful compliance insight for banking institutions.")
    assert set(result[0].keys()) == {"category", "color", "text", "delay"}
