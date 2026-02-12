import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
import asyncio
import logging
import mcp.types as types
from mcp.shared.message import SessionMessage
from pydantic_core import ValidationError
import secrets
import socket
import webbrowser
import websockets
from websockets.asyncio.server import ServerConnection
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response
from websockets.typing import Subprotocol

WEB_SOCKET_PORT = 9998

COLAB = "https://colab.google.com"
SCRATCH_PATH = "/notebooks/empty.ipynb"


class ColabWebSocketServer:
    """
    A WebSocket server designed to accept a single connection specifically
    from a Google Colab session (colab.google.com).
    """

    def __init__(self, host="localhost", port=WEB_SOCKET_PORT):
        self.host = host
        self.port = port
        self.connection_lock = asyncio.Lock()
        self.connection_live = asyncio.Event()
        self.allowed_origins = [COLAB]
        self._server: websockets.Server | None = None

        self.read_stream: MemoryObjectReceiveStream[SessionMessage | Exception]
        self._read_stream_writer: MemoryObjectSendStream[SessionMessage | Exception]
        self.write_stream: MemoryObjectSendStream[SessionMessage]
        self._write_stream_reader: MemoryObjectReceiveStream[SessionMessage]

        self._read_stream_writer, self.read_stream = anyio.create_memory_object_stream(
            0
        )
        self.write_stream, self._write_stream_reader = (
            anyio.create_memory_object_stream(0)
        )
        self.token = secrets.token_urlsafe(16)

    async def _read_from_socket(self, websocket):
        """Listens to the socket and puts messages into the read stream."""
        async for msg in websocket:
            try:
                client_message = types.JSONRPCMessage.model_validate_json(msg)
            except ValidationError as exc:
                await self._read_stream_writer.send(exc)
                continue
            await self._read_stream_writer.send(SessionMessage(client_message))

    async def _write_to_socket(self, websocket):
        """Reads from the write stream and sends over the socket."""
        try:
            while True:
                # Wait for a message from the application
                msg = await self._write_stream_reader.receive()

                try:
                    json_obj = msg.message.model_dump_json(
                        by_alias=True, exclude_none=True
                    )
                    await websocket.send(json_obj)
                except ConnectionClosed:
                    break
        except (anyio.ClosedResourceError, anyio.EndOfStream):
            # server closed write stream
            pass

    def _validate_authorization(self, websocket: ServerConnection, request: Request):
        if request.path.find(f"access_token={self.token}") != -1:
            return None
        try:
            headers: Headers = request.headers
            auth_header = headers.get("Authorization")
            if not auth_header:
                return Response(401, "Missing authorization", Headers([]))
            scheme, token = auth_header.split(None, 1)
            if scheme.lower() != "bearer":
                return Response(400, "Invalid authorization header", Headers([]))
        except ValueError:
            return Response(400, "Invalid header format", Headers([]))
        if token == self.token:
            return None
        return Response(403, "Bad authorization token", Headers([]))

    async def _connection_handler(self, websocket: ServerConnection):
        """
        Handles incoming websocket connections.
        Validates Origin and ensures single-client exclusivity.
        """
        if self.connection_lock.locked():
            logging.warning(
                f"Connection rejected: {websocket.remote_address}. A client is already connected"
            )
            await websocket.close(code=1013, reason="Server is busy")
            return

        async with self.connection_lock:
            try:
                self.connection_live.set()

                reading_task = asyncio.create_task(self._read_from_socket(websocket))
                writing_task = asyncio.create_task(self._write_to_socket(websocket))
                _, pending = await asyncio.wait(
                    [reading_task, writing_task], return_when=asyncio.FIRST_COMPLETED
                )

                for task in pending:
                    task.cancel()

            except websockets.exceptions.ConnectionClosed as e:
                logging.info(f"Connection closed: {e.code} - {e.reason}")
                await self._read_stream_writer.send(
                    Exception("Colab Frontend disconnected")
                )
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
            finally:
                self.connection_live.clear()

    async def __aenter__(self):
        logging.info(f"Starting WebSocket server on ws://{self.host}:{self.port}")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Set the SO_REUSEADDR option to allow the address to be reused immediately
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        self._server = await websockets.serve(
            self._connection_handler,
            sock=sock,
            subprotocols=[Subprotocol("mcp")],
            origins=self.allowed_origins,
            process_request=self._validate_authorization,
        )
        webbrowser.open_new(f"{COLAB}{SCRATCH_PATH}#mcpProxyToken={self.token}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        logging.info("Closing WebSocket server")
        if self._server:
            self._server.close()
            self.write_stream.close()
            self.read_stream.close()
            await self._server.wait_closed()
