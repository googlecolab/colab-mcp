# Colab-mcp

An MCP server for interacting with Colab.


## Gemini CLI setup

```
{
  "general": {
    "previewFeatures": true
  },
  "mcpServers": {
	<mark>
    "colab-mcp": {
      "command": "uv",
      "args": ["run", "colab-mcp"],
      "cwd": "/Users/rtp/github/colab-mcp",
      "timeout": 30000
    }
	</mark>
  }
}
```

## Developing

Set your hooks to use the repo hooks:

```shell
git config core.hooksPath .githooks
```
