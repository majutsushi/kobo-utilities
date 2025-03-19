# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import annotations

__license__ = "GPL v3"
__copyright__ = "2012-2017, David Forrester <davidfor@internode.on.net>"
__docformat__ = "restructuredtext en"

import os
import re
import shutil
import time
from datetime import datetime

from calibre import prints
from calibre.constants import DEBUG
from calibre.ebooks.BeautifulSoup import BeautifulStoneSoup
from calibre.utils.ipc.job import ParallelJob
from calibre.utils.ipc.server import Server
from calibre.utils.logging import Log
from calibre.utils.zipfile import ZipFile

from . import config as cfg
from .common_utils import (
    BOOKMARK_SEPARATOR,
    MIMETYPE_KOBO,
    DeviceDatabaseConnection,
    check_device_database,
    convert_kobo_date,
)

# TODO: Sort out the logging
logger = Log()  # logging.getLogger(__name__)
JOBS_DEBUG = True
BASE_TIME = time.time()


def debug_print(*args):
    if cfg.DEBUG or JOBS_DEBUG or DEBUG:  # or True:
        prints("DEBUG: %6.1f" % (time.time() - BASE_TIME), *args)


def do_device_database_backup(backup_options):
    logger = Log()
    debug_print("do_device_database_backup - start")
    logger("logger - do_device_database_backup - start")

    def backup_file(backup_zip, file_to_add, basename=None):
        debug_print(
            "do_device_database_backup:backup_file - file_to_add=%s" % file_to_add
        )
        basename = basename if basename else os.path.basename(file_to_add)
        try:
            backup_zip.write(file_to_add, basename)
        except Exception as e:
            debug_print(
                "do_device_database_backup:backup_file - file '%s' not added. Exception was: %s"
                % (file_to_add, e)
            )

    debug_print("do_device_database_backup - backup_options=", backup_options)
    device_name = backup_options["device_name"]
    serial_number = backup_options["serial_number"]
    backup_file_template = backup_options["backup_file_template"]
    dest_dir = backup_options[cfg.KEY_BACKUP_DEST_DIRECTORY]
    copies_to_keep = backup_options[cfg.KEY_BACKUP_COPIES_TO_KEEP]
    do_daily_backup = backup_options[cfg.KEY_DO_DAILY_BACKUP]
    zip_database = backup_options[cfg.KEY_BACKUP_ZIP_DATABASE]
    database_file = backup_options["database_file"]
    device_path = backup_options["device_path"]
    debug_print("do_device_database_backup - copies_to_keep=", copies_to_keep)

    bookreader_backup_file_template = "BookReader-{0}-{1}-{2}"
    bookreader_database_file = os.path.join(
        backup_options["device_path"], ".kobo", "BookReader.sqlite"
    )

    now = datetime.now()  # noqa: DTZ005
    backup_timestamp = now.strftime("%Y%m%d-%H%M%S")
    import glob

    if do_daily_backup:
        backup_file_search = (
            now.strftime(
                backup_file_template.format(
                    device_name, serial_number, "%Y%m%d-" + "[0-9]" * 6
                )
            )
            + ".sqlite"
        )
        backup_file_search = (
            now.strftime(
                backup_file_template.format(
                    device_name, serial_number, "%Y%m%d-" + "[0-9]" * 6
                )
            )
            + ".*"
        )
        debug_print(
            "do_device_database_backup - backup_file_search=", backup_file_search
        )
        backup_file_search = os.path.join(dest_dir, backup_file_search)
        debug_print(
            "do_device_database_backup - backup_file_search=", backup_file_search
        )
        backup_files = glob.glob(backup_file_search)
        debug_print("do_device_database_backup - backup_files=", backup_files)

        if len(backup_files) > 0:
            debug_print("auto_backup_device_database - Backup already done today")
            return

    backup_file_name = backup_file_template.format(
        device_name, serial_number, backup_timestamp
    )
    backup_file_path = os.path.join(dest_dir, backup_file_name + ".sqlite")
    debug_print("do_device_database_backup - backup_file_name=%s" % backup_file_name)
    debug_print("do_device_database_backup - backup_file_path=%s" % backup_file_path)
    debug_print("do_device_database_backup - database_file=%s" % database_file)
    shutil.copyfile(database_file, backup_file_path)

    bookreader_backup_file_path = None
    try:
        bookreader_backup_file_name = bookreader_backup_file_template.format(
            device_name, serial_number, backup_timestamp
        )
        bookreader_backup_file_path = os.path.join(
            dest_dir, bookreader_backup_file_name + ".sqlite"
        )
        debug_print(
            "do_device_database_backup - bookreader_backup_file_name=%s"
            % bookreader_backup_file_name
        )
        debug_print(
            "do_device_database_backup - bookreader_backup_file_path=%s"
            % bookreader_backup_file_path
        )
        debug_print(
            "do_device_database_backup - bookreader_database_file=%s"
            % bookreader_database_file
        )
        shutil.copyfile(bookreader_database_file, bookreader_backup_file_path)
    except Exception as e:
        debug_print(
            "do_device_database_backup - backup of database BookReader.sqlite failed. Exception: {0}".format(
                e
            )
        )

    try:
        check_result = check_device_database(backup_file_path)
        if check_result.split()[0] != "ok":
            debug_print("do_device_database_backup - database is corrupt!")
            raise Exception(check_result)
    except:
        debug_print("do_device_database_backup - backup is corrupt - renaming file.")
        filename = os.path.basename(backup_file_path)
        filename, fileext = os.path.splitext(filename)
        corrupt_filename = filename + "_CORRUPT" + fileext
        corrupt_file_path = os.path.join(dest_dir, corrupt_filename)
        debug_print("do_device_database_backup - backup_file_name=%s" % database_file)
        debug_print(
            "do_device_database_backup - corrupt_file_path=%s" % corrupt_file_path
        )
        os.rename(backup_file_path, corrupt_file_path)
        raise

    # Create the zip file archive
    config_backup_path = os.path.join(dest_dir, backup_file_name + ".zip")
    debug_print(
        "do_device_database_backup - config_backup_path=%s" % config_backup_path
    )
    with ZipFile(config_backup_path, "w") as config_backup_zip:
        config_file = os.path.join(device_path, ".kobo", "Kobo", "Kobo eReader.conf")
        backup_file(config_backup_zip, config_file)

        version_file = os.path.join(device_path, ".kobo", "version")
        backup_file(config_backup_zip, version_file)

        affiliate_file = os.path.join(device_path, ".kobo", "affiliate.conf")
        backup_file(config_backup_zip, affiliate_file)

        ade_file = os.path.join(device_path, ".adobe-digital-editions")
        backup_file(config_backup_zip, ade_file)

        for root, _dirs, files in os.walk(ade_file):
            for fn in files:
                absfn = os.path.join(root, fn)
                zfn = os.path.relpath(absfn, device_path).replace(os.sep, "/")
                backup_file(config_backup_zip, absfn, basename=zfn)

        if zip_database:
            debug_print(
                "do_device_database_backup - adding database KoboReader to zip file=%s"
                % backup_file_path
            )
            backup_file(
                config_backup_zip, backup_file_path, basename="KoboReader.sqlite"
            )
            os.unlink(backup_file_path)

            if bookreader_backup_file_path is not None:
                debug_print(
                    "do_device_database_backup - adding database BookReader to zip file=%s"
                    % bookreader_backup_file_path
                )
                backup_file(
                    config_backup_zip,
                    bookreader_backup_file_path,
                    basename="BookReader.sqlite",
                )
                os.unlink(bookreader_backup_file_path)

    if copies_to_keep > 0:
        debug_print("do_device_database_backup - copies to keep:%s" % copies_to_keep)

        timestamp_filter = "{0}-{1}".format("[0-9]" * 8, "[0-9]" * 6)
        backup_file_search = backup_file_template.format(
            device_name, serial_number, timestamp_filter
        )
        debug_print(
            "do_device_database_backup - backup_file_search=", backup_file_search
        )
        db_backup_file_search = os.path.join(dest_dir, backup_file_search + ".sqlite")
        debug_print(
            "do_device_database_backup - db_backup_file_search=", db_backup_file_search
        )
        backup_files = glob.glob(db_backup_file_search)
        debug_print("do_device_database_backup - backup_files=", backup_files)
        debug_print(
            "do_device_database_backup - backup_files=",
            backup_files[: len(backup_files) - copies_to_keep],
        )
        debug_print(
            "do_device_database_backup - len(backup_files) - copies_to_keep=",
            len(backup_files) - copies_to_keep,
        )

        if len(backup_files) - copies_to_keep > 0:
            for filename in sorted(backup_files)[: len(backup_files) - copies_to_keep]:
                debug_print(
                    "do_device_database_backup - removing backup file:", filename
                )
                os.unlink(filename)
                zip_filename = os.path.splitext(filename)[0] + ".zip"
                if os.path.exists(zip_filename):
                    debug_print(
                        "do_device_database_backup - removing zip backup file:",
                        zip_filename,
                    )
                    os.unlink(zip_filename)

        config_backup_file_search = os.path.join(dest_dir, backup_file_search + ".zip")
        debug_print(
            "do_device_database_backup - config_backup_file_search=",
            config_backup_file_search,
        )
        backup_files = glob.glob(config_backup_file_search)
        debug_print(
            "do_device_database_backup - backup_files=",
            backup_files[: len(backup_files) - copies_to_keep],
        )
        debug_print(
            "do_device_database_backup - len(backup_files) - copies_to_keep=",
            len(backup_files) - copies_to_keep,
        )

        if len(backup_files) - copies_to_keep > 0:
            for filename in sorted(backup_files)[: len(backup_files) - copies_to_keep]:
                debug_print(
                    "do_device_database_backup - removing backup file:", filename
                )
                os.unlink(filename)
                sqlite_filename = os.path.splitext(filename)[0] + ".sqlite"
                if os.path.exists(sqlite_filename):
                    debug_print(
                        "do_device_database_backup - removing sqlite backup file:",
                        sqlite_filename,
                    )
                    os.unlink(sqlite_filename)

        debug_print("do_device_database_backup - Removing old backups - finished")
    else:
        debug_print("do_device_database_backup - Manually managing backups")

    return


