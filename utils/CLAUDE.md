# Logging Guidelines

## Log Levels

### DEBUG (default)
- Detailed diagnostic information
- Algorithm state, variable values, execution flow
- Example: `logger.debug("SQL query executed: %s with params: %s", query, params)`

### INFO
- Significant application events
- Service lifecycle, successful operations
- Example: `logger.info("Service started with configuration: %s", config)`

### WARNING
- Potential issues that don't block operations
- Unexpected but handled conditions
- Example: `logger.warning("API rate limit at 80%: %d/%d requests", used, limit)`

### ERROR
- Failed operations that affect specific functions
- Unhandled exceptions, API failures
- Example: `logger.error("Failed to process transaction %s: %s", tx_id, error)`

### CRITICAL
- System-wide failures that prevent core functions
- Data corruption, security breaches
- Example: `logger.critical("Unable to access database after %d attempts", max_retries)`

## Best Practices

- Use string formatting instead of concatenation:
  ```python
  # Good
  logger.debug("Processing item %s", item_id)
  
  # Avoid
  logger.debug("Processing item " + item_id)
  ```

- Include contextual data:
  ```python
  logger.error("Payment failed", extra={"tx_id": tx_id, "amount": amount})
  ```

- Log exceptions with traceback:
  ```python
  try:
      process_data(data)
  except Exception as e:
      logger.exception("Unexpected error processing data")
  ```

- Use appropriate log levels based on operational impact, not development convenience