# Colab-mcp

An MCP server for interacting with Colab.

# Setup

- Install `uv` (`pip install uv`)
- Configure for usage (eg for mcp.json style services):

```
...
  "mcpServers": {
    "colab-mcp": {
      "command": "uvx",
      "args": ["git+https://github.com/googlecolab/colab-mcp"],
      "timeout": 30000
    }
  }
...
```

## Internal - For Colab Developers

### Prerequisites

- `uv` is required (`pip install uv`)
- Configure git hooks to run repo presubmits

```shell
git config core.hooksPath .githooks
```

### Gemini CLI setup

```
...
  "mcpServers": {
    "colab-mcp": {
      "command": "uv",
      "args": ["run", "colab-mcp"],
      "cwd": "/path/to/github/colab-mcp",
      "timeout": 30000
    }
  }
...
```
