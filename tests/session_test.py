# Copyright 2026 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
from colab_mcp import session, websocket_server
from fastmcp import Client, FastMCP
from fastmcp.server.middleware import MiddlewareContext
import pytest
from unittest.mock import patch, call, AsyncMock, Mock

TEST_PROXY_TOKEN = "test_token"
TEST_PROXY_PORT = 1111


@pytest.fixture(autouse=True)
def no_browser_open(monkeypatch):
    import webbrowser

    monkeypatch.setattr(webbrowser, "open_new", lambda *a, **k: True)


@pytest.fixture(autouse=True)
def instant_timeout(monkeypatch):
    monkeypatch.setattr(session, "UI_CONNECTION_TIMEOUT", 0.1)


@pytest.fixture
def mock_wss():
    """Provides a mock ColabWebSocketServer instance."""
    return MockColabWebSocketServer()


def assertExpectedContextCalls(mock_set_state, mock_wss):
    expected_set_context_calls = [
        call("fe_connected", mock_wss.connection_live.is_set()),
        call("proxy_token", TEST_PROXY_TOKEN),
        call("proxy_port", TEST_PROXY_PORT),
    ]
    mock_set_state.assert_has_calls(expected_set_context_calls)


class MockColabWebSocketServer:
    def __init__(self):
        self.connection_live = asyncio.Event()
        self.read_stream = AsyncMock()
        self.write_stream = AsyncMock()
        self.token = TEST_PROXY_TOKEN
        self.port = TEST_PROXY_PORT

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class TestColabProxyMiddleware:
    @pytest.mark.asyncio
    async def test_connection_live(self, mock_wss):
        """Tests connection state change from disconnected to connected."""
        mock_wss.connection_live.clear()
        middleware = session.ColabProxyMiddleware(mock_wss)
        mock_wss.connection_live.set()
        context = Mock(spec=MiddlewareContext)
        context.fastmcp_context.set_state = Mock()
        context.fastmcp_context.send_prompt_list_changed = AsyncMock()
        context.fastmcp_context.send_resource_list_changed = AsyncMock()
        context.fastmcp_context.send_tool_list_changed = AsyncMock()
        call_next = AsyncMock()

        await middleware.on_message(context, call_next)

        assertExpectedContextCalls(context.fastmcp_context.set_state, mock_wss)
        call_next.assert_called_once_with(context)
        assert middleware.last_message_connected is True
        context.fastmcp_context.send_prompt_list_changed.assert_called_once()
        context.fastmcp_context.send_resource_list_changed.assert_called_once()
        context.fastmcp_context.send_tool_list_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_not_live(self, mock_wss):
        """Tests connection state change from connected to disconnected."""
        mock_wss.connection_live.set()
        middleware = session.ColabProxyMiddleware(mock_wss)
        mock_wss.connection_live.clear()
        context = Mock(spec=MiddlewareContext)
        context.fastmcp_context.set_state = Mock()
        context.fastmcp_context.send_prompt_list_changed = AsyncMock()
        context.fastmcp_context.send_resource_list_changed = AsyncMock()
        context.fastmcp_context.send_tool_list_changed = AsyncMock()
        call_next = AsyncMock()

        await middleware.on_message(context, call_next)

        assertExpectedContextCalls(context.fastmcp_context.set_state, mock_wss)
        call_next.assert_called_once_with(context)
        assert middleware.last_message_connected is False
        context.fastmcp_context.send_prompt_list_changed.assert_called_once()
        context.fastmcp_context.send_resource_list_changed.assert_called_once()
        context.fastmcp_context.send_tool_list_changed.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_connection_change(self, mock_wss):
        """Tests no connection state change."""
        mock_wss.connection_live.set()
        middleware = session.ColabProxyMiddleware(mock_wss)
        context = Mock(spec=MiddlewareContext)
        context.fastmcp_context.set_state = Mock()
        context.fastmcp_context.send_prompt_list_changed = AsyncMock()
        context.fastmcp_context.send_resource_list_changed = AsyncMock()
        context.fastmcp_context.send_tool_list_changed = AsyncMock()
        call_next = AsyncMock()

        await middleware.on_message(context, call_next)

        assertExpectedContextCalls(context.fastmcp_context.set_state, mock_wss)
        call_next.assert_called_once_with(context)
        assert middleware.last_message_connected is True
        context.fastmcp_context.send_prompt_list_changed.assert_not_called()
        context.fastmcp_context.send_resource_list_changed.assert_not_called()
        context.fastmcp_context.send_tool_list_changed.assert_not_called()


