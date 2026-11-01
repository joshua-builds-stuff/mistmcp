from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from mistmcp.config import config
from mistmcp.elicitation_middleware import ElicitationMiddleware
from mistmcp.elicitation_processor import config_elicitation_handler
from test_elicitation_middleware import FakeFastMCPContext, FakeMiddlewareContext


@pytest.mark.parametrize("query,headers", [
    (b"", [(b"x-disable-elicitation", b"true")]),
    (b"disable_elicitation=true", []),
    (b"experimental=true", []),
    (b"enable_write_delete_tools=true", [(b"x-enable-write-delete-tools", b"true")]),
])
@pytest.mark.parametrize("supports_elicitation", [False, True])
async def test_client_cannot_override_server_policy(monkeypatch, query, headers, supports_elicitation):
    monkeypatch.setattr(config, "enable_write_tools", True)
    monkeypatch.setattr(config, "enable_write_delete_tools", False)
    monkeypatch.setattr(config, "disable_elicitation", False)
    monkeypatch.setattr(config, "transport_mode", "http")
    monkeypatch.setattr(config, "stateless", False)
    request = Request({"type": "http", "headers": headers, "query_string": query})
    monkeypatch.setattr("fastmcp.server.dependencies.get_http_request", lambda: request)
    ctx = FakeFastMCPContext()
    context = FakeMiddlewareContext(ctx)
    context.message.params.enable_write_delete_tools = True
    context.message.params.disable_elicitation = True
    if supports_elicitation:
        context.message.params.capabilities.elicitation = SimpleNamespace()
    await ElicitationMiddleware().on_initialize(context, AsyncMock(return_value="ok"))
    assert ctx.state.get("disable_elicitation") is not True
    assert all("write_delete" not in call["tags"] for call in ctx.enabled_calls)
    assert bool(ctx.enabled_calls) == supports_elicitation
    ctx.elicit = AsyncMock(return_value=None)
    await config_elicitation_handler("synthetic change", ctx)
    ctx.elicit.assert_awaited_once()


async def test_stale_session_flag_cannot_auto_accept(monkeypatch):
    monkeypatch.setattr(config, "disable_elicitation", False)
    monkeypatch.setattr(config, "stateless", False)
    ctx = FakeFastMCPContext()
    ctx.state["disable_elicitation"] = True
    ctx.elicit = AsyncMock(return_value=None)
    await config_elicitation_handler("synthetic change", ctx)
    ctx.elicit.assert_awaited_once()


async def test_server_opt_out_is_logged(monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setattr(config, "enable_write_tools", True)
    monkeypatch.setattr(config, "disable_elicitation", True)
    warning = Mock()
    monkeypatch.setattr("mistmcp.elicitation_processor.logger.warning", warning)
    ctx = FakeFastMCPContext()
    result = await config_elicitation_handler("synthetic change", ctx)
    assert result.action == "accept"
    warning.assert_called_once()
    assert "server policy" in warning.call_args.args[0]
