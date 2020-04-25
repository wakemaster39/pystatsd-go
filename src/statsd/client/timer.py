import functools
from time import perf_counter
from types import TracebackType
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterable, Optional, Type

if TYPE_CHECKING:
    from statsd.client.base import StatsClientBase


def safe_wraps(wrapper: Callable, *args: Any, **kwargs: Any) -> Callable:
    """Safely wraps partial functions."""
    while isinstance(wrapper, functools.partial):
        wrapper = wrapper.func
    return functools.wraps(wrapper, *args, **kwargs)


class Timer:
    """A context manager/decorator for statsd.timing()."""

    _start_time: Optional[float]
    ms: Optional[float]

    def __init__(
        self,
        client: "StatsClientBase",
        stat: str,
        rate: float = 1,
        simple_tags: Optional[Iterable[str]] = None,
        kv_tags: Optional[Dict[str, str]] = None,
    ):
        self.client = client
        self.stat = stat
        self.rate = rate
        self.ms = None
        self._sent = False
        self._start_time = None
        self._simple_tags = simple_tags or []
        self._kv_tags = kv_tags or {}

    def __call__(self, f: Callable) -> Callable:
        """Thread-safe timing function decorator."""

        @safe_wraps(f)
        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            start_time = perf_counter()
            try:
                return f(*args, **kwargs)
            finally:
                elapsed_time_ms = 1000.0 * (perf_counter() - start_time)
                self.client.timing(self.stat, elapsed_time_ms, self.rate, self._simple_tags, self._kv_tags)

        return _wrapped  # type: ignore

    def __enter__(self) -> "Timer":
        return self.start()

    def __exit__(
        self, exctype: Optional[Type[BaseException]], excinst: Optional[BaseException], exctb: Optional[TracebackType],
    ) -> Optional[bool]:
        self.stop()
        return None

    def start(self) -> "Timer":
        self.ms = None
        self._sent = False
        self._start_time = perf_counter()
        return self

    def stop(
        self, send: bool = True, simple_tags: Optional[Iterable[str]] = None, kv_tags: Optional[Dict[str, str]] = None,
    ) -> "Timer":
        if self._start_time is None:
            raise RuntimeError("Timer has not started.")
        dt = perf_counter() - self._start_time
        self.ms = 1000.0 * dt  # Convert to milliseconds.
        if send:
            self.send(simple_tags, kv_tags)
        return self

    def send(self, simple_tags: Optional[Iterable[str]], kv_tags: Optional[Dict[str, str]]) -> None:
        if self.ms is None:
            raise RuntimeError("No data recorded.")
        if self._sent:
            raise RuntimeError("Already sent data.")
        self._sent = True
        self.client.timing(self.stat, self.ms, self.rate, simple_tags, kv_tags)