def do_store_locations(books_to_scan, options, cpus, notification=lambda x, _y: x):
    """
    Master job to do store the current reading positions
    """
    debug_print("do_store_locations - start")
    server = Server(pool_size=cpus)

    debug_print("do_store_locations - options=%s" % (options))
    # Queue all the jobs

    args = [
        "calibre_plugins.koboutilities.jobs",
        "do_store_locations_all",
        (books_to_scan, options),
    ]
    debug_print("do_store_locations - len(books_to_scan)=%d" % (len(books_to_scan)))
    job: ParallelJob = ParallelJob("arbitrary", "Store locations", done=None, args=args)
    server.add_job(job)

    # This server is an arbitrary_n job, so there is a notifier available.
    # Set the % complete to a small number to avoid the 'unavailable' indicator
    notification(0.01, "Reading device database")

    # dequeue the job results as they arrive, saving the results
    total = 1
    count = 0
    stored_locations = {}
    while True:
        job = server.changed_jobs_queue.get()
        # A job can 'change' when it is not finished, for example if it
        # produces a notification. Ignore these.
        job.update()
        if not job.is_finished:
            debug_print("do_store_locations - Job not finished")
            continue
        # A job really finished. Get the information.
        stored_locations = job.result
        count += 1
        notification(float(count) / total, "Storing locations")
        number_bookmarks = len(stored_locations) if stored_locations else 0
        debug_print("Stored_location count=%d" % number_bookmarks)
        debug_print(job.details)
        if count >= total:
            # All done!
            break

    server.close()
    debug_print("do_store_locations - finished")
    # return the map as the job result
    return stored_locations, options


