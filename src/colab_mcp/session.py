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
from collections.abc import AsyncIterator
import contextlib
from contextlib import AsyncExitStack
from fastmcp import FastMCP, Client
from fastmcp.client.transports import ClientTransport
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.tool_injection import ToolInjectionMiddleware
from fastmcp.server.proxy import FastMCPProxy
from fastmcp.tools.tool import Tool
from mcp.client.session import ClientSession
import webbrowser

from colab_mcp.websocket_server import ColabWebSocketServer, COLAB, SCRATCH_PATH

UI_CONNECTION_TIMEOUT = 60.0  # secs

FE_CONNECT_EVENT_KEY = "fe_connect_event"
PROXY_TOKEN_KEY = "proxy_token"
PROXY_PORT_KEY = "proxy_port"


class ColabProxyMiddleware(Middleware):
    def __init__(self, wss: ColabWebSocketServer):
        self.wss = wss
        self.last_message_connected = self.wss.connection_live.is_set()

    async def on_message(self, context: MiddlewareContext, call_next):
        """
        Check for a change to Colab session connectivity on any communication with this MCP server and
        notify the client when the connectivity status has changed.
        """
        context.fastmcp_context.set_state(
            FE_CONNECT_EVENT_KEY, self.wss.connection_live
        )
        context.fastmcp_context.set_state(PROXY_TOKEN_KEY, self.wss.token)
        context.fastmcp_context.set_state(PROXY_PORT_KEY, self.wss.port)

        result = await call_next(context)

        connected = self.wss.connection_live.is_set()
        connection_state_changed = connected != self.last_message_connected
        self.last_message_connected = connected
        if connection_state_changed:
            await context.fastmcp_context.send_prompt_list_changed()
            await context.fastmcp_context.send_resource_list_changed()
            await context.fastmcp_context.send_tool_list_changed()

        return result


class ColabTransport(ClientTransport):
    def __init__(self, wss: ColabWebSocketServer):
        self.wss = wss

    @contextlib.asynccontextmanager
    async def connect_session(self, **session_kwargs) -> AsyncIterator[ClientSession]:
        async with ClientSession(
            self.wss.read_stream, self.wss.write_stream, **session_kwargs
        ) as session:
            yield session

    def __repr__(self) -> str:
        return "<ColabSessionProxyTransport>"


class ColabProxyClient:
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
        self.proxy_mcp_client = await self._exit_stack.enter_async_context(
            Client(ColabTransport(self.wss))
        )

    async def __aenter__(self):
        self._start_task = asyncio.create_task(self._start_proxy_client())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._start_task:
            self._start_task.cancel()
        await self._exit_stack.aclose()


async def check_session_proxy_tool_fn(ctx: Context = CurrentContext()) -> bool:
    connect_event = ctx.get_state(FE_CONNECT_EVENT_KEY)
    token = ctx.get_state(PROXY_TOKEN_KEY)
    port = ctx.get_state(PROXY_PORT_KEY)
    if connect_event.is_set():
        return True
    with contextlib.suppress(asyncio.TimeoutError):
        await ctx.report_progress(
            progress=1, total=3, message="The user is not connected to the Colab UI"
        )
        webbrowser.open_new(
            f"{COLAB}{SCRATCH_PATH}#mcpProxyToken={token}&mcpProxyPort={port}"
        )
        await ctx.report_progress(
            progress=2,
            total=3,
            message="Waiting for user to connect in Colab - will wait for 60s",
        )
        await asyncio.wait_for(connect_event.wait(), timeout=UI_CONNECTION_TIMEOUT)
    if connect_event.is_set():
        await ctx.report_progress(
            progress=3, total=3, message="The Colab UI is successfully connected!"
        )
        return True
    else:
        await ctx.report_progress(
            progress=3,
            total=3,
            message="Timeout while waiting for the user to connect.",
        )
        return False


check_session_proxy_tool = Tool.from_function(
    fn=check_session_proxy_tool_fn,
    name="open_colab_browser_connection",
    description="Opens a connection to a Google Colab browser session. If the user is trying to edit a notebook in Google Colab, this needs to happen first. Returns True if the connection was successful and False if the connection failed",
)


class ColabSessionProxy:
    def __init__(self):
        self._exit_stack = AsyncExitStack()
        self.proxy_server: FastMCPProxy | None = None
        # list order matters, see: https://gofastmcp.com/servers/middleware#multiple-middleware
        self.middleware: list[Middleware] = []

    async def start_proxy_server(self):
        wss = await self._exit_stack.enter_async_context(ColabWebSocketServer())
        proxy_client = await self._exit_stack.enter_async_context(ColabProxyClient(wss))
        self.proxy_server = FastMCPProxy(
            client_factory=proxy_client.client_factory,
            instructions="Connects to a user's Google Colab session in a browser and allows for interactions with their Google Colab notebook",
        )
        # ColabProxyMiddleware must be first because it sets the fe_connected state
        self.middleware.append(ColabProxyMiddleware(wss))
        self.middleware.append(
            ToolInjectionMiddleware(tools=[check_session_proxy_tool])
        )

    async def cleanup(self):
        await self._exit_stack.aclose()
