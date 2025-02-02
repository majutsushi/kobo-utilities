# ruff: noqa: INP001, PT009

import dataclasses
import os
import sys
import unittest
import uuid
from contextlib import ExitStack
from datetime import datetime as dt
from datetime import timedelta, timezone
from enum import Enum
from pathlib import Path
from pprint import pprint
from queue import Queue
from typing import TYPE_CHECKING, ClassVar, List, Optional
from unittest import mock
from unittest.mock import MagicMock

import apsw  # type: ignore
from calibre.devices.kobo.books import Book
from calibre.devices.kobo.driver import KOBOTOUCH
from calibre.ebooks.metadata import MetaInformation
from calibre.utils.logging import default_log

test_dir = os.path.dirname(os.path.abspath(__file__))
sys.path = [test_dir, *sys.path]

if TYPE_CHECKING:
    from .. import config, jobs
    from ..action import KoboUtilitiesAction
else:
    from calibre_plugins.koboutilities import config, jobs
    from calibre_plugins.koboutilities.action import KoboUtilitiesAction

TIMESTAMP_STRING = KOBOTOUCH.TIMESTAMP_STRING


class ReadStatus(Enum):
    UNREAD = 0
    READING = 1
    FINISHED = 2


@dataclasses.dataclass
class TestBook:
    title: str
    authors: List[str]
    rating: int
    chapter_id: Optional[str]
    read_status: ReadStatus
    percent_read: int
    last_read: Optional[dt]
    time_spent_reading: int
    rest_of_book_estimate: int
    is_kepub: bool
    contentID: str = dataclasses.field(init=False)
    mime_type: str = dataclasses.field(init=False)
    calibre_id: int = dataclasses.field(init=False)
    _next_calibre_id: ClassVar[int] = 1

    def __post_init__(self):
        self.contentID = uuid.uuid4().hex
        self.mime_type = (
            "application/x-kobo-epub+zip" if self.is_kepub else "application/epub+zip"
        )
        self.calibre_id = TestBook._next_calibre_id
        TestBook._next_calibre_id += 1

    def to_calibre_book(self) -> Book:
        mi = MetaInformation(self.title, self.authors)
        book = Book("", "lpath", title=mi.title, other=mi)
        book.calibre_id = self.calibre_id
        book.contentIDs = [self.contentID]
        book.rating = self.rating
        book.set_all_user_metadata(
            {
                "#chapter_id": {"datatype": "text", "#value#": self.chapter_id},
                "#percent_read": {"datatype": "int", "#value#": self.percent_read},
                "#last_read": {"datatype": "datetime", "#value#": self.last_read},
            }
        )

        return book


