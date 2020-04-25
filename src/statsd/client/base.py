import random
from collections import deque
from datetime import timedelta
from itertools import chain
from types import TracebackType
from typing import Dict, Iterable, Optional, Sequence, Type, Union

from .timer import Timer


class StatsClientBase:
    _prefix: Optional[str]
    _simple_tags: Sequence[str]
    _kv_tags: Dict[str, str]
    _maxudpsize: int

    """A Base class for various statsd clients."""

    def _send(self, data: str) -> None:
        raise NotImplementedError()

    def pipeline(self) -> "PipelineBase":
        raise NotImplementedError()

    def timer(
        self,
        stat: str,
        rate: float = 1,
        simple_tags: Optional[Iterable[str]] = None,
        kv_tags: Optional[Dict[str, str]] = None,
    ) -> Timer:
        return Timer(self, stat, rate, simple_tags, kv_tags)

    def timing(
        self,
        stat: str,
        delta: Union[timedelta, float],
        rate: float = 1,
        simple_tags: Optional[Iterable[str]] = None,
        kv_tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Send new timing information.

        `delta` can be either a number of milliseconds or a timedelta.
        """
        if isinstance(delta, timedelta):
            # Convert timedelta to number of milliseconds.
            delta = delta.total_seconds() * 1000.0
        self._send_stat(stat, f"{delta}|ms", rate, simple_tags, kv_tags)

    def incr(
        self,
        stat: str,
        count: int = 1,
        rate: float = 1,
        simple_tags: Optional[Iterable[str]] = None,
        kv_tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Increment a stat by `count`."""
        self._send_stat(stat, f"{count}|c", rate, simple_tags, kv_tags)

    def decr(
        self,
        stat: str,
        count: int = 1,
        rate: float = 1,
        simple_tags: Optional[Iterable[str]] = None,
        kv_tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Decrement a stat by `count`."""
        self.incr(stat, -count, rate, simple_tags, kv_tags)

    def gauge(
        self,
        stat: str,
        value: int,
        rate: float = 1,
        delta: bool = False,
        simple_tags: Optional[Iterable[str]] = None,
        kv_tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set a gauge value."""
        if value < 0 and not delta:
            if rate < 1:
                if random.random() > rate:
                    return
            with self.pipeline() as pipe:
                pipe._send_stat(stat, "0|g", 1, simple_tags, kv_tags)
                pipe._send_stat(stat, f"{value}|g", 1, simple_tags, kv_tags)
        else:
            prefix = "+" if delta and value >= 0 else ""
            self._send_stat(stat, f"{prefix}{value}|g", rate, simple_tags, kv_tags)

    def set(
        self,
        stat: str,
        value: int,
        rate: float = 1,
        simple_tags: Optional[Iterable[str]] = None,
        kv_tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Set a set value."""
        self._send_stat(stat, f"{value}|s", rate, simple_tags, kv_tags)

    def _send_stat(
        self,
        stat: str,
        value: str,
        rate: float,
        simple_tags: Optional[Iterable[str]],
        kv_tags: Optional[Dict[str, str]],
    ) -> None:
        self._after(self._prepare(stat, value, rate), simple_tags, kv_tags)

    def _prepare(self, stat: str, value: str, rate: float) -> Optional[str]:
        if rate < 1:
            if random.random() > rate:
                return None
            value = f"{value}|@{rate}"

        if self._prefix:
            stat = f"{self._prefix}.{stat}"

        return f"{stat}:{value}"

    def _after(
        self, data: Optional[str], simple_tags: Optional[Iterable[str]], kv_tags: Optional[Dict[str, str]],
    ) -> None:
        if data:
            self._send(data + self._build_tags_suffix(simple_tags, kv_tags))

    def _build_tags_suffix(self, simple_tags: Optional[Iterable[str]], kv_tags: Optional[Dict[str, str]]) -> str:
        stags = ",".join(set(chain((simple_tags or []), self._simple_tags)))

        kv_tags = kv_tags or {}
        for k, v in self._kv_tags.items():
            kv_tags.setdefault(k, v)

        kvtags = ",".join(f"{k}:{v}" for k, v in kv_tags.items())
        tags = ",".join(x for x in (stags, kvtags) if x)

        return f"|#{tags}" if tags else ""


class PipelineBase(StatsClientBase):
    _stats: deque

    def __init__(self, client: StatsClientBase):
        self._client = client
        self._prefix = client._prefix
        self._simple_tags = client._simple_tags
        self._kv_tags = client._kv_tags
        self._stats = deque()

    def _send(self, data: str = "") -> None:
        raise NotImplementedError()

    def _after(
        self, data: Optional[str], simple_tags: Optional[Iterable[str]], kv_tags: Optional[Dict[str, str]],
    ) -> None:
        if data is not None:
            self._stats.append(data + self._build_tags_suffix(simple_tags, kv_tags))

    def __enter__(self) -> "PipelineBase":
        return self

    def __exit__(
        self, exctype: Optional[Type[BaseException]], excinst: Optional[BaseException], exctb: Optional[TracebackType],
    ) -> Optional[bool]:
        self.send()
        return None

    def send(self) -> None:
        if not self._stats:
            return
        self._send()

    def pipeline(self) -> "PipelineBase":
        return self.__class__(self)
