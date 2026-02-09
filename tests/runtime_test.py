from unittest import mock

import pytest
from colab_mcp import runtime


@pytest.fixture
def runtime_tool():
    with mock.patch("fastmcp.FastMCP"):
        return runtime.ColabRuntimeTool()


def test_session_property(runtime_tool):
    mock_session = mock.Mock()
    with mock.patch(
        "colab_mcp.auth.GoogleOAuthClient.get_session", return_value=mock_session
    ):
        assert runtime_tool.session == mock_session
        # Test memoization
        assert runtime_tool.session == mock_session


def test_colab_prod_client_property(runtime_tool):
    mock_session = mock.Mock()
    mock_client_instance = mock.Mock()
    with (
        mock.patch.object(
            runtime.ColabRuntimeTool, "session", new_callable=mock.PropertyMock
        ) as mock_session_prop,
        mock.patch("colab_mcp.client.ColabClient", return_value=mock_client_instance),
    ):
        mock_session_prop.return_value = mock_session
        assert runtime_tool.colab_prod_client == mock_client_instance
        # Test memoization
        assert runtime_tool.colab_prod_client == mock_client_instance


def test_assignment_property(runtime_tool):
    mock_client = mock.Mock()
    mock_assignment = mock.Mock()
    mock_client.assign.return_value = mock_assignment

    with mock.patch.object(
        runtime.ColabRuntimeTool, "colab_prod_client", new_callable=mock.PropertyMock
    ) as mock_client_prop:
        mock_client_prop.return_value = mock_client
        assert runtime_tool.assignment == mock_assignment
        mock_client.assign.assert_called_once()
        # Test memoization
        assert runtime_tool.assignment == mock_assignment
        assert mock_client.assign.call_count == 1


def test_kernel_client_property(runtime_tool):
    mock_assignment = mock.Mock()
    mock_assignment.runtime_proxy_info.url = "http://server"
    mock_assignment.runtime_proxy_info.token = "token123"

    mock_kc_instance = mock.Mock()

    with (
        mock.patch.object(
            runtime.ColabRuntimeTool, "assignment", new_callable=mock.PropertyMock
        ) as mock_assignment_prop,
        mock.patch("jupyter_kernel_client.KernelClient", return_value=mock_kc_instance),
    ):
        mock_assignment_prop.return_value = mock_assignment
        assert runtime_tool.kernel_client == mock_kc_instance
        mock_kc_instance.start.assert_called_once()
        # Test memoization
        assert runtime_tool.kernel_client == mock_kc_instance
        assert mock_kc_instance.start.call_count == 1


def test_start(runtime_tool):
    mock_kc = mock.Mock()
    mock_assignment = mock.Mock()
    mock_assignment.endpoint = "vm-endpoint"

    with (
        mock.patch.object(
            runtime.ColabRuntimeTool, "kernel_client", new_callable=mock.PropertyMock
        ) as mock_kc_prop,
        mock.patch.object(
            runtime.ColabRuntimeTool, "assignment", new_callable=mock.PropertyMock
        ) as mock_assignment_prop,
    ):
        mock_kc_prop.return_value = mock_kc
        mock_assignment_prop.return_value = mock_assignment

        runtime_tool.start()

        mock_kc.execute.assert_called_once_with("_colab_mcp = True")


def test_stop(runtime_tool):
    mock_client = mock.Mock()
    mock_assignment = mock.Mock()
    mock_assignment.endpoint = "vm-endpoint"

    # Test stop when assignment exists
    with (
        mock.patch.object(
            runtime.ColabRuntimeTool,
            "colab_prod_client",
            new_callable=mock.PropertyMock,
        ) as mock_client_prop,
        mock.patch.object(
            runtime.ColabRuntimeTool, "assignment", new_callable=mock.PropertyMock
        ) as mock_assignment_prop,
    ):
        mock_client_prop.return_value = mock_client
        mock_assignment_prop.return_value = mock_assignment

        runtime_tool.stop()

        mock_client.unassign.assert_called_once_with("vm-endpoint")

    # Test stop when assignment is None
    mock_client.unassign.reset_mock()
    with mock.patch.object(
        runtime.ColabRuntimeTool, "assignment", new_callable=mock.PropertyMock
    ) as mock_assignment_prop:
        mock_assignment_prop.return_value = None
        runtime_tool.stop()
        mock_client.unassign.assert_not_called()


def test_execute_code(runtime_tool):
    mock_kc = mock.Mock()
    mock_kc.execute.return_value = {"outputs": [{"text": "hello"}]}

    with mock.patch.object(
        runtime.ColabRuntimeTool, "kernel_client", new_callable=mock.PropertyMock
    ) as mock_kc_prop:
        mock_kc_prop.return_value = mock_kc

        result = runtime_tool.execute_code("print('hello')")

        assert result == [{"text": "hello"}]
        mock_kc.execute.assert_called_once_with("print('hello')")


def test_execute_code_no_outputs(runtime_tool):
    mock_kc = mock.Mock()
    mock_kc.execute.return_value = {"status": "ok"}

    with mock.patch.object(
        runtime.ColabRuntimeTool, "kernel_client", new_callable=mock.PropertyMock
    ) as mock_kc_prop:
        mock_kc_prop.return_value = mock_kc

        result = runtime_tool.execute_code("print('hello')")

        assert result is None


def test_execute_code_empty_reply(runtime_tool):
    mock_kc = mock.Mock()
    mock_kc.execute.return_value = None

    with mock.patch.object(
        runtime.ColabRuntimeTool, "kernel_client", new_callable=mock.PropertyMock
    ) as mock_kc_prop:
        mock_kc_prop.return_value = mock_kc

        result = runtime_tool.execute_code("print('hello')")

        assert result is None
