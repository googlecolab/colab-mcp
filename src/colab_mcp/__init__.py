from fastmcp import FastMCP
import asyncio

from colab_mcp import runtime
from colab_mcp.session import ColabSessionProxy

mcp = FastMCP(name="ColabMCP")

async def main_async():
    await mcp.import_server(runtime.mcp, prefix="runtime")
    session_mcp = ColabSessionProxy()
    await session_mcp.start_proxy_server()
    mcp.mount(session_mcp.proxy_server, as_proxy=True)
    await mcp.run_async()
    await session_mcp.cleanup()
    session_mcp = ColabSessionProxy()
    await session_mcp.start_proxy_server()
    mcp.mount(session_mcp.proxy_server, as_proxy=True)
    await mcp.run_async()
    await session_mcp.cleanup()


def main() -> None:
    asyncio.run(main_async())
