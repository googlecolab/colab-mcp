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
from colab_mcp.websocket_server import ColabWebSocketServer
from mcp.types import JSONRPCRequest, JSONRPCResponse, JSONRPCMessage
from mcp.shared.message import SessionMessage
import pytest
import websockets


@pytest.mark.asyncio
@pytest.mark.parametrize("origin_domain", ["https://colab.google.com", "https://colab.research.google.com"])
async def test_successful_connection(origin_domain):
    async with ColabWebSocketServer() as server:
        client = await websockets.connect(
            f"ws://localhost:{server.port}",
            origin=origin_domain,
            subprotocols=["mcp"],
            additional_headers={"Authorization": f"Bearer {server.token}"},
        )
        assert server.connection_live.is_set()
        assert server.connection_lock.locked()

        await client.close()
        await client.wait_closed()
        await asyncio.sleep(1)  # Allow server to update state

        assert not server.connection_live.is_set()
        assert not server.connection_lock.locked()


@pytest.mark.asyncio
async def test_unauthorized_origin_rejected():
    async with ColabWebSocketServer() as server:
        with pytest.raises(websockets.exceptions.InvalidStatus):
            await websockets.connect(
                f"ws://localhost:{server.port}",
                origin="https://wrong.com",
                subprotocols=["mcp"],
                additional_headers={"Authorization": f"Bearer {server.token}"},
            )
        assert not server.connection_live.is_set()


@pytest.mark.asyncio
async def test_second_connection_rejected():
    async with ColabWebSocketServer() as server:
        client1 = await websockets.connect(
            f"ws://localhost:{server.port}",
            origin="https://colab.google.com",
            subprotocols=["mcp"],
            additional_headers={"Authorization": f"Bearer {server.token}"},
        )
        assert server.connection_live.is_set()

        client2 = await websockets.connect(
            f"ws://localhost:{server.port}",
            origin="https://colab.google.com",
            subprotocols=["mcp"],
            additional_headers={"Authorization": f"Bearer {server.token}"},
        )

        with pytest.raises(
            websockets.exceptions.ConnectionClosed,
            match="Server is busy",
            check=lambda e: e.rcvd.code == 1013,
        ):
            # assert we cannot ping via the second client
            await client2.ping()

        # assert we can ping via the original client
        pong = await client1.ping()
        pong_latency = await pong
        assert pong_latency > 0
        await client1.close()


@pytest.mark.asyncio
async def test_incoming_message_handling():
    async with ColabWebSocketServer() as server:
        client = await websockets.connect(
            f"ws://localhost:{server.port}",
            origin="https://colab.google.com",
            subprotocols=["mcp"],
            additional_headers={"Authorization": f"Bearer {server.token}"},
        )
        assert server.connection_live.is_set()

        test_message = JSONRPCResponse(
            jsonrpc="2.0",
            id="abc",
            result={"result": "success"},
            additional_headers={"Authorization": f"Bearer {server.token}"},
        )
        await client.send(test_message.model_dump_json())

        received_msg = await asyncio.wait_for(server.read_stream.receive(), timeout=1)
        test_json_message = JSONRPCMessage(test_message)
        assert received_msg.message == test_json_message

        await client.close()


@pytest.mark.asyncio
async def test_outgoing_message_handling():
    async with ColabWebSocketServer() as server:
        client = await websockets.connect(
            f"ws://localhost:{server.port}",
            origin="https://colab.google.com",
            subprotocols=["mcp"],
            additional_headers={"Authorization": f"Bearer {server.token}"},
        )
        assert server.connection_live.is_set()

        test_message = JSONRPCRequest(
            jsonrpc="2.0",
            id="abc",
            method="test_method",
            params={"bar": "baz"},
        )
        await server.write_stream.send(SessionMessage(test_message))

        received_msg_str = await asyncio.wait_for(client.recv(), timeout=1)
        received_msg = JSONRPCRequest.model_validate_json(received_msg_str)
        assert received_msg == test_message

        await client.close()


@pytest.mark.asyncio
async def test_malformed_incoming_message():
    async with ColabWebSocketServer() as server:
        client = await websockets.connect(
            f"ws://localhost:{server.port}",
            origin="https://colab.google.com",
            subprotocols=["mcp"],
            additional_headers={"Authorization": f"Bearer {server.token}"},
        )
        assert server.connection_live.is_set()

        await client.send("this is not json")

        received_item = await asyncio.wait_for(server.read_stream.receive(), timeout=1)
        assert isinstance(received_item, Exception)

        await client.close()


@pytest.mark.asyncio
async def test_bad_token():
    with pytest.raises(
        websockets.exceptions.InvalidStatus,
        check=lambda e: e.response.status_code == 403,
    ):
        async with ColabWebSocketServer() as server:
            await websockets.connect(
                f"ws://localhost:{server.port}",
                origin="https://colab.google.com",
                subprotocols=["mcp"],
                additional_headers={"Authorization": "Bearer bad_token"},
            )


@pytest.mark.asyncio
async def test_no_auth():
    with pytest.raises(
        websockets.exceptions.InvalidStatus,
        check=lambda e: e.response.status_code == 401,
    ):
        async with ColabWebSocketServer() as server:
            await websockets.connect(
                f"ws://localhost:{server.port}",
                origin="https://colab.google.com",
                subprotocols=["mcp"],
            )


@pytest.mark.asyncio
async def test_malformed_auth_header():
    with pytest.raises(
        websockets.exceptions.InvalidStatus,
        check=lambda e: e.response.status_code == 400,
    ):
        async with ColabWebSocketServer() as server:
            await websockets.connect(
                f"ws://localhost:{server.port}",
                origin="https://colab.google.com",
                subprotocols=["mcp"],
                additional_headers={"Authorization": f"Bearer?{server.token}"},
            )


@pytest.mark.asyncio
async def test_token_in_url():
    async with ColabWebSocketServer() as server:
        client = await websockets.connect(
            f"ws://localhost:{server.port}?access_token={server.token}",
            origin="https://colab.google.com",
            subprotocols=["mcp"],
        )
        assert server.connection_live.is_set()
        assert server.connection_lock.locked()

        await client.close()
        await client.wait_closed()
        await asyncio.sleep(1)  # Allow server to update state

        assert not server.connection_live.is_set()
        assert not server.connection_lock.locked()
