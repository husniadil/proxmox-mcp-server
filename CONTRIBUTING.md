# Contributing to Proxmox MCP Server

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue with:

1. **Clear title** - Describe the issue concisely
2. **Steps to reproduce** - How can we reproduce the bug?
3. **Expected behavior** - What should happen?
4. **Actual behavior** - What actually happened?
5. **Environment details**:
   - Proxmox VE version
   - Python version
   - OS (macOS/Windows/Linux)
   - Claude Desktop version

### Suggesting Features

Feature requests are welcome! Please include:

1. **Use case** - Why is this feature needed?
2. **Proposed solution** - How should it work?
3. **Alternatives considered** - What other approaches did you think about?

### Pull Requests

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes**
4. **Test thoroughly**
   - Test with actual Proxmox environment
   - Verify error handling
   - Check documentation accuracy
5. **Commit with clear messages**
   ```bash
   git commit -m "Add feature: description"
   ```
6. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

## Development Guidelines

### Code Style

- Follow PEP 8 style guide
- Use type hints
- Write clear docstrings
- Keep functions focused and small
- Use meaningful variable names

### Testing

Before submitting:

- Test with real Proxmox environment
- Verify all tools work correctly
- Check error handling paths
- Test with different configurations

### Documentation

- Update README.md if needed
- Add docstrings to new functions
- Update examples if behavior changes
- Keep comments clear and concise

### MCP Best Practices

When adding tools:

- Use descriptive tool names (snake_case)
- Provide comprehensive docstrings
- Include input validation with Pydantic
- Return structured data (JSON or text)
- Handle errors gracefully with helpful messages
- Add appropriate tool annotations

Example tool structure:

```python
@mcp.tool(
    name="tool_name",
    annotations={
        "title": "Human-Readable Title",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True
    }
)
async def tool_name(params: InputModel) -> str:
    """Clear description of what the tool does.

    More details about usage, parameters, and return values.

    Args:
        params (InputModel): Description of parameters

    Returns:
        str: Description of return value
    """
    # Implementation
```

## Areas for Contribution

### Easy

- Documentation improvements
- Example commands
- Error message improvements
- Configuration examples

### Medium

- Additional container operations
- Better output formatting
- Performance optimizations
- More comprehensive error handling

### Advanced

- VM support (not just containers)
- Multiple Proxmox host support
- Advanced monitoring features
- Snapshot management
- Backup/restore operations
- Network configuration management
- Storage pool management

## Questions?

- Open an [Issue](https://github.com/husniadil/proxmox-mcp-server/issues) for questions or discussions

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing! 🎉
