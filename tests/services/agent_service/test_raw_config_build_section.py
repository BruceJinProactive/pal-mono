"""Tests for RawConfig._build_section XML tag wrapping."""

from services.agent_service._raw_config import RawConfig


class TestBuildSection:
    """Test the _build_section static method."""

    def test_no_xml_tags_uses_markdown_headers(self):
        """Without xml_tags, headers are kept as markdown."""
        result = RawConfig._build_section(
            "# Section",
            [("## Header", "content")],
        )
        assert "## Header" in result
        assert "content" in result
        assert "<" not in "".join(result).replace("\n", "")

    def test_xml_tags_wraps_matching_headers(self):
        """Headers in xml_tags map get wrapped in XML."""
        tags = {"## Store Hours": "store_hours"}
        result = RawConfig._build_section(
            "# Store Context",
            [("## Store Hours", "Mon-Fri 9-5")],
            xml_tags=tags,
        )
        joined = "\n".join(result)
        assert "<store_hours>" in joined
        assert "</store_hours>" in joined
        assert "Mon-Fri 9-5" in joined
        assert "## Store Hours" not in joined

    def test_xml_tags_skips_unmatched_headers(self):
        """Headers not in xml_tags map keep markdown format."""
        tags = {"## Store Hours": "store_hours"}
        result = RawConfig._build_section(
            "# Store Context",
            [("## Custom Service Instruction", "Key rules here")],
            xml_tags=tags,
        )
        joined = "\n".join(result)
        assert "## Custom Service Instruction" in joined
        assert "Key rules here" in joined
        assert "<" not in joined.replace("\n", "")

    def test_empty_header_appends_content_only(self):
        """Empty header string should append content without a header."""
        result = RawConfig._build_section(
            "# Agent Instructions",
            [("", "<ordering>\nDo stuff.\n</ordering>")],
        )
        joined = "\n".join(result)
        assert "<ordering>" in joined
        assert "Do stuff." in joined

    def test_none_content_skipped(self):
        """Entries with None content are excluded."""
        result = RawConfig._build_section(
            "# Section",
            [("## Header", None), ("## Other", "present")],
        )
        joined = "\n".join(result)
        assert "## Header" not in joined
        assert "present" in joined

    def test_all_none_content_returns_empty(self):
        """If no content is present, returns empty list."""
        result = RawConfig._build_section(
            "# Section",
            [("## A", None), ("## B", None)],
        )
        assert result == []

    def test_mixed_xml_and_markdown(self):
        """Some headers get XML, others stay markdown."""
        tags = {
            "## Store Address": "store_address",
            "## Store Hours": "store_hours",
        }
        result = RawConfig._build_section(
            "# Store Context",
            [
                ("## Store Address", "123 Main St"),
                ("## Store Hours", "9-5"),
                ("## Custom Service Instruction", "Rules"),
            ],
            xml_tags=tags,
        )
        joined = "\n".join(result)
        assert "<store_address>" in joined
        assert "<store_hours>" in joined
        assert "## Custom Service Instruction" in joined
