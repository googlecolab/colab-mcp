import argparse
import asyncio
import datetime
import logging
import tempfile
import sys

from fastmcp import FastMCP
from fastmcp.utilities import logging as fastmcp_logger

from colab_mcp import runtime
from colab_mcp import auth
from colab_mcp.session import ColabSessionProxy


mcp = FastMCP(name="ColabMCP")


def init_logger(logdir):
    log_filename = datetime.datetime.now().strftime(
        f"{logdir}/colab-mcp.%Y-%m-%d_%H-%M-%S.log"
    )
    logging.basicConfig(
        format="%(asctime)s %(levelname)s:%(message)s",
        datefmt="%m/%d/%Y %I:%M:%S %p",
        filename=log_filename,
        level=logging.INFO,  # Set the minimum logging level to capture
    )
    fastmcp_logger.get_logger("colab-mcp").info("logging to %s" % log_filename)


def parse_args(v):
    parser = argparse.ArgumentParser(
        description="ColabMCP is an MCP server that lets you interact with Colab."
    )
    parser.add_argument(
        "-l",
        "--log",
        help="if set, use this directory as a location for logfiles (if unset, will log to %s/colab-mcp-logs/)"
        % tempfile.gettempdir(),
        action="store",
        default=tempfile.mkdtemp(prefix="colab-mcp-logs-"),
    )
    parser.add_argument(
        "-r",
        "--enable-runtime",
        help="if set, export tools to talk directly to the Colab Jupyter runtime (disabled by default).",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "-p",
        "--enable-proxy",
        help="if set, enable the runtime proxy (enabled by default).",
        action="store_true",
        default=True,
    )
    return parser.parse_args(v)


async def main_async():
    args = parse_args(sys.argv[1:])
    init_logger(args.log)

    if args.enable_runtime:
        # preemptively initialize credentials when we start so they're available
        try:
            auth.GoogleOAuthClient.get_session()
        except PermissionError as e:
            sys.exit(f"failed to initialize authentication credentials, exiting - {e}")
        crt = runtime.ColabRuntimeTool()
        logging.info("enabling runtime tools")
        mcp.mount(crt.mcp, prefix="runtime")

    if args.enable_proxy:
        logging.info("enabling session proxy tools")
        session_mcp = ColabSessionProxy()
        await session_mcp.start_proxy_server()
        mcp.mount(session_mcp.proxy_server)
        for middleware in session_mcp.middleware:
            mcp.add_middleware(middleware)

    try:
        await mcp.run_async()

    finally:
        if args.enable_proxy:
            await session_mcp.cleanup()

        if args.enable_runtime:
            if crt:
                crt.stop()


def main() -> None:
    asyncio.run(main_async())