@mock.patch.object(
    KoboUtilitiesAction,
    "device_fwversion",
    new_callable=mock.PropertyMock,
    return_value=(4, 41, 23145),
)
@mock.patch.object(
    KoboUtilitiesAction,
    "device_timestamp_string",
    new_callable=mock.PropertyMock,
    return_value=TIMESTAMP_STRING,
)
class TestKoboUtilities(unittest.TestCase):
    def setUp(self):
        self.plugin = KoboUtilitiesAction(None, None)
        self.plugin.supports_ratings = True
        self.plugin.epub_location_like_kepub = True
        self.plugin.log = default_log
        self.queue = Queue()

    @mock.patch.object(jobs, "device_database_connection")
    def test_store_bookmarks(self, conn: MagicMock, _fwversion, _timestamp):
        #     (
        #         book.calibre_id,
        #         book.contentIDs,
        #         title,
        #         authors,
        #         current_chapterid,
        #         current_percentRead,
        #         current_rating,
        #         current_last_read,
        #         current_time_spent_reading,
        #         current_rest_of_book_estimate,
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
                100,
                200,
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
                300,
                400,
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
                "TimeSpentReading": 100,
                "RestOfBookEstimate": 200,
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
                "TimeSpentReading": 450,
                "RestOfBookEstimate": 250,
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
            config.KEY_TIME_SPENT_READING_COLUMN: "#time_spent_reading",
            config.KEY_REST_OF_BOOK_ESTIMATE_COLUMN: "#rest_of_book_estimate",
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
        self.assertEqual(stored_locations["2"]["TimeSpentReading"], 450)
        self.assertEqual(stored_locations["2"]["RestOfBookEstimate"], 250)

    def test_restore_current_bookmark(self, _fwversion, _timestamp):
        book1 = TestBook(
            title="Title A",
            authors=["Author A"],
            rating=3,
            chapter_id=None,
            read_status=ReadStatus.UNREAD,
            percent_read=0,
            last_read=None,
            time_spent_reading=0,
            rest_of_book_estimate=0,
            is_kepub=True,
        )
        book2 = TestBook(
            title="Title B",
            authors=["Author B"],
            rating=5,
            chapter_id="chapter3",
            read_status=ReadStatus.READING,
            percent_read=10,
            last_read=dt(2001, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=0))),
            time_spent_reading=100,
            rest_of_book_estimate=200,
            is_kepub=True,
        )
        books = [book1, book2]

        plugin = self.plugin
        plugin.options = {
            "profileName": None,
            config.KEY_READING_STATUS: True,  # TODO
            config.KEY_DATE_TO_NOW: False,
            config.KEY_SET_RATING: True,
        }

        column_names = (
            "#chapter_id",
            "#percent_read",
            "rating",
            "#last_read",
            "#time_spent_reading",
            "#rest_of_book_estimate",
        )

        sync_time = dt(
            2002, 9, 9, 12, 0, 0, tzinfo=timezone(timedelta(hours=0))
        ).strftime(TIMESTAMP_STRING)
        schema = Path(test_dir, "kobo-schema.sql").read_text()
        db_conn = apsw.Connection(":memory:")
        db_conn.setrowtrace(row_factory)
        cursor = db_conn.cursor()
        cursor.execute(schema)
        for book in books:
            cursor.execute(
                """
                    INSERT INTO content (
                        ContentID,
                        ContentType,
                        MimeType,
                        ___SyncTime,
                        ___UserID,
                        Title,
                        ChapterIDBookmarked,
                        ReadStatus,
                        ___PercentRead,
                        DateLastRead,
                        TimeSpentReading,
                        RestOfBookEstimate
                    ) VALUES (
                        :contentID,
                        :content_type,
                        :mime_type,
                        :sync_time,
                        :user_id,
                        :title,
                        :chapter_id,
                        :read_status,
                        :percent_read,
                        :last_read,
                        :time_spent_reading,
                        :rest_of_book_estimate
                    )
                """,
                {
                    **dataclasses.asdict(book),
                    "content_type": "6",
                    "sync_time": sync_time,
                    "user_id": "",
                    "read_status": book.read_status.value,
                    "last_read": book.last_read.strftime(TIMESTAMP_STRING)
                    if book.last_read is not None
                    else None,
                },
            )
            cursor.execute(
                "INSERT INTO ratings (ContentID, Rating, DateModified) VALUES (?, ?, ?)",
                (
                    book.contentID,
                    book.rating,
                    dt(
                        2002, 1, 1, 12, 0, 0, tzinfo=timezone(timedelta(hours=0))
                    ).strftime(TIMESTAMP_STRING),
                ),
            )

        test_query = """
            SELECT content.*, ratings.Rating FROM content
            LEFT OUTER JOIN ratings ON content.ContentID = ratings.ContentID
        """
        db_books_before = {
            book["ContentID"]: book for book in cursor.execute(test_query).fetchall()
        }

        # Simulate changing the books in Calibre
        book1.rating = 4
        book1.chapter_id = "chapter2"
        book1.read_status = ReadStatus.READING
        book1.percent_read = 20
        book1.last_read = dt(2001, 1, 15, 12, 0, 0, tzinfo=timezone(timedelta(hours=0)))
        book1.time_spent_reading = 111
        book1.rest_of_book_estimate = 333
        book2.rating = 2
        book2.chapter_id = "chapter5"
        book2.read_status = ReadStatus.FINISHED
        book2.percent_read = 100
        book2.last_read = dt(2001, 2, 27, 12, 0, 0, tzinfo=timezone(timedelta(hours=0)))
        book2.time_spent_reading = 555
        book2.rest_of_book_estimate = 0

        # Update expected DB values
        db_book1 = db_books_before[book1.contentID]
        db_book1["ChapterIDBookmarked"] = book1.chapter_id
        db_book1["ReadStatus"] = book1.read_status.value
        db_book1["___PercentRead"] = book1.percent_read
        db_book1["DateLastRead"] = book1.last_read.strftime(TIMESTAMP_STRING)
        db_book1["___SyncTime"] = book1.last_read.strftime(TIMESTAMP_STRING)
        db_book1["FirstTimeReading"] = "false"
        db_book1["Rating"] = int(book1.rating / 2)
        db_book2 = db_books_before[book2.contentID]
        db_book2["ChapterIDBookmarked"] = book2.chapter_id
        db_book2["ReadStatus"] = book2.read_status.value
        db_book2["___PercentRead"] = book2.percent_read
        db_book2["DateLastRead"] = book2.last_read.strftime(TIMESTAMP_STRING)
        db_book2["___SyncTime"] = book2.last_read.strftime(TIMESTAMP_STRING)
        db_book2["Rating"] = int(book2.rating / 2)
        db_book2["FirstTimeReading"] = "false"

        with ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(plugin, "get_column_names", return_value=column_names)
            )
            stack.enter_context(
                mock.patch.object(
                    plugin, "device_database_connection", return_value=db_conn
                )
            )
            plugin._restore_current_bookmark([book.to_calibre_book() for book in books])

        db_books_after = {
            book["ContentID"]: book for book in cursor.execute(test_query).fetchall()
        }
        self.maxDiff = None
        self.assertDictEqual(db_books_before, db_books_after)


def row_factory(cursor, row):
    return {k[0]: row[i] for i, k in enumerate(cursor.getdescription())}


if __name__ == "__main__":
    unittest.main(module="test_koboutilities", verbosity=2)
