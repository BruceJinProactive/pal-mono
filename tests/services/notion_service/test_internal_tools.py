"""Tests for Notion internal tools service."""

from unittest.mock import AsyncMock, patch

import pytest

from services.notion_service._internal_tools import (
    INTERNAL_TOOLS_DATABASE_ID,
    TOOL_FEEDBACK_DATABASE_ID,
    TOOL_REQUESTS_DATABASE_ID,
    get_internal_tools,
    submit_tool_feedback,
    submit_tool_request,
)


class TestGetInternalTools:
    @pytest.mark.asyncio
    async def test_returns_tools_sorted_alphabetically(self) -> None:
        mock_client = AsyncMock()
        mock_client.databases.query.return_value = {
            "results": [
                {
                    "id": "page-2",
                    "properties": {
                        "Name": {
                            "type": "title",
                            "title": [{"plain_text": "Zebra Tool"}],
                        },
                        "Status": {"select": {"name": "Live"}},
                    },
                },
                {
                    "id": "page-1",
                    "properties": {
                        "Name": {
                            "type": "title",
                            "title": [{"plain_text": "Alpha Tool"}],
                        },
                        "Status": {"select": {"name": "Live"}},
                    },
                },
            ],
            "has_more": False,
            "next_cursor": None,
        }

        result = await get_internal_tools(client=mock_client)

        assert len(result) == 2
        assert result[0]["name"] == "Alpha Tool"
        assert result[1]["name"] == "Zebra Tool"

    @pytest.mark.asyncio
    async def test_filters_by_status_live(self) -> None:
        mock_client = AsyncMock()
        mock_client.databases.query.return_value = {
            "results": [],
            "has_more": False,
            "next_cursor": None,
        }

        await get_internal_tools(client=mock_client)

        call_kwargs = mock_client.databases.query.call_args
        assert call_kwargs.kwargs["filter"]["property"] == "Status"
        assert call_kwargs.kwargs["filter"]["select"]["equals"] == "Live"

    @pytest.mark.asyncio
    async def test_queries_correct_database(self) -> None:
        mock_client = AsyncMock()
        mock_client.databases.query.return_value = {
            "results": [],
            "has_more": False,
            "next_cursor": None,
        }

        await get_internal_tools(client=mock_client)

        call_kwargs = mock_client.databases.query.call_args
        assert call_kwargs.kwargs["database_id"] == INTERNAL_TOOLS_DATABASE_ID

    @pytest.mark.asyncio
    async def test_skips_tools_with_empty_names(self) -> None:
        mock_client = AsyncMock()
        mock_client.databases.query.return_value = {
            "results": [
                {
                    "id": "page-1",
                    "properties": {
                        "Name": {"type": "title", "title": []},
                    },
                },
                {
                    "id": "page-2",
                    "properties": {
                        "Name": {
                            "type": "title",
                            "title": [{"plain_text": "  "}],
                        },
                    },
                },
            ],
            "has_more": False,
            "next_cursor": None,
        }

        result = await get_internal_tools(client=mock_client)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_handles_pagination(self) -> None:
        mock_client = AsyncMock()
        mock_client.databases.query.side_effect = [
            {
                "results": [
                    {
                        "id": "p1",
                        "properties": {
                            "Name": {
                                "type": "title",
                                "title": [{"plain_text": "Tool A"}],
                            },
                        },
                    },
                ],
                "has_more": True,
                "next_cursor": "cursor-1",
            },
            {
                "results": [
                    {
                        "id": "p2",
                        "properties": {
                            "Name": {
                                "type": "title",
                                "title": [{"plain_text": "Tool B"}],
                            },
                        },
                    },
                ],
                "has_more": False,
                "next_cursor": None,
            },
        ]

        result = await get_internal_tools(client=mock_client)
        assert len(result) == 2
        assert mock_client.databases.query.call_count == 2

    @pytest.mark.asyncio
    async def test_returns_empty_list_on_exception(self) -> None:
        mock_client = AsyncMock()
        mock_client.databases.query.side_effect = Exception("API error")

        result = await get_internal_tools(client=mock_client)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_client_unavailable(self) -> None:
        with patch(
            "services.notion_service._internal_tools.get_notion_client",
            side_effect=ValueError("No token"),
        ):
            result = await get_internal_tools()
            assert result == []


