import asyncio
from collections.abc import AsyncIterator
import contextlib
from contextlib import AsyncExitStack
from fastmcp import FastMCP, Client
from fastmcp.client.transports import ClientTransport
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.proxy import FastMCPProxy
from mcp.client.session import ClientSession

from colab_mcp.websocket_server import ColabWebSocketServer

class ColabProxyMiddleware(Middleware):
    def __init__(self, wss: ColabWebSocketServer):
        self.wss = wss

    async def on_message(self, context: MiddlewareContext, call_next):
        if self.wss.connection_live.is_set():
            return await call_next(context)
        else:
            raise Exception('No Colab browser session is connected. The user needs to connect their Colab session.')

class ColabTransport(ClientTransport):
    def __init__(self, wss: ColabWebSocketServer):
        self.wss = wss

    @contextlib.asynccontextmanager
    async def connect_session(
        self, **session_kwargs
    ) -> AsyncIterator[ClientSession]:
        async with ClientSession(
            self.wss.read_stream, self.wss.write_stream, **session_kwargs
        ) as session:
            yield session

    def __repr__(self) -> str:
        return f"<ColabSessionProxyTransport>"

class ColabProxyClient():
    def __init__(self, wss: ColabWebSocketServer):
        self.wss = wss
        self.stubbed_mcp_client = Client(FastMCP())
        self.proxy_mcp_client: Client | None = None
        self._exit_stack = AsyncExitStack()
        self._start_task = None 

    def client_factory(self):
        if self.wss.connection_live.is_set() and self.proxy_mcp_client is not None:
            return self.proxy_mcp_client
        # return a client mapped to a stubbed mcp server if there is no session proxy 
        return self.stubbed_mcp_client
    
    async def _start_proxy_client(self):
        # blocks until a websocket connection is made successfully
        self.proxy_mcp_client = await self._exit_stack.enter_async_context(Client(ColabTransport(self.wss)))

    async def __aenter__ (self):
        self._start_task = asyncio.create_task(self._start_proxy_client())
        return self

    async def __aexit__ (self, exc_type, exc_val, exc_tb):
        if self._start_task:
            self._start_task.cancel()
        await self._exit_stack.aclose()


class ColabSessionProxy():
    def __init__(self):
        self._exit_stack = AsyncExitStack()
        self.proxy_server: FastMCPProxy | None = None

    async def start_proxy_server(self):
        wss = await self._exit_stack.enter_async_context(ColabWebSocketServer())
        proxy_client = await self._exit_stack.enter_async_context(ColabProxyClient(wss))
        self.proxy_server = FastMCPProxy(client_factory=proxy_client.client_factory, 
                        instructions="Connects to a user's active Google Colab session and allows for interactions with their Google Colab notebook")
        self.proxy_server.add_middleware(ColabProxyMiddleware(wss))

    async def cleanup(self):
        await self._exit_stack.aclose()
