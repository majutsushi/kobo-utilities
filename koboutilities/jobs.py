# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import annotations

__license__ = "GPL v3"
__copyright__ = "2012-2017, David Forrester <davidfor@internode.on.net>"
__docformat__ = "restructuredtext en"

import os
import pickle
import shutil
from datetime import datetime
from typing import TYPE_CHECKING

from calibre.utils.zipfile import ZipFile

from .utils import (
    check_device_database,
    debug,
)

if TYPE_CHECKING:
    from . import config as cfg


def do_device_database_backup(backup_options_raw: bytes):
    debug("start")
    backup_options: cfg.DatabaseBackupJobOptions = pickle.loads(backup_options_raw)  # noqa: S301

    def backup_file(backup_zip: ZipFile, file_to_add: str, basename: str | None = None):
        debug("file_to_add=%s" % file_to_add)
        basename = basename if basename else os.path.basename(file_to_add)
        try:
            backup_zip.write(file_to_add, basename)
        except Exception as e:
            debug("file '%s' not added. Exception was: %s" % (file_to_add, e))

    debug("backup_options=", backup_options)
    device_name = backup_options.device_name
    serial_number = backup_options.serial_number
    backup_file_template = backup_options.backup_file_template
    dest_dir = backup_options.backup_store_config.backupDestDirectory
    copies_to_keep = backup_options.backup_store_config.backupCopiesToKeepSpin
    do_daily_backup = backup_options.backup_store_config.doDailyBackp
    zip_database = backup_options.backup_store_config.backupZipDatabase
    database_file = backup_options.database_file
    device_path = backup_options.device_path
    debug("copies_to_keep=", copies_to_keep)

    bookreader_backup_file_template = "BookReader-{0}-{1}-{2}"
    bookreader_database_file = os.path.join(device_path, ".kobo", "BookReader.sqlite")

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
        debug("backup_file_search=", backup_file_search)
        backup_file_search = os.path.join(dest_dir, backup_file_search)
        debug("backup_file_search=", backup_file_search)
        backup_files = glob.glob(backup_file_search)
        debug("backup_files=", backup_files)

        if len(backup_files) > 0:
            debug("Backup already done today")
            return

    backup_file_name = backup_file_template.format(
        device_name, serial_number, backup_timestamp
    )
    backup_file_path = os.path.join(dest_dir, backup_file_name + ".sqlite")
    debug("backup_file_name=%s" % backup_file_name)
    debug("backup_file_path=%s" % backup_file_path)
    debug("database_file=%s" % database_file)
    shutil.copyfile(database_file, backup_file_path)

    bookreader_backup_file_path = None
    try:
        bookreader_backup_file_name = bookreader_backup_file_template.format(
            device_name, serial_number, backup_timestamp
        )
        bookreader_backup_file_path = os.path.join(
            dest_dir, bookreader_backup_file_name + ".sqlite"
        )
        debug("bookreader_backup_file_name=%s" % bookreader_backup_file_name)
        debug("bookreader_backup_file_path=%s" % bookreader_backup_file_path)
        debug("bookreader_database_file=%s" % bookreader_database_file)
        shutil.copyfile(bookreader_database_file, bookreader_backup_file_path)
    except Exception as e:
        debug(f"backup of database BookReader.sqlite failed. Exception: {e}")
        bookreader_backup_file_path = None

    try:
        check_result = check_device_database(backup_file_path)
        if check_result.split()[0] != "ok":
            debug("database is corrupt!")
            raise Exception(check_result)
    except:
        debug("backup is corrupt - renaming file.")
        filename = os.path.basename(backup_file_path)
        filename, fileext = os.path.splitext(filename)
        corrupt_filename = filename + "_CORRUPT" + fileext
        corrupt_file_path = os.path.join(dest_dir, corrupt_filename)
        debug("backup_file_name=%s" % database_file)
        debug("corrupt_file_path=%s" % corrupt_file_path)
        os.rename(backup_file_path, corrupt_file_path)
        raise

    # Create the zip file archive
    config_backup_path = os.path.join(dest_dir, backup_file_name + ".zip")
    debug("config_backup_path=%s" % config_backup_path)
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
            debug("adding database KoboReader to zip file=%s" % backup_file_path)
            backup_file(
                config_backup_zip, backup_file_path, basename="KoboReader.sqlite"
            )
            os.unlink(backup_file_path)

            if bookreader_backup_file_path is not None:
                debug(
                    "adding database BookReader to zip file=%s"
                    % bookreader_backup_file_path
                )
                backup_file(
                    config_backup_zip,
                    bookreader_backup_file_path,
                    basename="BookReader.sqlite",
                )
                os.unlink(bookreader_backup_file_path)

    if copies_to_keep > 0:
        debug("copies to keep:%s" % copies_to_keep)

        timestamp_filter = "{0}-{1}".format("[0-9]" * 8, "[0-9]" * 6)
        backup_file_search = backup_file_template.format(
            device_name, serial_number, timestamp_filter
        )
        debug("backup_file_search=", backup_file_search)
        db_backup_file_search = os.path.join(dest_dir, backup_file_search + ".sqlite")
        debug("db_backup_file_search=", db_backup_file_search)
        backup_files = glob.glob(db_backup_file_search)
        debug("backup_files=", backup_files)
        debug(
            "backup_files=",
            backup_files[: len(backup_files) - copies_to_keep],
        )
        debug("len(backup_files) - copies_to_keep=", len(backup_files) - copies_to_keep)

        if len(backup_files) - copies_to_keep > 0:
            for filename in sorted(backup_files)[: len(backup_files) - copies_to_keep]:
                debug("removing backup file:", filename)
                os.unlink(filename)
                zip_filename = os.path.splitext(filename)[0] + ".zip"
                if os.path.exists(zip_filename):
                    debug("removing zip backup file:", zip_filename)
                    os.unlink(zip_filename)

        config_backup_file_search = os.path.join(dest_dir, backup_file_search + ".zip")
        debug("config_backup_file_search=", config_backup_file_search)
        backup_files = glob.glob(config_backup_file_search)
        debug("backup_files=", backup_files[: len(backup_files) - copies_to_keep])
        debug("len(backup_files) - copies_to_keep=", len(backup_files) - copies_to_keep)

        if len(backup_files) - copies_to_keep > 0:
            for filename in sorted(backup_files)[: len(backup_files) - copies_to_keep]:
                debug("removing backup file:", filename)
                os.unlink(filename)
                sqlite_filename = os.path.splitext(filename)[0] + ".sqlite"
                if os.path.exists(sqlite_filename):
                    debug("removing sqlite backup file:", sqlite_filename)
                    os.unlink(sqlite_filename)

        debug("Removing old backups - finished")
    else:
        debug("Manually managing backups")

    return
