from colab_mcp import runtime

import pytest


@pytest.mark.asyncio
async def test_execute_code():
    result = runtime.ColabRuntimeTool.execute_code("1+2")
    assert result == 3
