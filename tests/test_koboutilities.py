# ruff: noqa: INP001, PT009

import os
import sys
import typing
import unittest
from datetime import datetime as dt
from datetime import timedelta, timezone
from pprint import pprint
from queue import Queue
from unittest import mock
from unittest.mock import MagicMock

test_dir = os.path.dirname(os.path.abspath(__file__))
sys.path = [test_dir, *sys.path]

from calibre.utils.logging import default_log  # noqa: E402

if typing.TYPE_CHECKING:
    from .. import config, jobs
    from ..action import KoboUtilitiesAction
else:
    from calibre_plugins.koboutilities import config, jobs
    from calibre_plugins.koboutilities.action import KoboUtilitiesAction


class TestKoboUtilities(unittest.TestCase):
    def setUp(self):
        self.plugin = KoboUtilitiesAction(None, None)
        self.plugin.log = default_log
        self.queue = Queue()

    @mock.patch.object(jobs, "device_database_connection")
    def test_store_bookmarks(self, conn: MagicMock):
        #     (
        #         book.calibre_id,
        #         book.contentIDs,
        #         title,
        #         authors,
        #         current_chapterid,
        #         current_percentRead,
        #         current_rating,
        #         current_last_read,
        #     )
        books_in_calibre = [
            (
                "1",
                ["a.kepub.epub"],
                "Title 1",
                ["Author 1"],
                1,
                50,
                0,
                dt(2000, 1, 2, 12, 34, 56, tzinfo=timezone(timedelta(hours=0))),
            ),
            (
                "2",
                ["b.kepub.epub"],
                "Title 2",
                ["Author 2"],
                2,
                25,
                1,
                dt(2000, 1, 2, 12, 34, 56, tzinfo=timezone(timedelta(hours=0))),
            ),
        ]
        cursor = conn.return_value.__enter__.return_value.cursor.return_value
        books_on_kobo = [
            {
                "ChapterIDBookmarked": 1,
                "adobe_location": None,
                "ReadStatus": 1,
                "___PercentRead": 90,
                "Attribution": None,
                "DateLastRead": "2000-01-02T12:34:56Z",
                "Title": "Title 1",
                "MimeType": "foo/bar",
                "Rating": 1,
                "contentId": "a.kepub.epub",
            },
            {
                "ChapterIDBookmarked": 2,
                "adobe_location": None,
                "ReadStatus": 1,
                "___PercentRead": 75,
                "Attribution": None,
                "DateLastRead": "2001-01-02T12:34:56Z",
                "Title": "Title 2",
                "MimeType": "foo/bar",
                "Rating": 2,
                "contentId": "b.kepub.epub",
            },
        ]
        cursor.__next__ = MagicMock(side_effect=books_on_kobo)
        cfg = {
            config.KEY_CLEAR_IF_UNREAD: False,
            config.KEY_STORE_IF_MORE_RECENT: True,
            config.KEY_DO_NOT_STORE_IF_REOPENED: True,
            config.KEY_CURRENT_LOCATION_CUSTOM_COLUMN: None,
            config.KEY_PERCENT_READ_CUSTOM_COLUMN: "#percent_read",
            config.KEY_RATING_CUSTOM_COLUMN: None,
            config.KEY_LAST_READ_CUSTOM_COLUMN: "#last_read",
            "epub_location_like_kepub": True,
            "fetch_queries": {"kepub": "kepub_query", "epub": "epub_query"},
            "device_database_path": "db_path",
        }

        stored_locations = jobs._store_bookmarks(None, books_in_calibre, cfg)
        pprint(stored_locations)
        conn.assert_called_with("db_path", use_row_factory=True)
        cursor.execute.assert_called_with("kepub_query", ("b.kepub.epub",))
        self.assertNotIn("1", stored_locations)
        self.assertEqual(stored_locations["2"]["___PercentRead"], 75)


if __name__ == "__main__":
    unittest.main(module="test_koboutilities", verbosity=2)
