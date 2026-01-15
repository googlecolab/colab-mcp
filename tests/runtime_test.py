from colab_mcp import runtime

import pytest


@pytest.mark.asyncio
async def test_execute_code():
    print("runtime: " % dir(runtime))
    # result = await runtime.execute_code({"code": "1+2"})
    # assert len(result.content) == 1
    # assert result.content[0].text == "3"
