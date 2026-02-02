import logging
import uuid

from fastmcp import FastMCP
import jupyter_kernel_client

from colab_mcp import auth
from colab_mcp import client

# Create an MCP server
mcp = FastMCP("runtime")


class _ColabRuntimeTool(object):
    def __init__(self):
        self.__session = None
        self.__colab_prod_client = None

    @property
    def session(self):
        if not self.__session:
            self.__session = auth.GoogleOAuthClient.get_session()
        return self.__session

    @property
    def colab_prod_client(self):
        if not self.__colab_prod_client:
            self.__colab_prod_client = client.ColabClient(client.Prod, self.session)
        return self.__colab_prod_client

    def kernel_client_for(self, server_url, token, kernel_id=None):
        k = jupyter_kernel_client.KernelClient(
            server_url=server_url,
            kernel_id=kernel_id,
            token="unused",
            client_kwargs={
                "subprotocol": jupyter_kernel_client.JupyterSubprotocol.DEFAULT,
                "extra_params": {"colab-runtime-proxy-token": token},
            },
            headers={
                "X-Colab-Client-Agent": "colab-mcp",
                "X-Colab-Runtime-Proxy-Token": token,
            },
        )

        # Note that start() checks to see if there is already a connection, so repeating it won't hurt.
        # See https://github.com/datalayer/jupyter-kernel-client/blob/786cdc38b7c97beaab751eee2a6836f25e010b06/jupyter_kernel_client/client.py#L413
        k.start()
        return k

    def new_colab_server(self, notebook_id: uuid.UUID):
        """Provisions a new Colab VM assignment for a specific notebook.

        Use this if `list_all_kernel_sessions()` returns an empty list or if you
        need a fresh environment. The `notebook_id` can be extracted from the
        Colab notebook URL.
        """
        return self.colab_prod_client.assign(notebook_id)

    def list_all_kernel_sessions(self):
        """Discovers all active Colab runtimes and their Jupyter kernels.

        This is the primary discovery tool. It returns a list of dictionaries
        containing `server_url`, `token`, and `kernel` information (including `kernel_id`).
        These values are required for `execute_code`.

        Note: Metadata can expire; if a connection fails, call this again to refresh.
        """
        r = []
        for assignment in self.colab_prod_client.list_assignments():
            server_url = assignment.runtime_proxy_info.url
            token = assignment.runtime_proxy_info.token
            kc = self.kernel_client_for(server_url, token)
            for kernel in kc.list_kernels():
                r.append(
                    {
                        "server_url": server_url,
                        "token": token,
                        "kernel": kernel,
                    }
                )
        return r

    def execute_code(self, server_url: str, token: str, kernel_id: str, code: str):
        """Evaluates Python code in a specific Colab kernel.

        Requires connection details (url, token, kernel_id) obtained from
        `list_all_kernel_sessions()`.

        Returns a list of output objects (e.g., text, display data, or errors).

        Arguments:
            - server_url (string): The Colab Jupyter server URL to run code on.
            - token (string): The token required to talk to the given Colab Jupyter server.
            - kernel_id (string): The kernel ID to use to execute the given code.
            - code (string): the code to execute.
        """
        logging.info(f"running code {code}")
        reply = self.kernel_client_for(server_url, token).execute(code)
        if reply and reply.get("outputs"):
            return reply.get("outputs")


ColabRuntimeTool = _ColabRuntimeTool()

mcp.tool(ColabRuntimeTool.list_all_kernel_sessions)
mcp.tool(ColabRuntimeTool.new_colab_server)
mcp.tool(ColabRuntimeTool.execute_code)