def do_store_locations_all(books, options):
    """
    Child job, to store location for all the books
    """
    return _store_bookmarks(books, options)


def _store_bookmarks(books, options):
    debug_print("_store_bookmarks - start")
    debug_print("DEBUG=", DEBUG)
    count_books = 0
    stored_locations = {}
    clear_if_unread = options[cfg.KEY_CLEAR_IF_UNREAD]
    store_if_more_recent = options[cfg.KEY_STORE_IF_MORE_RECENT]
    do_not_store_if_reopened = options[cfg.KEY_DO_NOT_STORE_IF_REOPENED]
    epub_location_like_kepub = options["epub_location_like_kepub"]
    kepub_fetch_query = options["fetch_queries"]["kepub"]
    epub_fetch_query = options["fetch_queries"]["epub"]

    kobo_percentRead_column_name = options[cfg.KEY_PERCENT_READ_CUSTOM_COLUMN]
    last_read_column_name = options[cfg.KEY_LAST_READ_CUSTOM_COLUMN]

    connection = DeviceDatabaseConnection(
        options["device_database_path"], use_row_factory=True
    )
    cursor = connection.cursor()
    count_books += 1

    debug_print("_store_bookmarks - about to start book loop")
    for (
        book_id,
        contentIDs,
        title,
        authors,
        current_chapterid,
        current_percentRead,
        current_rating,
        current_last_read,
        current_time_spent_reading,
        current_rest_of_book_estimate,
    ) in books:
        device_status = None
        debug_print("----------- _store_bookmarks - top of loop -----------")
        debug_print("_store_bookmarks - Current book: %s - %s" % (title, authors))
        debug_print("_store_bookmarks - contentIds='%s'" % (contentIDs))
        device_status = None
        contentID = None
        for contentID in contentIDs:
            debug_print("_store_bookmarks - contentId='%s'" % (contentID))
            fetch_values = (contentID,)
            if contentID.endswith(".kepub.epub"):
                fetch_query = kepub_fetch_query
            else:
                fetch_query = epub_fetch_query
            cursor.execute(fetch_query, fetch_values)
            result = None
            try:
                result = next(cursor)
                debug_print("_store_bookmarks - device_status='%s'" % (device_status))
                debug_print("_store_bookmarks - result='%s'" % (result))
                if device_status is None:
                    debug_print("_store_bookmarks - device_status is None")
                    device_status = result
                elif (
                    result["DateLastRead"] is not None
                    and device_status["DateLastRead"] is None
                ):
                    debug_print(
                        "_store_bookmarks - result['DateLastRead'] is not None - result['DateLastRead']='%s'"
                        % result["DateLastRead"]
                    )
                    debug_print(
                        "_store_bookmarks - device_status['DateLastRead'] is None"
                    )
                    device_status = result
                elif (
                    result["DateLastRead"] is not None
                    and device_status["DateLastRead"] is not None
                    and (result["DateLastRead"] > device_status["DateLastRead"])
                ):
                    debug_print(
                        "_store_bookmarks - result['DateLastRead'] > device_status['DateLastRead']=%s"
                        % result["DateLastRead"]
                        > device_status["DateLastRead"]
                    )
                    device_status = result
            except TypeError:
                debug_print(
                    "_store_bookmarks - TypeError for: contentID='%s'" % (contentID)
                )
                debug_print("_store_bookmarks - device_status='%s'" % (device_status))
                debug_print("_store_bookmarks - database result='%s'" % (result))
                raise
            except StopIteration:
                pass

        if not device_status:
            continue

        new_last_read = None
        if device_status["DateLastRead"]:
            new_last_read = convert_kobo_date(device_status["DateLastRead"])

        if last_read_column_name is not None and store_if_more_recent:
            debug_print("_store_bookmarks - setting mi.last_read=", new_last_read)
            if current_last_read is not None and new_last_read is not None:
                debug_print(
                    "_store_bookmarks - store_if_more_recent - current_last_read < new_last_read=",
                    current_last_read < new_last_read,
                )
                if current_last_read >= new_last_read:
                    continue
            elif current_last_read is not None and new_last_read is None:
                continue

        if kobo_percentRead_column_name is not None and do_not_store_if_reopened:
            debug_print(
                "_store_current_bookmark - do_not_store_if_reopened - current_percentRead=",
                current_percentRead,
            )
            if current_percentRead is not None and current_percentRead >= 100:
                continue

        debug_print(
            "_store_bookmarks - finished reading database for book - device_status=",
            device_status,
        )
        kobo_chapteridbookmarked = None
        kobo_adobe_location = None
        if device_status["MimeType"] == MIMETYPE_KOBO or epub_location_like_kepub:
            kobo_chapteridbookmarked = device_status["ChapterIDBookmarked"]
            kobo_adobe_location = None
        elif contentID is not None:
            kobo_chapteridbookmarked = (
                device_status["ChapterIDBookmarked"][len(contentID) + 1 :]
                if device_status["ChapterIDBookmarked"]
                else None
            )
            kobo_adobe_location = device_status["adobe_location"]
        if kobo_chapteridbookmarked and kobo_adobe_location:
            new_chapterid = (
                kobo_chapteridbookmarked + BOOKMARK_SEPARATOR + kobo_adobe_location
            )
        elif kobo_chapteridbookmarked:
            new_chapterid = kobo_chapteridbookmarked
        else:
            new_chapterid = None

        new_kobo_percentRead = None
        if device_status["ReadStatus"] == 1:
            new_kobo_percentRead = device_status["___PercentRead"]
        elif device_status["ReadStatus"] == 2:
            new_kobo_percentRead = 100

        new_kobo_rating = device_status["Rating"] * 2 if device_status["Rating"] else 0

        if device_status["TimeSpentReading"]:
            new_time_spent_reading = device_status["TimeSpentReading"]
        else:
            new_time_spent_reading = None

        if device_status["RestOfBookEstimate"]:
            new_rest_of_book_estimate = device_status["RestOfBookEstimate"]
        else:
            new_rest_of_book_estimate = None

        reading_position_changed = False
        if device_status["ReadStatus"] == 0 and clear_if_unread:
            reading_position_changed = True
            new_chapterid = None
            new_kobo_percentRead = 0
            new_last_read = None
            new_time_spent_reading = None
            new_rest_of_book_estimate = None
        elif device_status["ReadStatus"] > 0:
            try:
                debug_print(
                    "_store_bookmarks - Start of checks for current_last_read - reading_position_changed='%s'"
                    % reading_position_changed
                )
                debug_print(
                    "_store_bookmarks - current_last_read='%s'" % current_last_read
                )
                debug_print("_store_bookmarks - new_last_read    ='%s'" % new_last_read)
                debug_print(
                    "_store_bookmarks - current_last_read != new_last_read='%s'"
                    % (current_last_read != new_last_read)
                )
            except Exception:
                debug_print(
                    "_store_bookmarks - Exception raised when logging details of last read. Ignoring."
                )
            reading_position_changed = reading_position_changed or (
                current_last_read != new_last_read
            )
            debug_print(
                "_store_bookmarks - After checking current_last_read - reading_position_changed='%s'"
                % reading_position_changed
            )
            if store_if_more_recent:
                if current_last_read is not None and new_last_read is not None:
                    debug_print(
                        "_store_bookmarks - store_if_more_recent - current_last_read < new_last_read=",
                        current_last_read < new_last_read,
                    )
                    if current_last_read >= new_last_read:
                        debug_print(
                            "_store_bookmarks - store_if_more_recent - new timestamp not more recent than current timestamp. Do not store."
                        )
                        break
                    reading_position_changed = reading_position_changed and (
                        current_last_read < new_last_read
                    )
                elif new_last_read is not None:
                    reading_position_changed = True

            try:
                debug_print(
                    "_store_bookmarks - current_percentRead ='%s'" % current_percentRead
                )
                debug_print(
                    "_store_bookmarks - new_kobo_percentRead='%s'"
                    % new_kobo_percentRead
                )
                debug_print(
                    "_store_bookmarks - current_percentRead != new_kobo_percentRead='%s'"
                    % (current_percentRead != new_kobo_percentRead)
                )
            except Exception:
                debug_print(
                    "_store_bookmarks - Exception raised when logging details of percent read. Ignoring."
                )
            debug_print(
                "_store_bookmarks - After checking percent read - reading_position_changed=",
                reading_position_changed,
            )
            if do_not_store_if_reopened:
                debug_print(
                    "_store_bookmarks - do_not_store_if_reopened - current_percentRead=",
                    current_percentRead,
                )
                if current_percentRead is not None and current_percentRead >= 100:
                    debug_print(
                        "_store_bookmarks - do_not_store_if_reopened - Already finished. Do not store."
                    )
                    break
            reading_position_changed = (
                reading_position_changed or current_percentRead != new_kobo_percentRead
            )

            try:
                debug_print(
                    "_store_bookmarks - current_chapterid ='%s'" % current_chapterid
                )
                debug_print("_store_bookmarks - new_chapterid='%s'" % new_chapterid)
                debug_print(
                    "_store_bookmarks - current_chapterid != new_chapterid='%s'"
                    % (current_chapterid != new_chapterid)
                )
            except Exception:
                debug_print(
                    "_store_bookmarks - Exception raised when logging details of percent read. Ignoring."
                )
            reading_position_changed = reading_position_changed or value_changed(
                current_chapterid, new_chapterid
            )
            debug_print(
                "_store_bookmarks - After checking location - reading_position_changed=",
                reading_position_changed,
            )

            debug_print(
                "_store_bookmarks - current_rating=%s, new_kobo_rating=%s"
                % (current_rating, new_kobo_rating)
            )
            debug_print(
                "_store_bookmarks - current_rating != new_kobo_rating=",
                current_rating != new_kobo_rating,
            )
            debug_print(
                "_store_bookmarks - current_rating != new_kobo_rating and not (current_rating is None and new_kobo_rating == 0)=",
                current_rating != new_kobo_rating
                and not (current_rating is None and new_kobo_rating == 0),
            )
            debug_print(
                "_store_bookmarks - current_rating != new_kobo_rating and new_kobo_rating > 0=",
                current_rating != new_kobo_rating and new_kobo_rating > 0,
            )
            reading_position_changed = reading_position_changed or (
                current_rating != new_kobo_rating
                and not (current_rating is None and new_kobo_rating == 0)
            )
            reading_position_changed = reading_position_changed or (
                current_rating != new_kobo_rating and new_kobo_rating > 0
            )

            debug_print(
                "_store_bookmarks - current_time_spent_reading=%s, new_time_spent_reading=%s"
                % (current_time_spent_reading, new_time_spent_reading)
            )
            debug_print(
                "_store_bookmarks - current_time_spent_reading != new_time_spent_reading=",
                current_time_spent_reading != new_time_spent_reading,
            )
            reading_position_changed = reading_position_changed or value_changed(
                current_time_spent_reading, new_time_spent_reading
            )

            debug_print(
                "_store_bookmarks - current_rest_of_book_estimate=%s, new_rest_of_book_estimate=%s"
                % (current_rest_of_book_estimate, new_rest_of_book_estimate)
            )
            debug_print(
                "_store_bookmarks - current_rest_of_book_estimate != new_rest_of_book_estimate=",
                current_rest_of_book_estimate != new_rest_of_book_estimate,
            )
            reading_position_changed = reading_position_changed or value_changed(
                current_rest_of_book_estimate, new_rest_of_book_estimate
            )

        if reading_position_changed:
            debug_print(
                "_store_bookmarks - position changed for: %s - %s" % (title, authors)
            )
            stored_locations[book_id] = device_status

    debug_print("_store_bookmarks - finished book loop")

    debug_print("_store_bookmarks - finished")
    return stored_locations


