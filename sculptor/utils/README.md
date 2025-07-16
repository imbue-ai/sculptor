# Sentry Exception Priority Management in Sculptor

This document explains how exception priorities are handled in Sculptor's Sentry integration, specifically focusing on the interaction between Loguru logging, monkey-patched exception handling, and Sentry error reporting.

## Overview

Sculptor uses a custom logging system that integrates Loguru with Sentry to provide prioritized exception reporting. The system allows for fine-grained control over which exceptions are sent to Sentry and at what priority level.

## Exception Priority Levels

Exception priorities are defined in `imbue_core/imbue_core/constants.py:13-19`:

```python
class ExceptionPriority(StrEnum):
    HIGH_PRIORITY = "HIGH_PRIORITY"     # App-crashing issues
    MEDIUM_PRIORITY = "MEDIUM_PRIORITY" # Major functionality failures
    LOW_PRIORITY = "LOW_PRIORITY"       # Retriable exceptions
```

These map to Loguru levels with specific numeric values:
- `LOW_PRIORITY`: Level 37
- `MEDIUM_PRIORITY`: Level 38
- `HIGH_PRIORITY`: Level 39

## Key Components

### 1. Sentry-Loguru Handler (`imbue_core/imbue_core/sentry_loguru_handler.py:47-58`)

The `SentryLoguruLoggingLevels` enum maps Loguru levels to Sentry priorities:
- Standard levels: TRACE(5), DEBUG(10), INFO(20), SUCCESS(25), WARNING(30), ERROR(40), CRITICAL(50)
- Custom priority levels: LOW_PRIORITY(37), MEDIUM_PRIORITY(38), HIGH_PRIORITY(39)

### 2. Monkey-Patched Exception Logging (`imbue_core/imbue_core/async_monkey_patches.py:381-387`)

The `log_exception` function in async monkey patches handles exception reporting:
- If a priority is specified, uses that priority's level value
- If no priority is specified, defaults to "ERROR" level
- Logs exceptions through Loguru, which then routes to Sentry

### 3. Logger Setup (`sculptor/sculptor/utils/logs.py:61-70`)

Custom priority levels are registered with Loguru during logger initialization:
- `LOW_PRIORITY`: Yellow color, level 37
- `MEDIUM_PRIORITY`: Orange color, level 38
- `HIGH_PRIORITY`: Red color, level 39

## Example: LLMAPIError Handling

In `sculptor/sculptor/tasks/handlers/run_agent/setup.py:490`, LLMAPIError exceptions are caught and logged with LOW_PRIORITY:

```python
except Exception as e:
    log_exception(e, "Failed to generate title and branch name", priority=ExceptionPriority.LOW_PRIORITY)
```

This results in:
1. Exception logged at Loguru level 37 (LOW_PRIORITY)
2. Sent to Sentry as INFO level (based on SentryLoguruLoggingLevels mapping)
3. Appears in Sentry with lower urgency than ERROR or CRITICAL exceptions

## Adjusting Exception Priorities

To modify how exceptions are reported to Sentry:

1. **Change exception priority**: Use different `ExceptionPriority` values when calling `log_exception()`
2. **Modify level mapping**: Update `SentryLoguruLoggingLevels` enum in sentry_loguru_handler.py
3. **Add custom levels**: Define new priority levels in constants.py and register them in logs.py

## Best Practices

- Use `HIGH_PRIORITY` for exceptions that crash the application
- Use `MEDIUM_PRIORITY` for exceptions that break major functionality
- Use `LOW_PRIORITY` for retriable exceptions or expected failure scenarios
- When in doubt, specify a priority explicitly rather than relying on the default ERROR level
