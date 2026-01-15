import asyncio
import logging
import sys

from fastmcp import FastMCP

from colab_mcp import runtime
from colab_mcp import auth
from colab_mcp.session import ColabSessionProxy

import jupyter_kernel_client

mcp = FastMCP(name="ColabMCP")


async def main_async():
    # initialize credentials when we start so they're available
    # after.
    creds = auth.GoogleOAuthClient.get_credentials()
    if not creds.token:
        sys.exit("failed to initialize authentication credentials, exiting!")
    logging.basicConfig(
        filename="colab-mcp.log",  # Specify the log file name
        level=logging.INFO,  # Set the minimum logging level to capture
    )
    logging.info(
        "using mcp server: %s, kernel client: %s" % (runtime.mcp, jupyter_kernel_client)
    )
    await mcp.import_server(runtime.mcp, prefix="runtime")
    session_mcp = ColabSessionProxy()
    await session_mcp.start_proxy_server()
    mcp.mount(session_mcp.proxy_server)
    for middleware in session_mcp.middleware:
        mcp.add_middleware(middleware)
    await mcp.run_async()
    await session_mcp.cleanup()


def main() -> None:
    asyncio.run(main_async())