def value_changed(old_value, new_value):
    return (
        (old_value is not None and new_value is None)
        or (old_value is None and new_value is not None)
        or old_value != new_value
    )


def do_clean_images_dir(options, cpus, notification=lambda x, _y: x):
    del cpus
    main_image_path = options["main_image_path"]
    sd_image_path = options["sd_image_path"]
    device_database_path = options["device_database_path"]

    notification(1 / 7, "Getting ImageIDs from main images directory")
    debug_print(
        "Getting ImageIDs from main images directory - Path is: '%s'"
        % (main_image_path)
    )
    imageids_files_main = _get_file_imageIds(main_image_path)

    notification(2 / 7, "Getting ImageIDs from SD card images directory")
    debug_print(
        "Getting ImageIDs from SD images directory - Path is: '%s'" % (sd_image_path)
    )
    imageids_files_sd = _get_file_imageIds(sd_image_path)

    notification(3 / 7, "Getting ImageIDs from device database.")
    debug_print("Getting ImageIDs from device database.")
    imageids_db = _get_imageId_set(device_database_path)

    notification(4 / 7, "Checking/removing images from main images directory")
    extra_imageids_files_main = set(imageids_files_main.keys()) - imageids_db
    debug_print(
        "Checking/removing images from main images directory - Number of extra images: %d"
        % (len(extra_imageids_files_main))
    )
    extra_image_files_main = _remove_extra_files(
        extra_imageids_files_main,
        imageids_files_main,
        options["delete_extra_covers"],
        main_image_path,
        images_tree=options["images_tree"],
    )

    notification(5 / 7, "Checking/removing images from SD card images directory")
    extra_imageids_files_sd = set(imageids_files_sd.keys()) - imageids_db
    debug_print(
        "Checking/removing images from SD card images directory - Number of extra images: %d"
        % (len(extra_imageids_files_sd))
    )
    extra_image_files_sd = _remove_extra_files(
        extra_imageids_files_sd,
        imageids_files_sd,
        options["delete_extra_covers"],
        sd_image_path,
        images_tree=options["images_tree"],
    )

    extra_image_files = {}
    extra_image_files["main_memory"] = extra_image_files_main
    extra_image_files["sd_card"] = extra_image_files_sd

    notification(7 / 7, "Cleaning images directory - Done")

    return extra_image_files


