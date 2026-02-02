import argparse
import asyncio
import datetime
import logging
import sys

from fastmcp import FastMCP

from colab_mcp import runtime
from colab_mcp import auth
from colab_mcp.session import ColabSessionProxy

import jupyter_kernel_client

mcp = FastMCP(name="ColabMCP")


def init_logger():
    log_filename = datetime.datetime.now().strftime(
        "logs/colab-mcp.%Y-%m-%d_%H-%M-%S.log"
    )
    logging.basicConfig(
        format="%(asctime)s %(levelname)s:%(message)s",
        datefmt="%m/%d/%Y %I:%M:%S %p",
        filename=log_filename,
        level=logging.INFO,  # Set the minimum logging level to capture
    )


def parse_args(v):
    parser = argparse.ArgumentParser(
        description="ColabMCP is an MCP server that lets you interact with Colab."
    )
    parser.add_argument(
        "-r",
        "--enable-runtime",
        help="if set, export tools to talk directly to the Colab Jupyter runtime (disabled by default).",
        action="store_true",
        default=False,
    )
    return parser.parse_args(v)


async def main_async():
    args = parse_args(sys.argv[1:])
    init_logger()

    # initialize credentials when we start so they're available
    # after.
    try:
        auth.GoogleOAuthClient.get_session()
    except PermissionError as e:
        sys.exit(f"failed to initialize authentication credentials, exiting - {e}")

    logging.info(
        "using mcp server: %s, kernel client: %s" % (runtime.mcp, jupyter_kernel_client)
    )

    if args.enable_runtime:
        mcp.mount(runtime.mcp, prefix="runtime")

    session_mcp = ColabSessionProxy()
    await session_mcp.start_proxy_server()
    mcp.mount(session_mcp.proxy_server)
    for middleware in session_mcp.middleware:
        mcp.add_middleware(middleware)
    await mcp.run_async()
    await session_mcp.cleanup()


def main() -> None:
    asyncio.run(main_async())
