from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar, Union

if TYPE_CHECKING:
    from .errors import ForgeError

T = TypeVar("T")


@dataclass(frozen=True)
class Success[T]:
    value: T

    @property
    def is_ok(self) -> bool:
        return True

    @property
    def is_err(self) -> bool:
        return False


@dataclass(frozen=True)
class Failure:
    error: ForgeError

    @property
    def is_ok(self) -> bool:
        return False

    @property
    def is_err(self) -> bool:
        return True


Result = Union[Success[T], Failure]


def ok[T](value: T) -> Success[T]:
    return Success(value=value)


def err(error: ForgeError) -> Failure:
    return Failure(error=error)