def _get_file_imageIds(image_path):
    imageids_files = {}
    if image_path:
        for path, _dirs, files in os.walk(image_path):
            for filename in files:
                if filename.find(" - N3_") > 0:
                    imageid = filename.split(" - N3_")[0]
                    imageids_files[imageid] = path
                    continue
                if filename.find(" - AndroidBookLoadTablet_Aspect") > 0:
                    imageid = filename.split(" - AndroidBookLoadTablet_Aspect")[0]
                    imageids_files[imageid] = path
                    continue
                debug_print("_get_file_imageIds - path=%s" % (path))
                debug_print("check_covers: not 'N3' file - filename=%s" % (filename))

    return imageids_files


def _remove_extra_files(
    extra_imageids_files,
    imageids_files,
    delete_extra_covers,
    image_path,
    images_tree=False,
):
    extra_image_files = []
    from glob import glob

    debug_print("_remove_extra_files - images_tree=%s" % (images_tree))
    for imageId in extra_imageids_files:
        image_path = imageids_files[imageId]
        debug_print("_remove_extra_files - image_path=%s" % (image_path))
        debug_print("_remove_extra_files - imageId=%s" % (imageId))
        escaped_path = os.path.join(image_path, imageId + "*")
        escaped_path = re.sub(r"([\[\]])", r"[\1]", escaped_path)
        debug_print("_remove_extra_files - escaped_path:", escaped_path)
        for filename in glob(escaped_path):
            debug_print("_remove_extra_files - filename=%s" % (filename))
            extra_image_files.append(os.path.basename(filename))
            if delete_extra_covers:
                os.unlink(filename)
        if images_tree and delete_extra_covers:
            debug_print(
                "_remove_extra_files - about to remove directory: image_path=%s"
                % image_path
            )
            try:
                os.removedirs(image_path)
                debug_print("_remove_extra_files - removed path=%s" % (image_path))
            except Exception as e:
                debug_print("_remove_extra_files - removed path exception=", e)

    return extra_image_files


