"""
Notion Properties Module

Helper functions for building Notion property objects and blocks.
These builders simplify the creation of Notion API-compatible data structures.
"""

from typing import Any, Dict, List


def build_title_property(text: str) -> Dict[str, Any]:
    """Build a Notion title property."""
    return {"title": [{"text": {"content": text}}]}


def build_rich_text_property(text: str) -> Dict[str, Any]:
    """Build a Notion rich_text property."""
    return {"rich_text": [{"text": {"content": text}}]}


def build_select_property(option_name: str) -> Dict[str, Any]:
    """Build a Notion select property."""
    return {"select": {"name": option_name}}


def build_multi_select_property(option_names: List[str]) -> Dict[str, Any]:
    """Build a Notion multi_select property."""
    return {"multi_select": [{"name": name} for name in option_names]}


def build_email_property(email: str) -> Dict[str, Any]:
    """Build a Notion email property."""
    return {"email": email}


def build_url_property(url: str) -> Dict[str, Any]:
    """Build a Notion url property."""
    return {"url": url}


def build_paragraph_block(text: str) -> Dict[str, Any]:
    """Build a Notion paragraph block."""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }
