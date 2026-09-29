# ==========================================
# Retry helper for transient network failures
# (timeouts, connection drops) — the exact
# kind of error that just killed a long
# backtest run partway through.
# ==========================================

import time


def retry_on_network_error(func, *args, max_attempts=4, base_delay=5, **kwargs):
    """
    Calls func(*args, **kwargs). If it raises a network-related
    exception, waits and retries, with the wait time increasing
    each attempt (5s, 10s, 20s...). Re-raises the last error if
    every attempt fails.
    """

    last_error = None

    for attempt in range(1, max_attempts + 1):

        try:
            return func(*args, **kwargs)

        except Exception as e:
            last_error = e
            error_name = type(e).__name__

            is_network_error = any(
                keyword in error_name
                for keyword in ["Timeout", "Connection", "ReadTimeout"]
            ) or any(
                keyword in str(e)
                for keyword in ["timed out", "Connection", "timeout"]
            )

            if not is_network_error:
                raise  # not a network issue — don't retry, fail fast

            if attempt == max_attempts:
                break  # out of retries, fall through to raise below

            delay = base_delay * (2 ** (attempt - 1))

            print(
                f"  ⚠️ Network error ({error_name}), "
                f"retry {attempt}/{max_attempts} in {delay}s..."
            )

            time.sleep(delay)

    raise last_error