def _get_imageId_set(device_database_path):
    connection = DeviceDatabaseConnection(device_database_path, use_row_factory=True)
    imageId_query = (
        "SELECT DISTINCT ImageId "
        "FROM content "
        "WHERE ContentType = 6 OR ContentType = 901"
    )
    cursor = connection.cursor()

    cursor.execute(imageId_query)
    return {row["ImageId"] for row in cursor}


def do_remove_annotations(options, books, cpus, notification=lambda x, _y: x):
    del cpus
    annotations_dir = options["annotations_dir"]
    annotations_ext = options["annotations_ext"]
    device_path = options["device_path"]
    msg = None
    details = None
    steps = 3
    current_step = 1
    annotation_files = {}

    notification(
        current_step / steps, _("Removing annotations files") + " - " + _("Start")
    )
    debug_print("do_remove_annotations - options:", options)
    debug_print("do_remove_annotations - len(books):", len(books))
    debug_print("do_remove_annotations - annotations_dir: '%s'" % (annotations_dir))
    if options[cfg.KEY_REMOVE_ANNOT_ACTION] == cfg.KEY_REMOVE_ANNOT_ALL:
        if os.path.exists(annotations_dir):
            debug_print("do_remove_annotations: removing annotations directory")
            shutil.rmtree(annotations_dir)
            msg = _("Annotations directory removed.")
            debug_print("do_remove_annotations: removing annotations directory - done")
    elif options[cfg.KEY_REMOVE_ANNOT_ACTION] == cfg.KEY_REMOVE_ANNOT_SELECTED:
        if books and len(books) > 0:
            annotation_files = _get_annotation_files_for_books(
                books, annotations_dir, annotations_ext, device_path
            )
    else:
        current_step += 1
        notification(current_step / steps, _("Getting annotations files."))
        annotation_files = _get_annotation_files(annotations_dir, annotations_ext)
        msg = _("Found {0} annotation files.").format(len(annotation_files))

    if len(annotation_files.keys()) > 0:
        annotation_test_func = None
        if options[cfg.KEY_REMOVE_ANNOT_ACTION] == cfg.KEY_REMOVE_ANNOT_NOBOOK:
            annotation_test_func = _book_file_does_not_exists
        elif options[cfg.KEY_REMOVE_ANNOT_ACTION] == cfg.KEY_REMOVE_ANNOT_EMPTY:
            annotation_test_func = _annotation_file_is_empty
        elif options[cfg.KEY_REMOVE_ANNOT_ACTION] == cfg.KEY_REMOVE_ANNOT_NONEMPTY:
            annotation_test_func = _annotation_file_is_not_empty
        elif options[cfg.KEY_REMOVE_ANNOT_ACTION] == cfg.KEY_REMOVE_ANNOT_SELECTED:
            pass
        if annotation_test_func:
            current_step += 1
            notification(current_step / steps, _("Checking annotations files."))
            annotation_files = _check_annotation_files(
                annotation_files,
                annotations_dir,
                device_path,
                annotation_test_func,
            )
            msg = _("Found {0} annotation files to be removed.").format(
                len(annotation_files)
            )

    if len(annotation_files.keys()) > 0:
        current_step += 1
        notification(current_step / steps, _("Removing annotations files"))
        debug_print("do_remove_annotations - Removing annotations files")
        annotation_files_names = set(annotation_files.keys())
        removed_annotation_files = _remove_extra_files(
            annotation_files_names,
            annotation_files,
            True,
            annotations_dir,
            images_tree=True,
        )
        msg = _("{0} annotations files removed.").format(len(removed_annotation_files))

    remove_annotations_result = {}
    remove_annotations_result["message"] = msg
    remove_annotations_result["details"] = details
    remove_annotations_result["options"] = options

    current_step = steps
    notification(
        current_step / steps, _("Removing annotations files") + " - " + _("Finished")
    )

    return remove_annotations_result


