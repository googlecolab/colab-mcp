import uuid
from unittest import mock

import pytest
from colab_mcp import runtime
from colab_mcp.client import (
    Accelerator,
    AssignmentVariant,
    ListedAssignment,
    RuntimeProxyInfo,
    Shape,
)


@pytest.fixture(autouse=True)
def reset_runtime_tool():
    """Reset the singleton ColabRuntimeTool before each test."""
    runtime.ColabRuntimeTool._ColabRuntimeTool__session = None
    runtime.ColabRuntimeTool._ColabRuntimeTool__colab_prod_client = None
    runtime.ColabRuntimeTool._ColabRuntimeTool__kernel_client = None
    yield


@pytest.mark.asyncio
async def test_new_colab_server():
    notebook_id = uuid.uuid4()
    mock_session = mock.Mock()
    mock_colab_client = mock.Mock()
    expected_result = {"assignment": "foo"}
    mock_colab_client.assign.return_value = expected_result

    with (
        mock.patch(
            "colab_mcp.auth.GoogleOAuthClient.get_session", return_value=mock_session
        ),
        mock.patch("colab_mcp.client.ColabClient", return_value=mock_colab_client),
    ):
        result = runtime.ColabRuntimeTool.new_colab_server(notebook_id)

    mock_colab_client.assign.assert_called_once_with(notebook_id)
    assert result == expected_result


@pytest.mark.asyncio
async def test_list_all_kernel_sessions():
    mock_session = mock.Mock()
    mock_colab_client = mock.Mock()

    assignment = ListedAssignment(
        accelerator=Accelerator.NONE,
        endpoint="endpoint",
        variant=AssignmentVariant.DEFAULT,
        machineShape=Shape.STANDARD,
        runtimeProxyInfo=RuntimeProxyInfo(
            token="token123", tokenExpiresInSeconds=3600, url="http://server"
        ),
    )
    mock_colab_client.list_assignments.return_value = [assignment]

    mock_kc = mock.Mock()
    mock_kc.list_kernels.return_value = [{"id": "k1"}]

    with (
        mock.patch(
            "colab_mcp.auth.GoogleOAuthClient.get_session", return_value=mock_session
        ),
        mock.patch("colab_mcp.client.ColabClient", return_value=mock_colab_client),
        mock.patch("jupyter_kernel_client.KernelClient", return_value=mock_kc),
    ):
        result = runtime.ColabRuntimeTool.list_all_kernel_sessions()

    assert len(result) == 1
    assert result[0]["server_url"] == "http://server"
    assert result[0]["token"] == "token123"
    assert result[0]["kernel"] == {"id": "k1"}


@pytest.mark.asyncio
async def test_execute_code():
    mock_kc = mock.Mock()
    mock_kc.execute.return_value = {"outputs": [{"text": "hello"}]}

    with mock.patch("jupyter_kernel_client.KernelClient", return_value=mock_kc):
        result = runtime.ColabRuntimeTool.execute_code(
            "http://server", "token123", "k1", "print('hello')"
        )

    assert result == [{"text": "hello"}]
    mock_kc.execute.assert_called_once_with("print('hello')")
    mock_kc.start.assert_called_once()


@pytest.mark.asyncio
async def test_execute_code_no_outputs():
    mock_kc = mock.Mock()
    # Mocking return value for execute that has no outputs
    mock_kc.execute.return_value = {"status": "ok"}

    with mock.patch("jupyter_kernel_client.KernelClient", return_value=mock_kc):
        result = runtime.ColabRuntimeTool.execute_code(
            "http://server", "token123", "k1", "print('hello')"
        )

    assert result is None


@pytest.mark.asyncio
async def test_execute_code_empty_reply():
    mock_kc = mock.Mock()
    mock_kc.execute.return_value = None

    with mock.patch("jupyter_kernel_client.KernelClient", return_value=mock_kc):
        result = runtime.ColabRuntimeTool.execute_code(
            "http://server", "token123", "k1", "print('hello')"
        )

    assert result is None


@pytest.mark.asyncio
async def test_list_all_kernel_sessions_no_assignments():
    mock_session = mock.Mock()
    mock_colab_client = mock.Mock()
    mock_colab_client.list_assignments.return_value = []

    with (
        mock.patch(
            "colab_mcp.auth.GoogleOAuthClient.get_session", return_value=mock_session
        ),
        mock.patch("colab_mcp.client.ColabClient", return_value=mock_colab_client),
    ):
        result = runtime.ColabRuntimeTool.list_all_kernel_sessions()

    assert result == []


@pytest.mark.asyncio
async def test_list_all_kernel_sessions_no_kernels():
    mock_session = mock.Mock()
    mock_colab_client = mock.Mock()

    assignment = ListedAssignment(
        accelerator=Accelerator.NONE,
        endpoint="endpoint",
        variant=AssignmentVariant.DEFAULT,
        machineShape=Shape.STANDARD,
        runtimeProxyInfo=RuntimeProxyInfo(
            token="token123", tokenExpiresInSeconds=3600, url="http://server"
        ),
    )
    mock_colab_client.list_assignments.return_value = [assignment]

    mock_kc = mock.Mock()
    mock_kc.list_kernels.return_value = []

    with (
        mock.patch(
            "colab_mcp.auth.GoogleOAuthClient.get_session", return_value=mock_session
        ),
        mock.patch("colab_mcp.client.ColabClient", return_value=mock_colab_client),
        mock.patch("jupyter_kernel_client.KernelClient", return_value=mock_kc),
    ):
        result = runtime.ColabRuntimeTool.list_all_kernel_sessions()

    assert result == []
