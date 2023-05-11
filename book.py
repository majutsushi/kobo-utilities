#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2011, Grant Drake <grant.drake@gmail.com>'
__docformat__ = 'restructuredtext en'

import re
from calibre.utils.date import format_date
from calibre.ebooks.metadata import fmt_sidx
from calibre.ebooks.metadata.book.base import Metadata
from calibre_plugins.koboutilities.common_utils import debug_print

def get_indent_for_index(series_index):
    if not series_index:
        return 0
    return len(str(series_index).split('.')[1].rstrip('0'))

class SeriesBook(object):
    series_column = 'Series'


    def __init__(self, mi, series_columns):
        debug_print("SeriesBook:__init__ - mi.series_index=", mi.series_index)
        self._orig_mi      = Metadata(_('Unknown'), other=mi)
        self._mi           = mi
        self._orig_title   = mi.title
        self._orig_pubdate = self._mi.pubdate
        self._orig_series  = self._mi.kobo_series
        self.get_series_index()
        self._series_columns     = series_columns
        self._assigned_indexes   = { 'Series': None }
        self._series_indents     = { 'Series': get_indent_for_index(mi.series_index) }
        self._is_valid_index     = True
        self._orig_custom_series = {}

        for key in self._series_columns:
            self._orig_custom_series[key] = mi.get_user_metadata(key, True)
            self._series_indents[key] = get_indent_for_index(self.series_index())
            self._assigned_indexes[key] = None

    def get_series_index(self):
        self._orig_series_index_string = None
        self._series_index_format      = None
        try:
            debug_print("SeriesBook:get_series_index - self._mi.kobo_series_number=%s" % self._mi.kobo_series_number)
            self._orig_series_index = float(self._mi.kobo_series_number) if self._mi.kobo_series_number is not None else None
        except:
            debug_print("SeriesBook:get_series_index - non numeric series - self._mi.kobo_series_number=%s" % self._mi.kobo_series_number)
            numbers = re.findall(r"\d*\.?\d+", self._mi.kobo_series_number)
            if len(numbers) > 0:
                self._orig_series_index        = float(numbers[0])
                self._orig_series_index_string = self._mi.kobo_series_number
                self._series_index_format      = self._mi.kobo_series_number.replace(numbers[0], "%g", 1)
#            self._orig_series_index = re.findall(r"\d*", self._mi.kobo_series_number)
            debug_print("SeriesBook:get_series_index - self._orig_series_index=", self._orig_series_index)

    def get_mi_to_persist(self):
        # self._mi will be potentially polluted with changes applied to multiple series columns
        # Instead return a Metadata object with only changes relevant to the last series column selected.
        debug_print("SeriesBook:get_mi_to_persist")
        self._orig_title = self._mi.title
        if hasattr(self._mi, 'pubdate'):
            self._orig_pubdate = self._mi.pubdate
        self._orig_series = self._mi.series
        self._orig_series_index = self._mi.series_index

        return self._orig_mi

    def revert_changes(self):
        debug_print("SeriesBook:revert_changes")
        self._mi.title = self._orig_title
        if hasattr(self._mi, 'pubdate'):
            self._mi.pubdate = self._orig_pubdate
        self._mi.series = self._mi.kobo_series
        self._mi.series_index = self._orig_series_index

        return


    def id(self):
        if hasattr(self._mi, 'id'):
            return self._mi.id

    def authors(self):
        return self._mi.authors

    def title(self):
        return self._mi.title

    def set_title(self, title):
        self._mi.title = title

    def is_title_changed(self):
        return self._mi.title != self._orig_title

    def pubdate(self):
        if hasattr(self._mi, 'pubdate'):
            return self._mi.pubdate

    def set_pubdate(self, pubdate):
        self._mi.pubdate = pubdate

    def is_pubdate_changed(self):
        if hasattr(self._mi, 'pubdate') and hasattr(self._orig_mi, 'pubdate'):
            return self._mi.pubdate != self._orig_pubdate
        return False

    def is_series_changed(self):
        if self._mi.series != self._orig_series:
            return True
        if self._mi.series_index != self._orig_series_index:
            return True
        
        return False

    def orig_series_name(self):
        return self._orig_series

    def orig_series_index(self):
        debug_print("SeriesBook:orig_series_index - self._orig_series_index=", self._orig_series_index)
        debug_print("SeriesBook:orig_series_index - self._orig_series_index.__class__=", self._orig_series_index.__class__)
        return self._orig_series_index

    def orig_series_index_string(self):
#        debug_print("SeriesBook:orig_series_index - self._orig_series_index=", self._orig_series_index)
#        debug_print("SeriesBook:orig_series_index - self._orig_series_index.__class__=", self._orig_series_index.__class__)
        if self._orig_series_index_string is not None:
            return self._orig_series_index_string
        
        return fmt_sidx(self._orig_series_index)

    def series_name(self):
        return self._mi.series

    def set_series_name(self, series_name):
        self._mi.series = series_name

    def series_index(self):
        return self._mi.series_index

    def series_index_string(self, column=None):
        if self._series_index_format is not None:
            return self._series_index_format % self._mi.series_index
        return fmt_sidx(self._mi.series_index)

    def set_series_index(self, series_index):
        self._mi.series_index = series_index
        self.set_series_indent(get_indent_for_index(series_index))

    def series_indent(self):
        return self._series_indents[self.series_column]

    def set_series_indent(self, index):
        self._series_indents[self.series_column] = index

    def assigned_index(self):
        return self._assigned_indexes[self.series_column]

    def set_assigned_index(self, index):
        self._assigned_indexes[self.series_column] = index

    def is_valid(self):
        return self._is_valid_index

    def set_is_valid(self, is_valid_index):
        self._is_valid_index = is_valid_index

    def sort_key(self, sort_by_pubdate=False, sort_by_name=False):
        if sort_by_pubdate:
            pub_date = self.pubdate()
            if pub_date is not None and pub_date.year > 101:
                return format_date(pub_date, 'yyyyMMdd')
        else:
            series = self.orig_series_name()
            series_number = self.orig_series_index() if self.orig_series_index() is not None else -1
            debug_print("sort_key - series_number=", series_number)
            debug_print("sort_key - series_number.__class__=", series_number.__class__)
            if series:
                if sort_by_name:
                    return '%s%06.2f'% (series, series_number)
                else:
                    return '%06.2f%s'% (series_number, series)
        return ''

