# LLM Specs Overview

## Project Overview
OSW-Builder is a tool for building Virtual Machine images for testing and malware analysis, supporting Windows (XP/10/11) and Ubuntu systems using Packer and Docker.

## Key Commands for Testing
```bash
# Run all tests
python -m pytest

# Run specific module tests  
python -m pytest osw_builder/image_builder/test_utils.py -v

# Run tests with coverage
python -m pytest osw_builder/image_builder/test_utils.py --cov=osw_builder.image_builder.build --cov-report=term-missing

# Run linting (if available)
python -m ruff check osw_builder/
python -m black --check osw_builder/
```

## Architecture: Image Builder Module

The `osw_builder.image_builder.build` module has been refactored for better testability and maintainability:

### Pure Functions (Highly Testable)
These functions have no side effects and are easy to unit test:

- **`build_packer_cmdline(template, packer_args)`** - Builds Packer command line arguments
- **`build_docker_volumes(response_file, tmp_varfile_path, packer_cache)`** - Creates Docker volume configuration
- **`build_docker_config(volumes, cmdline, network)`** - Creates Docker container configuration

### Context Managers
- **`docker_packer_runner(docker_config, network)`** - Manages Docker container lifecycle with guaranteed cleanup
- **`write_temp_varfile(varfile_data)`** - Creates temporary HCL variable files
- **`ensure_cleanup_output()`** - Ensures output directory cleanup

### Orchestration Functions
- **`run_packer()`** - Main orchestration function that uses pure functions + context manager
- **`build_image()`** - High-level function for the complete image building process

### Testing Strategy
1. **Unit tests** for all pure functions (no mocking needed)
2. **Mocked tests** for context managers using `unittest.mock`
3. **Parametrized tests** for different OS configurations
4. **Integration tests** using the existing pattern in `test_utils.py`

### Current Test Coverage
- Pure functions: 100% covered with fast unit tests
- Context managers: 95%+ covered with mocked Docker operations
- Overall module: ~52% (higher-level orchestration functions use real I/O)

## Development Guidelines

### Adding New Features
1. Extract business logic into pure functions first
2. Use context managers for resource management
3. Keep orchestration functions thin
4. Add unit tests for pure functions immediately
5. Add mocked tests for context managers

### Testing New Code
```bash
# Test your changes
python -m pytest osw_builder/image_builder/test_utils.py -v

# Check coverage
python -m pytest osw_builder/image_builder/test_utils.py --cov=osw_builder.image_builder.build

# Run all tests to ensure no regressions
python -m pytest osw_builder/
```

### Code Style
- Follow existing patterns for response file handling
- Use type hints for function parameters and return values  
- Keep functions focused on single responsibilities
- Use context managers for resource cleanup

## Response File System
The system supports multiple OS types through polymorphic response files:
- **Windows 10/11**: `Autounattend.xml` files  
- **Windows XP**: `WINNT.SIF` files
- **Ubuntu**: `preseed.cfg` files

Each response file type implements the `ResponseFile` interface with OS-specific configuration logic.

## Common Patterns

### Testing Pure Functions
```python
def test_build_packer_cmdline():
    result = build_packer_cmdline("ubuntu.pkr.hcl", ["cpus=4"])
    expected = ["build", "-only", "qemu.vm", ..., "ubuntu.pkr.hcl"]
    assert result == expected
```

### Testing Context Managers with Mocks
```python
@patch('osw_builder.image_builder.build.docker.from_env')
def test_docker_context_manager(mock_docker):
    mock_client = MagicMock()
    mock_docker.return_value = mock_client
    
    with docker_packer_runner(config, network=True):
        pass
    
    mock_client.containers.run.assert_called_once()
```

## Architecture Benefits
- **Fast unit tests** for business logic without Docker dependencies
- **Reliable resource cleanup** through context managers
- **Clear separation of concerns** between pure logic and side effects
- **Easy to mock and test** complex Docker interactions
- **Maintainable code** with single-responsibility functions

This architecture enables confident refactoring and feature additions while maintaining backward compatibility.