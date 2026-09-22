from dataclasses import dataclass

from fastapi import Query
from pydantic import BaseModel


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int


@dataclass
class PageParams:
    page: int
    page_size: int
    q: str | None

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    q: str | None = Query(None, max_length=100),
) -> PageParams:
    """Shared `?page=&page_size=&q=` query params. Module routers add their own filters (class_id, ...)."""
    return PageParams(page=page, page_size=page_size, q=(q or "").strip() or None)
