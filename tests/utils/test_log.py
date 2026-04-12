import logging
from unittest.mock import MagicMock, patch

from utils.log import OTelJsonFormatter, configure_global_logger, request_id_ctx


class TestOTelJsonFormatter:
    """Tests for OTelJsonFormatter trace correlation and service attributes."""

    def _make_record(
        self,
        otel_trace_id: str = "0",
        otel_span_id: str = "0",
    ) -> logging.LogRecord:
        """Create a LogRecord with optional OTel attributes (as LoggingInstrumentor would)."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=None,
            exc_info=None,
        )
        record.otelTraceID = otel_trace_id  # type: ignore[attr-defined]
        record.otelSpanID = otel_span_id  # type: ignore[attr-defined]
        return record

    def test_adds_env_and_service(self):
        """Formatter should add env and service fields from environment."""
        formatter = OTelJsonFormatter()
        record = self._make_record()
        log_record: dict = {}
        with patch.dict(
            "os.environ", {"RUNTIME_ENV": "test", "OTEL_SERVICE_NAME": "test-svc"}
        ):
            formatter.add_fields(log_record, record, {})
        assert log_record["env"] == "test"
        assert log_record["service"] == "test-svc"

    def test_injects_trace_ids_from_otel_attributes(self):
        """Formatter should map otelTraceID/otelSpanID to trace_id/span_id."""
        formatter = OTelJsonFormatter()
        record = self._make_record(
            otel_trace_id="0af7651916cd43dd8448eb211c80319c",
            otel_span_id="b7ad6b7169203331",
        )
        log_record: dict = {}
        formatter.add_fields(log_record, record, {})
        assert log_record["trace_id"] == "0af7651916cd43dd8448eb211c80319c"
        assert log_record["span_id"] == "b7ad6b7169203331"

    def test_skips_trace_ids_when_no_active_span(self):
        """Formatter should not add trace fields when otelTraceID is '0' (no span)."""
        formatter = OTelJsonFormatter()
        record = self._make_record()  # defaults: "0", "0"
        log_record: dict = {}
        formatter.add_fields(log_record, record, {})
        assert "trace_id" not in log_record
        assert "span_id" not in log_record

    def test_injects_request_id_from_context(self):
        """Formatter should inject request_id from context variable."""
        formatter = OTelJsonFormatter()
        record = self._make_record()
        log_record: dict = {}
        token = request_id_ctx.set("req-abc-123")
        try:
            formatter.add_fields(log_record, record, {})
            assert log_record["request_id"] == "req-abc-123"
        finally:
            request_id_ctx.reset(token)

    def test_skips_request_id_when_empty(self):
        """Formatter should not add request_id when context var is empty."""
        formatter = OTelJsonFormatter()
        record = self._make_record()
        log_record: dict = {}
        token = request_id_ctx.set("")
        try:
            formatter.add_fields(log_record, record, {})
            assert "request_id" not in log_record
        finally:
            request_id_ctx.reset(token)

    def test_does_not_overwrite_existing_env(self):
        """Formatter should preserve env if already present in log_record."""
        formatter = OTelJsonFormatter()
        record = self._make_record()
        log_record: dict = {"env": "production"}
        formatter.add_fields(log_record, record, {})
        assert log_record["env"] == "production"


class TestConfigureGlobalLogger:
    """Tests for configure_global_logger() setup."""

    def setup_method(self):
        self._root = logging.getLogger()
        self._orig_level = self._root.level
        self._orig_handlers = self._root.handlers[:]

    def teardown_method(self):
        root = self._root
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        for handler in self._orig_handlers:
            root.addHandler(handler)
        root.setLevel(self._orig_level)

    @patch("utils.log.LoggingInstrumentor")
    def test_instruments_logging(self, mock_instrumentor_cls: MagicMock):
        """configure_global_logger should call LoggingInstrumentor().instrument()."""
        mock_instance = MagicMock()
        mock_instance.is_instrumented_by_opentelemetry = False
        mock_instrumentor_cls.return_value = mock_instance
        configure_global_logger()
        mock_instance.instrument.assert_called_once()

    def test_sets_root_logger_level_from_env(self):
        """configure_global_logger should set root logger level from LOG_LEVEL env var."""
        with patch.dict("os.environ", {"LOG_LEVEL": "DEBUG"}):
            with patch("utils.log.LoggingInstrumentor"):
                configure_global_logger()
        assert logging.getLogger().level == logging.DEBUG

    def test_adds_json_handler(self):
        """configure_global_logger should add a StreamHandler with OTelJsonFormatter."""
        with patch("utils.log.LoggingInstrumentor"):
            configure_global_logger()
        root = logging.getLogger()
        assert len(root.handlers) == 1
        handler = root.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert isinstance(handler.formatter, OTelJsonFormatter)