class TestColabProxyClient:
    def test_client_factory_connection_live(self, mock_wss):
        mock_wss.connection_live.set()
        client = session.ColabProxyClient(mock_wss)
        client.proxy_mcp_client = Mock()

        assert client.client_factory() is client.proxy_mcp_client

    def test_client_factory_connection_not_live(self, mock_wss):
        client = session.ColabProxyClient(mock_wss)
        assert client.client_factory() is client.stubbed_mcp_client

    @pytest.mark.asyncio
    @patch("colab_mcp.session.Client")
    @patch("colab_mcp.session.ColabTransport", spec=session.ColabTransport)
    async def test_start_proxy_client(
        self, mock_colab_transport, mock_client, mock_wss
    ):
        mock_client.return_value.__aenter__ = AsyncMock()
        client = session.ColabProxyClient(mock_wss)
        mock_wss.connection_live.set()
        async with client:
            await client._start_task

        mock_colab_transport.assert_called_once_with(mock_wss)
        mock_client.assert_called_with(mock_colab_transport.return_value)


class TestColabSessionProxy:
    @pytest.mark.asyncio
    @patch("colab_mcp.session.ToolInjectionMiddleware")
    @patch("colab_mcp.session.ColabWebSocketServer")
    @patch("colab_mcp.session.ColabProxyClient")
    @patch("colab_mcp.session.ColabProxyMiddleware")
    async def test_start_proxy_server_startup(
        self,
        mock_colab_proxy_middleware,
        mock_colab_proxy_client,
        mock_colab_web_socket_server,
        mock_tool_injection_middleware,
    ):
        mock_colab_web_socket_server.return_value.__aenter__ = AsyncMock()
        mock_colab_proxy_client.return_value.__aenter__ = AsyncMock()
        proxy = session.ColabSessionProxy()
        await proxy.start_proxy_server()
        mock_colab_proxy_client.assert_called_once()
        assert proxy.proxy_server is not None
        mock_colab_proxy_middleware.assert_called_once()
        mock_tool_injection_middleware.assert_called_once()


class TestCheckSessionProxyTool:
    @pytest.mark.asyncio
    @patch("colab_mcp.session.webbrowser.open_new")
    async def test_tool(self, mock_open, monkeypatch):
        monkeypatch.setattr(
            websocket_server.secrets,
            "token_urlsafe",
            lambda nbytes=None: TEST_PROXY_TOKEN,
        )
        testServer = FastMCP(name="test server")
        session_mcp = session.ColabSessionProxy()
        await session_mcp.start_proxy_server()
        testServer.mount(session_mcp.proxy_server)
        for middleware in session_mcp.middleware:
            testServer.add_middleware(middleware)

        async with Client(testServer) as testClient:
            tools = await testClient.list_tools()
            assert tools[0].name == "open_colab_browser_connection"
            result = await testClient.call_tool("open_colab_browser_connection")
            assert not result.structured_content["result"]  # is False
        await session_mcp.cleanup()

        mock_open.assert_called_once_with(
            f"https://colab.google.com/notebooks/empty.ipynb#mcpProxyToken={TEST_PROXY_TOKEN}&mcpProxyPort={session_mcp.wss.port}"
        )

    @pytest.mark.asyncio
    async def test_tool_middleware_injects_new_connection(self, mock_wss):
        testServer = FastMCP(name="test server")
        session_mcp = session.ColabSessionProxy()
        await session_mcp.start_proxy_server()
        testServer.mount(session_mcp.proxy_server)
        for middleware in session_mcp.middleware:
            testServer.add_middleware(middleware)

        async with Client(testServer) as testClient:
            tools = await testClient.list_tools()
            assert tools[0].name == "open_colab_browser_connection"
            result = testClient.call_tool("open_colab_browser_connection")
            result_coroutine = testClient.call_tool("open_colab_browser_connection")
            session_mcp.wss.connection_live.set()
            result = await result_coroutine
            assert result.structured_content["result"]  # is True
        await session_mcp.cleanup()
