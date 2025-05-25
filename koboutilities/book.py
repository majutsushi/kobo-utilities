# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import annotations

__license__ = "GPL v3"
__copyright__ = "2011, Grant Drake <grant.drake@gmail.com>"
__docformat__ = "restructuredtext en"

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from calibre.ebooks.metadata import fmt_sidx
from calibre.ebooks.metadata.book.base import Metadata
from calibre.utils.date import format_date

from .common_utils import debug

if TYPE_CHECKING:
    import datetime as dt

    from calibre.devices.kobo.books import Book


def get_indent_for_index(series_index: Optional[float]) -> int:
    if not series_index:
        return 0
    return len(str(series_index).split(".")[1].rstrip("0"))


class SeriesBook(object):
    series_column = "Series"

    def __init__(self, mi: Book, series_columns: Dict[str, Dict[str, Any]]):
        debug("mi.series_index=", mi.series_index)
        self._orig_mi = Metadata(_("Unknown"), other=mi)
        self._mi = mi
        self._orig_title = mi.title
        self._orig_pubdate = cast("dt.datetime", self._mi.pubdate)
        self._orig_series = cast("Optional[str]", self._mi.kobo_series)
        self.get_series_index()
        self._series_columns = series_columns
        self._assigned_indexes: Dict[str, Optional[float]] = {"Series": None}
        self._series_indents = {
            "Series": get_indent_for_index(cast("float", mi.series_index))
        }
        self._is_valid_index = True
        self._orig_custom_series = {}

        for key in self._series_columns:
            self._orig_custom_series[key] = mi.get_user_metadata(key, True)
            self._series_indents[key] = get_indent_for_index(self.series_index())
            self._assigned_indexes[key] = None

    def get_series_index(self) -> None:
        self._orig_series_index_string = None
        self._series_index_format = None
        try:
            debug("self._mi.kobo_series_number=%s" % self._mi.kobo_series_number)
            self._orig_series_index = (
                float(self._mi.kobo_series_number)
                if self._mi.kobo_series_number is not None
                else None
            )
        except ValueError:
            debug(
                "non numeric series - self._mi.kobo_series_number=%s"
                % self._mi.kobo_series_number
            )
            assert self._mi.kobo_series_number is not None
            numbers = re.findall(r"\d*\.?\d+", self._mi.kobo_series_number)
            if len(numbers) > 0:
                self._orig_series_index = float(numbers[0])
                self._orig_series_index_string = self._mi.kobo_series_number
                self._series_index_format = self._mi.kobo_series_number.replace(
                    numbers[0], "%g", 1
                )
            debug("self._orig_series_index=", self._orig_series_index)

    def revert_changes(self):
        debug("start")
        self._mi.title = self._orig_title
        if hasattr(self._mi, "pubdate"):
            self._mi.pubdate = self._orig_pubdate
        self._mi.series = self._mi.kobo_series
        self._mi.series_index = self._orig_series_index  # pyright: ignore[reportAttributeAccessIssue]

        return

    def id(self) -> Optional[int]:
        if hasattr(self._mi, "id"):
            return cast("int", self._mi.id)
        return None

    def authors(self) -> List[str]:
        return self._mi.authors

    def title(self) -> str:
        return self._mi.title

    def set_title(self, title: str):
        self._mi.title = title

    def is_title_changed(self) -> bool:
        return self._mi.title != self._orig_title

    def pubdate(self) -> Optional[dt.datetime]:
        if hasattr(self._mi, "pubdate"):
            return cast("dt.datetime", self._mi.pubdate)
        return None

    def set_pubdate(self, pubdate: dt.datetime):
        self._mi.pubdate = pubdate

    def is_pubdate_changed(self) -> bool:
        if hasattr(self._mi, "pubdate") and hasattr(self._orig_mi, "pubdate"):
            return self._mi.pubdate != self._orig_pubdate
        return False

    def is_series_changed(self) -> bool:
        if self._mi.series != self._orig_series:
            return True
        return self._mi.series_index != self._orig_series_index

    def orig_series_name(self) -> Optional[str]:
        return self._orig_series

    def orig_series_index(self):
        debug("self._orig_series_index=", self._orig_series_index)
        debug("self._orig_series_index.__class__=", self._orig_series_index.__class__)
        return self._orig_series_index

    def orig_series_index_string(self):
        if self._orig_series_index_string is not None:
            return self._orig_series_index_string

        return fmt_sidx(self._orig_series_index)

    def series_name(self) -> Optional[str]:
        return cast("Optional[str]", self._mi.series)

    def set_series_name(self, series_name: Optional[str]) -> None:
        self._mi.series = series_name

    def series_index(self) -> float:
        return cast("float", self._mi.series_index)

    def series_index_string(self) -> str:
        if self._series_index_format is not None:
            return self._series_index_format % self._mi.series_index
        return fmt_sidx(self._mi.series_index)

    def set_series_index(self, series_index: Optional[float]):
        self._mi.series_index = series_index  # pyright: ignore[reportAttributeAccessIssue]
        self.set_series_indent(get_indent_for_index(series_index))

    def series_indent(self) -> int:
        return self._series_indents[self.series_column]

    def set_series_indent(self, index: int):
        self._series_indents[self.series_column] = index

    def assigned_index(self):
        return self._assigned_indexes[self.series_column]

    def set_assigned_index(self, index: Optional[float]) -> None:
        self._assigned_indexes[self.series_column] = index

    def is_valid(self) -> bool:
        return self._is_valid_index

    def set_is_valid(self, is_valid_index: bool) -> None:
        self._is_valid_index = is_valid_index

    def sort_key(
        self, sort_by_pubdate: bool = False, sort_by_name: bool = False
    ) -> str:
        if sort_by_pubdate:
            pub_date = self.pubdate()
            if pub_date is not None and pub_date.year > 101:
                return format_date(pub_date, "yyyyMMdd")
        else:
            series = self.orig_series_name()
            series_number = (
                self.orig_series_index() if self.orig_series_index() is not None else -1
            )
            debug("series_number=", series_number)
            debug("series_number.__class__=", series_number.__class__)
            if series:
                if sort_by_name:
                    return "%s%06.2f" % (series, series_number)
                return "%06.2f%s" % (series_number, series)
        return ""
