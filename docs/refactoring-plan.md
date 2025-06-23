# OSW-Builder Refactoring Plan

## Executive Summary

This document outlines a comprehensive refactoring strategy for the osw-builder project to improve code organization, maintainability, and testability. The plan is structured in 5 phases, prioritizing low-risk changes with high impact first.

## Current Architecture Analysis

### Identified Issues

1. **Monolithic Main Function**: The `capture_os` function in `__main__.py` is 236 lines long with multiple responsibilities
2. **Hardcoded Constants**: Magic values scattered throughout the codebase (`BLACKLISTED_UPDATES`, snapshots)
3. **Mixed Concerns**: Business logic, configuration, and orchestration mixed in single modules
4. **Limited Error Handling**: Inconsistent error handling patterns across modules
5. **Testing Gaps**: Limited unit test coverage for complex workflows
6. **Configuration Management**: Settings scattered across YAML and hardcoded values

### Current Module Structure

```
osw_builder/
├── __main__.py           # CLI entry point + main orchestration (236 lines)
├── build/               # Image building with Packer/Docker
├── capture/             # Filesystem capture with libguestfs/neogit
├── vagrant/             # VM management with Vagrant/libvirt
├── settings.py          # Configuration management
└── default_settings.yaml # OS image definitions
```

## Proposed Refactoring Plan

### Phase 1: Extract Constants and Configuration (Low Risk, High Impact)

**Objective**: Centralize hardcoded values and improve configuration management.

**Changes**:
- Create `osw_builder/constants.py` for all hardcoded values
- Extract `BLACKLISTED_UPDATES`, `BUILD_SNAPSHOT`, `IDLE_SNAPSHOT` from `__main__.py`
- Consolidate snapshot definitions in configuration
- Add configuration validation

**Files Modified**:
- `osw_builder/__main__.py` (remove hardcoded constants)
- `osw_builder/constants.py` (new file)
- `osw_builder/settings.py` (add validation)
- `osw_builder/default_settings.yaml` (add snapshot configs)

**Benefits**:
- Single source of truth for configuration
- Easier to modify behavior without code changes
- Improved maintainability

### Phase 2: Extract Core Domain Models (Low Risk, Medium Impact)

**Objective**: Create clear data structures representing core domain concepts.

**Changes**:
- Enhance `Snapshot` class with validation and serialization
- Create `OSImage` dataclass to encapsulate image metadata
- Create `BuildContext` to encapsulate build parameters
- Add type hints throughout

**Files Modified**:
- `osw_builder/models.py` (new file)
- `osw_builder/snapshot.py` (enhance existing)
- Update imports across modules

**Benefits**:
- Better type safety
- Clearer data contracts
- Improved IDE support

### Phase 3: Break Down Monolithic Functions (Medium Risk, High Impact)

**Objective**: Split large functions into focused, testable units.

**Changes**:
- Extract VM lifecycle management from `capture_os`
- Create `OSImageBuilder` class for orchestration
- Split snapshot processing into separate functions
- Extract Windows Update handling logic

**New Structure**:
```python
class OSImageBuilder:
    def __init__(self, config, os_name):
        self.config = config
        self.os_name = os_name
    
    def build_and_capture(self):
        """Main orchestration method"""
        
    def _prepare_vm_environment(self):
        """VM setup and validation"""
        
    def _process_build_snapshot(self):
        """Handle build snapshot capture"""
        
    def _process_idle_snapshot(self):
        """Handle idle state capture"""
        
    def _process_update_snapshots(self):
        """Handle Windows Update snapshots"""
```

**Files Modified**:
- `osw_builder/orchestration.py` (new file)
- `osw_builder/__main__.py` (simplified to CLI parsing + orchestration)

### Phase 4: Improve Error Handling and Validation (Medium Risk, Medium Impact)

**Objective**: Standardize error handling and add comprehensive validation.

**Changes**:
- Create custom exception hierarchy
- Add input validation for all public functions
- Implement proper cleanup on failures
- Add logging improvements

**New Exception Structure**:
```python
class OSWBuilderError(Exception):
    """Base exception for osw-builder"""

class ConfigurationError(OSWBuilderError):
    """Invalid configuration or settings"""

class BuildError(OSWBuilderError):
    """Errors during image building"""

class CaptureError(OSWBuilderError):
    """Errors during filesystem capture"""

class VMError(OSWBuilderError):
    """VM management errors"""
```

### Phase 5: Enhance Testing and Documentation (Low Risk, High Impact)

**Objective**: Improve test coverage and code documentation.

**Changes**:
- Add unit tests for all new classes and functions
- Create integration test suite
- Add docstrings following Google/NumPy style
- Create architecture documentation

**Testing Strategy**:
- Mock external dependencies (Docker, libvirt, etc.)
- Test configuration validation
- Test error handling paths
- Integration tests for critical workflows

## Implementation Guidelines

### Code Quality Standards

- **Type Hints**: All new code must include comprehensive type hints
- **Docstrings**: All public functions and classes need docstrings
- **Error Handling**: Explicit error handling with custom exceptions
- **Logging**: Structured logging with appropriate levels
- **Testing**: Unit tests for all business logic

### Migration Strategy

1. **Backward Compatibility**: Maintain existing CLI interface during refactoring
2. **Incremental Changes**: Complete each phase before moving to the next
3. **Testing**: Ensure all existing tests pass after each phase
4. **Documentation**: Update documentation as changes are made

### Risk Mitigation

- **Extensive Testing**: Run full test suite after each change
- **Gradual Rollout**: Implement changes in isolated modules first
- **Rollback Plan**: Git branching strategy for easy rollback
- **Code Review**: Peer review for all significant changes

## Expected Benefits

### Short Term (Phases 1-2)
- Reduced hardcoded values
- Better configuration management
- Improved type safety
- Clearer data structures

### Medium Term (Phases 3-4)
- More maintainable code
- Better error handling
- Easier debugging
- Improved testability

### Long Term (Phase 5)
- Higher test coverage
- Better documentation
- Easier onboarding for new developers
- More robust error recovery

## Implementation Timeline

- **Phase 1**: 1-2 weeks (constants and configuration)
- **Phase 2**: 1-2 weeks (domain models)
- **Phase 3**: 2-3 weeks (function decomposition)
- **Phase 4**: 2-3 weeks (error handling)
- **Phase 5**: 2-3 weeks (testing and documentation)

**Total Estimated Time**: 8-13 weeks

## Success Metrics

- **Code Quality**: Reduced cyclomatic complexity, improved maintainability index
- **Test Coverage**: >80% unit test coverage
- **Bug Reduction**: Fewer runtime errors and configuration issues
- **Development Speed**: Faster implementation of new features
- **Documentation**: Complete API documentation and architecture guides

## Conclusion

This refactoring plan provides a structured approach to improving the osw-builder codebase while minimizing risk. By focusing on incremental changes with clear benefits, we can significantly improve code quality and maintainability without disrupting existing functionality.

The plan prioritizes changes that provide immediate benefits (configuration management, constants) before tackling more complex structural changes. This approach ensures that each phase delivers value while building toward a more robust and maintainable architecture.