import asyncio
from colab_mcp import session
from colab_mcp.websocket_server import ColabWebSocketServer
from fastmcp.server.middleware import MiddlewareContext

from unittest import mock
import pytest

@pytest.fixture
def mock_wss():
    """Provides a mock ColabWebSocketServer instance."""
    return MockColabWebSocketServer()


class MockColabWebSocketServer:
    def __init__(self):
        self.connection_live = asyncio.Event()
        self.read_stream = mock.AsyncMock()
        self.write_stream = mock.AsyncMock()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class TestColabProxyMiddleware:
    @pytest.mark.asyncio
    async def test_connection_live(self, mock_wss):
        mock_wss.connection_live.set()
        middleware = session.ColabProxyMiddleware(mock_wss)
        context = mock.Mock(spec=MiddlewareContext)
        call_next = mock.AsyncMock()

        await middleware.on_message(context, call_next)

        call_next.assert_called_once_with(context)

    @pytest.mark.asyncio
    async def test_connection_not_live(self, mock_wss):
        middleware = session.ColabProxyMiddleware(mock_wss)
        context = mock.Mock(spec=MiddlewareContext)
        call_next = mock.AsyncMock()

        with pytest.raises(Exception, match="No Colab browser session is connected."):
            await middleware.on_message(context, call_next)


class TestColabProxyClient:
    def test_client_factory_connection_live(self, mock_wss):
        mock_wss.connection_live.set()
        client = session.ColabProxyClient(mock_wss)
        client.proxy_mcp_client = mock.Mock()

        assert client.client_factory() is client.proxy_mcp_client

    def test_client_factory_connection_not_live(self, mock_wss):
        client = session.ColabProxyClient(mock_wss)
        assert client.client_factory() is client.stubbed_mcp_client

    @pytest.mark.asyncio
    @mock.patch("colab_mcp.session.Client")
    @mock.patch("colab_mcp.session.ColabTransport", spec=session.ColabTransport)
    async def test_start_proxy_client(self, mock_colab_transport, mock_client, mock_wss):
        client = session.ColabProxyClient(mock_wss)
        mock_wss.connection_live.set()
        async with client:
            await client._start_task

        mock_colab_transport.assert_called_once_with(mock_wss)
        mock_client.assert_any_call(mock_colab_transport.return_value)


class TestColabSessionProxy:
    @pytest.mark.asyncio
    @mock.patch("colab_mcp.session.ColabProxyClient")
    @mock.patch("colab_mcp.session.ColabProxyMiddleware")
    async def test_start_proxy_server(
        self, mock_colab_proxy_client, mock_colab_proxy_middleware
    ):
        proxy = session.ColabSessionProxy()
        await proxy.start_proxy_server()
        mock_colab_proxy_client.assert_called_once()
        assert proxy.proxy_server is not None
        mock_colab_proxy_middleware.assert_called_once()