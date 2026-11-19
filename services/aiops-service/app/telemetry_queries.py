def api_requests(service: str, extra: str = "") -> str:
    # Go's ServeMux supplies the method and registered route pattern.
    return f'job="{service}",route=~"[A-Z]+ /api/v1/.*"{extra}'


def positive_ratio(numerator: str, denominator: str, *, missing_numerator_is_zero: bool = False) -> str:
    if missing_numerator_is_zero:
        numerator = f"({numerator} or ({denominator} * 0))"
    # Keep the measured denominator, including rates below one. An idle or
    # missing denominator returns no series, instead of 0/0 or a synthetic zero.
    return f"({numerator} / ({denominator} > 0))"


def with_counter_samples(expression: str, selector: str, window: str) -> str:
    # A newly seen counter cannot establish an increase from a single sample.
    return f"({expression}) and on() (min(count_over_time({selector}[{window}])) >= 2)"
