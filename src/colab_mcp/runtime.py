import logging

from fastmcp import FastMCP

# from colab_mcp import auth

# Create an MCP server
mcp = FastMCP("runtime")


class _ColabRuntimeTool(object):
    def execute_code(self, code: str):
        """(Eventually) Evaluates code in a Colab kernel."""
        # creds = auth.GoogleOAuthClient.get_credentials()
        logging.info(f"running code {code}")
        # But for now, just evals here.
        return eval(code)


ColabRuntimeTool = _ColabRuntimeTool()

mcp.tool(ColabRuntimeTool.execute_code)
