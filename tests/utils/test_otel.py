import asyncio
from unittest.mock import patch

import pytest

from utils.otel import trace_async_block, trace_block, traced


class TestTraced:
    """Tests for the traced() decorator."""

    @patch("utils.otel.is_testing_mode", return_value=False)
    def test_sync_creates_span(self, mock_testing_mode):
        """traced() should create an OTel span around a sync function."""

        @traced("test.sync_op")
        def my_func(x: int) -> int:
            return x + 1

        result = my_func(5)
        assert result == 6

    @patch("utils.otel.is_testing_mode", return_value=False)
    def test_async_creates_span(self, mock_testing_mode):
        """traced() should create an OTel span around an async function."""

        @traced("test.async_op")
        async def my_func(x: int) -> int:
            return x + 1

        result = asyncio.run(my_func(5))
        assert result == 6

    @patch("utils.otel.is_testing_mode", return_value=True)
    def test_sync_skips_in_testing_mode(self, mock_testing_mode):
        """traced() should skip span creation when testing mode is enabled."""

        @traced("test.sync_op")
        def my_func(x: int) -> int:
            return x + 1

        with patch("utils.otel._tracer") as mock_tracer:
            result = my_func(5)
            assert result == 6
            mock_tracer.start_as_current_span.assert_not_called()

    @patch("utils.otel.is_testing_mode", return_value=True)
    def test_async_skips_in_testing_mode(self, mock_testing_mode):
        """traced() should skip span creation when testing mode is enabled."""

        @traced("test.async_op")
        async def my_func(x: int) -> int:
            return x + 1

        with patch("utils.otel._tracer") as mock_tracer:
            result = asyncio.run(my_func(5))
            assert result == 6
            mock_tracer.start_as_current_span.assert_not_called()

    @patch("utils.otel.is_testing_mode", return_value=False)
    def test_tags_raises_on_non_dict(self, mock_testing_mode):
        """traced() should raise TypeError if tags is not a dict."""

        @traced("test.op", tags="not_a_dict")  # type: ignore[arg-type]
        def my_func() -> str:
            return "ok"

        with pytest.raises(TypeError, match="tags must be a dictionary"):
            my_func()

    @patch("utils.otel.is_testing_mode", return_value=False)
    def test_sync_records_exception(self, mock_testing_mode):
        """traced() should record exceptions on the span and re-raise."""

        @traced("test.op")
        def my_func() -> str:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            my_func()

    @patch("utils.otel.is_testing_mode", return_value=False)
    def test_async_records_exception(self, mock_testing_mode):
        """traced() should record exceptions on the span and re-raise (async)."""

        @traced("test.op")
        async def my_func() -> str:
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            asyncio.run(my_func())


class TestTraceBlock:
    """Tests for trace_block() context manager."""

    @patch("utils.otel.is_testing_mode", return_value=True)
    def test_yields_none_in_testing_mode(self, mock_testing_mode):
        """trace_block() should yield None when testing mode is enabled."""
        with trace_block("test.block") as span:
            assert span is None

    @patch("utils.otel.is_testing_mode", return_value=False)
    def test_creates_span(self, mock_testing_mode):
        """trace_block() should create an OTel span."""
        with trace_block("test.block") as span:
            assert span is not None

    @patch("utils.otel.is_testing_mode", return_value=False)
    def test_records_exception(self, mock_testing_mode):
        """trace_block() should record exceptions on the span and re-raise."""
        with pytest.raises(ValueError, match="test error"):
            with trace_block("test.block"):
                raise ValueError("test error")


class TestTraceAsyncBlock:
    """Tests for trace_async_block() context manager."""

    @patch("utils.otel.is_testing_mode", return_value=True)
    def test_yields_none_in_testing_mode(self, mock_testing_mode):
        """trace_async_block() should yield None when testing mode is enabled."""

        async def run():
            async with trace_async_block("test.block") as span:
                assert span is None

        asyncio.run(run())

    @patch("utils.otel.is_testing_mode", return_value=False)
    def test_creates_span(self, mock_testing_mode):
        """trace_async_block() should create an OTel span."""

        async def run():
            async with trace_async_block("test.block") as span:
                assert span is not None

        asyncio.run(run())

    @patch("utils.otel.is_testing_mode", return_value=False)
    def test_records_exception(self, mock_testing_mode):
        """trace_async_block() should record exceptions on the span and re-raise."""

        async def run():
            with pytest.raises(ValueError, match="test error"):
                async with trace_async_block("test.block"):
                    raise ValueError("test error")

        asyncio.run(run())