def _get_annotation_files(annotations_path, annotations_ext):
    annotation_files = {}
    if annotations_path:
        for path, dirs, files in os.walk(annotations_path):
            debug_print("_get_annotation_files - path=%s, dirs=%s" % (path, dirs))
            debug_print("_get_annotation_files - files=", files)
            debug_print("_get_annotation_files - len(files)=", len(files))
            for filename in files:
                debug_print("_get_annotation_files - filename=", filename)
                if filename.endswith(annotations_ext):
                    annotation_files[filename] = path

    return annotation_files


def _get_annotation_files_for_books(
    books, annotations_path, annotations_ext, device_path
):
    annotation_files = {}
    debug_print("_get_annotation_files_for_books - annotations_path=", annotations_path)
    debug_print("_get_annotation_files_for_books - device_path=", device_path)
    for book in books:
        for filename in book[2]:
            debug_print("_get_annotation_files_for_books - filename=", filename)
            book_filename = filename
            debug_print(
                "_get_annotation_files_for_books - book_filename=", book_filename
            )
            annotation_file_path = (
                book_filename.replace(device_path, annotations_path) + annotations_ext
            )
            debug_print(
                "_get_annotation_files_for_books - annotation_file_path=",
                annotation_file_path,
            )
            if os.path.exists(annotation_file_path):
                annotation_filename = os.path.basename(annotation_file_path)
                debug_print(
                    "_get_annotation_files_for_books - annotation_filename=",
                    annotation_filename,
                )
                path = os.path.dirname(annotation_file_path)
                debug_print("_get_annotation_files_for_books - path=", path)
                annotation_files[annotation_filename] = path

    return annotation_files


