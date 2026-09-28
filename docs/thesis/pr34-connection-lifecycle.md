# PR #34: connection lifecycle follow-up

## Scope

This follow-up starts from PR #34 at `faadf9f2`. It preserves the native-USB startup order and addresses two review
findings. It does not change watchpoint handling or the separate multi-window trace-merge problem.

## Step 1: restore MSP430 initialization

Moving reset ownership from the serial connection to the debugger instance is necessary because the transport now opens
before STM32's debugger attaches. MSP430 also uses that shared transport, but the PR added the replacement reset only to
STM32. Add an explicit MSP430 reset after attachment and connection initialization.

This restores the startup handshake: opening serial clears buffered input, so firmware must restart to issue a fresh
input request. The connection worker should not own debugger operations.

## Step 2: clean up failed connection startup

Until `init_connection()` returns, its local variable is the only owner able to clean up the new process. Terminate,
join, and close that process if readiness times out, connection establishment reports failure, or the requested reset
raises. Re-raise the original exception; preserve the timeout's `queue.Empty` cause.

Catching `BaseException` here also cleans up on cancellation such as `KeyboardInterrupt`; it does not suppress errors.
Successful initialization transfers ownership to the existing caller without stopping the child.

## Step 3: verify without hardware

Run the small standard-library regression check with Python 3.12 and the project's dependencies installed:

```sh
PYTHONPATH=src python tests/test_connection_lifecycle.py
ruff check src/tracer/connection/sut_connection.py src/tracer/instance/msp430_instance.py tests/test_connection_lifecycle.py
ruff format --check src/tracer/connection/sut_connection.py src/tracer/instance/msp430_instance.py tests/test_connection_lifecycle.py
basedpyright
```

Results:

- Regression checks passed for timeout, reported connection failure, reset failure, cancellation, successful startup,
  and MSP430 reset ordering.
- Both regression checks failed when run against the original PR implementation, confirming they detect these bugs.
- A separate real-process check used `fork` and a simulated 30-second connection delay with a one-second timeout.
  After `TimeoutError`, `multiprocessing.active_children()` was empty.
- Ruff lint and formatting checks passed for the changed Python files. Repository type checking reported no errors.

The checks replace hardware operations with mocks or a simulated connection. Physical STM32/MSP430 compatibility and
complete RP2350 tracing remain unverified by this follow-up. No new research sources were used.
