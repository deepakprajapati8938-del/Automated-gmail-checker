from collections import Counter

_counters: Counter[str] = Counter()

def increment(name: str, by: int = 1) -> None:
    _counters[name] += by

def snapshot() -> dict[str, int]:
    return dict(_counters)