def _check_annotation_files(
    annotation_files,
    annotations_dir,
    device_path,
    annotation_test_func,
):
    annotation_files_to_remove = {}
    for filename in annotation_files:
        debug_print(
            "_check_annotation_files - filename='%s', path='%s'"
            % (filename, annotation_files[filename])
        )
        file_path = annotation_files[filename]
        if annotation_test_func(filename, file_path, annotations_dir, device_path):
            debug_print("_check_annotation_files - annotation to be removed=", filename)
            annotation_files_to_remove[filename] = file_path

    return annotation_files_to_remove


def _book_file_does_not_exists(
    annotation_filename, annotation_path, annotations_dir, device_path
):
    book_file = os.path.splitext(annotation_filename)[0]
    book_path = annotation_path.replace(annotations_dir, device_path)
    book_file = os.path.join(book_path, book_file)
    return not os.path.exists(book_file)


def _annotation_file_is_empty(
    annotation_filename, annotation_path, annotations_dir, device_path
):
    return not _annotation_file_is_not_empty(
        annotation_filename, annotation_path, annotations_dir, device_path
    )


def _annotation_file_is_not_empty(
    annotation_filename, annotation_path, annotations_dir, device_path
):
    del annotations_dir, device_path
    debug_print(
        "_annotation_file_is_not_empty - annotation_filename=", annotation_filename
    )
    annotation_filepath = os.path.join(annotation_path, annotation_filename)
    with open(annotation_filepath) as annotation_file:
        soup = BeautifulStoneSoup(annotation_file.read())
        annotation = soup.find("annotation")

    return annotation is not None