class TestSubmitToolFeedback:
    @pytest.mark.asyncio
    async def test_creates_page_with_correct_properties(self) -> None:
        with patch(
            "services.notion_service._internal_tools.create_page",
            new_callable=AsyncMock,
            return_value="https://notion.so/page",
        ) as mock_create:
            result = await submit_tool_feedback(
                tool_name="Analytics",
                tool_page_id="abc123def456abc123def456abc123de",
                request_type="Bug",
                priority="P1",
                feedback_text="Something is broken",
                submitted_by="testuser",
            )

            assert result == "https://notion.so/page"
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args
            assert call_kwargs.kwargs["database_id"] == TOOL_FEEDBACK_DATABASE_ID
            props = call_kwargs.kwargs["properties"]
            assert "Feedback" in props
            assert "Tool" in props
            assert "Request type" in props
            assert "Priority" in props

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self) -> None:
        with patch(
            "services.notion_service._internal_tools.create_page",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            result = await submit_tool_feedback(
                tool_name="Analytics",
                tool_page_id="abc123",
                request_type="Bug",
                priority="P1",
                feedback_text="Error",
                submitted_by="testuser",
            )
            assert result is None


class TestSubmitToolRequest:
    @pytest.mark.asyncio
    async def test_creates_page_with_required_properties(self) -> None:
        with patch(
            "services.notion_service._internal_tools.create_page",
            new_callable=AsyncMock,
            return_value="https://notion.so/request",
        ) as mock_create:
            result = await submit_tool_request(
                request_title="New Dashboard",
                priority="P2",
                submitted_by="testuser",
            )

            assert result == "https://notion.so/request"
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args
            assert call_kwargs.kwargs["database_id"] == TOOL_REQUESTS_DATABASE_ID
            props = call_kwargs.kwargs["properties"]
            assert "Request" in props
            assert "Priority" in props

    @pytest.mark.asyncio
    async def test_includes_optional_problem_context(self) -> None:
        with patch(
            "services.notion_service._internal_tools.create_page",
            new_callable=AsyncMock,
            return_value="https://notion.so/request",
        ) as mock_create:
            await submit_tool_request(
                request_title="New Tool",
                priority="P1",
                problem_context="We need this because...",
            )

            props = mock_create.call_args.kwargs["properties"]
            assert "Problem / context" in props

    @pytest.mark.asyncio
    async def test_includes_optional_proposed_solution(self) -> None:
        with patch(
            "services.notion_service._internal_tools.create_page",
            new_callable=AsyncMock,
            return_value="https://notion.so/request",
        ) as mock_create:
            await submit_tool_request(
                request_title="New Tool",
                priority="P1",
                proposed_solution="We could build...",
            )

            props = mock_create.call_args.kwargs["properties"]
            assert "Proposed solution" in props

    @pytest.mark.asyncio
    async def test_excludes_empty_optional_fields(self) -> None:
        with patch(
            "services.notion_service._internal_tools.create_page",
            new_callable=AsyncMock,
            return_value="https://notion.so/request",
        ) as mock_create:
            await submit_tool_request(
                request_title="New Tool",
                priority="P1",
                problem_context="",
                proposed_solution="   ",
            )

            props = mock_create.call_args.kwargs["properties"]
            assert "Problem / context" not in props
            assert "Proposed solution" not in props

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self) -> None:
        with patch(
            "services.notion_service._internal_tools.create_page",
            new_callable=AsyncMock,
            side_effect=Exception("API error"),
        ):
            result = await submit_tool_request(
                request_title="New Tool",
                priority="P2",
            )
            assert result is None
