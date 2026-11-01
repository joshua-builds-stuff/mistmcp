from unittest.mock import AsyncMock, Mock

import pytest

from mistmcp.config import ServerConfig, config
from mistmcp.elicitation_middleware import ElicitationMiddleware
from mistmcp.elicitation_processor import config_elicitation_handler
from mistmcp.server import _write_visible_tags
from test_elicitation_middleware import FakeFastMCPContext, FakeMiddlewareContext


@pytest.mark.parametrize("auto_accept", [False, True])
async def test_operator_enables_destructive_tools(monkeypatch, auto_accept):
    monkeypatch.setattr(config, "enable_write_tools", True)
    monkeypatch.setattr(config, "enable_write_delete_tools", True, raising=False)
    monkeypatch.setattr(config, "disable_elicitation", auto_accept)
    monkeypatch.setattr(config, "transport_mode", "stdio")
    monkeypatch.setattr(config, "stateless", False)
    ctx = FakeFastMCPContext()
    context = FakeMiddlewareContext(ctx)
    context.message.params.capabilities.elicitation = {}
    await ElicitationMiddleware().on_initialize(context, AsyncMock())
    assert {"tags": {"write_delete"}, "components": {"tool"}} in ctx.enabled_calls
    assert {"tags": {"write"}, "components": {"tool"}} in ctx.disabled_calls
    ctx.elicit = AsyncMock(return_value=None)
    result = await config_elicitation_handler("synthetic destructive change", ctx)
    if auto_accept:
        assert result.action == "accept"
        ctx.elicit.assert_not_awaited()
    else:
        ctx.elicit.assert_awaited_once()


def test_stateless_visibility_requires_both_operator_gates():
    cfg = ServerConfig(enable_write_tools=True, disable_elicitation=True)
    cfg.enable_write_delete_tools = True
    assert _write_visible_tags(cfg) == {"write_delete"}
    cfg.enable_write_tools = False
    assert _write_visible_tags(cfg) == set()


@pytest.mark.parametrize("write_enabled,supports_elicitation", [(False, True), (True, False)])
async def test_destructive_opt_in_preserves_other_gates(monkeypatch, write_enabled, supports_elicitation):
    monkeypatch.setattr(config, "enable_write_tools", write_enabled)
    monkeypatch.setattr(config, "enable_write_delete_tools", True)
    monkeypatch.setattr(config, "disable_elicitation", False)
    monkeypatch.setattr(config, "transport_mode", "stdio")
    ctx = FakeFastMCPContext()
    context = FakeMiddlewareContext(ctx)
    context.message.params.capabilities.elicitation = {} if supports_elicitation else None
    await ElicitationMiddleware().on_initialize(context, AsyncMock())
    assert ctx.enabled_calls == []


def test_startup_logs_operator_policy(monkeypatch):
    from mistmcp.__main__ import start
    warning = Mock()
    monkeypatch.setattr("mistmcp.__main__.setup_logging", Mock())
    monkeypatch.setattr("mistmcp.__main__.create_mcp_server", Mock(return_value=Mock()))
    monkeypatch.setattr("mistmcp.__main__.logger.warning", warning)
    original = config.__dict__.copy()
    try:
        start("stdio", "0.0.0.0", 8000, enable_write_tools=True,
              enable_write_delete_tools=True, disable_elicitation=True)
        messages = [call.args[0] for call in warning.call_args_list]
        assert any("destructive" in message for message in messages)
        assert any("confirmation" in message for message in messages)
    finally:
        config.__dict__.clear()
        config.__dict__.update(original)


@pytest.mark.parametrize("source", ["cli", "env"])
def test_operator_option_reaches_start(monkeypatch, source):
    from mistmcp.__main__ import main
    start = Mock()
    monkeypatch.setattr("mistmcp.__main__.start", start)
    monkeypatch.setattr("mistmcp.__main__.load_env_file", Mock())
    monkeypatch.delenv("MISTMCP_ENABLE_WRITE_DELETE_TOOLS", raising=False)
    args = ["mistmcp", "--enable-write-tools"]
    if source == "cli":
        args.append("--enable-write-delete-tools")
    else:
        monkeypatch.setenv("MISTMCP_ENABLE_WRITE_DELETE_TOOLS", "true")
    monkeypatch.setattr("sys.argv", args)
    main()
    assert start.call_args.kwargs["enable_write_delete_tools"] is True
