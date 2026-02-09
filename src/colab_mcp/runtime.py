import logging
import uuid

from fastmcp import FastMCP

import jupyter_kernel_client

from colab_mcp import auth
from colab_mcp import client


class ColabRuntimeTool(object):
    def __init__(self):
        self.__session = None
        self.__colab_prod_client = None
        self.__kernel_client = None
        self.__assignment = None
        # This is meant to be unique per each ColabRuntimeTool.
        self.__id = uuid.uuid4()
        # initialize MCP server bits
        self.mcp = FastMCP("runtime")
        self.mcp.tool(self.execute_code)

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

    @property
    def assignment(self):
        if not self.__assignment:
            self.__assignment = self.colab_prod_client.assign(self.__id)
        return self.__assignment

    @property
    def kernel_client(self):
        if not self.__kernel_client:
            url = self.assignment.runtime_proxy_info.url
            token = self.assignment.runtime_proxy_info.token

            self.__kernel_client = jupyter_kernel_client.KernelClient(
                server_url=url,
                token=token,
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
            self.__kernel_client.start()
        return self.__kernel_client

    def start(self):
        """Start a Colab session. Fetch (assign) a VM, and initialize a Jupyter kernel."""

        # All the resources in this class are lazily initialized, so touching the
        # kernel client here will cause use to get a VM assignment, then find the right
        # kernel to use.
        self.kernel_client.execute("_colab_mcp = True")
        logging.info("initialized - assigned %s", self.assignment.endpoint)

    def stop(self):
        """Stop the session. Unassign the VM."""
        if self.assignment:
            self.colab_prod_client.unassign(self.assignment.endpoint)
            logging.info("unassigned %s", self.assignment.endpoint)

    def execute_code(self, code: str):
        """Evaluates Python code in a specific Colab kernel.

        Returns a list of output objects (e.g., text, display data, or errors).

        Arguments:
            - code (string): the code to execute.
        """
        logging.info(f"running code {code}")
        reply = self.kernel_client.execute(code)
        if reply and reply.get("outputs"):
            return reply.get("outputs")
