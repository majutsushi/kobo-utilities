from __future__ import annotations

import os
import shutil
from typing import TYPE_CHECKING

from calibre.gui2 import FileDialog, info_dialog, ui
from calibre.gui2.dialogs.message_box import ViewLog
from qt.core import (
    QFileDialog,
)

from .. import utils
from ..utils import Dispatcher, debug

if TYPE_CHECKING:
    from ..action import KoboDevice


def check_device_database(
    device: KoboDevice, gui: ui.Main, dispatcher: Dispatcher
) -> None:
    del dispatcher
    check_result = utils.check_device_database(device.db_path)

    check_result = (
        _(
            "Result of running 'PRAGMA integrity_check' on database on the Kobo device:\n\n"
        )
        + check_result
    )

    d = ViewLog("Kobo Utilities - Device Database Check", check_result, parent=gui)
    d.exec()


def vacuum_device_database(
    device: KoboDevice, gui: ui.Main, dispatcher: Dispatcher
) -> None:
    del dispatcher
    debug("start")

    uncompressed_db_size = os.path.getsize(device.db_path)

    connection = utils.device_database_connection(device)
    connection.execute("VACUUM")

    compressed_db_size = os.path.getsize(device.db_path)
    result_message = _(
        "The database on the device has been compressed.\n\tOriginal size = {0}MB\n\tCompressed size = {1}MB"
    ).format(
        "%.3f" % (uncompressed_db_size / 1024 / 1024),
        "%.3f" % (compressed_db_size / 1024 / 1024),
    )
    info_dialog(
        gui,
        _("Kobo Utilities") + " - " + _("Compress device database"),
        result_message,
        show=True,
    )


def backup_device_database(
    device: KoboDevice, gui: ui.Main, dispatcher: Dispatcher
) -> None:
    del dispatcher
    fd = FileDialog(
        parent=gui,
        name="Kobo Utilities plugin:choose backup destination",
        title=_("Choose backup destination"),
        filters=[(_("SQLite database"), ["sqlite"])],
        add_all_files_filter=False,
        mode=QFileDialog.FileMode.AnyFile,
    )
    if not fd.accepted:
        return
    backup_file = fd.get_files()[0]

    if not backup_file:
        return

    debug("backup file selected=", backup_file)
    source_file = device.db_path
    shutil.copyfile(source_file, backup_file)
