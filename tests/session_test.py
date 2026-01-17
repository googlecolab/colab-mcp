import asyncio
from colab_mcp import session
from fastmcp.server.middleware import MiddlewareContext
import pytest
from unittest.mock import patch, AsyncMock, Mock

@pytest.fixture(autouse=True)
def no_browser_open(monkeypatch):
    import webbrowser
    monkeypatch.setattr(webbrowser, "open_new", lambda *a, **k: True)

@pytest.fixture
def mock_wss():
    """Provides a mock ColabWebSocketServer instance."""
    return MockColabWebSocketServer()


class MockColabWebSocketServer:
    def __init__(self):
        self.connection_live = asyncio.Event()
        self.read_stream = AsyncMock()
        self.write_stream = AsyncMock()

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

        call_next.assert_called_once_with(context)
        context.fastmcp_context.set_state.assert_called_once_with(
            "fe_connected", True
        )
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

        call_next.assert_called_once_with(context)
        context.fastmcp_context.set_state.assert_called_once_with(
            "fe_connected", False
        )
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

        call_next.assert_called_once_with(context)
        context.fastmcp_context.set_state.assert_called_once_with(
            "fe_connected", True
        )
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
    async def test_start_proxy_client(self, mock_colab_transport, mock_client, mock_wss):
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
    async def test_start_proxy_server(
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
