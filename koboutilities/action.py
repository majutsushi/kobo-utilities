# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

__license__ = "GPL v3"
__copyright__ = "2012-2017, David Forrester <davidfor@internode.on.net>"
__docformat__ = "restructuredtext en"

import calendar
import dataclasses
import os
import re
import shutil
import threading
import time
from collections import OrderedDict, defaultdict
from configparser import ConfigParser
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, cast
from urllib.parse import quote

from calibre import strftime
from calibre.devices.kobo.books import Book
from calibre.devices.kobo.driver import KOBO, KOBOTOUCH
from calibre.devices.usbms.driver import USBMS
from calibre.ebooks.metadata import authors_to_string
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.oeb.polish.container import EpubContainer
from calibre.ebooks.oeb.polish.errors import DRMError
from calibre.gui2 import (
    FileDialog,
    error_dialog,
    info_dialog,
    open_local_file,
    open_url,
    question_dialog,
    ui,
)
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.device import device_signals
from calibre.gui2.dialogs.message_box import ViewLog
from calibre.gui2.library.views import DeviceBooksView
from calibre.utils.config import config_dir
from calibre.utils.icu import sort_key
from calibre.utils.logging import default_log
from qt.core import (
    QFileDialog,
    QIcon,
    QMenu,
    QModelIndex,
    QTimer,
    QUrl,
    pyqtSignal,
)

from . import ActionKoboUtilities
from . import config as cfg
from .book import SeriesBook
from .common_utils import (
    BOOKMARK_SEPARATOR,
    MIMETYPE_KOBO,
    ProgressBar,
    check_device_database,
    convert_kobo_date,
    create_menu_action_unique,
    debug_print,
    get_icon,
    row_factory,
    set_plugin_icon_resources,
)
from .dialogs import (
    AboutDialog,
    BackupAnnotationsOptionsDialog,
    BlockAnalyticsOptionsDialog,
    BookmarkOptionsDialog,
    ChangeReadingStatusOptionsDialog,
    CleanImagesDirOptionsDialog,
    CoverUploadOptionsDialog,
    FixDuplicateShelvesDialog,
    GetShelvesFromDeviceDialog,
    ManageSeriesDeviceDialog,
    OrderSeriesShelvesDialog,
    QueueProgressDialog,
    ReaderOptionsDialog,
    RemoveAnnotationsOptionsDialog,
    RemoveCoverOptionsDialog,
    SetRelatedBooksDialog,
    ShowBooksNotInDeviceDatabaseDialog,
    ShowReadingPositionChangesDialog,
    UpdateBooksToCDialog,
    UpdateMetadataOptionsDialog,
)

PLUGIN_ICONS = [
    "images/icon.png",
    "images/logo_kobo.png",
    "images/manage_series.png",
    "images/lock.png",
    "images/lock32.png",
    "images/lock_delete.png",
    "images/lock_open.png",
    "images/sort.png",
    "images/ms_ff.png",
    "images/device_connected.png",
]

EPUB_FETCH_QUERY = (
    "SELECT c1.ChapterIDBookmarked, "
    "c2.adobe_location, "
    "c1.ReadStatus, "
    "c1.___PercentRead, "
    "c1.Attribution, "
    "c1.DateLastRead, "
    "c1.Title, "
    "c1.MimeType, "
    "r.rating, "
    "c1.contentId, "
    "c1.TimeSpentReading, "
    "c1.RestOfBookEstimate "
    "FROM content c1 LEFT OUTER JOIN content c2 ON c1.ChapterIDBookmarked = c2.ContentID "
    "LEFT OUTER JOIN ratings r ON c1.ContentID = r.ContentID "
    "WHERE c1.ContentID = ?"
)

EPUB_FETCH_QUERY_NORATING = (
    "SELECT c1.ChapterIDBookmarked, "
    "c2.adobe_location, "
    "c1.ReadStatus, "
    "c1.___PercentRead, "
    "c1.Attribution, "
    "c1.DateLastRead, "
    "c1.Title, "
    "c1.MimeType, "
    "NULL as rating, "
    "c1.contentId, "
    "c1.TimeSpentReading, "
    "c1.RestOfBookEstimate "
    "FROM content c1 LEFT OUTER JOIN content c2 ON c1.ChapterIDBookmarked = c2.ContentID "
    "WHERE c1.ContentID = ?"
)

KEPUB_FETCH_QUERY = (
    "SELECT c1.ChapterIDBookmarked, "
    "c1.adobe_location, "
    "c1.ReadStatus, "
    "c1.___PercentRead, "
    "c1.Attribution, "
    "c1.DateLastRead, "
    "c1.Title, "
    "c1.MimeType, "
    "r.rating, "
    "c1.contentId, "
    "c1.TimeSpentReading, "
    "c1.RestOfBookEstimate "
    "FROM content c1 LEFT OUTER JOIN ratings r ON c1.ContentID = r.ContentID "
    "WHERE c1.ContentID = ?"
)

KEPUB_FETCH_QUERY_NORATING = (
    "SELECT c1.ChapterIDBookmarked, "
    "c1.adobe_location, "
    "c1.ReadStatus, "
    "c1.___PercentRead, "
    "c1.Attribution, "
    "c1.DateLastRead, "
    "c1.Title, "
    "c1.MimeType, "
    "NULL as rating, "
    "c1.contentId, "
    "c1.TimeSpentReading, "
    "c1.RestOfBookEstimate "
    "FROM content c1 "
    "WHERE c1.ContentID = ?"
)

# Dictionary of Reading status fetch queries
# Key is earliest firmware version that supports this query.
# Values are a dictionary. The key of this is the book formats with the query as the value.
FETCH_QUERIES: Dict[Tuple[int, int, int], Dict[str, str]] = {}
FETCH_QUERIES[(0, 0, 0)] = {
    "epub": EPUB_FETCH_QUERY_NORATING,
    "kepub": KEPUB_FETCH_QUERY_NORATING,
}
FETCH_QUERIES[(1, 9, 17)] = {"epub": EPUB_FETCH_QUERY, "kepub": KEPUB_FETCH_QUERY}
# With 4.17.13651, epub location is stored in the same way a for kepubs.
FETCH_QUERIES[(4, 17, 13651)] = {"epub": KEPUB_FETCH_QUERY, "kepub": KEPUB_FETCH_QUERY}

KOBO_ROOT_DIR_NAME = ".kobo"
KOBO_EPOCH_CONF_NAME = "epoch.conf"

load_translations()


# Implementation of QtQHash for strings. This doesn't seem to be in the Python implementation.
def qhash(inputstr):
    h = 0x00000000
    for c in inputstr:
        h = (h << 4) + ord(c)
        h ^= (h & 0xF0000000) >> 23
        h &= 0x0FFFFFFF

    return h


class KoboUtilitiesAction(InterfaceAction):
    interface_action_base_plugin: ActionKoboUtilities

    name = "KoboUtilities"
    giu_name = _("Kobo Utilities")
    # Create our top-level menu/toolbar action (text, icon_path, tooltip, keyboard shortcut)
    action_spec = (name, None, ActionKoboUtilities.description, ())
    action_type = "current"

    timestamp_string = None
    CONTENTTYPE = 6

    plugin_device_connection_changed = pyqtSignal(object)
    plugin_device_metadata_available = pyqtSignal()

    def genesis(self):
        # The attribute in the super class gets assigned dynamically
        base = self.interface_action_base_plugin
        self.version = base.name + " v%d.%d.%d" % base.version
        self.gui: ui.Main = self.gui

        self.menu = QMenu(self.gui)
        icon_resources = self.load_resources(PLUGIN_ICONS)
        set_plugin_icon_resources(self.name, icon_resources)
        self.device_actions_map = []
        self.library_actions_map = []
        self.no_device_actions_map = []
        self.menu_actions = {}

        # Assign our menu to this action and an icon
        self.qaction.setMenu(self.menu)
        self.qaction.setIcon(get_icon(PLUGIN_ICONS[0]))
        self.qaction.triggered.connect(self.toolbar_button_clicked)
        self.menu.aboutToShow.connect(self.about_to_show_menu)
        self.menus_lock = threading.RLock()

        self.device: Optional[KoboDevice] = None
        self.options: Dict[str, Any] = {}

    def initialization_complete(self):
        # otherwise configured hot keys won't work until the menu's
        # been displayed once.
        self.rebuild_menus()
        # Subscribe to device connection events
        device_signals.device_connection_changed.connect(
            self._on_device_connection_changed
        )
        device_signals.device_metadata_available.connect(
            self._on_device_metadata_available
        )

    def about_to_show_menu(self):
        self.rebuild_menus()

    def library_changed(self, db):
        # We need to reset our menus after switching libraries
        self.device = self.get_device()

        self.rebuild_menus()
        if self.device is not None and self.device.profile:
            if self.device.profile[cfg.STORE_OPTIONS_STORE_NAME][
                cfg.KEY_STORE_ON_CONNECT
            ]:
                debug_print("KoboUtilites:library_changed - About to do auto store")
                QTimer.singleShot(1000, self.auto_store_current_bookmark)

    def set_toolbar_button_tooltip(self, text=None):
        debug_print(
            "KoboUtilities:set_toolbar_button_tooltip - start: text='%s'" % text
        )
        if not text:
            text = ActionKoboUtilities.description
            text += "\n"
            if self.device is not None:
                debug_print(
                    "KoboUtilities:set_toolbar_button_tooltip - device connected. self.device.fwversion=",
                    self.device.device.fwversion,
                )
                text += "\n"
                text += _("Connected Device: ")
                text += self.device.name
                text += "\n"
                text += _("Firmware version: ")
                text += ".".join([str(i) for i in self.device.device.fwversion])
            text += "\n"
            text += _("Driver: ")
            text += self.device_driver_name

        debug_print(
            "KoboUtilities:set_toolbar_button_tooltip - setting to text='%s'" % text
        )
        a = self.qaction
        a.setToolTip(text)

    def _on_device_connection_changed(self, is_connected):
        debug_print(
            "KoboUtilities:_on_device_connection_changed - self.plugin_device_connection_changed.__class__: ",
            self.plugin_device_connection_changed.__class__,
        )
        debug_print(
            "Methods for self.plugin_device_connection_changed: ",
            dir(self.plugin_device_connection_changed),
        )

        self.plugin_device_connection_changed.emit(is_connected)
        if not is_connected:
            debug_print(
                "KoboUtilites:_on_device_connection_changed - Device disconnected"
            )
            self.device = None
            self.rebuild_menus()
        else:
            self.device = self.get_device()

        self.set_toolbar_button_tooltip()

    def _on_device_metadata_available(self):
        debug_print("KoboUtilites:_on_device_metadata_available - Start")
        self.plugin_device_metadata_available.emit()
        self.device = self.get_device()
        self.set_toolbar_button_tooltip()

        if self.device is not None:
            profile = self.device.profile
            backup_config = self.device.backup_config
            debug_print(
                "KoboUtilites:_on_device_metadata_available - profile:",
                profile,
            )
            debug_print(
                "KoboUtilites:_on_device_metadata_available - backup_config:",
                backup_config,
            )
            if (
                backup_config[cfg.KEY_DO_DAILY_BACKUP]
                or backup_config[cfg.KEY_BACKUP_EACH_CONNECTION]
            ):
                debug_print(
                    "KoboUtilites:_on_device_metadata_available - About to start auto backup"
                )
                self.auto_backup_device_database()

            if (
                profile
                and profile[cfg.STORE_OPTIONS_STORE_NAME][cfg.KEY_STORE_ON_CONNECT]
            ):
                debug_print(
                    "KoboUtilites:_on_device_metadata_available - About to start auto store"
                )
                self.auto_store_current_bookmark()

        self.rebuild_menus()

    def rebuild_menus(self):
        with self.menus_lock:
            # Show the config dialog
            # The config dialog can also be shown from within
            # Preferences->Plugins, which is why the do_user_config
            # method is defined on the base plugin class
            self.menu.clear()
            for action in self.menu_actions.values():
                self.gui.keyboard.unregister_shortcut(
                    action.calibre_shortcut_unique_name
                )
                # starting in calibre 2.10.0, actions are registers at
                # the top gui level for OSX' benefit.
                self.gui.removeAction(action)
            self.menu_actions = {}
            self.device_actions_map = []
            self.library_actions_map = []
            self.no_device_actions_map = []

            self.device = self.get_device()
            device = self.device
            debug_print(
                "rebuild_menus - device.supports_ratings=%s"
                % (device is not None and device.supports_ratings)
            )
            self.set_toolbar_button_tooltip()

            debug_print("rebuild_menus - have device.")
            self.set_reader_fonts_action = self.create_menu_item_ex(
                self.menu,
                _("&Set Reader Font for Selected Books"),
                unique_name="Set Reader Font for Selected Books",
                shortcut_name=_("Set Reader Font for Selected Books"),
                triggered=self.set_reader_fonts,
                enabled=device is not None and device.is_kobotouch,
                is_library_action=True,
                is_device_action=True,
                tooltip=(
                    None
                    if (device is None or device.is_kobotouch)
                    else "Not supported for this device"
                ),
            )

            self.remove_reader_fonts_action = self.create_menu_item_ex(
                self.menu,
                _("&Remove Reader Font for Selected Books"),
                unique_name="Remove Reader Font for Selected Books",
                shortcut_name=_("Remove Reader Font for Selected Books"),
                triggered=self.remove_reader_fonts,
                enabled=device is not None and device.is_kobotouch,
                is_library_action=True,
                is_device_action=True,
                tooltip=(
                    None
                    if (device is None or device.is_kobotouch)
                    else "Not supported for this device"
                ),
            )

            self.menu.addSeparator()

            self.update_metadata_action = self.create_menu_item_ex(
                self.menu,
                _("Update &metadata in device library"),
                unique_name="Update metadata in device library",
                shortcut_name=_("Update metadata in device library"),
                triggered=self.update_metadata,
                enabled=not self.isDeviceView() and device is not None,
                is_library_action=True,
            )

            self.change_reading_status_action = self.create_menu_item_ex(
                self.menu,
                _("&Change Reading Status in device library"),
                unique_name="Change Reading Status in device library",
                shortcut_name=_("Change Reading Status in device library"),
                triggered=self.change_reading_status,
                enabled=self.isDeviceView() and device is not None,
                is_device_action=True,
            )

            self.manage_series_on_device_action = self.create_menu_item_ex(
                self.menu,
                _("&Manage Series Information in device library"),
                unique_name="Manage Series Information in device library",
                shortcut_name=_("Manage Series Information in device library"),
                triggered=self.manage_series_on_device,
                enabled=self.isDeviceView()
                and device is not None
                and device.supports_series,
                is_device_action=True,
                tooltip=(
                    None
                    if (device is None or device.supports_series)
                    else "Not supported for this device"
                ),
            )

            self.handle_bookmarks_action = self.create_menu_item_ex(
                self.menu,
                _("&Store/Restore current bookmark"),
                unique_name="Store/Restore current bookmark",
                shortcut_name=_("Store/Restore current bookmark"),
                triggered=self.handle_bookmarks,
                enabled=not self.isDeviceView() and device is not None,
                is_library_action=True,
            )

            self.menu.addSeparator()
            self.update_book_toc_on_device_action = self.create_menu_item_ex(
                self.menu,
                _("&Update ToC for Selected Books"),
                image="toc.png",
                unique_name="Update ToC for Selected Books",
                shortcut_name=_("Update ToC for Selected Books"),
                triggered=self.update_book_toc_on_device,
                enabled=not self.isDeviceView() and device is not None,
                is_library_action=True,
            )

            self.menu.addSeparator()
            self.upload_covers_action = self.create_menu_item_ex(
                self.menu,
                _("&Upload covers for Selected Books"),
                unique_name="Upload/covers for Selected Books",
                shortcut_name=_("Upload covers for Selected Books"),
                triggered=self.upload_covers,
                enabled=not self.isDeviceView() and device is not None,
                is_library_action=True,
            )
            self.remove_covers_action = self.create_menu_item_ex(
                self.menu,
                _("&Remove covers for Selected Books"),
                unique_name="Remove covers for Selected Books",
                shortcut_name=_("Remove covers for Selected Books"),
                triggered=self.remove_covers,
                enabled=device is not None and device.is_kobotouch,
                is_library_action=True,
                is_device_action=True,
                tooltip=(
                    None
                    if (device is None or device.is_kobotouch)
                    else "Not supported for this device"
                ),
            )

            self.clean_images_dir_action = self.create_menu_item_ex(
                self.menu,
                _("&Clean images directory of extra cover images"),
                unique_name="Clean images directory of extra cover images",
                shortcut_name=_("Clean images directory of extra cover images"),
                triggered=self.clean_images_dir,
                enabled=device is not None,
                is_library_action=True,
                is_device_action=True,
            )
            self.open_cover_dir_action = self.create_menu_item_ex(
                self.menu,
                _("&Open cover image directory"),
                unique_name="Open cover image directory",
                shortcut_name=_("Open cover image directory"),
                triggered=self.open_cover_image_directory,
                enabled=device is not None and device.is_kobotouch,
                is_library_action=True,
                is_device_action=True,
                tooltip=(
                    None
                    if (device is None or device.is_kobotouch)
                    else "Not supported for this device"
                ),
            )
            self.menu.addSeparator()

            self.order_series_shelves_action = self.create_menu_item_ex(
                self.menu,
                _("Order Series Shelves"),
                unique_name="Order Series Shelves",
                shortcut_name=_("Order Series Shelves"),
                triggered=self.order_series_shelves,
                enabled=(device is not None and device.supports_series),
                is_library_action=True,
                is_device_action=True,
                tooltip=(
                    None
                    if (device is None or device.supports_series)
                    else "Not supported for this device"
                ),
            )
            self.get_shelves_from_device_action = self.create_menu_item_ex(
                self.menu,
                _("Get Shelves From Device"),
                unique_name="Get Shelves From Device",
                shortcut_name=_("Get Shelves From Device"),
                triggered=self.get_shelves_from_device,
                enabled=(
                    not self.isDeviceView()
                    and device is not None
                    and device.is_kobotouch
                ),
                is_library_action=True,
                is_device_action=False,
                tooltip=(
                    None
                    if (device is None or device.is_kobotouch)
                    else "Not supported for this device"
                ),
            )
            if device is not None and device.device.fwversion < (4, 4, 0):
                self.set_related_books_action = self.create_menu_item_ex(
                    self.menu,
                    _("Set Related Books"),
                    unique_name="Set Related Books",
                    shortcut_name=_("Set Related Books"),
                    triggered=self.set_related_books,
                    enabled=device.supports_series,
                    is_library_action=True,
                    is_device_action=True,
                    tooltip=(
                        None
                        if device.supports_series
                        else "Not supported for this device"
                    ),
                )
            self.menu.addSeparator()
            self.getAnnotationForSelected_action = self.create_menu_item_ex(
                self.menu,
                _("Copy annotation for Selected Book"),
                image="bookmarks.png",
                unique_name="Copy annotation for Selected Book",
                shortcut_name=_("Copy annotation for Selected Book"),
                triggered=self.getAnnotationForSelected,
                enabled=not self.isDeviceView() and device is not None,
                is_library_action=True,
            )
            self.backup_annotation_files_action = self.create_menu_item_ex(
                self.menu,
                _("Backup Annotation File"),
                unique_name="Backup Annotation File",
                shortcut_name=_("Backup Annotation File"),
                triggered=self.backup_annotation_files,
                enabled=not self.isDeviceView() and device is not None,
                is_library_action=True,
            )
            self.remove_annotations_files_action = self.create_menu_item_ex(
                self.menu,
                _("Remove Annotation Files"),
                unique_name="Remove Annotation Files",
                shortcut_name=_("Remove Annotation Files"),
                triggered=self.remove_annotations_files,
                enabled=device is not None,
                is_library_action=True,
                is_device_action=True,
            )

            self.menu.addSeparator()

            self.show_books_not_in_database_action = self.create_menu_item_ex(
                self.menu,
                _("Show books not in the device database"),
                unique_name="Show books not in the device database",
                shortcut_name=_("Show books not in the device database"),
                triggered=self.show_books_not_in_database,
                enabled=self.isDeviceView() and device is not None,
                is_device_action=True,
            )

            self.refresh_device_books_action = self.create_menu_item_ex(
                self.menu,
                _("Refresh the list of books on the device"),
                unique_name="Refresh the list of books on the device",
                shortcut_name=_("Refresh the list of books on the device"),
                triggered=self.refresh_device_books,
                enabled=device is not None,
                is_library_action=True,
                is_device_action=True,
            )
            self.databaseMenu = self.menu.addMenu(_("Database"))
            self.block_analytics_action = self.create_menu_item_ex(
                self.databaseMenu,
                _("Block Analytics Events"),
                unique_name="Block Analytics Events",
                shortcut_name=_("Block Analytics Events"),
                triggered=self.block_analytics,
                enabled=device is not None and device.is_kobotouch,
                is_library_action=True,
                is_device_action=True,
                tooltip=(
                    None
                    if (device is None or device.is_kobotouch)
                    else "Not supported for this device"
                ),
            )
            self.databaseMenu.addSeparator()
            self.fix_duplicate_shelves_action = self.create_menu_item_ex(
                self.databaseMenu,
                _("Fix Duplicate Shelves"),
                unique_name="Fix Duplicate Shelves",
                shortcut_name=_("Fix Duplicate Shelves"),
                triggered=self.fix_duplicate_shelves,
                enabled=device is not None and device.is_kobotouch,
                is_library_action=True,
                is_device_action=True,
                tooltip=(
                    None
                    if (device is None or device.is_kobotouch)
                    else "Not supported for this device"
                ),
            )
            self.check_device_database_action = self.create_menu_item_ex(
                self.databaseMenu,
                _("Check the device database"),
                unique_name="Check the device database",
                shortcut_name=_("Check the device database"),
                triggered=self.check_device_database,
                enabled=device is not None,
                is_library_action=True,
                is_device_action=True,
            )
            self.vacuum_device_database_action = self.create_menu_item_ex(
                self.databaseMenu,
                _("Compress the device database"),
                unique_name="Compress the device database",
                shortcut_name=_("Compress the device database"),
                triggered=self.vacuum_device_database,
                enabled=device is not None,
                is_library_action=True,
                is_device_action=True,
            )
            self.backup_device_database_action = self.create_menu_item_ex(
                self.databaseMenu,
                _("Backup device database"),
                unique_name="Backup device database",
                shortcut_name=_("Backup device database"),
                triggered=self.backup_device_database,
                enabled=device is not None,
                is_library_action=True,
                is_device_action=True,
            )

            self.menu.addSeparator()
            self.set_time_on_device_action = self.create_menu_item_ex(
                self.menu,
                _("Set time on device"),
                unique_name="Set time on device",
                shortcut_name=_("Set time on device"),
                tooltip=_(
                    "Creates a file on the device which will be used to set the time when the device is disconnected."
                ),
                triggered=self.set_time_on_device,
                enabled=device is not None,
                is_library_action=True,
                is_device_action=True,
            )

            self.menu.addSeparator()
            self.driverMenu = self.menu.addMenu(_("Driver"))
            self.config_device_action = self.create_menu_item_ex(
                self.driverMenu,
                _("&Configure current Driver") + " - " + self.device_driver_name,
                unique_name="Configure Driver",
                shortcut_name=_("Configure Driver"),
                image="config.png",
                triggered=self.configure_device,
                enabled=True,
                is_library_action=True,
                is_device_action=True,
                is_no_device_action=True,
            )
            self.switch_device_driver_action = self.create_menu_item_ex(
                self.driverMenu,
                _("Switch between main and extended driver"),
                unique_name="Switch between main and extended driver",
                shortcut_name=_("Switch between main and extended driver"),
                image="config.png",
                triggered=self.switch_device_driver,
                enabled=True,
                is_library_action=True,
                is_device_action=True,
                is_no_device_action=True,
            )
            self.driverMenu.addSeparator()

            self.config_action = self.create_menu_item_ex(
                self.menu,
                _("&Customize plugin") + "...",  # shortcut=False,
                unique_name="Customize plugin",
                shortcut_name=_("Customize plugin"),
                image="config.png",
                triggered=self.show_configuration,
                enabled=True,
                is_library_action=True,
                is_device_action=True,
                is_no_device_action=True,
            )

            self.config_action = self.create_menu_item_ex(
                self.menu,
                _("&About Plugin"),  # shortcut=False,
                image="images/icon.png",
                unique_name="About KoboUtilities",
                shortcut_name=_("About KoboUtilities"),
                triggered=self.about,
                enabled=True,
                is_library_action=True,
                is_device_action=True,
                is_no_device_action=True,
            )

            self.gui.keyboard.finalize()

    def about(self):
        # Get the about text from a file inside the plugin zip file
        # The get_resources function is a builtin function defined for all your
        # plugin code. It loads files from the plugin zip file. It returns
        # the bytes from the specified file.
        #
        # Note that if you are loading more than one file, for performance, you
        # should pass a list of names to get_resources. In this case,
        # get_resources will return a dictionary mapping names to bytes. Names that
        # are not found in the zip file will not be in the returned dictionary.

        about_text = "{0}\n\n{1}".format(
            self.version, get_resources("about.md").decode("utf-8")
        )
        debug_print("KoboUtilities::about - self.version=", self.version)
        debug_print("KoboUtilities::about - about_text=", about_text)
        AboutDialog(self.gui, self.qaction.icon(), about_text).exec_()

    def create_menu_item_ex(
        self,
        parent_menu,
        menu_text,
        image=None,
        tooltip=None,
        shortcut=None,
        triggered=None,
        is_checked=None,
        shortcut_name=None,
        unique_name=None,
        enabled=False,
        is_library_action=False,
        is_device_action=False,
        is_no_device_action=False,
    ):
        if (self.isDeviceView() and is_device_action) or (
            not self.isDeviceView() and is_library_action
        ):
            ac = create_menu_action_unique(
                self,
                parent_menu,
                menu_text,
                image,
                tooltip,
                shortcut,
                triggered,
                is_checked,
                shortcut_name,
                unique_name,
            )

            ac.setEnabled(enabled)
            self.menu_actions[shortcut_name] = ac
        else:
            ac = None

        if is_library_action:
            self.library_actions_map.append(shortcut_name)
        if is_device_action:
            self.device_actions_map.append(shortcut_name)
        if is_no_device_action:
            self.no_device_actions_map.append(shortcut_name)

        return ac

    def toolbar_button_clicked(self):
        self.rebuild_menus()

        self.device = self.get_device()

        if self.isDeviceView():
            assert self.device is not None
            if self.device.supports_series:
                button_action = cfg.get_plugin_pref(
                    cfg.COMMON_OPTIONS_STORE_NAME, cfg.KEY_BUTTON_ACTION_DEVICE
                )
                if button_action == "":
                    self.show_configuration()
                else:
                    self.menu_actions[button_action].trigger()
            else:
                self.change_reading_status()
        else:
            button_action = cfg.get_plugin_pref(
                cfg.COMMON_OPTIONS_STORE_NAME, cfg.KEY_BUTTON_ACTION_LIBRARY
            )
            if button_action == "":
                debug_print("toolbar_button_clicked - no button action")
                self.show_configuration()
            else:
                try:
                    debug_print(
                        "toolbar_button_clicked - self.no_device_actions_map=",
                        self.no_device_actions_map,
                    )
                    if self.device or button_action in self.no_device_actions_map:
                        self.menu_actions[button_action].trigger()
                    else:
                        self.show_configuration()
                except Exception as e:
                    debug_print(
                        "toolbar_button_clicked - exception running button action:",
                        button_action,
                        " exception: ",
                        e,
                    )
                    self.show_configuration()

    def isDeviceView(self):
        view = self.gui.current_view()
        return isinstance(view, DeviceBooksView)

    def _get_contentIDs_for_selected(self):
        view = self.gui.current_view()
        if view is None:
            return []
        if self.isDeviceView():
            rows = view.selectionModel().selectedRows()
            books = [view.model().db[view.model().map[r.row()]] for r in rows]
            contentIDs = [book.contentID for book in books]
        else:
            book_ids = view.get_selected_ids()
            contentIDs = self.get_contentIDs_for_books(book_ids)
            debug_print("_get_contentIDs_for_selected - contentIDs=", contentIDs)

        return contentIDs

    @property
    def device_driver_name(self):
        if self.device:
            device_driver_name = self.device.device.name
        else:
            from calibre.customize.ui import is_disabled

            try:
                from calibre_plugins.kobotouch_extended.device.driver import (  # type: ignore[reportMissingImports]
                    KOBOTOUCHEXTENDED,
                )

                cuurent_driver = (
                    KOBOTOUCHEXTENDED
                    if not is_disabled(KOBOTOUCHEXTENDED)
                    else KOBOTOUCH
                )
            except Exception as e:
                debug_print(
                    "device_driver_name - could not load extended driver. Exception=", e
                )
                cuurent_driver = KOBOTOUCH
            device_driver_name = cuurent_driver.name

        return device_driver_name

    def configure_device(self):
        if self.device:
            self.gui.configure_connected_device()
        else:
            from calibre.customize.ui import is_disabled

            try:
                from calibre_plugins.kobotouch_extended.device.driver import (  # type: ignore[reportMissingImports]
                    KOBOTOUCHEXTENDED,
                )

                driver_to_configure = (
                    KOBOTOUCHEXTENDED
                    if not is_disabled(KOBOTOUCHEXTENDED)
                    else KOBOTOUCH
                )
            except Exception as e:
                debug_print(
                    "configure_device - could not load extended driver. Exception=", e
                )
                driver_to_configure = KOBOTOUCH
            driver_to_configure = driver_to_configure(None)
            driver_to_configure.do_user_config(self.gui)

    def switch_device_driver(self):
        from calibre.customize.ui import disable_plugin, enable_plugin, is_disabled

        try:
            from calibre_plugins.kobotouch_extended.device.driver import (  # type: ignore[reportMissingImports]
                KOBOTOUCHEXTENDED,
            )
        except Exception as e:
            debug_print(
                "switch_device_driver - could not load extended driver. Exception=", e
            )
            result_message = _(
                "The KoboTouchExtended driver is not installed. There is nothing to switch between, so no changes have been made."
            )
            info_dialog(
                self.gui,
                _("Kobo Utilities") + " - " + _("Switch device drivers"),
                result_message,
                show=True,
            )
            return

        extended_disabled = is_disabled(KOBOTOUCHEXTENDED)
        main_disabled = is_disabled(KOBOTOUCH)
        debug_print(
            "switch_device_driver - using is_disabled: main_disabled=%s, extended_disabled=%s"
            % (main_disabled, extended_disabled)
        )
        if extended_disabled:
            enable_plugin(KOBOTOUCHEXTENDED)
            disable_plugin(KOBOTOUCH)
            result_message = _(
                "The KoboTouch driver has been disabled and the KoboTouchExtended driver has been enabled."
            )
        else:
            enable_plugin(KOBOTOUCH)
            disable_plugin(KOBOTOUCHEXTENDED)
            result_message = _(
                "The KoboTouchExtended driver has been disabled and the KoboTouch driver has been enabled."
            )
        result_message += "\n" + _(
            "You will need to restart calibre for this change to be applied."
        )
        self.check_if_restart_needed(
            restart_message=result_message, restart_needed=True
        )

        self.set_toolbar_button_tooltip()
        return

    def show_configuration(self):
        debug_print("KoboUtilites::show_configuration - before do_user_config")
        restart_message = _(
            "Calibre must be restarted before the plugin can be configured."
        )
        # Check if a restart is needed. If the restart is needed, but the user does not
        # trigger it, the result is true and we do not do the configuration.
        if self.check_if_restart_needed(restart_message=restart_message):
            return

        self.interface_action_base_plugin.do_user_config(self.gui)
        debug_print("KoboUtilites::show_configuration - after do_user_config")
        restart_message = _(
            "New custom colums have been created."
            "\nYou will need to restart calibre for this change to be applied."
        )
        self.check_if_restart_needed(restart_message=restart_message)

    def check_if_restart_needed(self, restart_message=None, restart_needed=False):
        if self.gui.must_restart_before_config or restart_needed:
            if restart_message is None:
                restart_message = _(
                    "Calibre must be restarted before the plugin can be configured."
                )
            from calibre.gui2 import show_restart_warning

            do_restart = show_restart_warning(restart_message)
            if do_restart:
                debug_print(
                    "KoboUtilites::check_if_restart_needed - restarting calibre..."
                )
                self.gui.quit(restart=True)
            else:
                debug_print(
                    "KoboUtilites::check_if_restart_needed - calibre needs to be restarted, do not open configuration"
                )
                return True
        return False

    def set_reader_fonts(self):
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot set reader font settings."),
                _("No device connected."),
                show=True,
            )

        contentIDs = self._get_contentIDs_for_selected()

        debug_print("set_reader_fonts - contentIDs", contentIDs)

        if len(contentIDs) == 0:
            return

        if len(contentIDs) == 1:
            self.single_contentID = contentIDs[0]
        self.singleSelected = len(contentIDs) == 1

        dlg = ReaderOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.prefs

        if self.options[cfg.KEY_UPDATE_CONFIG_FILE]:
            self._update_config_reader_settings(self.options)

        updated_fonts, added_fonts, _deleted_fonts, count_books = (
            self._set_reader_fonts(contentIDs)
        )
        result_message = (
            _("Change summary:")
            + "\n\t"
            + _(
                "Font settings updated={0}\n\tFont settings added={1}\n\tTotal books={2}"
            ).format(updated_fonts, added_fonts, count_books)
        )
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Device library updated"),
            result_message,
            show=True,
        )

    def remove_reader_fonts(self):
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot remove reader font settings"),
                _("No device connected."),
                show=True,
            )

        contentIDs = self._get_contentIDs_for_selected()

        if len(contentIDs) == 0:
            return

        mb = question_dialog(
            self.gui,
            _("Remove Reader settings"),
            _("Do you want to remove the reader settings for the selected books?"),
            show_copy_button=False,
        )
        if not mb:
            return

        _updated_fonts, _added_fonts, deleted_fonts, _count_books = (
            self._set_reader_fonts(contentIDs, delete=True)
        )
        result_message = (
            _("Change summary:")
            + "\n\t"
            + _("Font settings deleted={0}").format(deleted_fonts)
        )
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Device library updated"),
            result_message,
            show=True,
        )

    def update_metadata(self):
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot update metadata in device library."),
                _("No device connected."),
                show=True,
            )

        self.progressbar(_("Getting book list"), on_top=False)

        selectedIDs = self._get_selected_ids()
        self.set_progressbar_label(
            _("Number of selected books {0}").format(len(selectedIDs))
        )
        if len(selectedIDs) == 0:
            self.hide_progressbar()
            return
        self.set_progressbar_label(
            _("Number of selected books {0}").format(len(selectedIDs))
        )
        self.show_progressbar(len(selectedIDs))
        debug_print("update_metadata - selectedIDs:", selectedIDs)
        books = self._convert_calibre_ids_to_books(current_view.model().db, selectedIDs)
        for book in books:
            self.increment_progressbar()
            device_book_paths = self.get_device_paths_from_id(book.calibre_id)
            debug_print("update_metadata - device_book_paths:", device_book_paths)
            book.paths = device_book_paths
            book.contentIDs = [
                self.contentid_from_path(path, self.CONTENTTYPE)
                for path in device_book_paths
            ]
        self.hide_progressbar()

        dlg = UpdateMetadataOptionsDialog(self.gui, self, books[0])
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return

        self.progressbar(_("Updating metadata on device"), on_top=False)

        self.options = dlg.new_prefs
        self.set_progressbar_label(
            _("Number of books to update metadata for {0}").format(len(books))
        )
        updated_books, unchanged_books, not_on_device_books, count_books = (
            self._update_metadata(books)
        )
        result_message = (
            _("Update summary:")
            + "\n\t"
            + _(
                "Books updated={0}\n\tUnchanged books={1}\n\tBooks not on device={2}\n\tTotal books={3}"
            ).format(updated_books, unchanged_books, not_on_device_books, count_books)
        )
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Device library updated"),
            result_message,
            show=True,
        )

    def handle_bookmarks(self):
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot store or restore current reading position."),
                _("No device connected."),
                show=True,
            )

        selectedIDs = self._get_selected_ids()

        if len(selectedIDs) == 0:
            return

        dlg = BookmarkOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.options

        if self.options["storeBookmarks"]:
            self.store_current_bookmark()
        else:
            self.restore_current_bookmark()

    def auto_store_current_bookmark(self):
        debug_print("auto_store_current_bookmark - start")
        self.device = self.get_device()
        assert self.device is not None

        library_db = self.gui.current_db

        self.options = {}
        self.options[cfg.KEY_STORE_BOOKMARK] = True
        self.options[cfg.KEY_READING_STATUS] = False
        self.options[cfg.KEY_DATE_TO_NOW] = False
        self.options[cfg.KEY_SET_RATING] = False
        self.options[cfg.KEY_CLEAR_IF_UNREAD] = False
        self.options[cfg.KEY_BACKGROUND_JOB] = True
        if self.device.profile is not None:
            self.options[cfg.KEY_PROMPT_TO_STORE] = self.device.profile[
                cfg.STORE_OPTIONS_STORE_NAME
            ][cfg.KEY_PROMPT_TO_STORE]
            self.options[cfg.KEY_STORE_IF_MORE_RECENT] = self.device.profile[
                cfg.STORE_OPTIONS_STORE_NAME
            ][cfg.KEY_STORE_IF_MORE_RECENT]
            self.options[cfg.KEY_DO_NOT_STORE_IF_REOPENED] = self.device.profile[
                cfg.STORE_OPTIONS_STORE_NAME
            ][cfg.KEY_DO_NOT_STORE_IF_REOPENED]

        (
            kobo_chapteridbookmarked_column,
            kobo_percentRead_column,
            rating_column,
            last_read_column,
            time_spent_reading_column,
            rest_of_book_estimate_column,
        ) = self.get_column_names()
        self.options[cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN] = (
            kobo_chapteridbookmarked_column
        )
        self.options[cfg.KEY_PERCENT_READ_CUSTOM_COLUMN] = kobo_percentRead_column
        self.options[cfg.KEY_RATING_CUSTOM_COLUMN] = rating_column
        self.options[cfg.KEY_LAST_READ_CUSTOM_COLUMN] = last_read_column
        self.options[cfg.KEY_TIME_SPENT_READING_COLUMN] = time_spent_reading_column
        self.options[cfg.KEY_REST_OF_BOOK_ESTIMATE_COLUMN] = (
            rest_of_book_estimate_column
        )

        self.options["device_database_path"] = self.device_database_path()
        self.options["job_function"] = "store_current_bookmark"
        self.options["supports_ratings"] = self.device.supports_ratings
        self.options["epub_location_like_kepub"] = self.device.epub_location_like_kepub
        self.options["fetch_queries"] = self._get_fetch_query_for_firmware_version(
            self.device_fwversion
        )
        self.options["allOnDevice"] = True

        if self.options[cfg.KEY_DO_NOT_STORE_IF_REOPENED]:
            search_condition = "and ({0}:false or {0}:<100)".format(
                kobo_percentRead_column
            )
        else:
            search_condition = ""

        self.progressbar(_("Queuing books for storing reading position"), on_top=False)
        self.show_progressbar(0)
        self.set_progressbar_label(_("Getting list of books"))

        search_condition = "ondevice:True {0}".format(search_condition)
        debug_print(
            "auto_store_current_bookmark::do_books - search_condition=",
            search_condition,
        )
        onDeviceIds = set(
            library_db.search_getting_ids(
                search_condition, None, sort_results=False, use_virtual_library=False
            )
        )
        debug_print(
            "auto_store_current_bookmark::do_all_books -- onDeviceIds:",
            len(onDeviceIds),
        )
        onDevice_book_paths = self.get_device_paths_from_ids(onDeviceIds)
        debug_print(
            "auto_store_current_bookmark::do_all_books -- onDevice_book_paths:",
            len(onDevice_book_paths),
        )

        self.books = self._convert_calibre_ids_to_books(library_db, onDeviceIds)
        self.show_progressbar(len(self.books))
        self.set_progressbar_label(_("Queuing books"))
        books_to_scan = []

        for book in self.books:
            self.increment_progressbar()
            device_book_paths = [x.path for x in onDevice_book_paths[book.calibre_id]]
            book.contentIDs = [
                self.contentid_from_path(path, self.CONTENTTYPE)
                for path in device_book_paths
            ]
            if len(book.contentIDs) > 0:
                title = book.title
                self.set_progressbar_label(_("Queueing ") + title)
                authors = authors_to_string(book.authors)
                current_chapterid = None
                current_percentRead = None
                current_rating = None
                current_last_read = None
                current_time_spent_reading = None
                current_rest_of_book_estimate = None
                if kobo_chapteridbookmarked_column is not None:
                    metadata = book.get_user_metadata(
                        kobo_chapteridbookmarked_column, False
                    )
                    assert metadata is not None
                    current_chapterid = metadata["#value#"]
                if kobo_percentRead_column is not None:
                    metadata = book.get_user_metadata(kobo_percentRead_column, False)
                    assert metadata is not None
                    current_percentRead = metadata["#value#"]
                if rating_column is not None:
                    if rating_column == "rating":
                        current_rating = book.rating
                    else:
                        metadata = book.get_user_metadata(rating_column, False)
                        assert metadata is not None
                        current_rating = metadata["#value#"]
                if last_read_column is not None:
                    metadata = book.get_user_metadata(last_read_column, False)
                    assert metadata is not None
                    current_last_read = metadata["#value#"]
                if time_spent_reading_column is not None:
                    metadata = book.get_user_metadata(time_spent_reading_column, False)
                    assert metadata is not None
                    current_time_spent_reading = metadata["#value#"]
                if rest_of_book_estimate_column is not None:
                    metadata = book.get_user_metadata(
                        rest_of_book_estimate_column, False
                    )
                    assert metadata is not None
                    current_rest_of_book_estimate = metadata["#value#"]

                books_to_scan.append(
                    (
                        book.calibre_id,
                        book.contentIDs,
                        title,
                        authors,
                        current_chapterid,
                        current_percentRead,
                        current_rating,
                        current_last_read,
                        current_time_spent_reading,
                        current_rest_of_book_estimate,
                    )
                )

        if len(books_to_scan) > 0:
            self._store_queue_job(self.options, books_to_scan)

        self.hide_progressbar()

        debug_print("auto_store_current_bookmark::do_books - Finish")

    def set_time_on_device(self):
        debug_print("set_time_on_device - start")
        now = calendar.timegm(time.gmtime())
        debug_print("set_time_on_device - time=%s" % now)
        assert self.device is not None
        epoch_conf_path = os.path.join(
            self.device.path, KOBO_ROOT_DIR_NAME, KOBO_EPOCH_CONF_NAME
        )
        with open(epoch_conf_path, "w") as epoch_conf:
            epoch_conf.write("%s" % now)
        self.gui.status_bar.show_message(
            _("Kobo Utilities") + " - " + _("Time file created on device."), 3000
        )
        debug_print("set_time_on_device - end")

    def device_serial_no(self) -> str:
        version_info = self.device.version_info if self.device is not None else None
        return version_info.serial_no if version_info else "Unknown"

    def auto_backup_device_database(self):
        debug_print("auto_backup_device_database - start")
        if not self.device or not self.device.backup_config:
            debug_print("auto_backup_device_database - no backup configuration")
            return
        backup_config = self.device.backup_config

        dest_dir = backup_config[cfg.KEY_BACKUP_DEST_DIRECTORY]
        debug_print("auto_backup_device_database - destination directory=", dest_dir)
        if not dest_dir or len(dest_dir) == 0:
            debug_print(
                "auto_backup_device_database - destination directory not set, not doing backup"
            )
            return

        # Backup file names will be KoboReader-devicename-serialnumber-timestamp.sqlite
        backup_file_template = "KoboReader-{0}-{1}-{2}"
        debug_print(
            "auto_backup_device_database - about to get version info from device..."
        )
        version_info = self.device.version_info
        debug_print("auto_backup_device_database - version_info=", version_info)
        serial_number = self.device_serial_no()
        device_name = "".join(self.device.device.gui_name.split())
        debug_print(
            "auto_backup_device_database - device_information=",
            self.device.device.get_device_information(),
        )
        debug_print("auto_backup_device_database - device_name=", device_name)
        debug_print(
            "auto_backup_device_database - backup_file_template=",
            backup_file_template.format(device_name, serial_number, ""),
        )

        backup_options = {}
        backup_options[cfg.KEY_BACKUP_DEST_DIRECTORY] = dest_dir
        backup_options[cfg.KEY_BACKUP_COPIES_TO_KEEP] = backup_config[
            cfg.KEY_BACKUP_COPIES_TO_KEEP
        ]
        backup_options[cfg.KEY_DO_DAILY_BACKUP] = backup_config[cfg.KEY_DO_DAILY_BACKUP]
        backup_options[cfg.KEY_BACKUP_EACH_CONNECTION] = backup_config[
            cfg.KEY_BACKUP_EACH_CONNECTION
        ]
        backup_options[cfg.KEY_BACKUP_ZIP_DATABASE] = backup_config[
            cfg.KEY_BACKUP_ZIP_DATABASE
        ]
        backup_options["device_name"] = device_name
        backup_options["serial_number"] = serial_number
        backup_options["backup_file_template"] = backup_file_template
        backup_options["database_file"] = self.device_database_path()
        backup_options["device_path"] = self.device.device._main_prefix
        debug_print("auto_backup_device_database - backup_options=", backup_options)

        self._device_database_backup(backup_options)
        debug_print("auto_backup_device_database - end")

    def store_current_bookmark(self):
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot update metadata in device library."),
                _("No device connected."),
                show=True,
            )

        self.options["device_database_path"] = self.device_database_path()
        self.options["job_function"] = "store_current_bookmark"
        self.options["supports_ratings"] = self.device.supports_ratings
        self.options["epub_location_like_kepub"] = self.device.epub_location_like_kepub
        self.options["fetch_queries"] = self._get_fetch_query_for_firmware_version(
            self.device_fwversion
        )
        self.options["allOnDevice"] = False
        self.options[cfg.KEY_PROMPT_TO_STORE] = True
        debug_print("store_current_bookmark - self.options:", self.options)

        if self.options[cfg.KEY_BACKGROUND_JOB]:
            QueueProgressDialog(
                self.gui,
                [],
                self.options,
                self._store_queue_job,
                current_view.model().db,
                plugin_action=self,
            )
        else:
            selectedIDs = self._get_selected_ids()

            if len(selectedIDs) == 0:
                return
            debug_print("store_current_bookmark - selectedIDs:", selectedIDs)
            books = self._convert_calibre_ids_to_books(
                current_view.model().db, selectedIDs
            )
            for book in books:
                device_book_paths = self.get_device_paths_from_id(book.calibre_id)
                book.paths = device_book_paths
                book.contentIDs = [
                    self.contentid_from_path(path, self.CONTENTTYPE)
                    for path in device_book_paths
                ]

            reading_locations_updated, books_without_reading_locations, count_books = (
                self._store_current_bookmark(books)
            )
            result_message = (
                _("Update summary:")
                + "\n\t"
                + _(
                    "Reading locations updated={0}\n\tBooks with no reading location={1}\n\tTotal books checked={2}"
                ).format(
                    reading_locations_updated,
                    books_without_reading_locations,
                    count_books,
                )
            )
            info_dialog(
                self.gui,
                _("Kobo Utilities") + " - " + _("Library updated"),
                result_message,
                show=True,
            )

    def restore_current_bookmark(self):
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot set bookmark in device library."),
                _("No device connected."),
                show=True,
            )

        selectedIDs = self._get_selected_ids()

        if len(selectedIDs) == 0:
            return
        debug_print("restore_current_bookmark - selectedIDs:", selectedIDs)
        books = self._convert_calibre_ids_to_books(current_view.model().db, selectedIDs)
        for book in books:
            device_book_paths = self.get_device_paths_from_id(book.calibre_id)
            debug_print(
                "store_current_bookmark - device_book_paths:", device_book_paths
            )
            book.paths = device_book_paths
            book.contentIDs = [
                self.contentid_from_path(path, self.CONTENTTYPE)
                for path in device_book_paths
            ]

        updated_books, not_on_device_books, count_books = (
            self._restore_current_bookmark(books)
        )
        result_message = (
            _("Update summary:")
            + "\n\t"
            + _(
                "Books updated={0}\n\tBooks not on device={1}\n\tTotal books={2}"
            ).format(updated_books, not_on_device_books, count_books)
        )
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Device library updated"),
            result_message,
            show=True,
        )

    def _get_fetch_query_for_firmware_version(
        self, current_firmware_version
    ) -> Optional[Dict[str, str]]:
        fetch_queries = None
        for fw_version in sorted(FETCH_QUERIES.keys()):
            if current_firmware_version < fw_version:
                break
            fetch_queries = FETCH_QUERIES[fw_version]

        debug_print(
            "KoboUtilities::_get_fetch_query_for_firmware_version - using fetch_queries:",
            fetch_queries,
        )
        return fetch_queries

    def backup_device_database(self):
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot backup the device database."),
                _("No device connected."),
                show=True,
            )

        debug_print("backup_device_database")

        fd = FileDialog(
            parent=self.gui,
            name="Kobo Utilities plugin:choose backup destination",
            title=_("Choose Backup Destination"),
            filters=[(_("SQLite database"), ["sqlite"])],
            add_all_files_filter=False,
            mode=QFileDialog.FileMode.AnyFile,
        )
        if not fd.accepted:
            return
        backup_file = fd.get_files()[0]

        if not backup_file:
            return

        debug_print("backup_device_database - backup file selected=", backup_file)
        source_file = self.device_database_path()
        shutil.copyfile(source_file, backup_file)

    def backup_annotation_files(self):
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return

        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot backup annotation files from device."),
                _("No device connected."),
                show=True,
            )

        selectedIDs = self._get_selected_ids()

        if len(selectedIDs) == 0:
            return

        dlg = BackupAnnotationsOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return

        dest_path = dlg.dest_path()
        debug_print("backup_annotation_files - selectedIDs:", selectedIDs)
        books = self._convert_calibre_ids_to_books(current_view.model().db, selectedIDs)
        for book in books:
            device_book_paths = self.get_device_paths_from_id(book.calibre_id)
            debug_print(
                "backup_annotation_files - device_book_paths:", device_book_paths
            )
            book.paths = device_book_paths
            book.contentIDs = [
                self.contentid_from_path(path, self.CONTENTTYPE)
                for path in device_book_paths
            ]

        debug_print("backup_annotation_files - dest_path=", dest_path)
        annotations_found, no_annotations, kepubs, count_books = (
            self._backup_annotation_files(books, dest_path)
        )
        result_message = _(
            "Annotations backup summary:\n\tBooks with annotations={0}\n\tBooks without annotations={1}\n\tKobo epubs={2}\n\tTotal books={3}"
        ).format(annotations_found, no_annotations, kepubs, count_books)
        info_dialog(
            self.gui,
            _("Kobo Utilities") + _(" - Annotations backup"),
            result_message,
            show=True,
        )

    def remove_annotations_files(self):
        self.device = self.get_device()
        current_view = self.gui.current_view()
        if current_view is None:
            return

        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot remove files from device."),
                _("No device connected."),
                show=True,
            )

        dlg = RemoveAnnotationsOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.options

        debug_print(
            "remove_annotations_files - self.device.path='%s'" % (self.device.path)
        )

        self.options["annotations_dir"] = self.device.device.normalize_path(
            self.device.path + "Digital Editions/Annotations/"
        )
        self.options["annotations_ext"] = ".annot"
        self.options["device_path"] = self.device.path
        self.options["device_database_path"] = self.device_database_path()
        self.options["job_function"] = "remove_annotations"
        debug_print("remove_annotations_files - self.options=", self.options)
        QueueProgressDialog(
            self.gui,
            [],
            self.options,
            self._remove_annotations_job,
            current_view.model().db,
            plugin_action=self,
        )

        return

    def refresh_device_books(self):
        self.gui.device_detected(True, KOBOTOUCH)

    def change_reading_status(self):
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot change reading status in device library."),
                _("No device connected."),
                show=True,
            )

        books = self._get_books_for_selected()

        if len(books) == 0:
            return
        for book in books:
            debug_print("change_reading_status - book:", book)
            book.contentIDs = [book.contentID]
        debug_print("change_reading_status - books:", books)

        dlg = ChangeReadingStatusOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.options
        self.options[cfg.KEY_USE_PLUGBOARD] = False
        self.options[cfg.KEY_USE_TITLE_SORT] = False
        self.options[cfg.KEY_USE_AUTHOR_SORT] = False
        self.options[cfg.KEY_SET_SUBTITLE] = False
        debug_print("change_reading_status - self.options:", self.options)

        self.progressbar(_("Changing reading status on device"), on_top=False)

        updated_books, unchanged_books, not_on_device_books, count_books = (
            self._update_metadata(books)
        )
        result_message = (
            _("Update summary:")
            + "\n\t"
            + _(
                "Books updated={0}\n\tUnchanged books={1}\n\tBooks not on device={2}\n\tTotal books={3}"
            ).format(updated_books, unchanged_books, not_on_device_books, count_books)
        )
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Device library updated"),
            result_message,
            show=True,
        )

    def show_books_not_in_database(self):
        current_view = self.gui.current_view()
        if current_view is None:
            return

        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot list books not in device library."),
                _("No device connected."),
                show=True,
            )

        books = self._get_books_for_selected()

        if len(books) == 0:
            books = current_view.model().db

        books_not_in_database = self._check_book_in_database(books)

        dlg = ShowBooksNotInDeviceDatabaseDialog(self.gui, books_not_in_database)
        dlg.show()

    def fix_duplicate_shelves(self):
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot fix the duplicate shelves in the device library."),
                _("No device connected."),
                show=True,
            )

        shelves = self._get_shelf_count()
        dlg = FixDuplicateShelvesDialog(self.gui, self, shelves)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            debug_print("fix_duplicate_shelves - dialog cancelled")
            return
        self.options = dlg.options
        debug_print(
            "fix_duplicate_shelves - about to fix shelves - options=%s" % self.options
        )

        starting_shelves, shelves_removed, finished_shelves = (
            self._remove_duplicate_shelves(shelves, self.options)
        )
        result_message = (
            _("Update summary:")
            + "\n\t"
            + _(
                "Starting number of shelves={0}\n\tShelves removed={1}\n\tTotal shelves={2}"
            ).format(starting_shelves, shelves_removed, finished_shelves)
        )
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Duplicate Shelves Fixed"),
            result_message,
            show=True,
        )

    def order_series_shelves(self):
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot order the series shelves in the device library."),
                _("No device connected."),
                show=True,
            )

        shelves = []
        dlg = OrderSeriesShelvesDialog(self.gui, self, shelves)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            debug_print("order_series_shelves - dialog cancelled")
            return
        self.options = dlg.options
        shelves = dlg.get_shelves()
        debug_print(
            "order_series_shelves - about to order shelves - options=%s" % self.options
        )
        debug_print("order_series_shelves - shelves=", shelves)

        starting_shelves, shelves_ordered = self._order_series_shelves(
            shelves, self.options
        )
        result_message = (
            _("Update summary:")
            + "\n\t"
            + _("Starting number of shelves={0}\n\tShelves reordered={1}").format(
                starting_shelves, shelves_ordered
            )
        )
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Order Series Shelves"),
            result_message,
            show=True,
        )

    def set_related_books(self):
        debug_print("set_related_books - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot set the related books."),
                _("No device connected."),
                show=True,
            )

        shelves = []
        dlg = SetRelatedBooksDialog(self.gui, self, shelves)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            debug_print("set_related_books - dialog cancelled")
            return
        self.options = dlg.options
        debug_print("set_related_books - options=%s" % self.options)
        if self.options["deleteAllRelatedBooks"]:
            self._delete_related_books(self.options)
            result_message = _("Deleted all related books for sideloaded books.")
        else:
            related_types = dlg.get_related_types()
            debug_print("set_related_books - related_types=", related_types)

            categories_count, books_count = self._set_related_books(
                related_types, self.options
            )
            result_message = (
                _("Update summary:")
                + "\n\t"
                + _("Number of series or authors={0}\n\tNumber of books={1}").format(
                    categories_count, books_count
                )
            )

        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Set Related Books"),
            result_message,
            show=True,
        )

    def get_shelves_from_device(self):
        current_view = self.gui.current_view()
        if current_view is None:
            return

        debug_print("get_shelves_from_device - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot get the shelves from device."),
                _("No device connected."),
                show=True,
            )

        dlg = GetShelvesFromDeviceDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            debug_print("get_shelves_from_device - dialog cancelled")
            return
        self.options = dlg.options

        # Check if driver is configured to manage shelves. If so, warn if selected column is one of
        # the configured columns.
        driver_shelves = self.device.device.get_collections_attributes()
        debug_print("get_shelves_from_device - driver_shelves=", driver_shelves)
        debug_print(
            "get_shelves_from_device - selected column=",
            self.options[cfg.KEY_SHELVES_CUSTOM_COLUMN],
        )
        if self.options[cfg.KEY_SHELVES_CUSTOM_COLUMN] in driver_shelves:
            debug_print(
                "get_shelves_from_device - selected column is one of the columns used in the driver configuration!"
            )
            details_msg = _(
                "The selected column is {0}."
                "\n"
                "The driver shelf management columns are: {1}"
            ).format(
                self.options[cfg.KEY_SHELVES_CUSTOM_COLUMN], ", ".join(driver_shelves)
            )
            mb = question_dialog(
                self.gui,
                _("Getting shelves from device"),
                _(
                    "The column selected is one of the columns used in the driver configuration for shelf management. "
                    "Updating this column might affect the shelf management the next time you connect the device. "
                    "\n\nAre you sure you want to do this?"
                ),
                override_icon=QIcon(I("dialog_warning.png")),
                show_copy_button=False,
                det_msg=details_msg,
            )
            if not mb:
                debug_print(
                    "get_shelves_from_device - User cancelled because of column used."
                )
                return

        self.progressbar(_("Getting shelves from device"), on_top=False)
        self.set_progressbar_label(_("Getting list of shelves"))

        library_db = current_view.model().db
        if self.options[cfg.KEY_ALL_BOOKS]:
            selectedIDs = set(
                library_db.search_getting_ids(
                    "ondevice:True", None, sort_results=False, use_virtual_library=False
                )
            )
        else:
            selectedIDs = self._get_selected_ids()

        if len(selectedIDs) == 0:
            return
        debug_print("get_shelves_from_device - selectedIDs:", selectedIDs)
        books = self._convert_calibre_ids_to_books(library_db, selectedIDs)
        self.set_progressbar_label(
            _("Number of books to get shelves for {0}").format(len(books))
        )
        for book in books:
            device_book_paths = self.get_device_paths_from_id(book.calibre_id)
            debug_print(
                "get_shelves_from_device - device_book_paths:", device_book_paths
            )
            book.paths = device_book_paths
            book.contentIDs = [
                self.contentid_from_path(path, self.CONTENTTYPE)
                for path in device_book_paths
            ]

        debug_print(
            "get_shelves_from_device - about get shelves - options=%s" % self.options
        )

        books_with_shelves, books_without_shelves, count_books = (
            self._get_shelves_from_device(books, self.options)
        )
        result_message = (
            _("Update summary:")
            + "\n\t"
            + _(
                "Books processed={0}\n\tBooks with Shelves={1}\n\tBooks without Shelves={2}"
            ).format(count_books, books_with_shelves, books_without_shelves)
        )
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Get Shelves from Device"),
            result_message,
            show=True,
        )

    def check_device_database(self):
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot check Kobo device database."),
                _("No device connected."),
                show=True,
            )

        check_result = self._check_device_database()

        check_result = (
            _(
                "Result of running 'PRAGMA integrity_check' on database on the Kobo device:\n\n"
            )
            + check_result
        )

        d = ViewLog(
            "Kobo Utilities - Device Database Check", check_result, parent=self.gui
        )
        d.setWindowIcon(self.qaction.icon())
        d.exec_()

    def block_analytics(self):
        debug_print("block_analytics - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot block analytics events."),
                _("No device connected."),
                show=True,
            )

        debug_print("block_analytics")

        dlg = BlockAnalyticsOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.options

        block_analytics_result = self._block_analytics()
        if block_analytics_result:
            info_dialog(
                self.gui,
                _("Kobo Utilities") + " - " + _("Block Analytics Events"),
                block_analytics_result,
                show=True,
            )
        else:
            result_message = _("Failed to block analytics events.")
            d = ViewLog(
                _("Kobo Utilities") + " - " + _("Block Analytics Events"),
                result_message,
                parent=self.gui,
            )
            d.setWindowIcon(self.qaction.icon())
            d.exec_()

    def vacuum_device_database(self):
        debug_print("vacuum_device_database - start")
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot compress Kobo device database."),
                _("No device connected."),
                show=True,
            )

        uncompressed_db_size = os.path.getsize(self.device_database_path())
        vacuum_result = self._vacuum_device_database()

        if vacuum_result == "":
            compressed_db_size = os.path.getsize(self.device_database_path())
            result_message = _(
                "The database on the device has been compressed.\n\tOriginal size = {0}MB\n\tCompressed size = {1}MB"
            ).format(
                "%.3f" % (uncompressed_db_size / 1024 / 1024),
                "%.3f" % (compressed_db_size / 1024 / 1024),
            )
            info_dialog(
                self.gui,
                _("Kobo Utilities") + " - " + _("Compress Device Database"),
                result_message,
                show=True,
            )

        else:
            vacuum_result = (
                _("Result of running 'vacuum' on database on the Kobo device:\n\n")
                + vacuum_result
            )

            d = ViewLog(
                "Kobo Utilities - Compress Device Database",
                vacuum_result,
                parent=self.gui,
            )
            d.setWindowIcon(self.qaction.icon())
            d.exec_()

    def default_options(self):
        options = cfg.METADATA_OPTIONS_DEFAULTS
        return options

    def manage_series_on_device(self):
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return

        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot manage series in device library."),
                _("No device connected."),
                show=True,
            )
        series_columns = self.get_series_columns()

        books = self._get_books_for_selected()
        debug_print("manage_series_on_device - books[0].__class__=", books[0].__class__)

        if len(books) == 0:
            return
        seriesBooks = [SeriesBook(book, series_columns) for book in books]
        seriesBooks = sorted(seriesBooks, key=lambda k: k.sort_key(sort_by_name=True))
        debug_print(
            "manage_series_on_device - seriesBooks[0]._mi.__class__=",
            seriesBooks[0]._mi.__class__,
        )
        debug_print(
            "manage_series_on_device - seriesBooks[0]._mi.kobo_series=",
            seriesBooks[0]._mi.kobo_series,
        )
        debug_print(
            "manage_series_on_device - seriesBooks[0]._mi.kobo_series_number=",
            seriesBooks[0]._mi.kobo_series_number,
        )
        debug_print("manage_series_on_device - books:", seriesBooks)

        library_db = self.gui.library_view.model().db
        all_series = library_db.all_series()
        all_series.sort(key=lambda x: sort_key(x[1]))

        d = ManageSeriesDeviceDialog(
            self.gui, self, seriesBooks, all_series, series_columns
        )
        d.exec_()
        if d.result() != d.Accepted:
            return

        debug_print(
            "manage_series_on_device - done series management - books:", seriesBooks
        )

        self.options = self.default_options()
        books = []
        for seriesBook in seriesBooks:
            debug_print(
                "manage_series_on_device - seriesBook._mi.contentID=",
                seriesBook._mi.contentID,
            )
            if (
                seriesBook.is_title_changed()
                or seriesBook.is_pubdate_changed()
                or seriesBook.is_series_changed()
            ):
                book = seriesBook._mi
                book.series_index_string = seriesBook.series_index_string()
                book.kobo_series_number = seriesBook.series_index_string()
                book.kobo_series = seriesBook.series_name()
                book._new_book = True
                book.contentIDs = [book.contentID]
                books.append(book)
                self.options["title"] = (
                    self.options["title"] or seriesBook.is_title_changed()
                )
                self.options["series"] = (
                    self.options["series"] or seriesBook.is_series_changed()
                )
                self.options["published_date"] = (
                    self.options["published_date"] or seriesBook.is_pubdate_changed()
                )
                debug_print(
                    "manage_series_on_device - seriesBook._mi.__class__=",
                    seriesBook._mi.__class__,
                )
                debug_print(
                    "manage_series_on_device - seriesBook.is_pubdate_changed()=%s"
                    % seriesBook.is_pubdate_changed()
                )
                debug_print(
                    "manage_series_on_device - book.kobo_series=", book.kobo_series
                )
                debug_print(
                    "manage_series_on_device - book.kobo_series_number=",
                    book.kobo_series_number,
                )
                debug_print("manage_series_on_device - book.series=", book.series)
                debug_print(
                    "manage_series_on_device - book.series_index=%s" % book.series_index
                )

        if (
            self.options["title"]
            or self.options["series"]
            or self.options["published_date"]
        ):
            self.progressbar(_("Updating series information on device"), on_top=True)
            updated_books, unchanged_books, not_on_device_books, count_books = (
                self._update_metadata(books)
            )

            debug_print("manage_series_on_device - about to call sync_booklists")
            USBMS.sync_booklists(
                self.device.device, (current_view.model().db, None, None)
            )
            result_message = (
                _("Update summary:")
                + "\n\t"
                + _(
                    "Books updated={0}\n\tUnchanged books={1}\n\tBooks not on device={2}\n\tTotal books={3}"
                ).format(
                    updated_books, unchanged_books, not_on_device_books, count_books
                )
            )
        else:
            result_message = _("No changes made to series information.")
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Manage Series On Device"),
            result_message,
            show=True,
        )

    def get_series_columns(self):
        custom_columns = self.gui.library_view.model().custom_columns
        series_columns = OrderedDict()
        for key, column in list(custom_columns.items()):
            typ = column["datatype"]
            if typ == "series":
                series_columns[key] = column
        return series_columns

    def get_selected_books(self, rows, series_columns):
        db = self.gui.library_view.model().db
        idxs = [row.row() for row in rows]
        books = []
        for idx in idxs:
            mi = db.get_metadata(idx)
            book = SeriesBook(mi, series_columns)
            books.append(book)
        # Sort books by the current series
        books = sorted(books, key=lambda k: k.sort_key())
        return books

    def upload_covers(self):
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot upload covers."),
                _("No device connected."),
                show=True,
            )

        selectedIDs = self._get_selected_ids()

        if len(selectedIDs) == 0:
            return
        debug_print("upload_covers - selectedIDs:", selectedIDs)
        books = self._convert_calibre_ids_to_books(
            current_view.model().db, selectedIDs, get_cover=True
        )

        dlg = CoverUploadOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.options

        total_books, uploaded_covers, not_on_device_books = self._upload_covers(books)
        result_message = (
            _("Change summary:")
            + "\n\t"
            + _(
                "Covers uploaded={0}\n\tBooks not on device={1}\n\tTotal books={2}"
            ).format(uploaded_covers, not_on_device_books, total_books)
        )
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Covers uploaded"),
            result_message,
            show=True,
        )

    def remove_covers(self):
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot remove covers."),
                _("No device connected."),
                show=True,
            )
        debug_print("remove_covers - self.device.path", self.device.path)

        if self.gui.stack.currentIndex() == 0:
            selectedIDs = self._get_selected_ids()
            books = self._convert_calibre_ids_to_books(
                current_view.model().db, selectedIDs
            )
        else:
            books = self._get_books_for_selected()

        if len(books) == 0:
            return

        dlg = RemoveCoverOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.options

        removed_covers, not_on_device_books, total_books = self._remove_covers(books)
        result_message = (
            _("Change summary:")
            + "\n\t"
            + _(
                "Covers removed={0}\n\tBooks not on device={1}\n\tTotal books={2}"
            ).format(removed_covers, not_on_device_books, total_books)
        )
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Covers removed"),
            result_message,
            show=True,
        )

    def open_cover_image_directory(self):
        current_view = self.gui.current_view()
        if current_view is None:
            return
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot open cover directory"),
                _("No device connected."),
                show=True,
            )
        debug_print("open_cover_image_directory - self.device.path", self.device.path)

        if self.gui.stack.currentIndex() == 0:
            selectedIDs = self._get_selected_ids()
            books = self._convert_calibre_ids_to_books(
                current_view.model().db, selectedIDs
            )

        else:
            books = self._get_books_for_selected()

        if len(books) == 0:
            return

        self._open_cover_image_directory(books)

    def clean_images_dir(self):
        debug_print("clean_images_dir - start")

        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot clean covers directory."),
                _("No device connected."),
                show=True,
            )
        debug_print("clean_images_dir - self.device.path", self.device.path)

        dlg = CleanImagesDirOptionsDialog(self.gui, self)
        dlg.exec_()
        if dlg.result() != dlg.Accepted:
            return
        self.options = dlg.options
        main_prefix = self.device.device._main_prefix
        assert isinstance(main_prefix, str), f"_main_prefix is type {type(main_prefix)}"
        if (
            isinstance(self.device.device, KOBOTOUCH)
            and self.device.device.fwversion
            >= self.device.device.min_fwversion_images_tree
        ):
            self.main_image_path = os.path.join(main_prefix, ".kobo-images")
            self.sd_image_path = (
                os.path.join(
                    self.device.device._card_a_prefix, "koboExtStorage/images-cache/"
                )
                if self.device.device._card_a_prefix
                else None
            )
            self.options["images_tree"] = True
        else:
            self.main_image_path = os.path.join(main_prefix, ".kobo/images")
            self.sd_image_path = (
                os.path.join(self.device.device._card_a_prefix, "koboExtStorage/images")
                if self.device.device._card_a_prefix
                else None
            )
            self.options["images_tree"] = False
        self.options["main_image_path"] = self.device.device.normalize_path(
            self.main_image_path
        )
        self.options["sd_image_path"] = self.device.device.normalize_path(
            self.sd_image_path
        )
        self.options["device_database_path"] = self.device_database_path()
        self.options["job_function"] = "clean_images_dir"
        debug_print("clean_images_dir - self.options=", self.options)
        QueueProgressDialog(
            self.gui, [], self.options, self._clean_images_dir_job, None, self
        )

    def getAnnotationForSelected(self):
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            return error_dialog(
                self.gui,
                _("Cannot upload covers."),
                _("No device connected."),
                show=True,
            )

        self._getAnnotationForSelected()

    def _get_selected_ids(self):
        current_view = self.gui.current_view()
        if current_view is None:
            return []
        rows = current_view.selectionModel().selectedRows()
        if not rows or len(rows) == 0:
            return []
        debug_print(
            "_get_selected_ids - self.gui.current_view().model()",
            current_view.model(),
        )
        return list(map(current_view.model().id, rows))

    def contentid_from_path(self, path, ContentType):
        assert self.device is not None
        main_prefix = self.device.device._main_prefix
        assert isinstance(main_prefix, str), f"_main_prefix is type {type(main_prefix)}"
        if ContentType == 6:
            extension = os.path.splitext(path)[1]
            if extension == ".kobo":
                ContentID = os.path.splitext(path)[0]
                # Remove the prefix on the file.  it could be either
                ContentID = ContentID.replace(main_prefix, "")
            elif extension == "":
                ContentID = path
                kepub_path = self.device.device.normalize_path(".kobo/kepub/")
                assert kepub_path is not None
                ContentID = ContentID.replace(main_prefix + kepub_path, "")
            else:
                ContentID = path
                ContentID = ContentID.replace(main_prefix, "file:///mnt/onboard/")

            if self.device.device._card_a_prefix is not None:
                ContentID = ContentID.replace(
                    self.device.device._card_a_prefix, "file:///mnt/sd/"
                )
        else:  # ContentType = 16
            ContentID = path
            ContentID = ContentID.replace(main_prefix, "file:///mnt/onboard/")
            if self.device.device._card_a_prefix is not None:
                ContentID = ContentID.replace(
                    self.device.device._card_a_prefix, "file:///mnt/sd/"
                )
        ContentID = ContentID.replace("\\", "/")
        return ContentID

    def get_contentIDs_for_books(self, book_ids):
        contentIDs = []
        for book_id in book_ids:
            contentIDs_for_book = self.get_contentIDs_from_id(book_id)
            debug_print("get_contentIDs_for_books - contentIDs", contentIDs_for_book)
            contentIDs.extend(contentIDs_for_book)
        return contentIDs

    def _get_books_for_selected(self):
        view = self.gui.current_view()
        if view is None:
            return []
        if self.isDeviceView():
            rows = view.selectionModel().selectedRows()
            books = []
            for r in rows:
                book = view.model().db[view.model().map[r.row()]]
                book.calibre_id = r.row()
                books.append(book)
        else:
            books = []

        return books

    def _convert_calibre_ids_to_books(self, db, ids, get_cover=False) -> List[Book]:
        books = []
        for book_id in ids:
            book = self._convert_calibre_id_to_book(db, book_id, get_cover=get_cover)
            books.append(book)
        return books

    def _convert_calibre_id_to_book(self, db, book_id, get_cover=False) -> Book:
        mi = db.get_metadata(book_id, index_is_id=True, get_cover=get_cover)
        book = Book("", "lpath", title=mi.title, other=mi)
        book.calibre_id = mi.id
        return book

    def get_device_path(self) -> str:
        debug_print("BEGIN Get Device Path")

        device_path = ""
        try:
            device_connected = self.gui.library_view.model().device_connected
        except Exception:
            debug_print("No device connected")
            device_connected = None

        # If there is a device connected, test if we can retrieve the mount point from Calibre
        if device_connected is not None:
            try:
                # _main_prefix is not reset when device is ejected so must be sure device_connected above
                device_path = self.gui.device_manager.connected_device._main_prefix
                debug_print("Root path of device: %s" % device_path)
            except Exception:
                debug_print(
                    "A device appears to be connected, but device path not defined"
                )
        else:
            debug_print("No device appears to be connected")

        debug_print("END Get Device Path")
        return device_path

    def get_device(self):
        try:
            device = self.gui.device_manager.connected_device
            if device is None or not isinstance(device, KOBO):
                debug_print("No supported Kobo device appears to be connected")
                return None
        except Exception:
            debug_print("No device connected")
            return None

        version_info = None
        device_version_info = device.device_version_info()
        if device_version_info is not None:
            serial_no, _, fw_version, _, _, model_id = device_version_info
            version_info = KoboVersionInfo(serial_no, fw_version, model_id)

        device_path = self.get_device_path()
        debug_print('KoboUtilities:get_device - device_path="%s"' % device_path)
        current_device_information = (
            self.gui.device_manager.get_current_device_information()
        )
        if device_path == "" or not current_device_information:
            # No device actually connected or it isn't ready
            return None
        connected_device_info = current_device_information.get("info", None)
        drive_info = connected_device_info[4]
        debug_print("KoboUtilities:get_device - drive_info:", drive_info)
        library_db = self.gui.library_view.model().db
        device_uuid = drive_info["main"]["device_store_uuid"]
        current_device_profile = cfg.get_book_profile_for_device(
            library_db, device_uuid, use_any_device=True
        )
        current_device_config = cfg.get_device_config(device_uuid)
        device_name = cfg.get_device_name(device_uuid, device.gui_name)
        debug_print("KoboUtilities:get_device - device_name:", device_name)
        individual_device_options = cfg.get_plugin_pref(
            cfg.COMMON_OPTIONS_STORE_NAME, cfg.KEY_INDIVIDUAL_DEVICE_OPTIONS
        )
        if individual_device_options:
            current_backup_config = cfg.get_prefs(
                current_device_config, cfg.BACKUP_OPTIONS_STORE_NAME
            )
        else:
            current_backup_config = cfg.get_plugin_prefs(
                cfg.BACKUP_OPTIONS_STORE_NAME, fill_defaults=True
            )

        supports_series = (
            isinstance(device, KOBOTOUCH)
            and "supports_series" in dir(device)
            and device.supports_series()
        )
        supports_series_list = (
            isinstance(device, KOBOTOUCH)
            and "supports_series_list" in dir(device)
            and device.supports_series_list
            or device.dbversion > 136
        )
        supports_ratings = isinstance(device, KOBOTOUCH) and device.dbversion > 36
        try:
            epub_location_like_kepub = (
                isinstance(device, KOBOTOUCH)
                and device.fwversion >= device.min_fwversion_epub_location  # type: ignore[reportOperatorIssue]
            )
        except Exception:
            epub_location_like_kepub = isinstance(
                device, KOBOTOUCH
            ) and device.fwversion >= (4, 17, 13651)  # type: ignore[reportOperatorIssue]

        return KoboDevice(
            device,
            isinstance(device, KOBOTOUCH),
            current_device_profile,
            current_backup_config,
            connected_device_info,
            device_uuid,
            version_info,
            supports_series,
            supports_series_list,
            supports_ratings,
            epub_location_like_kepub,
            device_name,
            device_path,
        )

    @property
    def device_fwversion(self) -> Optional[Tuple[int, int, int]]:
        if self.device is not None:
            return cast(Tuple[int, int, int], self.device.device.fwversion)
        else:
            return None

    def get_device_path_from_id(self, book_id):
        paths = []
        for x in ("memory", "card_a"):
            x = getattr(self.gui, x + "_view").model()
            paths += x.paths_for_db_ids(set([book_id]), as_map=True)[book_id]
        return paths[0].path if paths else None

    def get_device_paths_from_id(self, book_id):
        paths = []
        for x in ("memory", "card_a"):
            x = getattr(self.gui, x + "_view").model()
            paths += x.paths_for_db_ids([book_id], as_map=True)[book_id]
        debug_print("get_device_paths_from_id - paths=", paths)
        return [r.path for r in paths]

    def get_device_paths_from_ids(self, book_ids):
        paths = defaultdict(list)
        for x in ("memory", "card_a"):
            x = getattr(self.gui, x + "_view").model()
            x = x.paths_for_db_ids(book_ids, as_map=True)
            for book_id in x.keys():
                paths[book_id].extend(x[book_id])
        return paths

    def get_device_path_from_contentID(self, contentID, mimetype):
        assert self.device is not None
        if contentID.startswith("file:///mnt/sd/"):
            card = "carda"
        else:
            card = "main"
        return self.device.device.path_from_contentid(contentID, "6", mimetype, card)

    def get_contentIDs_from_id(self, book_id):
        debug_print("get_contentIDs_from_id - book_id=", book_id)
        paths = []
        for x in ("memory", "card_a"):
            x = getattr(self.gui, x + "_view").model()
            paths += x.paths_for_db_ids(set([book_id]), as_map=True)[book_id]
        debug_print("get_contentIDs_from_id - paths=", paths)
        return [r.contentID for r in paths]

    def device_database_connection(self, use_row_factory=False):
        assert self.device is not None
        try:
            db_connection = self.device.device.device_database_connection()
        except AttributeError:
            import apsw  # type: ignore[reportMissingImports]

            db_connection = apsw.Connection(self.device_database_path())

        if use_row_factory:
            db_connection.setrowtrace(row_factory)

        return db_connection

    def _store_queue_job(self, options: Dict[str, Any], books_to_modify: List[Tuple]):
        debug_print("KoboUtilitiesAction::_store_queue_job")
        cpus = 1  # self.gui.device_manager.server.pool_size
        from .jobs import do_store_locations

        args = [books_to_modify, options, cpus]
        desc = _("Storing reading positions for {0} books").format(len(books_to_modify))
        self.gui.device_manager.create_job(
            do_store_locations,
            self.Dispatcher(self._store_completed),
            description=desc,
            args=args,
        )
        self.gui.status_bar.show_message(self.giu_name + " - " + desc, 3000)

    def _store_completed(self, job):
        if job.failed:
            self.gui.job_exception(
                job, dialog_title=_("Failed to get reading positions")
            )
            return
        modified_epubs_map, options = job.result
        debug_print("KoboUtilitiesAction::_store_completed - options", options)

        update_count = len(modified_epubs_map) if modified_epubs_map else 0
        if update_count == 0:
            self.gui.status_bar.show_message(
                _("Kobo Utilities")
                + " - "
                + _("Storing reading positions completed - No changes found"),
                3000,
            )
        else:
            goodreads_sync_plugin = None
            if options[cfg.KEY_PROMPT_TO_STORE]:
                profileName = (
                    options["profileName"] if "profileName" in options else None
                )
                db = self.gui.current_db

                if "Goodreads Sync" in self.gui.iactions:
                    goodreads_sync_plugin = self.gui.iactions["Goodreads Sync"]

                dlg = ShowReadingPositionChangesDialog(
                    self.gui,
                    self,
                    job.result,
                    db,
                    profileName,
                    goodreads_sync_plugin is not None,
                )
                dlg.exec_()
                if dlg.result() != dlg.Accepted:
                    debug_print("_store_completed - dialog cancelled")
                    return
                self.options = dlg.prefs
                modified_epubs_map = dlg.reading_locations
            self._update_database_columns(modified_epubs_map)

            if options[cfg.KEY_PROMPT_TO_STORE]:
                if (
                    self.options[cfg.KEY_SELECT_BOOKS_IN_LIBRARY]
                    or self.options[cfg.KEY_UPDATE_GOODREADS_PROGRESS]
                ):
                    self.gui.library_view.select_rows(list(modified_epubs_map.keys()))
                if (
                    goodreads_sync_plugin
                    and self.options[cfg.KEY_UPDATE_GOODREADS_PROGRESS]
                ):
                    debug_print(
                        "KoboUtilitiesAction::_store_completed - goodreads_sync_plugin.users.keys()=",
                        list(goodreads_sync_plugin.users.keys()),
                    )
                    goodreads_sync_plugin.update_reading_progress(
                        "progress", sorted(goodreads_sync_plugin.users.keys())[0]
                    )

    def _device_database_backup(self, backup_options):
        debug_print("KoboUtilitiesAction::_device_database_backup")

        cpus = 1  # self.gui.device_manager.server.pool_size
        from .jobs import do_device_database_backup

        args = [backup_options, cpus]
        desc = _("Backing up Kobo device database")
        job = self.gui.device_manager.create_job(
            do_device_database_backup,
            self.Dispatcher(self._device_database_backup_completed),
            description=desc,
            args=args,
        )
        job._tdir = None
        self.gui.status_bar.show_message(_("Kobo Utilities") + " - " + desc, 3000)

    def _device_database_backup_completed(self, job):
        if job.failed:
            self.gui.job_exception(
                job, dialog_title=_("Failed to backup device database")
            )
            return

    def _clean_images_dir_job(self, options):
        debug_print("KoboUtilitiesAction::_clean_images_dir_job")

        func = "arbitrary_n"
        cpus = self.gui.job_manager.server.pool_size
        args = [
            "calibre_plugins.koboutilities.jobs",
            "do_clean_images_dir",
            (options, cpus),
        ]
        desc = _("Cleaning images directory")
        self.gui.job_manager.run_job(
            self.Dispatcher(self._clean_images_dir_completed),
            func,
            args=args,
            description=desc,
        )
        self.gui.status_bar.show_message(_("Cleaning images directory") + "...")

    def _clean_images_dir_completed(self, job):
        if job.failed:
            self.gui.job_exception(
                job, dialog_title=_("Failed to check cover directory on device")
            )
            return
        extra_image_files = job.result
        extra_covers_count = len(extra_image_files["main_memory"]) + len(
            extra_image_files["sd_card"]
        )
        self.gui.status_bar.show_message(_("Checking cover directory completed"), 3000)

        details = ""
        if extra_covers_count == 0:
            msg = _("No extra files found")
        else:
            msg = _(
                "Kobo Utilities found <b>{0} extra cover(s)</b> in the cover directory."
            ).format(extra_covers_count)
            if self.options["delete_extra_covers"]:
                msg += "\n" + _("All files have been deleted.")
            if len(extra_image_files["main_memory"]):
                details += (
                    "\n"
                    + _("Extra files found in main memory images directory:")
                    + "\n"
                )
                for filename in extra_image_files["main_memory"]:
                    details += "\t%s\n" % filename

            if len(extra_image_files["sd_card"]):
                details += (
                    "\n" + _("Extra files found in SD card images directory:") + "\n"
                )
                for filename in extra_image_files["sd_card"]:
                    details += "\t%s\n" % filename

        return info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Finished"),
            msg,
            show_copy_button=True,
            show=True,
            det_msg=details,
        )

    def _remove_annotations_job(self, options, books):
        debug_print("KoboUtilitiesAction::_remove_annotations_job")

        func = "arbitrary_n"
        cpus = self.gui.job_manager.server.pool_size
        args = [
            "calibre_plugins.koboutilities.jobs",
            "do_remove_annotations",
            (options, books, cpus),
        ]
        desc = _("Removing annotations files")
        self.gui.job_manager.run_job(
            self.Dispatcher(self._remove_annotations_completed),
            func,
            args=args,
            description=desc,
        )
        self.gui.status_bar.show_message(_("Removing annotations files") + "...")

    def _remove_annotations_completed(self, job):
        if job.failed:
            self.gui.job_exception(
                job, dialog_title=_("Failed to check cover directory on device")
            )
            return
        annotations_removed = job.result
        msg = annotations_removed["message"]
        self.gui.status_bar.show_message(_("Cleaning annotations completed"), 3000)

        details = ""
        if msg:
            pass
        else:
            msg = _("Kobo Utilities removed <b>{0} annotation files(s)</b>.").format(0)

        return info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Finished"),
            msg,
            show_copy_button=True,
            show=True,
            det_msg=details,
        )

    def validate_profile(self, profile_name=None):
        columns_config = None
        if profile_name:
            profile = cfg.get_profile_info(self.gui.current_db, profile_name)
            columns_config = profile.get(cfg.CUSTOM_COLUMNS_STORE_NAME, None)
        elif self.device is not None and self.device.profile is not None:
            columns_config = self.device.profile[cfg.CUSTOM_COLUMNS_STORE_NAME]

        if columns_config is None:
            return "{0}\n\n{1}".format(
                _('Profile "{0}" does not exist.').format(profile_name),
                _("Select another profile to proceed."),
            )

        custom_cols = self.gui.current_db.field_metadata.custom_field_metadata(
            include_composites=False
        )

        def check_column_name(column_name):
            return (
                None
                if column_name is None or len(column_name.strip()) == 0
                else column_name
            )

        def check_column_exists(column_name):
            return column_name is not None and column_name in custom_cols

        debug_print("validate_profile - columns_config:", columns_config)
        kobo_chapteridbookmarked_column = columns_config.get(
            cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN,
            cfg.CUSTOM_COLUMNS_OPTIONS_DEFAULTS[cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN],
        )
        kobo_percentRead_column = columns_config.get(
            cfg.KEY_PERCENT_READ_CUSTOM_COLUMN,
            cfg.CUSTOM_COLUMNS_OPTIONS_DEFAULTS[cfg.KEY_PERCENT_READ_CUSTOM_COLUMN],
        )
        rating_column = columns_config.get(
            cfg.KEY_RATING_CUSTOM_COLUMN,
            cfg.CUSTOM_COLUMNS_OPTIONS_DEFAULTS[cfg.KEY_RATING_CUSTOM_COLUMN],
        )
        last_read_column = columns_config.get(
            cfg.KEY_LAST_READ_CUSTOM_COLUMN,
            cfg.CUSTOM_COLUMNS_OPTIONS_DEFAULTS[cfg.KEY_LAST_READ_CUSTOM_COLUMN],
        )

        kobo_chapteridbookmarked_column = check_column_name(
            kobo_chapteridbookmarked_column
        )
        kobo_percentRead_column = check_column_name(kobo_percentRead_column)
        rating_column = check_column_name(rating_column)
        last_read_column = check_column_name(last_read_column)

        if (
            kobo_chapteridbookmarked_column is None
            and kobo_percentRead_column is None
            and rating_column is None
            and last_read_column is None
        ):
            return "{0} {1}\n\n{2}".format(
                _('Profile "{0}" is invalid.').format(profile_name),
                _("It has no columns to store the reading status."),
                _("Select another profile to proceed."),
            )

        kobo_chapteridbookmarked_column_exists = check_column_exists(
            kobo_chapteridbookmarked_column
        )
        kobo_percentRead_column_exists = check_column_exists(kobo_percentRead_column)
        if rating_column is not None:
            rating_column_exists = rating_column == "rating" or check_column_exists(
                rating_column
            )
        else:
            rating_column_exists = False
        last_read_column_exists = check_column_exists(last_read_column)

        invalid_columns = []
        if (
            kobo_chapteridbookmarked_column is not None
            and not kobo_chapteridbookmarked_column_exists
        ):
            invalid_columns.append(kobo_chapteridbookmarked_column)
        if kobo_percentRead_column is not None and not kobo_percentRead_column_exists:
            invalid_columns.append(kobo_percentRead_column)
        if rating_column is not None and not rating_column_exists:
            invalid_columns.append(rating_column)
        if last_read_column is not None and not last_read_column_exists:
            invalid_columns.append(last_read_column)

        if len(invalid_columns) > 0:
            invalid_columns_string = ", ".join(
                ['"{0}"'.format(invalid_column) for invalid_column in invalid_columns]
            )
            invalid_columns_msg = (
                _("The column {0} does not exist.")
                if len(invalid_columns) == 1
                else _("The columns {0} do not exist.")
            )
            return "{0} {1}\n\n{2}".format(
                _('Profile "{0}" is invalid.').format(profile_name),
                invalid_columns_msg.format(invalid_columns_string),
                _("Select another profile to proceed."),
            )

        return None

    def get_column_names(self, profile_name=None):
        if profile_name:
            profile = cfg.get_profile_info(self.gui.current_db, profile_name)
            columns_config = profile[cfg.CUSTOM_COLUMNS_STORE_NAME]
        elif self.device is not None and self.device.profile is not None:
            columns_config = self.device.profile[cfg.CUSTOM_COLUMNS_STORE_NAME]
        else:
            return None, None, None, None, None, None

        debug_print("get_column_names - columns_config:", columns_config)
        kobo_chapteridbookmarked_column = columns_config.get(
            cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN,
            cfg.CUSTOM_COLUMNS_OPTIONS_DEFAULTS[cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN],
        )
        kobo_percentRead_column = columns_config.get(
            cfg.KEY_PERCENT_READ_CUSTOM_COLUMN,
            cfg.CUSTOM_COLUMNS_OPTIONS_DEFAULTS[cfg.KEY_PERCENT_READ_CUSTOM_COLUMN],
        )
        rating_column = columns_config.get(
            cfg.KEY_RATING_CUSTOM_COLUMN,
            cfg.CUSTOM_COLUMNS_OPTIONS_DEFAULTS[cfg.KEY_RATING_CUSTOM_COLUMN],
        )
        last_read_column = columns_config.get(
            cfg.KEY_LAST_READ_CUSTOM_COLUMN,
            cfg.CUSTOM_COLUMNS_OPTIONS_DEFAULTS[cfg.KEY_LAST_READ_CUSTOM_COLUMN],
        )
        time_spent_reading_column = columns_config.get(
            cfg.KEY_TIME_SPENT_READING_COLUMN,
            cfg.CUSTOM_COLUMNS_OPTIONS_DEFAULTS[cfg.KEY_TIME_SPENT_READING_COLUMN],
        )
        rest_of_book_estimate_column = columns_config.get(
            cfg.KEY_REST_OF_BOOK_ESTIMATE_COLUMN,
            cfg.CUSTOM_COLUMNS_OPTIONS_DEFAULTS[cfg.KEY_REST_OF_BOOK_ESTIMATE_COLUMN],
        )

        custom_cols = self.gui.current_db.field_metadata.custom_field_metadata(
            include_composites=False
        )
        kobo_chapteridbookmarked_column = (
            kobo_chapteridbookmarked_column
            if kobo_chapteridbookmarked_column in custom_cols
            else None
        )
        kobo_percentRead_column = (
            kobo_percentRead_column if kobo_percentRead_column in custom_cols else None
        )
        if rating_column is not None:
            if rating_column != "rating":
                rating_column = rating_column if rating_column in custom_cols else None
        last_read_column = last_read_column if last_read_column in custom_cols else None
        time_spent_reading_column = (
            time_spent_reading_column
            if time_spent_reading_column in custom_cols
            else None
        )
        rest_of_book_estimate_column = (
            rest_of_book_estimate_column
            if rest_of_book_estimate_column in custom_cols
            else None
        )

        return (
            kobo_chapteridbookmarked_column,
            kobo_percentRead_column,
            rating_column,
            last_read_column,
            time_spent_reading_column,
            rest_of_book_estimate_column,
        )

    def get_rating_column(self, profile_name=None):
        (
            _kobo_chapteridbookmarked_column,
            _kobo_percentRead_column,
            rating_column,
            _last_read_column,
            _time_spent_reading_column,
            _rest_of_book_estimate_column,
        ) = self.get_column_names()
        return rating_column

    def _update_database_columns(self, reading_locations):
        debug_print("_update_database_columns - reading_locations=", reading_locations)
        debug_print(
            "_update_database_columns - start number of reading_locations= %d"
            % (len(reading_locations))
        )
        self.progressbar(_("Storing reading positions"), on_top=True)
        total_books = len(reading_locations)
        self.show_progressbar(total_books)

        library_db = self.gui.current_db

        def value_changed(old_value, new_value):
            return (
                old_value is not None
                and new_value is None
                or old_value is None
                and new_value is not None
                or not old_value == new_value
            )

        (
            kobo_chapteridbookmarked_column_name,
            kobo_percentRead_column_name,
            rating_column_name,
            last_read_column_name,
            time_spent_reading_column_name,
            rest_of_book_estimate_column_name,
        ) = self.get_column_names()

        if kobo_chapteridbookmarked_column_name is not None:
            debug_print(
                "_update_database_columns - kobo_chapteridbookmarked_column_name=",
                kobo_chapteridbookmarked_column_name,
            )
            kobo_chapteridbookmarked_col_label = library_db.field_metadata.key_to_label(
                kobo_chapteridbookmarked_column_name
            )
            debug_print(
                "_update_database_columns - kobo_chapteridbookmarked_col_label=",
                kobo_chapteridbookmarked_col_label,
            )

        debug_print(
            "_update_database_columns - kobo_chapteridbookmarked_column_name=",
            kobo_chapteridbookmarked_column_name,
        )
        debug_print(
            "_update_database_columns - kobo_percentRead_column_name=",
            kobo_percentRead_column_name,
        )
        debug_print(
            "_update_database_columns - rating_column_name=", rating_column_name
        )
        debug_print(
            "_update_database_columns - last_read_column_name=", last_read_column_name
        )
        debug_print(
            "_update_database_columns - time_spent_reading_column_name=",
            time_spent_reading_column_name,
        )
        debug_print(
            "_update_database_columns - rest_of_book_estimate_column_name=",
            rest_of_book_estimate_column_name,
        )
        # At this point we want to re-use code in edit_metadata to go ahead and
        # apply the changes. So we will create empty Metadata objects so only
        # the custom column field gets updated
        id_map = {}
        id_map_percentRead = {}
        id_map_chapteridbookmarked = {}
        id_map_rating = {}
        id_map_last_read = {}
        id_map_time_spent_reading = {}
        id_map_rest_of_book_estimate = {}
        for book_id, reading_location in list(reading_locations.items()):
            mi = Metadata(_("Unknown"))
            book_mi = library_db.get_metadata(
                book_id, index_is_id=True, get_cover=False
            )
            book = Book("", "lpath", title=book_mi.title, other=book_mi)
            self.set_progressbar_label(_("Updating ") + book_mi.title)
            self.increment_progressbar()

            kobo_chapteridbookmarked = None
            kobo_adobe_location = None
            kobo_percentRead = None
            last_read = None
            time_spent_reading = None
            rest_of_book_estimate = None
            if reading_location is not None:
                debug_print(
                    "_update_database_columns - reading_location=", reading_location
                )
                if (
                    reading_location["MimeType"] == MIMETYPE_KOBO
                    or self.epub_location_like_kepub
                ):
                    kobo_chapteridbookmarked = reading_location["ChapterIDBookmarked"]
                    kobo_adobe_location = None
                else:
                    kobo_chapteridbookmarked = (
                        reading_location["ChapterIDBookmarked"][
                            len(reading_location["ContentID"]) + 1 :
                        ]
                        if reading_location["ChapterIDBookmarked"]
                        else None
                    )
                    kobo_adobe_location = reading_location["adobe_location"]

                if reading_location["ReadStatus"] == 1:
                    kobo_percentRead = reading_location["___PercentRead"]
                elif reading_location["ReadStatus"] == 2:
                    kobo_percentRead = 100

                if reading_location["Rating"]:
                    kobo_rating = reading_location["Rating"] * 2
                else:
                    kobo_rating = 0

                if reading_location["DateLastRead"]:
                    last_read = convert_kobo_date(reading_location["DateLastRead"])

                if reading_location["TimeSpentReading"]:
                    time_spent_reading = reading_location["TimeSpentReading"]

                if reading_location["RestOfBookEstimate"]:
                    rest_of_book_estimate = reading_location["RestOfBookEstimate"]

            elif self.options[cfg.KEY_CLEAR_IF_UNREAD]:
                kobo_chapteridbookmarked = None
                kobo_adobe_location = None
                kobo_percentRead = None
                last_read = None
                kobo_rating = 0
                time_spent_reading = None
                rest_of_book_estimate = None
            else:
                continue

            book_updated = False
            if last_read_column_name is not None:
                last_read_metadata = book.get_user_metadata(last_read_column_name, True)
                assert last_read_metadata is not None
                current_last_read = last_read_metadata["#value#"]
                debug_print(
                    "_update_database_columns - book.get_user_metadata(last_read_column_name, True)['#value#']=",
                    current_last_read,
                )
                debug_print(
                    "_update_database_columns - setting mi.last_read=", last_read
                )
                debug_print(
                    "_update_database_columns - current_last_read == last_read=",
                    current_last_read == last_read,
                )

                if value_changed(current_last_read, last_read):
                    id_map_last_read[book_id] = last_read
                    book_updated = True
                else:
                    book_updated = book_updated or False

            if kobo_chapteridbookmarked_column_name is not None:
                debug_print(
                    "_update_database_columns - kobo_chapteridbookmarked='%s'"
                    % (kobo_chapteridbookmarked)
                )
                debug_print(
                    "_update_database_columns - kobo_adobe_location='%s'"
                    % (kobo_adobe_location)
                )
                debug_print(
                    "_update_database_columns - kobo_percentRead=", kobo_percentRead
                )
                if (
                    kobo_chapteridbookmarked is not None
                    and kobo_adobe_location is not None
                ):
                    new_value = (
                        kobo_chapteridbookmarked
                        + BOOKMARK_SEPARATOR
                        + kobo_adobe_location
                    )
                elif kobo_chapteridbookmarked:
                    new_value = kobo_chapteridbookmarked
                else:
                    new_value = None
                    debug_print(
                        "_update_database_columns - setting bookmark column to None"
                    )
                debug_print(
                    "_update_database_columns - chapterIdBookmark - on kobo=", new_value
                )
                metadata = book.get_user_metadata(
                    kobo_chapteridbookmarked_column_name, True
                )
                assert metadata is not None
                old_value = metadata["#value#"]
                debug_print(
                    "_update_database_columns - chapterIdBookmark - in library=",
                    old_value,
                )
                debug_print(
                    "_update_database_columns - chapterIdBookmark - on kobo==in library=",
                    new_value == old_value,
                )

                if value_changed(old_value, new_value):
                    id_map_chapteridbookmarked[book_id] = new_value
                    book_updated = True
                else:
                    book_updated = book_updated or False

            if kobo_percentRead_column_name is not None:
                debug_print(
                    "_update_database_columns - setting kobo_percentRead=",
                    kobo_percentRead,
                )
                metadata = book.get_user_metadata(kobo_percentRead_column_name, True)
                assert metadata is not None
                current_percentRead = metadata["#value#"]
                debug_print(
                    "_update_database_columns - percent read - in book=",
                    current_percentRead,
                )

                if value_changed(current_percentRead, kobo_percentRead):
                    id_map_percentRead[book_id] = kobo_percentRead
                    book_updated = True
                else:
                    book_updated = book_updated or False

            if rating_column_name is not None and kobo_rating > 0:
                debug_print(
                    "_update_database_columns - setting rating_column_name=",
                    rating_column_name,
                )
                if rating_column_name == "rating":
                    current_rating = book.rating
                    debug_print(
                        "_update_database_columns - rating - in book=", current_rating
                    )
                else:
                    metadata = book.get_user_metadata(rating_column_name, True)
                    assert metadata is not None
                    current_rating = metadata["#value#"]
                if value_changed(current_rating, kobo_rating):
                    id_map_rating[book_id] = kobo_rating
                    book_updated = True
                else:
                    book_updated = book_updated or False

            if time_spent_reading_column_name is not None:
                metadata = book.get_user_metadata(time_spent_reading_column_name, True)
                assert metadata is not None
                current_time_spent_reading = metadata["#value#"]
                debug_print(
                    "_update_database_columns - book.get_user_metadata(time_spent_reading_column_name, True)['#value#']=",
                    current_time_spent_reading,
                )
                debug_print(
                    "_update_database_columns - setting mi.time_spent_reading=",
                    time_spent_reading,
                )
                debug_print(
                    "_update_database_columns - current_time_spent_reading == time_spent_reading=",
                    current_time_spent_reading == time_spent_reading,
                )

                if value_changed(current_time_spent_reading, time_spent_reading):
                    id_map_time_spent_reading[book_id] = time_spent_reading
                    book_updated = True
                else:
                    book_updated = book_updated or False

            if rest_of_book_estimate_column_name is not None:
                metadata = book.get_user_metadata(
                    rest_of_book_estimate_column_name, True
                )
                assert metadata is not None
                current_rest_of_book_estimate = metadata["#value#"]
                debug_print(
                    "_update_database_columns - book.get_user_metadata(rest_of_book_estimate_column_name , True)['#value#']=",
                    current_rest_of_book_estimate,
                )
                debug_print(
                    "_update_database_columns - setting mi.rest_of_book_estimate=",
                    rest_of_book_estimate,
                )
                debug_print(
                    "_update_database_columns - current_rest_of_book_estimate == rest_of_book_estimate=",
                    current_rest_of_book_estimate == rest_of_book_estimate,
                )

                if value_changed(current_rest_of_book_estimate, rest_of_book_estimate):
                    id_map_rest_of_book_estimate[book_id] = rest_of_book_estimate
                    book_updated = True
                else:
                    book_updated = book_updated or False

            id_map[book_id] = mi

        if kobo_chapteridbookmarked_column_name:
            debug_print(
                "_update_database_columns - Updating metadata - for column: %s number of changes=%d"
                % (
                    kobo_chapteridbookmarked_column_name,
                    len(id_map_chapteridbookmarked),
                )
            )
            library_db.new_api.set_field(
                kobo_chapteridbookmarked_column_name, id_map_chapteridbookmarked
            )
        if kobo_percentRead_column_name:
            debug_print(
                "_update_database_columns - Updating metadata - for column: %s number of changes=%d"
                % (kobo_percentRead_column_name, len(id_map_percentRead))
            )
            library_db.new_api.set_field(
                kobo_percentRead_column_name, id_map_percentRead
            )
        if rating_column_name:
            debug_print(
                "_update_database_columns - Updating metadata - for column: %s number of changes=%d"
                % (rating_column_name, len(id_map_rating))
            )
            library_db.new_api.set_field(rating_column_name, id_map_rating)
        if last_read_column_name:
            debug_print(
                "_update_database_columns - Updating metadata - for column: %s number of changes=%d"
                % (last_read_column_name, len(id_map_last_read))
            )
            library_db.new_api.set_field(last_read_column_name, id_map_last_read)
        if time_spent_reading_column_name:
            debug_print(
                "_update_database_columns - Updating metadata - for column: %s number of changes=%d"
                % (time_spent_reading_column_name, len(id_map_time_spent_reading))
            )
            library_db.new_api.set_field(
                time_spent_reading_column_name, id_map_time_spent_reading
            )
        if rest_of_book_estimate_column_name:
            debug_print(
                "_update_database_columns - Updating metadata - for column: %s number of changes=%d"
                % (
                    rest_of_book_estimate_column_name,
                    len(id_map_rest_of_book_estimate),
                )
            )
            library_db.new_api.set_field(
                rest_of_book_estimate_column_name, id_map_rest_of_book_estimate
            )

        debug_print("_update_database_columns - Updating GUI - new DB engine")
        self.gui.iactions["Edit Metadata"].refresh_gui(list(reading_locations))
        debug_print("_update_database_columns - finished")

        self.hide_progressbar()
        self.gui.status_bar.show_message(
            _("Kobo Utilities")
            + " - "
            + _("Storing reading positions completed - {0} changed.").format(
                len(reading_locations)
            ),
            3000,
        )

    def _getAnnotationForSelected(self, *args):
        assert self.device is not None

        # Generate a path_map from selected ids
        def get_ids_from_selected_rows():
            rows = self.gui.library_view.selectionModel().selectedRows()
            if not rows or len(rows) < 1:
                rows = range(self.gui.library_view.model().rowCount(QModelIndex()))
            ids = list(map(self.gui.library_view.model().id, rows))
            return ids

        def get_formats(_id):
            formats = db.formats(_id, index_is_id=True)
            fmts = []
            if formats:
                for format in formats.split(","):
                    fmts.append(format.lower())
            return fmts

        def generate_annotation_paths(ids, db, device):
            # Generate path templates
            # Individual storage mount points scanned/resolved in driver.get_annotations()
            path_map = {}
            for _id in ids:
                paths = self.get_device_paths_from_id(_id)
                debug_print("generate_annotation_paths - paths=", paths)
                if len(paths) > 0:
                    the_path = paths[0]
                    if len(paths) > 1:
                        if (
                            len(os.path.splitext(paths[0])) > 1
                        ):  # No extension - is kepub
                            the_path = paths[1]
                    path_map[_id] = {"path": the_path, "fmts": get_formats(_id)}
            return path_map

        annotationText = []

        if self.gui.current_view() is not self.gui.library_view:
            return error_dialog(
                self.gui,
                _("Use library only"),
                _("User annotations generated from main library only"),
                show=True,
            )
        db = self.gui.library_view.model().db

        # Get the list of ids
        ids = get_ids_from_selected_rows()
        if not ids:
            return error_dialog(
                self.gui,
                _("No books selected"),
                _("No books selected to fetch annotations from"),
                show=True,
            )

        debug_print("_getAnnotationForSelected - ids=", ids)
        # Map ids to paths
        path_map = generate_annotation_paths(ids, db, self.device)
        debug_print("_getAnnotationForSelected - path_map=", path_map)
        if len(path_map) == 0:
            return error_dialog(
                self.gui,
                _("No books on device selected"),
                _(
                    "None of the books selected were on the device. Annotations can only be copied for books on the device."
                ),
                show=True,
            )

        from calibre.ebooks.metadata import authors_to_string

        # Dispatch to the device get_annotations()
        debug_print("_getAnnotationForSelected - path_map=", path_map)
        bookmarked_books = self.device.device.get_annotations(path_map)
        debug_print("_getAnnotationForSelected - bookmarked_books=", bookmarked_books)

        for id_ in bookmarked_books:
            bm = self.device.device.UserAnnotation(
                bookmarked_books[id_][0], bookmarked_books[id_][1]
            )

            mi = db.get_metadata(id_, index_is_id=True)

            user_notes_soup = self.device.device.generate_annotation_html(bm.value)
            book_heading = "<b>%(title)s</b> by <b>%(author)s</b>" % dict(
                title=mi.title, author=authors_to_string(mi.authors)
            )
            bookmark_html = str(user_notes_soup.div)
            debug_print("_getAnnotationForSelected - bookmark_html:", bookmark_html)
            annotationText.append(book_heading + bookmark_html)

        d = ViewLog(
            "Kobo Touch Annotation", "\n<hr/>\n".join(annotationText), parent=self.gui
        )
        d.setWindowIcon(self.qaction.icon())
        d.exec_()

    def _upload_covers(self, books):
        uploaded_covers = 0
        total_books = 0
        not_on_device_books = len(books)
        device = self.device
        assert device is not None

        kobo_kepub_dir = device.device.normalize_path(".kobo/kepub/")
        sd_kepub_dir = device.device.normalize_path("koboExtStorage/kepub/")
        debug_print("_upload_covers - kobo_kepub_dir=", kobo_kepub_dir)
        # Extra cover upload options were added in calibre 3.45.
        driver_supports_extended_cover_options = hasattr(self.device, "dithered_covers")
        driver_supports_cover_letterbox_colors = hasattr(
            self.device, "letterbox_fs_covers_color"
        )

        for book in books:
            total_books += 1
            paths = self.get_device_paths_from_id(book.calibre_id)
            not_on_device_books -= 1 if len(paths) > 0 else 0
            for path in paths:
                debug_print("_upload_covers - path=", path)
                if (
                    kobo_kepub_dir not in path and sd_kepub_dir not in path
                ) or self.options[cfg.KEY_COVERS_UPDLOAD_KEPUB]:
                    if isinstance(device.device, KOBOTOUCH):
                        if driver_supports_cover_letterbox_colors:
                            device.device._upload_cover(
                                path,
                                "",
                                book,
                                path,
                                self.options[cfg.KEY_COVERS_BLACKANDWHITE],
                                dithered_covers=self.options[cfg.KEY_COVERS_DITHERED],
                                keep_cover_aspect=self.options[
                                    cfg.KEY_COVERS_KEEP_ASPECT_RATIO
                                ],
                                letterbox_fs_covers=self.options[
                                    cfg.KEY_COVERS_LETTERBOX
                                ],
                                letterbox_color=cast(
                                    str, self.options[cfg.KEY_COVERS_LETTERBOX_COLOR]
                                ),
                                png_covers=self.options[cfg.KEY_COVERS_PNG],
                            )
                        elif driver_supports_extended_cover_options:
                            device.device._upload_cover(
                                path,
                                "",
                                book,
                                path,
                                self.options[cfg.KEY_COVERS_BLACKANDWHITE],
                                dithered_covers=self.options[cfg.KEY_COVERS_DITHERED],
                                keep_cover_aspect=self.options[
                                    cfg.KEY_COVERS_KEEP_ASPECT_RATIO
                                ],
                                letterbox_fs_covers=self.options[
                                    cfg.KEY_COVERS_LETTERBOX
                                ],
                                png_covers=self.options[cfg.KEY_COVERS_PNG],
                            )
                        else:
                            device.device._upload_cover(
                                path,
                                "",
                                book,
                                path,
                                self.options[cfg.KEY_COVERS_BLACKANDWHITE],
                                keep_cover_aspect=self.options[
                                    cfg.KEY_COVERS_KEEP_ASPECT_RATIO
                                ],
                            )
                    else:
                        device.device._upload_cover(
                            path,
                            "",
                            book,
                            path,
                            self.options[cfg.KEY_COVERS_BLACKANDWHITE],
                        )
                    uploaded_covers += 1

        return total_books, uploaded_covers, not_on_device_books

    def _remove_covers(self, books):
        connection = self.device_database_connection()
        total_books = 0
        removed_covers = 0
        not_on_device_books = 0

        device = self.device
        # These should have been checked in the calling method
        assert device is not None
        assert isinstance(device.device, KOBOTOUCH)

        remove_fullsize_covers = self.options[cfg.KEY_REMOVE_FULLSIZE_COVERS]
        debug_print("_remove_covers - remove_fullsize_covers=", remove_fullsize_covers)

        imageId_query = (
            "SELECT ImageId "
            "FROM content "
            "WHERE ContentType = ? "
            "AND ContentId = ?"
        )  # fmt: skip
        cursor = connection.cursor()

        for book in books:
            debug_print("_remove_covers - book=", book)
            debug_print("_remove_covers - book.__class__=", book.__class__)
            debug_print("_remove_covers - book.contentID=", book.contentID)
            debug_print("_remove_covers - book.lpath=", book.lpath)
            debug_print("_remove_covers - book.path=", book.path)
            contentIDs = (
                [book.contentID]
                if book.contentID is not None
                else self.get_contentIDs_from_id(book.calibre_id)
            )
            debug_print("_remove_covers - contentIDs=", contentIDs)
            for contentID in contentIDs:
                debug_print("_remove_covers - contentID=", contentID)
                if (
                    not contentID
                    or "file:///" not in contentID
                    and not self.options[cfg.KEY_COVERS_UPDLOAD_KEPUB]
                ):
                    continue

                if contentID.startswith("file:///mnt/sd/"):
                    path = device.device._card_a_prefix
                else:
                    path = device.device._main_prefix

                query_values = (
                    self.CONTENTTYPE,
                    contentID,
                )
                cursor.execute(imageId_query, query_values)
                try:
                    result = next(cursor)
                    debug_print(
                        "_remove_covers - contentId='%s', imageId='%s'"
                        % (contentID, result[0])
                    )
                    image_id = result[0]
                    debug_print("_remove_covers - image_id=", image_id)
                    if image_id is not None:
                        image_path = device.device.images_path(path, image_id)
                        debug_print("_remove_covers - image_path=%s" % image_path)

                        for ending in list(device.device.cover_file_endings().keys()):
                            debug_print("_remove_covers - ending='%s'" % ending)
                            if (
                                remove_fullsize_covers
                                and not ending == " - N3_FULL.parsed"
                            ):
                                debug_print(
                                    "_remove_covers - not the full sized cover. Skipping"
                                )
                                continue
                            fpath = image_path + ending
                            fpath = device.device.normalize_path(fpath)
                            assert isinstance(fpath, str)
                            debug_print("_remove_covers - fpath=%s" % fpath)

                            if os.path.exists(fpath):
                                debug_print("_remove_covers - Image File Exists")
                                os.unlink(fpath)

                        try:
                            os.removedirs(os.path.dirname(image_path))
                        except Exception:
                            pass
                    removed_covers += 1
                except StopIteration:
                    debug_print(
                        "_remove_covers - no match for contentId='%s'" % (contentID,)
                    )
                    not_on_device_books += 1
                total_books += 1

        return removed_covers, not_on_device_books, total_books

    def _open_cover_image_directory(self, books):
        connection = self.device_database_connection(use_row_factory=True)
        total_books = 0
        removed_covers = 0
        not_on_device_books = 0

        device = self.device
        assert device is not None
        assert isinstance(device.device, KOBOTOUCH)

        imageId_query = (
            "SELECT ImageId "
            "FROM content "
            "WHERE ContentType = ? "
            "AND ContentId = ?"
        )  # fmt: skip
        cursor = connection.cursor()

        for book in books:
            debug_print("_open_cover_image_directory - book=", book)
            debug_print("_open_cover_image_directory - book.__class__=", book.__class__)
            debug_print("_open_cover_image_directory - book.contentID=", book.contentID)
            debug_print("_open_cover_image_directory - book.lpath=", book.lpath)
            debug_print("_open_cover_image_directory - book.path=", book.path)
            contentIDs = (
                [book.contentID]
                if book.contentID is not None
                else self.get_contentIDs_from_id(book.calibre_id)
            )
            debug_print("_open_cover_image_directory - contentIDs=", contentIDs)
            for contentID in contentIDs:
                debug_print("_open_cover_image_directory - contentID=", contentID)

                if contentID is None:
                    debug_print(
                        "_open_cover_image_directory - Book does not have a content id."
                    )
                    continue
                elif contentID.startswith("file:///mnt/sd/"):
                    path = device.device._card_a_prefix
                else:
                    path = device.device._main_prefix

                query_values = (
                    self.CONTENTTYPE,
                    contentID,
                )
                cursor.execute(imageId_query, query_values)
                image_id = None
                try:
                    result = next(cursor)
                    debug_print(
                        "_open_cover_image_directory - contentId='%s', imageId='%s'"
                        % (contentID, result["ImageId"])
                    )
                    image_id = result["ImageId"]
                except StopIteration:
                    debug_print(
                        "_open_cover_image_directory - no match for contentId='%s'"
                        % (contentID,)
                    )
                    image_id = device.device.imageid_from_contentid(contentID)

                if image_id:
                    cover_image_file = device.device.images_path(path, image_id)
                    debug_print(
                        "_open_cover_image_directory - cover_image_file='%s'"
                        % (cover_image_file)
                    )
                    cover_dir = os.path.dirname(os.path.abspath(cover_image_file))
                    debug_print(
                        "_open_cover_image_directory - cover_dir='%s'" % (cover_dir)
                    )
                    if os.path.exists(cover_dir):
                        open_local_file(cover_dir)
                total_books += 1

        return removed_covers, not_on_device_books, total_books

    def _get_imageid_set(self):
        connection = self.device_database_connection(use_row_factory=True)
        imageId_query = (
            "SELECT DISTINCT ImageId "
            "FROM content "
            "WHERE BookID IS NULL"
        )  # fmt: skip
        cursor = connection.cursor()

        cursor.execute(imageId_query)
        imageIDs = {row["ImageId"] for row in cursor}

        return imageIDs

    def _check_book_in_database(self, books):
        connection = self.device_database_connection()
        not_on_device_books = []

        imageId_query = (
            "SELECT 1 "
            "FROM content "
            "WHERE BookID is NULL "
            "AND ContentId = ?"
        )  # fmt: skip
        cursor = connection.cursor()

        for book in books:
            if not book.contentID:
                book.contentID = self.contentid_from_path(book.path, self.CONTENTTYPE)

            query_values = (book.contentID,)
            cursor.execute(imageId_query, query_values)
            try:
                next(cursor)
            except StopIteration:
                debug_print(
                    "_check_book_in_database - no match for contentId='%s'"
                    % (book.contentID,)
                )
                not_on_device_books.append(book)

        return not_on_device_books

    def _get_shelf_count(self):
        connection = self.device_database_connection()
        shelves = []

        shelves_query = (
            "SELECT Name, MIN(CreationDate), MAX(CreationDate), COUNT(*), MAX(Id) "
            "FROM Shelf "
            "WHERE _IsDeleted = 'false' "
            "GROUP BY Name"
        )

        cursor = connection.cursor()
        cursor.execute(shelves_query)
        for i, row in enumerate(cursor):
            debug_print(
                "_get_shelf_count - row:", i, row[0], row[1], row[2], row[3], row[4]
            )
            shelves.append(
                [
                    row[0],
                    convert_kobo_date(row[1]),
                    convert_kobo_date(row[2]),
                    int(row[3]),
                    row[4],
                ]
            )

        return shelves

    def _get_series_shelf_count(self, order_shelf_type):
        debug_print("_get_series_shelf_count - order_shelf_type:", order_shelf_type)
        connection = self.device_database_connection()
        shelves = []

        series_query = (
            "SELECT s.InternalName, count(sc.ShelfName) "
            "FROM Shelf s LEFT OUTER JOIN ShelfContent sc on s.InternalName = sc.ShelfName "
            "WHERE s._IsDeleted = 'false' "
            "AND EXISTS (SELECT 1 FROM content c WHERE s.InternalName = c.Series ) "
            "GROUP BY s.InternalName"
        )
        authors_query = (
            "SELECT s.InternalName, count(sc.ShelfName) "
            "FROM Shelf s LEFT OUTER JOIN ShelfContent sc on s.InternalName = sc.ShelfName "
            "WHERE s._IsDeleted = 'false' "
            "AND EXISTS (SELECT 1 FROM content c WHERE s.InternalName = c.Attribution ) "
            "GROUP BY s.InternalName"
        )
        other_query = (
            "SELECT s.InternalName, count(sc.ShelfName) "
            "FROM Shelf s LEFT OUTER JOIN ShelfContent sc on name = sc.ShelfName "
            "WHERE s._IsDeleted = 'false' "
            "AND NOT EXISTS (SELECT 1 FROM content c WHERE s.InternalName = c.Attribution ) "
            "AND NOT EXISTS (SELECT 1 FROM content c WHERE s.InternalName = c.Series ) "
            "GROUP BY s.InternalName"
        )
        all_query = (
            "SELECT s.InternalName, count(sc.ShelfName) "
            "FROM Shelf s LEFT OUTER JOIN ShelfContent sc on s.InternalName = sc.ShelfName "
            "WHERE s._IsDeleted = 'false' "
            "GROUP BY s.InternalName"
        )

        shelves_queries = [series_query, authors_query, other_query, all_query]
        shelves_query = shelves_queries[order_shelf_type]
        debug_print("_get_series_shelf_count - shelves_query:", shelves_query)

        cursor = connection.cursor()
        cursor.execute(shelves_query)
        for i, row in enumerate(cursor):
            debug_print("_get_series_shelf_count - row:", i, row[0], row[1])
            shelf = {}
            shelf["name"] = row[0]
            shelf["count"] = int(row[1])
            shelves.append(shelf)

        debug_print("_get_series_shelf_count - shelves:", shelves)
        return shelves

    def _order_series_shelves(self, shelves, options):
        def urlquote(shelf_name):
            """Quote URL-unsafe characters, For unsafe characters, need "%xx" rather than the
            other encoding used for urls.
            Pulled from calibre.ebooks.oeb.base.py:urlquote"""
            ASCII_CHARS = {chr(x) for x in range(128)}
            UNIBYTE_CHARS = {chr(x) for x in range(256)}
            URL_SAFE = set(
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "abcdefghijklmnopqrstuvwxyz"
                "0123456789"
                "_.-/~"
            )  # fmt: skip
            URL_UNSAFE = [ASCII_CHARS - URL_SAFE, UNIBYTE_CHARS - URL_SAFE]
            result = []
            unsafe = 1 if isinstance(shelf_name, str) else 0
            unsafe = URL_UNSAFE[unsafe]
            for char in shelf_name:
                if char not in URL_SAFE:
                    char = ("%%%02x" % ord(char)).upper()
                    debug_print("urlquote - unsafe after ord char=", char)
                result.append(char)
            return "".join(result)

        debug_print("_order_series_shelves - shelves:", shelves, " options:", options)
        self.progressbar(_("Order Series Shelves"), on_top=False)
        self.show_progressbar(len(shelves))
        self.pb.left_align_label()

        starting_shelves = 0
        shelves_ordered = 0
        timeDiff = timedelta(0, 1)
        sort_descending = not options[cfg.KEY_SORT_DESCENDING]
        order_by = options[cfg.KEY_ORDER_SHELVES_BY]
        update_config = options[cfg.KEY_SORT_UPDATE_CONFIG]
        koboConfig = None
        config_file_path = None
        if update_config:
            koboConfig, config_file_path = self.get_config_file()
            debug_print(
                "_order_series_shelves - koboConfig={0}".format(koboConfig.sections())
            )
            for section in koboConfig.sections():
                debug_print(
                    "_order_series_shelves - koboConfig section={0}, options={1}".format(
                        section, koboConfig.options(section)
                    )
                )

        connection = self.device_database_connection(use_row_factory=True)
        shelves_query = (
            "SELECT sc.ShelfName, c.ContentId, c.Title, c.DateCreated, sc.DateModified, c.Series, c.SeriesNumber "
            "FROM ShelfContent sc JOIN content c on sc.ContentId= c.ContentId "
            "WHERE sc._IsDeleted = 'false' "
            "AND sc.ShelfName = ? "
            "ORDER BY sc.ShelfName, c.SeriesNumber"
        )
        update_query = (
            "UPDATE ShelfContent "
            "SET DateModified = ? "
            "WHERE ShelfName = ? "
            "AND ContentID = ? "
        )

        cursor = connection.cursor()
        for shelf in shelves:
            starting_shelves += 1
            debug_print(
                "_order_series_shelves - shelf=%s, count=%d"
                % (shelf["name"], shelf["count"])
            )
            self.set_progressbar_label(_("Updating shelf: {0}").format(shelf["name"]))
            self.increment_progressbar()
            if shelf["count"] <= 1:
                continue
            shelves_ordered += 1
            shelf_data = (shelf["name"],)
            debug_print("_order_series_shelves - shelf_data:", shelf_data)
            cursor.execute(shelves_query, shelf_data)
            shelf_dict = {}
            for i, row in enumerate(cursor):
                debug_print("_order_series_shelves - row:", i, row)
                debug_print(
                    "_order_series_shelves - row:",
                    i,
                    row["ShelfName"],
                    row["ContentID"],
                    row["Series"],
                    row["SeriesNumber"],
                )
                series_name = row["Series"] if row["Series"] else ""
                series_index = 0
                try:
                    series_index = (
                        float(row["SeriesNumber"])
                        if row["SeriesNumber"] is not None
                        else 0
                    )
                except Exception:
                    debug_print("_order_series_shelves - non numeric number")
                    numbers = re.findall(r"\d*\.?\d+", row["SeriesNumber"])
                    if len(numbers) > 0:
                        series_index = float(numbers[0])
                debug_print("_order_series_shelves - series_index=", series_index)
                if order_by == cfg.KEY_ORDER_SHELVES_PUBLISHED:
                    date_created = row["DateCreated"]
                    if date_created is None:
                        date_created = datetime.fromtimestamp(
                            time.mktime(time.gmtime())
                        )
                        date_created = strftime(
                            self.device_timestamp_string, date_created
                        )
                    sort_key = (date_created, row["Title"])
                else:
                    sort_key = (
                        (series_name, series_index, row["Title"])
                        if not series_name == ""
                        else (row["Title"], -1, "")
                    )
                debug_print("_order_series_shelves - sort_key:", sort_key)
                current_list = shelf_dict.get(sort_key, None)
                current_list = shelf_dict.get(sort_key, [])
                current_list.append(row["ContentID"])
                shelf_dict[sort_key] = current_list
            debug_print("_order_series_shelves - shelf_dict:", shelf_dict)

            debug_print(
                "_order_series_shelves - sorted shelf_dict:", sorted(shelf_dict)
            )

            lastModifiedTime = datetime.fromtimestamp(time.mktime(time.gmtime()))

            debug_print(
                "_order_series_shelves - lastModifiedTime=",
                lastModifiedTime,
                " timeDiff:",
                timeDiff,
            )
            for sort_key in sorted(shelf_dict, reverse=sort_descending):
                for contentId in shelf_dict[sort_key]:
                    update_data = (
                        strftime(
                            self.device_timestamp_string,
                            lastModifiedTime.timetuple(),
                        ),
                        shelf["name"],
                        contentId,
                    )
                    debug_print(
                        "_order_series_shelves - sort_key: ",
                        sort_key,
                        " update_data:",
                        update_data,
                    )
                    cursor.execute(update_query, update_data)
                    lastModifiedTime += timeDiff
            if update_config:
                try:
                    shelf_key = quote(
                        "LastLibrarySorter_shelf_filterByBookshelf("
                        + shelf["name"]
                        + ")"
                    )
                    shelf_key = quote(
                        "LastLibrarySorter_shelf_filterByBookshelf({0})".format(
                            shelf["name"]
                        )
                    )
                except Exception:
                    debug_print(
                        "_order_series_shelves - cannot encode shelf name=",
                        shelf["name"],
                    )
                    if isinstance(shelf["name"], str):
                        debug_print("_order_series_shelves - is unicode")
                        shelf_key = urlquote(shelf["name"])
                        shelf_key = (
                            quote("LastLibrarySorter_shelf_filterByBookshelf(")
                            + shelf_key
                            + quote(")")
                        )
                        shelf_key = quote(
                            "LastLibrarySorter_shelf_filterByBookshelf({0})".format(
                                shelf_key
                            )
                        )
                    else:
                        debug_print("_order_series_shelves - not unicode")
                        shelf_key = (
                            "LastLibrarySorter_shelf_filterByBookshelf("
                            + shelf["name"]
                            + ")"
                        )
                        shelf_key = (
                            "LastLibrarySorter_shelf_filterByBookshelf({0}".format(
                                shelf["name"]
                            )
                        )
                assert koboConfig is not None
                koboConfig.set(
                    "ApplicationPreferences", shelf_key, "sortByDateAddedToShelf()"
                )
                debug_print("_order_series_shelves - koboConfig=", koboConfig)

        if update_config:
            assert config_file_path is not None
            with open(config_file_path, "w") as config_file:
                debug_print("_order_series_shelves - writing config file")
                assert koboConfig is not None
                koboConfig.write(config_file)

        self.hide_progressbar()
        debug_print("_order_series_shelves - end")
        return starting_shelves, shelves_ordered

    def _get_related_books_count(self, related_category):
        debug_print("_get_related_books_count - order_shelf_type:", related_category)
        connection = self.device_database_connection()
        related_books = []

        series_query = (
            "SELECT Series, count(*) "
            "FROM content c "
            "WHERE c.ContentType = 6 "
            "AND c.ContentID LIKE 'file%' "
            "AND c.Series IS NOT NULL "
            "GROUP BY Series"
        )
        authors_query = (
            "SELECT Attribution, count(*) "
            "FROM content c "
            "WHERE c.ContentType = 6 "
            "AND c.ContentID LIKE 'file%' "
            "GROUP BY Attribution"
        )

        related_books_queries = [series_query, authors_query]
        related_books_query = related_books_queries[related_category]
        debug_print(
            "_get_related_books_count - related_books_query:", related_books_query
        )

        cursor = connection.cursor()
        cursor.execute(related_books_query)

        for i, row in enumerate(cursor):
            debug_print("_get_related_books_count - row:", i, row[0], row[1])
            shelf = {}
            shelf["name"] = row[0]
            shelf["count"] = int(row[1])
            related_books.append(shelf)

        debug_print("_get_related_books_count - related_books:", related_books)
        return related_books

    def _set_related_books(self, related_books, options):
        debug_print(
            "_set_related_books - related_books:", related_books, " options:", options
        )

        categories_count = 0
        books_count = 0

        self.progressbar(_("Set Related Books"), on_top=False)
        total_related_books = len(related_books)
        self.show_progressbar(total_related_books)
        self.pb.left_align_label()

        connection = self.device_database_connection(use_row_factory=True)
        series_query = (
            "SELECT c.ContentID, c.Title, c.Attribution, Series, SeriesNumber "
            "FROM content c "
            "WHERE c.ContentType = 6 "
            "AND Series = ? "
            "AND ContentID LIKE 'file%' "
        )
        author_query = (
            "SELECT c.ContentID, c.Title, c.Attribution, Series, SeriesNumber "
            "FROM content c "
            "WHERE c.ContentType = 6 "
            "AND Attribution = ? "
            "AND ContentID LIKE 'file%' "
        )
        get_queries = [series_query, author_query]
        get_query = get_queries[options[cfg.KEY_RELATED_BOOKS_TYPE]]
        insert_query = "INSERT INTO volume_tabs VALUES ( ?, ? )"
        delete_query = "DELETE FROM volume_tabs WHERE tabId = ? "

        cursor = connection.cursor()
        for related_type in related_books:
            self.set_progressbar_label(
                _("Setting related books for ") + related_type["name"]
            )
            self.increment_progressbar()

            categories_count += 1
            debug_print(
                "_set_related_books - related_type=%s, count=%d"
                % (related_type["name"], related_type["count"])
            )
            if related_type["count"] <= 1:
                continue
            related_type_data = (related_type["name"],)
            debug_print("_set_related_books - related_type_data:", related_type_data)
            cursor.execute(get_query, related_type_data)
            related_type_contentIds = []
            for i, row in enumerate(cursor):
                debug_print(
                    "_set_related_books - row:",
                    i,
                    row["ContentID"],
                    row["Title"],
                    row["Attribution"],
                    row["Series"],
                    row["SeriesNumber"],
                )
                related_type_contentIds.append(row["ContentID"])

            debug_print(
                "_set_related_books - related_type_contentIds:",
                related_type_contentIds,
            )
            for tab_contentId in related_type_contentIds:
                cursor.execute(delete_query, (tab_contentId,))
                books_count += 1
                for volume_contentId in related_type_contentIds:
                    if not tab_contentId == volume_contentId:
                        insert_data = (volume_contentId, tab_contentId)
                        debug_print("_set_related_books - insert_data:", insert_data)
                        cursor.execute(insert_query, insert_data)

        self.hide_progressbar()
        debug_print("_set_related_books - end")
        return categories_count, books_count

    def _delete_related_books(self, options):
        debug_print("_delete_related_books - options:", options)

        self.progressbar(_("Delete Related Books"), on_top=False)
        self.show_progressbar(100)
        self.pb.left_align_label()

        connection = self.device_database_connection()
        delete_query = (
            "DELETE FROM volume_tabs  "
            "WHERE tabId LIKE 'file%' "
            "OR volumeId LIKE 'file%' "
        )

        cursor = connection.cursor()
        self.set_progressbar_label(_("Delete Related Books"))
        self.increment_progressbar()

        cursor.execute(delete_query)

        self.hide_progressbar()
        debug_print("_delete_related_books - end")
        return

    def _remove_duplicate_shelves(self, shelves, options):
        debug_print(
            "_remove_duplicate_shelves - total shelves=%d: options=%s"
            % (len(shelves), options)
        )
        connection = self.device_database_connection()
        starting_shelves = 0
        shelves_removed = 0
        finished_shelves = 0
        self.progressbar(_("Duplicate Shelves in Device Database"), on_top=False)
        total_shelves = len(shelves)
        self.show_progressbar(total_shelves)
        self.pb.left_align_label()

        shelves_update_timestamp = (
            "UPDATE Shelf "
            "SET _IsDeleted = 'true', "
            "LastModified = ? "
            "WHERE _IsSynced = 'true' "
            "AND Name = ? "
            "AND CreationDate <> ?"
        )
        shelves_update_id = (
            "UPDATE Shelf "
            "SET _IsDeleted = 'true', "
            "LastModified = ? "
            "WHERE _IsSynced = 'true' "
            "AND Name = ? "
            "AND id <> ?"
        )

        shelves_delete_timestamp = (
            "DELETE FROM Shelf "
            "WHERE _IsSynced = 'false' "
            "AND Name = ? "
            "AND CreationDate <> ? "
            "AND _IsDeleted = 'true'"
        )
        shelves_delete_id = (
            "DELETE FROM Shelf "
            "WHERE _IsSynced = 'false' "
            "AND Name = ? "
            "AND id <> ?"
            "AND _IsDeleted = 'true'"
        )

        shelves_purge = "DELETE FROM Shelf WHERE _IsDeleted = 'true'"

        purge_shelves = options[cfg.KEY_PURGE_SHELVES]
        keep_newest = options[cfg.KEY_KEEP_NEWEST_SHELF]

        cursor = connection.cursor()
        for shelf in shelves:
            starting_shelves += shelf[3]
            finished_shelves += 1
            self.set_progressbar_label(_("Removing duplicates of shelf ") + shelf[0])
            self.increment_progressbar()

            if shelf[3] > 1:
                debug_print(
                    "_remove_duplicate_shelves - shelf: %s, '%s', '%s', '%s', '%s'"
                    % (shelf[0], shelf[1], shelf[2], shelf[3], shelf[4])
                )
                timestamp = shelf[2] if keep_newest else shelf[1]
                shelf_id = shelf[4] if shelf[1] == shelf[2] else None
                shelves_values = (
                    shelf[0],
                    timestamp.strftime(self.device_timestamp_string),
                )

                if shelf_id:
                    shelves_update_query = shelves_update_id
                    shelves_delete_query = shelves_delete_id
                    shelves_update_values = (
                        strftime(self.device_timestamp_string, time.gmtime()),
                        shelf[0],
                        shelf_id,
                    )
                    shelves_delete_values = (shelf[0], shelf_id)
                else:
                    shelves_update_query = shelves_update_timestamp
                    shelves_delete_query = shelves_delete_timestamp
                    shelves_update_values = (
                        strftime(self.device_timestamp_string, time.gmtime()),
                        shelf[0],
                        timestamp.strftime(self.device_timestamp_string),
                    )
                    shelves_delete_values = shelves_values
                debug_print(
                    "_remove_duplicate_shelves - marking as deleted:",
                    shelves_update_values,
                )
                debug_print(
                    "_remove_duplicate_shelves - shelves_update_query:",
                    shelves_update_query,
                )
                debug_print(
                    "_remove_duplicate_shelves - shelves_delete_query:",
                    shelves_delete_query,
                )
                debug_print(
                    "_remove_duplicate_shelves - shelves_delete_values:",
                    shelves_delete_values,
                )
                cursor.execute(shelves_update_query, shelves_update_values)
                cursor.execute(shelves_delete_query, shelves_delete_values)
                shelves_removed += shelf[3] - 1

        if purge_shelves:
            debug_print(
                "_remove_duplicate_shelves - purging all shelves marked as deleted"
            )
            cursor.execute(shelves_purge)

        self.hide_progressbar()
        return starting_shelves, shelves_removed, finished_shelves

    def _check_device_database(self):
        return check_device_database(self.device_database_path())

    def _block_analytics(self):
        connection = self.device_database_connection()
        block_result = "The trigger on the AnalyticsEvents table has been removed."

        cursor = connection.cursor()

        cursor.execute("DROP TRIGGER IF EXISTS BlockAnalyticsEvents")
        # Delete the Extended drvier version if it is there.
        cursor.execute("DROP TRIGGER IF EXISTS KTE_BlockAnalyticsEvents")

        if self.options[cfg.KEY_CREATE_ANALYTICSEVENTS_TRIGGER]:
            cursor.execute("DELETE FROM AnalyticsEvents")
            debug_print("KoboUtilities:_block_analytics - creating trigger.")
            trigger_query = (
                "CREATE TRIGGER IF NOT EXISTS BlockAnalyticsEvents "
                "AFTER INSERT ON AnalyticsEvents "
                "BEGIN "
                "DELETE FROM AnalyticsEvents; "
                "END"
            )
            cursor.execute(trigger_query)
            result = cursor.fetchall()

            if result is None:
                block_result = None
            else:
                debug_print("_block_analytics - result=", result)
                block_result = "AnalyticsEvents have been blocked in the database."

        return block_result

    def _vacuum_device_database(self):
        connection = self.device_database_connection()
        compress_query = "VACUUM"
        cursor = connection.cursor()

        compress_result = ""
        cursor.execute(compress_query)
        result = cursor.fetchall()
        if result is not None:
            debug_print("_vacuum_device_database - result=", result)
            for line in result:
                compress_result += "\n" + line[0]
                debug_print("_vacuum_device_database - result line=", line[0])
        else:
            compress_result = _("Execution of '%s' failed") % compress_query

        return compress_result

    def generate_metadata_query(self):
        assert self.device is not None
        debug_print(
            "generate_metadata_query - self.device.supports_series=%s, self.device.supports_series_list%s"
            % (self.device.supports_series, self.device.supports_series_list)
        )

        test_query_columns = []
        test_query_columns.append("Title")
        test_query_columns.append("Attribution")
        test_query_columns.append("Description")
        test_query_columns.append("Publisher")
        test_query_columns.append("MimeType")

        if self.device.supports_series:
            debug_print("generate_metadata_query - supports series is true")
            test_query_columns.append("Series")
            test_query_columns.append("SeriesNumber")
            test_query_columns.append("Subtitle")
        else:
            test_query_columns.append("null as Series")
            test_query_columns.append("null as SeriesNumber")
        if self.device.supports_series_list:
            debug_print("generate_metadata_query - supports series list is true")
            test_query_columns.append("SeriesID")
            test_query_columns.append("SeriesNumberFloat")
        else:
            test_query_columns.append("null as SeriesID")
            test_query_columns.append("null as SeriesNumberFloat")

        test_query_columns.append("ReadStatus")
        test_query_columns.append("DateCreated")
        test_query_columns.append("Language")
        test_query_columns.append("PageProgressDirection")
        test_query_columns.append("___SyncTime")
        if self.device.supports_ratings:
            test_query_columns.append("ISBN")
            test_query_columns.append("FeedbackType")
            test_query_columns.append("FeedbackTypeSynced")
            test_query_columns.append("r.Rating")
            test_query_columns.append("r.DateModified")
        else:
            test_query_columns.append("NULL as ISBN")
            test_query_columns.append("NULL as FeedbackType")
            test_query_columns.append("NULL as FeedbackTypeSynced")
            test_query_columns.append("NULL as Rating")
            test_query_columns.append("NULL as DateModified")

        test_query = "SELECT "
        test_query += ",".join(test_query_columns)
        test_query += " FROM content c1 "
        if self.device.supports_ratings:
            test_query += " left outer join ratings r on c1.ContentID = r.ContentID "

        test_query += "WHERE c1.BookId IS NULL AND c1.ContentID = ?"
        debug_print("generate_metadata_query - test_query=%s" % test_query)
        return test_query

    def _update_metadata(self, books):
        assert self.device is not None
        from calibre.ebooks.metadata import authors_to_string
        from calibre.utils.localization import canonicalize_lang, lang_as_iso639_1

        debug_print(
            "_update_metadata: number books=", len(books), "options=", self.options
        )

        updated_books = 0
        not_on_device_books = 0
        unchanged_books = 0
        count_books = 0

        total_books = len(books)
        self.show_progressbar(total_books)

        from calibre.library.save_to_disk import find_plugboard

        plugboards = self.gui.library_view.model().db.prefs.get("plugboards", {})
        debug_print("_update_metadata: plugboards=", plugboards)
        debug_print(
            "_update_metadata: self.device.__class__.__name__=",
            self.device.__class__.__name__,
        )

        rating_update = (
            "UPDATE ratings "
            "SET Rating = ?, "
            "DateModified = ? "
            "WHERE ContentID  = ?"
        )  # fmt: skip
        rating_insert = (
            "INSERT INTO ratings ("
            "Rating, "
            "DateModified, "
            "ContentID "
            ")"
            "VALUES (?, ?, ?)"
        )  # fmt: skip
        rating_delete = "DELETE FROM ratings WHERE ContentID = ?"

        series_id_query = (
            "SELECT DISTINCT Series, SeriesID "
            "FROM content "
            "WHERE contentType = 6 "
            "AND contentId NOT LIKE 'file%' "
            "AND series IS NOT NULL "
            "AND seriesid IS NOT NULL "
        )

        connection = self.device_database_connection(use_row_factory=True)
        test_query = self.generate_metadata_query()
        cursor = connection.cursor()
        kobo_series_dict = {}
        if self.device.supports_series_list:
            cursor.execute(series_id_query)
            rows = list(cursor)
            debug_print("_update_metadata: series_id_query result=", rows)
            for row in rows:
                kobo_series_dict[row["Series"]] = row["SeriesID"]
            debug_print("_update_metadata: kobo_series_list=", kobo_series_dict)

        for book in books:
            self.set_progressbar_label(_("Updating metadata for ") + book.title)
            self.increment_progressbar()

            for contentID in book.contentIDs:
                debug_print(
                    "_update_metadata: searching for contentId='%s'" % (contentID)
                )
                if not contentID:
                    contentID = self.contentid_from_path(book.path, self.CONTENTTYPE)
                debug_print(
                    "_update_metadata: self.options[cfg.KEY_UDPATE_KOBO_EPUBS]=",
                    self.options[cfg.KEY_UDPATE_KOBO_EPUBS],
                )
                debug_print(
                    "_update_metadata: contentID.startswith('file')=",
                    contentID.startswith("file"),
                )
                if not self.options[
                    cfg.KEY_UDPATE_KOBO_EPUBS
                ] and not contentID.startswith("file"):
                    debug_print("_update_metadata: skipping book")
                    continue

                count_books += 1
                query_values = (contentID,)
                cursor.execute(test_query, query_values)
                try:
                    result = next(cursor)
                except StopIteration:
                    result = None
                if result is not None:
                    debug_print("_update_metadata: found contentId='%s'" % (contentID))
                    debug_print("    result=", result)
                    debug_print("    result['Title']='%s'" % (result["Title"]))
                    debug_print(
                        "    result['Attribution']='%s'" % (result["Attribution"])
                    )

                    title_string = None
                    authors_string = None
                    newmi = book.deepcopy_metadata()
                    if self.options[cfg.KEY_USE_PLUGBOARD] and plugboards is not None:
                        book_format = os.path.splitext(contentID)[1][1:]
                        debug_print("_update_metadata: format='%s'" % (book_format))
                        plugboard = find_plugboard(
                            self.device.__class__.__name__, book_format, plugboards
                        )
                        debug_print("_update_metadata: plugboard=", plugboard)

                        if plugboard is not None:
                            debug_print("_update_metadata: applying plugboard")
                            newmi.template_to_attribute(book, plugboard)
                        debug_print("_update_metadata: newmi.title=", newmi.title)
                        debug_print("_update_metadata: newmi.authors=", newmi.authors)
                        debug_print("_update_metadata: newmi.comments=", newmi.comments)
                    else:
                        if self.options[cfg.KEY_USE_TITLE_SORT]:
                            title_string = newmi.title_sort
                        if self.options[cfg.KEY_USE_AUTHOR_SORT]:
                            debug_print("_update_metadata: author=", newmi.authors)
                            debug_print(
                                "_update_metadata: using author_sort=",
                                newmi.author_sort,
                            )
                            debug_print(
                                "_update_metadata: using author_sort - author=",
                                newmi.authors,
                            )
                            authors_string = newmi.author_sort
                    debug_print("_update_metadata: title_string=", title_string)
                    title_string = newmi.title if title_string is None else title_string
                    debug_print("_update_metadata: title_string=", title_string)
                    debug_print("_update_metadata: authors_string=", authors_string)
                    authors_string = (
                        authors_to_string(newmi.authors)
                        if authors_string is None
                        else authors_string
                    )
                    debug_print("_update_metadata: authors_string=", authors_string)
                    newmi.series_index_string = getattr(
                        book, "series_index_string", None
                    )

                    update_query = "UPDATE content SET "
                    update_values = []
                    set_clause_columns = []
                    changes_found = False
                    rating_values = []
                    rating_change_query = None

                    if (
                        self.options[cfg.KEY_SET_TITLE]
                        and not result["Title"] == title_string
                    ):
                        set_clause_columns.append("Title=?")
                        debug_print("_update_metadata: set_clause=", set_clause_columns)
                        update_values.append(title_string)

                    if (
                        self.options[cfg.KEY_SET_AUTHOR]
                        and not result["Attribution"] == authors_string
                    ):
                        set_clause_columns.append("Attribution=?")
                        debug_print(
                            "_update_metadata: set_clause_columns=",
                            set_clause_columns,
                        )
                        update_values.append(authors_string)

                    if self.options[cfg.KEY_SET_DESCRIPTION]:
                        new_comments = library_comments = newmi.comments
                        if self.options[cfg.KEY_DESCRIPTION_USE_TEMPLATE]:
                            new_comments = self._render_synopsis(
                                newmi,
                                book,
                                template=self.options[cfg.KEY_DESCRIPTION_TEMPLATE],
                            )
                            if len(new_comments) == 0:
                                new_comments = library_comments
                        if (
                            new_comments
                            and len(new_comments) > 0
                            and not result["Description"] == new_comments
                        ):
                            set_clause_columns.append("Description=?")
                            update_values.append(new_comments)
                        else:
                            debug_print(
                                "_update_metadata: Description not changed - not updating."
                            )

                    if (
                        self.options[cfg.KEY_SET_PUBLISHER]
                        and not result["Publisher"] == newmi.publisher
                    ):
                        set_clause_columns.append("Publisher=?")
                        update_values.append(newmi.publisher)

                    if self.options[cfg.KEY_SET_PUBLISHED_DATE]:
                        pubdate_string = strftime(
                            self.device_timestamp_string, newmi.pubdate
                        )
                        if not (result["DateCreated"] == pubdate_string):
                            set_clause_columns.append("DateCreated=?")
                            debug_print(
                                "_update_metadata: convert_kobo_date(result['DateCreated'])=",
                                convert_kobo_date(result["DateCreated"]),
                            )
                            debug_print(
                                "_update_metadata: convert_kobo_date(result['DateCreated']).__class__=",
                                convert_kobo_date(result["DateCreated"]).__class__,
                            )
                            debug_print(
                                "_update_metadata: newmi.pubdate  =", newmi.pubdate
                            )
                            debug_print(
                                "_update_metadata: result['DateCreated']     =",
                                result["DateCreated"],
                            )
                            debug_print(
                                "_update_metadata: pubdate_string=", pubdate_string
                            )
                            debug_print(
                                "_update_metadata: newmi.pubdate.__class__=",
                                newmi.pubdate.__class__,
                            )
                            update_values.append(pubdate_string)

                    if (
                        self.options[cfg.KEY_SET_ISBN]
                        and not result["ISBN"] == newmi.isbn
                    ):
                        set_clause_columns.append("ISBN=?")
                        update_values.append(newmi.isbn)

                    if self.options[cfg.KEY_SET_LANGUAGE] and not result[
                        "Language"
                    ] == lang_as_iso639_1(newmi.language):
                        debug_print(
                            "_update_metadata: newmi.language =", newmi.language
                        )
                        debug_print(
                            "_update_metadata: lang_as_iso639_1(newmi.language)=",
                            lang_as_iso639_1(newmi.language),
                        )
                        debug_print(
                            "_update_metadata: canonicalize_lang(newmi.language)=",
                            canonicalize_lang(newmi.language),
                        )

                    debug_print(
                        "_update_metadata: self.options[cfg.KEY_SET_RATING]= ",
                        self.options[cfg.KEY_SET_RATING],
                    )
                    if self.options[cfg.KEY_SET_RATING]:
                        rating_column = self.get_rating_column()

                        if rating_column:
                            if rating_column == "rating":
                                rating = newmi.rating
                            else:
                                rating = newmi.get_user_metadata(rating_column, True)[
                                    "#value#"
                                ]
                            debug_print(
                                "_update_metadata: rating=",
                                rating,
                                "result[Rating]=",
                                result["Rating"],
                            )
                            rating = None if not rating or rating == 0 else rating / 2
                            debug_print(
                                "_update_metadata: rating=",
                                rating,
                                "result[Rating]=",
                                result["Rating"],
                            )
                            rating_values.append(rating)
                            rating_values.append(
                                strftime(self.device_timestamp_string, time.gmtime())
                            )
                            rating_values.append(contentID)
                            if not rating == result["Rating"]:
                                if not rating:
                                    rating_change_query = rating_delete
                                    rating_values = (contentID,)
                                elif (
                                    result["DateModified"] is None
                                ):  # If the date modified column does not have a value, there is no rating column
                                    rating_change_query = rating_insert
                                else:
                                    rating_change_query = rating_update

                    if self.device.supports_series and self.options["series"]:
                        debug_print(
                            "_update_metadata: self.options['series']",
                            self.options["series"],
                        )
                        debug_print(
                            "_update_metadata: newmi.series= ='%s' newmi.series_index='%s' newmi.series_index_string='%s'"
                            % (
                                newmi.series,
                                newmi.series_index,
                                newmi.series_index_string,
                            )
                        )
                        debug_print(
                            "_update_metadata: result['Series'] ='%s' result['SeriesNumber'] =%s"
                            % (result["Series"], result["SeriesNumber"])
                        )
                        debug_print(
                            "_update_metadata: result['SeriesID'] ='%s' result['SeriesNumberFloat'] =%s"
                            % (result["SeriesID"], result["SeriesNumberFloat"])
                        )

                        if newmi.series is not None:
                            new_series = newmi.series
                            try:
                                new_series_number = "%g" % newmi.series_index
                            except Exception:
                                new_series_number = None
                        else:
                            new_series = None
                            new_series_number = None

                        series_changed = not (new_series == result["Series"])
                        series_number_changed = not (
                            new_series_number == result["SeriesNumber"]
                        )
                        debug_print('_update_metadata: new_series="%s"' % (new_series,))
                        debug_print(
                            '_update_metadata: new_series_number="%s"'
                            % (new_series_number,)
                        )
                        debug_print(
                            '_update_metadata: series_number_changed="%s"'
                            % (series_number_changed,)
                        )
                        debug_print(
                            '_update_metadata: series_changed="%s"' % (series_changed,)
                        )
                        if series_changed or series_number_changed:
                            debug_print("_update_metadata: setting series")
                            set_clause_columns.append("Series=?")
                            update_values.append(new_series)
                            set_clause_columns.append("SeriesNumber=?")
                            update_values.append(new_series_number)
                        debug_print(
                            "_update_metadata: self.device.supports_series_list='%s'"
                            % self.device.supports_series_list
                        )
                        if self.device.supports_series_list:
                            debug_print("_update_metadata: supports_series_list")
                            series_id = kobo_series_dict.get(newmi.series, newmi.series)
                            debug_print("_update_metadata: series_id='%s'" % series_id)
                            if (
                                series_changed
                                or series_number_changed
                                or not (
                                    result["SeriesID"] == series_id
                                    and (
                                        result["SeriesNumberFloat"]
                                        == newmi.series_index
                                    )
                                )
                            ):
                                debug_print("_update_metadata: setting SeriesID")
                                set_clause_columns.append("SeriesID=?")
                                set_clause_columns.append("SeriesNumberFloat=?")
                                if series_id is None or series_id == "":
                                    update_values.append(None)
                                    update_values.append(None)
                                else:
                                    update_values.append(series_id)
                                    update_values.append(newmi.series_index)

                    if self.options[
                        cfg.KEY_SET_SUBTITLE
                    ]:  # and self.options[cfg.KEY_SUBTITLE_TEMPLATE]:
                        debug_print(
                            "_update_metadata: setting subtitle - column name =",
                            self.options[cfg.KEY_SUBTITLE_TEMPLATE],
                        )
                        subtitle_template = self.options[cfg.KEY_SUBTITLE_TEMPLATE]
                        if (
                            self.options[cfg.KEY_SUBTITLE_TEMPLATE]
                            == cfg.TOKEN_CLEAR_SUBTITLE
                        ):
                            new_subtitle = None
                        elif (
                            subtitle_template
                            and self.options[cfg.KEY_SUBTITLE_TEMPLATE][0] == "#"
                        ):
                            new_subtitle = newmi.get_user_metadata(
                                self.options[cfg.KEY_SUBTITLE_TEMPLATE], True
                            )["#value#"]
                        else:
                            pb = [
                                (
                                    self.options[cfg.KEY_SUBTITLE_TEMPLATE],
                                    "subtitle",
                                )
                            ]
                            book.template_to_attribute(book, pb)
                            debug_print(
                                "_render_synopsis: after - mi.subtitle=",
                                book.subtitle,
                            )
                            new_subtitle = (
                                book.subtitle if len(book.subtitle) > 0 else None
                            )
                            if (
                                new_subtitle
                                and self.options[cfg.KEY_SUBTITLE_TEMPLATE]
                                == new_subtitle
                            ):
                                new_subtitle = None
                            debug_print(
                                '_update_metadata: setting subtitle - subtitle ="%s"'
                                % new_subtitle
                            )
                            debug_print(
                                '_update_metadata: setting subtitle - result["Subtitle"] = "%s"'
                                % result["Subtitle"]
                            )
                        if (
                            not new_subtitle
                            and (
                                not (
                                    result["Subtitle"] is None
                                    or result["Subtitle"] == ""
                                )
                            )
                        ) or (new_subtitle and not result["Subtitle"] == new_subtitle):
                            update_values.append(new_subtitle)
                            set_clause_columns.append("Subtitle=?")

                    debug_print(
                        "_update_metadata: self.options[cfg.KEY_SET_READING_DIRECTION]",
                        self.options[cfg.KEY_SET_READING_DIRECTION],
                    )
                    debug_print(
                        "_update_metadata: self.options[cfg.KEY_READING_DIRECTION]",
                        self.options[cfg.KEY_READING_DIRECTION],
                    )
                    if self.options[cfg.KEY_SET_READING_DIRECTION] and (
                        not (
                            result["PageProgressDirection"]
                            == self.options[cfg.KEY_READING_DIRECTION]
                        )
                    ):
                        set_clause_columns.append("PageProgressDirection=?")
                        update_values.append(self.options[cfg.KEY_READING_DIRECTION])

                    debug_print(
                        "_update_metadata: self.options[cfg.KEY_SYNC_DATE]",
                        self.options[cfg.KEY_SYNC_DATE],
                    )
                    debug_print(
                        "_update_metadata: self.options[cfg.KEY_SYNC_DATE_COLUMN]",
                        self.options[cfg.KEY_SYNC_DATE_COLUMN],
                    )
                    new_timestamp = None
                    if self.options[cfg.KEY_SYNC_DATE]:
                        if self.options[cfg.KEY_SYNC_DATE_COLUMN] == "timestamp":
                            new_timestamp = newmi.timestamp
                        elif self.options[cfg.KEY_SYNC_DATE_COLUMN] == "last_modified":
                            new_timestamp = newmi.last_modified
                        elif self.options[cfg.KEY_SYNC_DATE_COLUMN] == "pubdate":
                            new_timestamp = newmi.pubdate
                        elif self.options[cfg.KEY_SYNC_DATE_COLUMN][0] == "#":
                            new_timestamp = newmi.get_user_metadata(
                                self.options[cfg.KEY_SYNC_DATE_COLUMN], True
                            )["#value#"]
                        elif (
                            self.options[cfg.KEY_SYNC_DATE_COLUMN]
                            == cfg.TOKEN_FILE_TIMESTAMP
                        ):
                            debug_print(
                                "_update_metadata: Using book file timestamp for Date Added sort."
                            )
                            debug_print("_update_metadata - book=", book)
                            device_book_path = self.get_device_path_from_contentID(
                                contentID, result["MimeType"]
                            )
                            debug_print(
                                "_update_metadata: device_book_path=",
                                device_book_path,
                            )
                            new_timestamp = datetime.fromtimestamp(
                                os.path.getmtime(device_book_path), tz=timezone.utc
                            )
                            debug_print(
                                "_update_metadata: new_timestamp=", new_timestamp
                            )

                        if new_timestamp is not None:
                            synctime_string = strftime(
                                self.device_timestamp_string, new_timestamp
                            )
                            if result["___SyncTime"] != synctime_string:
                                set_clause_columns.append("___SyncTime=?")
                                debug_print(
                                    "_update_metadata: convert_kobo_date(result['___SyncTime'])=",
                                    convert_kobo_date(result["___SyncTime"]),
                                )
                                debug_print(
                                    "_update_metadata: convert_kobo_date(result['___SyncTime']).__class__=",
                                    convert_kobo_date(result["___SyncTime"]).__class__,
                                )
                                debug_print(
                                    "_update_metadata: new_timestamp  =", new_timestamp
                                )
                                debug_print(
                                    "_update_metadata: result['___SyncTime']     =",
                                    result["___SyncTime"],
                                )
                                debug_print(
                                    "_update_metadata: synctime_string=",
                                    synctime_string,
                                )
                                update_values.append(synctime_string)

                    if self.options["setRreadingStatus"] and (
                        not (result["ReadStatus"] == self.options["readingStatus"])
                        or self.options["resetPosition"]
                    ):
                        set_clause_columns.append("ReadStatus=?")
                        update_values.append(self.options["readingStatus"])
                        if self.options["resetPosition"]:
                            set_clause_columns.append("DateLastRead=?")
                            update_values.append(None)
                            set_clause_columns.append("ChapterIDBookmarked=?")
                            update_values.append(None)
                            set_clause_columns.append("___PercentRead=?")
                            update_values.append(0)
                            set_clause_columns.append("FirstTimeReading=?")
                            update_values.append(self.options["readingStatus"] < 2)

                    if len(set_clause_columns) > 0:
                        update_query += ",".join(set_clause_columns)
                        changes_found = True

                    if not (changes_found or rating_change_query):
                        debug_print(
                            "_update_metadata: no changes found to selected metadata. No changes being made."
                        )
                        unchanged_books += 1
                        continue

                    update_query += " WHERE ContentID = ? AND BookID IS NULL"
                    update_values.append(contentID)
                    debug_print("_update_metadata: update_query=%s" % update_query)
                    debug_print("_update_metadata: update_values= ", update_values)
                    try:
                        if changes_found:
                            cursor.execute(update_query, update_values)

                        if rating_change_query:
                            debug_print(
                                "_update_metadata: rating_change_query=%s"
                                % rating_change_query
                            )
                            debug_print(
                                "_update_metadata: rating_values= ", rating_values
                            )
                            cursor.execute(rating_change_query, rating_values)

                        updated_books += 1
                    except:
                        debug_print(
                            "    Database Exception:  Unable to set series info"
                        )
                        raise
                else:
                    debug_print(
                        "_update_metadata: no match for title='%s' contentId='%s'"
                        % (book.title, contentID)
                    )
                    not_on_device_books += 1
        debug_print(
            "Update summary: Books updated=%d, unchanged books=%d, not on device=%d, Total=%d"
            % (updated_books, unchanged_books, not_on_device_books, count_books)
        )

        self.hide_progressbar()

        return (updated_books, unchanged_books, not_on_device_books, count_books)

    def _render_synopsis(self, mi, book, template=None):
        from xml.sax.saxutils import escape

        from calibre.customize.ui import output_profiles
        from calibre.ebooks.conversion.config import load_defaults
        from calibre.ebooks.oeb.transforms.jacket import (
            SafeFormatter,
            Series,
            Tags,
            get_rating,
        )
        from calibre.library.comments import comments_to_html
        from calibre.utils.date import is_date_undefined

        debug_print('_render_synopsis: start - book.comments="%s"' % book.comments)

        if not template:
            try:
                data = P("kobo_template.xhtml", data=True)
                assert isinstance(data, bytes), f"data is of type {type(data)}"
                template = data.decode("utf-8")
            except Exception:
                template = ""
        debug_print("_render_synopsis: template=", template)

        colon_pos = template.find(":")
        jacket_style = False
        if colon_pos > 0:
            if template.startswith(("template:", "plugboard:")):
                jacket_style = False
                template = template[colon_pos + 1 :]
            elif template.startswith("jacket:"):
                jacket_style = True
                template = template[colon_pos + 1 :]

        if jacket_style:
            debug_print("_render_synopsis: using jacket style template.")

            ps = load_defaults("page_setup")
            op = ps.get("output_profile", "default")
            opmap = {x.short_name: x for x in output_profiles()}
            output_profile = opmap.get(op, opmap["default"])

            rating = get_rating(
                mi.rating,
                output_profile.ratings_char,
                output_profile.empty_ratings_char,
            )

            tags = Tags((mi.tags if mi.tags else []), output_profile)
            debug_print("_render_synopsis: tags=", tags)

            comments = mi.comments.strip() if mi.comments else ""
            if comments:
                comments = comments_to_html(comments)
            debug_print("_render_synopsis: comments=", comments)
            try:
                author = mi.format_authors()
            except Exception:
                author = ""
            author = escape(author)
            publisher = mi.publisher if mi.publisher else ""
            publisher = escape(publisher)
            title_str = mi.title if mi.title else _("Unknown")
            title_str = escape(title_str)
            series = Series(mi.series, mi.series_index)

            try:
                if is_date_undefined(mi.pubdate):
                    pubdate = ""
                else:
                    pubdate = strftime("%Y", mi.pubdate.timetuple())
            except Exception:
                pubdate = ""

            args = {
                "title_str": title_str,
                "title": title_str,
                "author": author,
                "publisher": publisher,
                "pubdate_label": _("Published"),
                "pubdate": pubdate,
                "series_label": _("Series"),
                "series": series,
                "rating_label": _("Rating"),
                "rating": rating,
                "tags_label": _("Tags"),
                "tags": tags,
                "comments": comments,
            }
            for key in mi.custom_field_keys():
                try:
                    display_name, val = mi.format_field_extended(key)[:2]
                    debug_print(
                        "_render_synopsis: key=%s, display_name=%s, val=%s"
                        % (key, display_name, val)
                    )
                    key = key.replace("#", "_")
                    args[key + "_label"] = escape(display_name)
                    debug_print(
                        "_render_synopsis: display_name arg=", (args[key + "_label"])
                    )
                    args[key] = escape(val)
                except Exception:
                    # if the val (custom column contents) is None, don't add to args
                    pass

            if False:
                debug_print("Custom column values available in jacket template:")
                for key in list(args.keys()):
                    if key.startswith("_") and not key.endswith("_label"):
                        debug_print(" %s: %s" % ("#" + key[1:], args[key]))

            # Used in the comment describing use of custom columns in templates
            # Don't change this unless you also change it in template.xhtml
            args["_genre_label"] = args.get("_genre_label", "{_genre_label}")
            args["_genre"] = args.get("_genre", "{_genre}")

            formatter = SafeFormatter()
            rendered_comments = formatter.format(template, **args)
            debug_print("_render_synopsis: generated_html=", rendered_comments)

        else:
            pb = [(template, "comments")]
            debug_print("_render_synopsis: before - mi.comments=", mi.comments)
            debug_print("_render_synopsis: book.comments=", book.comments)
            debug_print("_render_synopsis: pb=", pb)
            mi.template_to_attribute(book, pb)
            debug_print("_render_synopsis: after - mi.comments=", mi.comments)
            rendered_comments = mi.comments

        return rendered_comments

    def _store_current_bookmark(self, books, options=None):
        if options:
            self.options = options

        reading_locations_updated = 0
        books_without_reading_locations = 0
        count_books = 0

        def value_changed(old_value, new_value):
            return (
                old_value is not None
                and new_value is None
                or old_value is None
                and new_value is not None
                or not old_value == new_value
            )

        profileName = self.options.get("profileName", None)
        debug_print("_store_current_bookmark - profileName=", profileName)
        clear_if_unread = self.options[cfg.KEY_CLEAR_IF_UNREAD]
        store_if_more_recent = self.options[cfg.KEY_STORE_IF_MORE_RECENT]
        do_not_store_if_reopened = self.options[cfg.KEY_DO_NOT_STORE_IF_REOPENED]

        connection = self.device_database_connection(use_row_factory=True)
        self.progressbar(_("Storing reading positions"), on_top=True)
        self.show_progressbar(len(books))

        library_db = self.gui.current_db
        (
            kobo_chapteridbookmarked_column_name,
            kobo_percentRead_column_name,
            rating_column_name,
            last_read_column_name,
            time_spent_reading_column_name,
            rest_of_book_estimate_column_name,
        ) = self.get_column_names(profileName)
        debug_print(
            "_store_current_bookmark - kobo_chapteridbookmarked_column_name=",
            kobo_chapteridbookmarked_column_name,
        )
        debug_print(
            "_store_current_bookmark - kobo_percentRead_column_name=",
            kobo_percentRead_column_name,
        )
        debug_print("_store_current_bookmark - rating_column_name=", rating_column_name)
        debug_print(
            "_store_current_bookmark - last_read_column_name=",
            last_read_column_name,
        )
        debug_print(
            "_store_current_bookmark - time_spent_reading_column_name=",
            time_spent_reading_column_name,
        )
        debug_print(
            "_store_current_bookmark - rest_of_book_estimate_column_name=",
            rest_of_book_estimate_column_name,
        )

        rating_col_label = None
        if rating_column_name is not None:
            if not rating_column_name == "rating":
                rating_col_label = (
                    library_db.field_metadata.key_to_label(rating_column_name)
                    if rating_column_name
                    else ""
                )
            debug_print("_store_current_bookmark - rating_col_label=", rating_col_label)

        id_map = {}
        id_map_percentRead = {}
        id_map_chapteridbookmarked = {}
        id_map_rating = {}
        id_map_last_read = {}
        id_map_time_spent_reading = {}
        id_map_rest_of_book_estimate = {}

        debug_print("_store_current_bookmark - Starting to look at selected books...")
        cursor = connection.cursor()
        for book in books:
            count_books += 1
            mi = Metadata("Unknown")
            debug_print("_store_current_bookmark - Looking at book: %s" % book.title)
            self.set_progressbar_label(_("Checkin ") + book.title)
            self.increment_progressbar()
            book_updated = False

            if len(book.contentIDs) == 0:
                books_without_reading_locations += 1
                continue

            for contentID in book.contentIDs:
                debug_print("_store_current_bookmark - contentId='%s'" % (contentID))
                fetch_values = (contentID,)
                fetch_queries = self._get_fetch_query_for_firmware_version(
                    self.device_fwversion
                )
                assert fetch_queries is not None
                if contentID.endswith(".kepub.epub"):
                    fetch_query = fetch_queries["kepub"]
                else:
                    fetch_query = fetch_queries["epub"]
                debug_print(
                    "_store_current_bookmark - fetch_query='%s'" % (fetch_query)
                )
                cursor.execute(fetch_query, fetch_values)
                try:
                    result = next(cursor)
                except StopIteration:
                    result = None

                kobo_chapteridbookmarked = None
                kobo_adobe_location = None
                kobo_percentRead = None
                last_read = None
                time_spent_reading = None
                rest_of_book_estimate = None

                if result is not None:
                    debug_print("_store_current_bookmark - result=", result)
                    if result["ReadStatus"] == 0:
                        if clear_if_unread:
                            kobo_chapteridbookmarked = None
                            kobo_adobe_location = None
                            kobo_percentRead = None
                            last_read = None
                            kobo_rating = 0
                            time_spent_reading = None
                            rest_of_book_estimate = None
                        else:
                            books_without_reading_locations += 1
                            continue
                    else:
                        if result["DateLastRead"]:
                            debug_print(
                                "_store_current_bookmark - result['DateLastRead']=",
                                result["DateLastRead"],
                            )
                            last_read = convert_kobo_date(result["DateLastRead"])
                            debug_print(
                                "_store_current_bookmark - last_read=", last_read
                            )

                        if last_read_column_name is not None and store_if_more_recent:
                            current_last_read = book.get_user_metadata(
                                last_read_column_name, True
                            )["#value#"]
                            debug_print(
                                "_store_current_bookmark - book.get_user_metadata(last_read_column_name, True)['#value#']=",
                                current_last_read,
                            )
                            debug_print(
                                "_store_current_bookmark - setting mi.last_read=",
                                last_read,
                            )
                            if current_last_read is not None and last_read is not None:
                                debug_print(
                                    "_store_current_bookmark - store_if_more_recent - current_last_read < last_read=",
                                    current_last_read < last_read,
                                )
                                if current_last_read >= last_read:
                                    continue
                            elif current_last_read is not None and last_read is None:
                                continue

                        if (
                            kobo_percentRead_column_name is not None
                            and do_not_store_if_reopened
                        ):
                            current_percentRead = book.get_user_metadata(
                                kobo_percentRead_column_name, True
                            )["#value#"]
                            debug_print(
                                "_store_current_bookmark - do_not_store_if_reopened - current_percentRead=",
                                current_percentRead,
                            )
                            if (
                                current_percentRead is not None
                                and current_percentRead >= 100
                            ):
                                continue

                        if (
                            result["MimeType"] == MIMETYPE_KOBO
                            or self.epub_location_like_kepub
                        ):
                            kobo_chapteridbookmarked = result["ChapterIDBookmarked"]
                            kobo_adobe_location = None
                        else:
                            kobo_chapteridbookmarked = (
                                result["ChapterIDBookmarked"][len(contentID) + 1 :]
                                if result["ChapterIDBookmarked"]
                                else None
                            )
                            kobo_adobe_location = result["adobe_location"]

                        if result["ReadStatus"] == 1:
                            kobo_percentRead = result["___PercentRead"]
                        elif result["ReadStatus"] == 2:
                            kobo_percentRead = 100

                        if result["Rating"]:
                            kobo_rating = result["Rating"] * 2
                        else:
                            kobo_rating = 0

                        if result["TimeSpentReading"]:
                            time_spent_reading = result["TimeSpentReading"]
                        if result["RestOfBookEstimate"]:
                            rest_of_book_estimate = result["RestOfBookEstimate"]

                else:
                    books_without_reading_locations += 1
                    continue

                debug_print(
                    "_store_current_bookmark - kobo_chapteridbookmarked='%s'"
                    % (kobo_chapteridbookmarked)
                )
                debug_print(
                    "_store_current_bookmark - kobo_adobe_location='%s'"
                    % (kobo_adobe_location)
                )
                debug_print(
                    "_store_current_bookmark - kobo_percentRead=", kobo_percentRead
                )
                debug_print(
                    "_store_current_bookmark - time_spent_reading='%s'"
                    % (time_spent_reading)
                )
                debug_print(
                    "_store_current_bookmark - rest_of_book_estimate='%s'"
                    % (rest_of_book_estimate)
                )

                if last_read_column_name is not None:
                    current_last_read = book.get_user_metadata(
                        last_read_column_name, True
                    )["#value#"]
                    debug_print(
                        "_store_current_bookmark - book.get_user_metadata(last_read_column_name, True)['#value#']=",
                        current_last_read,
                    )
                    debug_print(
                        "_store_current_bookmark - setting mi.last_read=", last_read
                    )
                    debug_print(
                        "_store_current_bookmark - current_last_read == last_read=",
                        current_last_read == last_read,
                    )

                    if value_changed(current_last_read, last_read):
                        id_map_last_read[book.calibre_id] = last_read
                        book_updated = True
                    else:
                        book_updated = book_updated or False

                if kobo_chapteridbookmarked_column_name is not None:
                    if (
                        kobo_chapteridbookmarked is not None
                        and kobo_adobe_location is not None
                    ):
                        new_value = (
                            kobo_chapteridbookmarked
                            + BOOKMARK_SEPARATOR
                            + kobo_adobe_location
                        )
                    elif kobo_chapteridbookmarked:
                        new_value = kobo_chapteridbookmarked
                    else:
                        new_value = None
                        debug_print(
                            "_store_current_bookmark - setting bookmark column to None"
                        )
                    debug_print(
                        "_store_current_bookmark - chapterIdBookmark - on kobo=",
                        new_value,
                    )
                    debug_print(
                        "_store_current_bookmark - chapterIdBookmark - in library=",
                        book.get_user_metadata(
                            kobo_chapteridbookmarked_column_name, True
                        )["#value#"],
                    )
                    debug_print(
                        "_store_current_bookmark - chapterIdBookmark - on kobo==in library=",
                        new_value
                        == book.get_user_metadata(
                            kobo_chapteridbookmarked_column_name, True
                        )["#value#"],
                    )
                    old_value = book.get_user_metadata(
                        kobo_chapteridbookmarked_column_name, True
                    )["#value#"]

                    if value_changed(old_value, new_value):
                        id_map_chapteridbookmarked[book.calibre_id] = new_value
                        book_updated = True
                    else:
                        book_updated = book_updated or False

                if kobo_percentRead_column_name is not None:
                    debug_print(
                        "_store_current_bookmark - setting kobo_percentRead=",
                        kobo_percentRead,
                    )
                    current_percentRead = book.get_user_metadata(
                        kobo_percentRead_column_name, True
                    )["#value#"]
                    debug_print(
                        "_store_current_bookmark - percent read - in book=",
                        current_percentRead,
                    )

                    if value_changed(current_percentRead, kobo_percentRead):
                        id_map_percentRead[book.calibre_id] = kobo_percentRead
                        book_updated = True
                    else:
                        book_updated = book_updated or False

                if rating_column_name is not None and kobo_rating > 0:
                    debug_print(
                        "_store_current_bookmark - setting rating_column_name=",
                        rating_column_name,
                    )
                    if rating_column_name == "rating":
                        current_rating = book.rating
                        debug_print(
                            "_store_current_bookmark - rating - in book=",
                            current_rating,
                        )
                        if not current_rating == kobo_rating:
                            library_db.set_rating(
                                book.calibre_id, kobo_rating, commit=False
                            )
                    else:
                        current_rating = book.get_user_metadata(
                            rating_column_name, True
                        )["#value#"]
                        if not current_rating == kobo_rating:
                            library_db.set_custom(
                                book.calibre_id,
                                kobo_rating,
                                label=rating_col_label,
                                commit=False,
                            )
                    if value_changed(current_rating, kobo_rating):
                        id_map_rating[book.calibre_id] = kobo_rating
                        book_updated = True
                    else:
                        book_updated = book_updated or False

                if time_spent_reading_column_name is not None:
                    debug_print(
                        "_store_current_bookmark - setting time_spent_reading=",
                        time_spent_reading,
                    )
                    current_time_spent_reading = book.get_user_metadata(
                        time_spent_reading_column_name, True
                    )["#value#"]
                    debug_print(
                        "_store_current_bookmark - time spent reading - in book=",
                        current_time_spent_reading,
                    )

                    if value_changed(current_time_spent_reading, time_spent_reading):
                        id_map_time_spent_reading[book.calibre_id] = time_spent_reading
                        book_updated = True
                    else:
                        book_updated = book_updated or False

                if rest_of_book_estimate_column_name is not None:
                    debug_print(
                        "_store_current_bookmark - setting rest_of_book_estimate=",
                        rest_of_book_estimate,
                    )
                    current_rest_of_book_estimate = book.get_user_metadata(
                        time_spent_reading_column_name, True
                    )["#value#"]
                    debug_print(
                        "_store_current_bookmark - rest of book estimate - in book=",
                        current_rest_of_book_estimate,
                    )

                    if value_changed(
                        current_rest_of_book_estimate, rest_of_book_estimate
                    ):
                        id_map_rest_of_book_estimate[book.calibre_id] = (
                            rest_of_book_estimate
                        )
                        book_updated = True
                    else:
                        book_updated = book_updated or False

                id_map[book.calibre_id] = mi

            if book_updated:
                reading_locations_updated += 1

        debug_print("_store_current_bookmark - Updating GUI - new DB engine")
        if kobo_chapteridbookmarked_column_name and len(id_map_chapteridbookmarked) > 0:
            debug_print(
                "_store_current_bookmark - Updating metadata - for column: %s number of changes=%d"
                % (
                    kobo_chapteridbookmarked_column_name,
                    len(id_map_chapteridbookmarked),
                )
            )
            library_db.new_api.set_field(
                kobo_chapteridbookmarked_column_name, id_map_chapteridbookmarked
            )
        if kobo_percentRead_column_name and len(id_map_percentRead) > 0:
            debug_print(
                "_store_current_bookmark - Updating metadata - for column: %s number of changes=%d"
                % (kobo_percentRead_column_name, len(id_map_percentRead))
            )
            library_db.new_api.set_field(
                kobo_percentRead_column_name, id_map_percentRead
            )
        if rating_column_name and len(id_map_rating) > 0:
            debug_print(
                "_store_current_bookmark - Updating metadata - for column: %s number of changes=%d"
                % (rating_column_name, len(id_map_rating))
            )
            library_db.new_api.set_field(rating_column_name, id_map_rating)
        if last_read_column_name and len(id_map_last_read) > 0:
            debug_print(
                "_store_current_bookmark - Updating metadata - for column: %s number of changes=%d"
                % (last_read_column_name, len(id_map_last_read))
            )
            library_db.new_api.set_field(last_read_column_name, id_map_last_read)
        if time_spent_reading_column_name and len(id_map_time_spent_reading) > 0:
            debug_print(
                "_store_current_bookmark - Updating metadata - for column: %s number of changes=%d"
                % (time_spent_reading_column_name, len(id_map_time_spent_reading))
            )
            library_db.new_api.set_field(
                time_spent_reading_column_name, id_map_time_spent_reading
            )
        if rest_of_book_estimate_column_name and len(id_map_rest_of_book_estimate) > 0:
            debug_print(
                "_store_current_bookmark - Updating metadata - for column: %s number of changes=%d"
                % (
                    rest_of_book_estimate_column_name,
                    len(id_map_rest_of_book_estimate),
                )
            )
            library_db.new_api.set_field(
                rest_of_book_estimate_column_name, id_map_rest_of_book_estimate
            )
        self.gui.iactions["Edit Metadata"].refresh_gui(list(id_map))

        self.hide_progressbar()
        if len(id_map) > 0:
            self.gui.status_bar.show_message(
                _("Kobo Utilities")
                + " - "
                + _("Storing reading positions completed - {0} changed.").format(
                    len(id_map)
                ),
                3000,
            )

        library_db.commit()

        debug_print("_store_current_bookmark - finished")

        return (reading_locations_updated, books_without_reading_locations, count_books)

    def _restore_current_bookmark(self, books):
        assert self.device is not None
        updated_books = 0
        not_on_device_books = 0
        count_books = 0

        profileName = self.options.get("profileName", None)
        (
            kobo_chapteridbookmarked_column,
            kobo_percentRead_column,
            rating_column,
            last_read_column,
            time_spent_reading_column,
            rest_of_book_estimate_column,
        ) = self.get_column_names(profileName)
        chapter_query = (
            "SELECT c1.ChapterIDBookmarked, "
            "c1.ReadStatus, "
            "c1.___PercentRead, "
            "c1.Attribution, "
            "c1.DateLastRead, "
            "c1.___SyncTime, "
            "c1.Title, "
            "c1.MimeType, "
            "c1.TimeSpentReading, "
            "c1.RestOfBookEstimate, "
        )
        if self.device.supports_ratings:
            chapter_query += " r.Rating, r.DateModified "
        else:
            chapter_query += " NULL as Rating, NULL as DateModified "
        chapter_query += "FROM content c1 "
        if self.device.supports_ratings:
            chapter_query += " left outer join ratings r on c1.ContentID = r.ContentID "
        chapter_query += "WHERE c1.BookId IS NULL AND c1.ContentId = ?"
        debug_print("_restore_current_bookmark - chapter_query= ", chapter_query)

        volume_zero_query = (
            "SELECT contentID FROM content WHERE BookId = ? and VolumeIndex = 0"
        )

        chapter_update = (
            "UPDATE content "
            "SET ChapterIDBookmarked = ? "
            "  , FirstTimeReading = ? "
            "  , ReadStatus = ? "
            "  , ___PercentRead = ? "
            "  , DateLastRead = ? "
            "  , TimeSpentReading = ? "
            "  , RestOfBookEstimate = ? "
            "WHERE BookID IS NULL "
            "AND ContentID = ?"
        )
        location_update = (
            "UPDATE content "
            "SET adobe_location = ? "
            "WHERE ContentType = 9 "
            "AND ContentID = ?"
        )
        rating_update = (
            "UPDATE ratings "
            "SET Rating = ?, "
            "DateModified = ? "
            "WHERE ContentID  = ?"
        )  # fmt: skip
        rating_insert = (
            "INSERT INTO ratings ("
            "Rating, "
            "DateModified, "
            "ContentID "
            ")"
            "VALUES (?, ?, ?)"
        )  # fmt: skip
        rating_delete = "DELETE FROM ratings WHERE ContentID = ?"

        connection = self.device_database_connection(use_row_factory=True)
        cursor = connection.cursor()

        for book in books:
            count_books += 1
            for contentID in book.contentIDs:
                chapter_values = (contentID,)
                cursor.execute(chapter_query, chapter_values)
                try:
                    result = next(cursor)
                except StopIteration:
                    result = None

                if result is not None:
                    debug_print("_restore_current_bookmark - result= ", result)
                    chapter_update = "UPDATE content SET "
                    chapter_set_clause = ""
                    chapter_values = []
                    location_update = "UPDATE content SET "
                    location_set_clause = ""
                    location_values = []
                    rating_change_query = None
                    rating_values = []

                    kobo_chapteridbookmarked = None
                    kobo_adobe_location = None
                    kobo_percentRead = None
                    kobo_time_spent_reading = None
                    kobo_rest_of_book_estimate = None

                    if kobo_chapteridbookmarked_column:
                        reading_location_string = book.get_user_metadata(
                            kobo_chapteridbookmarked_column, True
                        )["#value#"]
                        debug_print(
                            "_restore_current_bookmark - reading_location_string=",
                            reading_location_string,
                        )
                        if reading_location_string is not None:
                            if result["MimeType"] == MIMETYPE_KOBO:
                                kobo_chapteridbookmarked = reading_location_string
                                kobo_adobe_location = None
                            else:
                                reading_location_parts = reading_location_string.split(
                                    BOOKMARK_SEPARATOR
                                )
                                debug_print(
                                    "_restore_current_bookmark - reading_location_parts=",
                                    reading_location_parts,
                                )
                                debug_print(
                                    "_restore_current_bookmark - self.epub_location_like_kepub=",
                                    self.epub_location_like_kepub,
                                )
                                if self.epub_location_like_kepub:
                                    kobo_chapteridbookmarked = (
                                        reading_location_parts[1]
                                        if len(reading_location_parts) == 2
                                        else reading_location_string
                                    )
                                    kobo_adobe_location = None
                                else:
                                    if len(reading_location_parts) == 2:
                                        kobo_chapteridbookmarked = (
                                            contentID + "#" + reading_location_parts[0]
                                        )
                                        kobo_adobe_location = reading_location_parts[1]
                                    else:
                                        cursor.execute(volume_zero_query, [contentID])
                                        try:
                                            volume_zero_result = next(cursor)
                                            kobo_chapteridbookmarked = (
                                                volume_zero_result["ContentID"]
                                            )
                                            kobo_adobe_location = (
                                                reading_location_parts[0]
                                            )
                                        except StopIteration:
                                            volume_zero_result = None

                        if reading_location_string:
                            chapter_values.append(kobo_chapteridbookmarked)
                            chapter_set_clause += ", ChapterIDBookmarked  = ? "
                            location_values.append(kobo_adobe_location)
                            location_set_clause += ", adobe_location  = ? "
                        else:
                            debug_print(
                                "_restore_current_bookmark - reading_location_string=",
                                reading_location_string,
                            )

                    if kobo_percentRead_column:
                        kobo_percentRead = book.get_user_metadata(
                            kobo_percentRead_column, True
                        )["#value#"]
                        kobo_percentRead = (
                            kobo_percentRead
                            if kobo_percentRead
                            else result["___PercentRead"]
                        )
                        chapter_values.append(kobo_percentRead)
                        chapter_set_clause += ", ___PercentRead  = ? "

                    if self.options[cfg.KEY_READING_STATUS]:
                        if kobo_percentRead:
                            debug_print(
                                "_restore_current_bookmark - chapter_values= ",
                                chapter_values,
                            )
                            if kobo_percentRead == 100:
                                chapter_values.append(2)
                                debug_print(
                                    "_restore_current_bookmark - chapter_values= ",
                                    chapter_values,
                                )
                            else:
                                chapter_values.append(1)
                                debug_print(
                                    "_restore_current_bookmark - chapter_values= ",
                                    chapter_values,
                                )
                            chapter_set_clause += ", ReadStatus  = ? "
                            chapter_values.append("false")
                            chapter_set_clause += ", FirstTimeReading = ? "

                    last_read = None
                    if self.options[cfg.KEY_DATE_TO_NOW]:
                        last_read = strftime(
                            self.device_timestamp_string, time.gmtime()
                        )
                        debug_print(
                            "_restore_current_bookmark - setting to now - last_read= ",
                            last_read,
                        )
                    elif last_read_column:
                        last_read = book.get_user_metadata(last_read_column, True)[
                            "#value#"
                        ]
                        if last_read is not None:
                            last_read = last_read.strftime(self.device_timestamp_string)
                        debug_print(
                            "_restore_current_bookmark - setting from library - last_read= ",
                            last_read,
                        )
                    debug_print("_restore_current_bookmark - last_read= ", last_read)
                    debug_print(
                        "_restore_current_bookmark - result['___SyncTime']= ",
                        result["___SyncTime"],
                    )
                    if last_read is not None:
                        chapter_values.append(last_read)
                        chapter_set_clause += ", DateLastRead  = ? "
                        # Somewhere the "Recent" sort changed from only using the ___SyncTime if DateLastRead was null,
                        # Now it uses the MAX(___SyncTime, DateLastRead). Need to set ___SyncTime if it is after DateLastRead
                        # to correctly maintain sort order.
                        if (
                            self.device_fwversion is not None
                            and self.device_fwversion >= (4, 1, 0)
                            and last_read < result["___SyncTime"]
                        ):
                            debug_print(
                                "_restore_current_bookmark - setting ___SyncTime to same as DateLastRead"
                            )
                            chapter_values.append(last_read)
                            chapter_set_clause += ", ___SyncTime  = ? "

                    debug_print(
                        "_restore_current_bookmark - self.options[cfg.KEY_SET_RATING]= ",
                        self.options[cfg.KEY_SET_RATING],
                    )
                    rating = None
                    if rating_column is not None and self.options[cfg.KEY_SET_RATING]:
                        if rating_column == "rating":
                            rating = book.rating
                        else:
                            rating = book.get_user_metadata(rating_column, True)[
                                "#value#"
                            ]
                        rating = None if not rating or rating == 0 else rating / 2
                        debug_print(
                            "_restore_current_bookmark - rating=",
                            rating,
                            " result['Rating']=",
                            result["Rating"],
                        )
                        rating_values.append(rating)
                        if last_read is not None:
                            rating_values.append(last_read)
                        else:
                            rating_values.append(
                                strftime(self.device_timestamp_string, time.gmtime())
                            )

                        rating_values.append(contentID)
                        if rating is None:
                            rating_change_query = rating_delete
                            rating_values = (contentID,)
                        elif (
                            result["DateModified"] is None
                        ):  # If the date modified column does not have a value, there is no rating column
                            rating_change_query = rating_insert
                        else:
                            rating_change_query = rating_update

                    if time_spent_reading_column:
                        kobo_time_spent_reading = book.get_user_metadata(
                            time_spent_reading_column, True
                        )["#value#"]
                        kobo_time_spent_reading = (
                            kobo_time_spent_reading
                            if kobo_time_spent_reading is not None
                            else 0
                        )
                        chapter_values.append(kobo_time_spent_reading)
                        chapter_set_clause += ", TimeSpentReading = ? "

                    if rest_of_book_estimate_column:
                        kobo_rest_of_book_estimate = book.get_user_metadata(
                            rest_of_book_estimate_column, True
                        )["#value#"]
                        kobo_rest_of_book_estimate = (
                            kobo_rest_of_book_estimate
                            if kobo_rest_of_book_estimate is not None
                            else 0
                        )
                        chapter_values.append(kobo_rest_of_book_estimate)
                        chapter_set_clause += ", RestOfBookEstimate = ? "

                    debug_print(
                        "_restore_current_bookmark - found contentId='%s'" % (contentID)
                    )
                    debug_print(
                        "_restore_current_bookmark - kobo_chapteridbookmarked=",
                        kobo_chapteridbookmarked,
                    )
                    debug_print(
                        "_restore_current_bookmark - kobo_adobe_location=",
                        kobo_adobe_location,
                    )
                    debug_print(
                        "_restore_current_bookmark - kobo_percentRead=",
                        kobo_percentRead,
                    )
                    debug_print("_restore_current_bookmark - rating=", rating)
                    debug_print("_restore_current_bookmark - last_read=", last_read)
                    debug_print(
                        "_restore_current_bookmark - kobo_time_spent_reading=",
                        kobo_time_spent_reading,
                    )
                    debug_print(
                        "_restore_current_bookmark - kobo_rest_of_book_estimate=",
                        kobo_rest_of_book_estimate,
                    )

                    if len(chapter_set_clause) > 0:
                        chapter_update += chapter_set_clause[1:]
                        chapter_update += "WHERE ContentID = ? AND BookID IS NULL"
                        chapter_values.append(contentID)
                    else:
                        debug_print(
                            "_restore_current_bookmark - no changes found to selected metadata. No changes being made."
                        )
                        not_on_device_books += 1
                        continue

                    debug_print(
                        "_restore_current_bookmark - chapter_update=%s" % chapter_update
                    )
                    debug_print(
                        "_restore_current_bookmark - chapter_values= ",
                        chapter_values,
                    )
                    try:
                        cursor.execute(chapter_update, chapter_values)
                        if len(location_set_clause) > 0 and not (
                            result["MimeType"] == MIMETYPE_KOBO
                            or self.epub_location_like_kepub
                        ):
                            location_update += location_set_clause[1:]
                            location_update += (
                                " WHERE ContentID = ? AND BookID IS NOT NULL"
                            )
                            location_values.append(kobo_chapteridbookmarked)
                            debug_print(
                                "_restore_current_bookmark - location_update=%s"
                                % location_update
                            )
                            debug_print(
                                "_restore_current_bookmark - location_values= ",
                                location_values,
                            )
                            cursor.execute(location_update, location_values)
                        if rating_change_query:
                            debug_print(
                                "_restore_current_bookmark - rating_change_query=%s"
                                % rating_change_query
                            )
                            debug_print(
                                "_restore_current_bookmark - rating_values= ",
                                rating_values,
                            )
                            cursor.execute(rating_change_query, rating_values)

                        updated_books += 1
                    except:
                        debug_print(
                            "    Database Exception:  Unable to set bookmark info."
                        )
                        raise
                else:
                    debug_print(
                        "_restore_current_bookmark - no match for title='%s' contentId='%s'"
                        % (book.title, book.contentID)
                    )
                    not_on_device_books += 1
        debug_print(
            "_restore_current_bookmark - Update summary: Books updated=%d, not on device=%d, Total=%d"
            % (updated_books, not_on_device_books, count_books)
        )

        return (updated_books, not_on_device_books, count_books)

    def _get_shelves_from_device(self, books, options=None):
        if options:
            self.options = options

        count_books = 0
        books_with_shelves = 0
        books_without_shelves = 0
        replace_shelves = self.options[cfg.KEY_REPLACE_SHELVES]

        total_books = len(books)
        self.show_progressbar(total_books)

        fetch_query = (
            "SELECT c.ContentID, sc.ShelfName "
            "FROM content c LEFT OUTER JOIN ShelfContent sc "
            "ON c.ContentID = sc.ContentId AND c.ContentType = 6  AND sc._IsDeleted = 'false' "
            "JOIN Shelf s ON s.Name = sc.ShelfName AND s._IsDeleted = 'false' "
            "WHERE c.ContentID = ? "
            "ORDER BY c.ContentID, sc.ShelfName"
        )

        connection = self.device_database_connection()
        library_db = self.gui.current_db
        library_config = cfg.get_library_config(library_db)
        bookshelf_column_name = library_config.get(
            cfg.KEY_SHELVES_CUSTOM_COLUMN,
            cfg.GET_SHELVES_OPTIONS_DEFAULTS[cfg.KEY_SHELVES_CUSTOM_COLUMN],
        )
        debug_print(
            "_get_shelves_from_device - bookshelf_column_name=",
            bookshelf_column_name,
        )
        bookshelf_column = library_db.field_metadata[bookshelf_column_name]
        bookshelf_column_label = library_db.field_metadata.key_to_label(
            bookshelf_column_name
        )
        bookshelf_column_is_multiple = (
            bookshelf_column["is_multiple"] is not None
            and len(bookshelf_column["is_multiple"]) > 0
        )
        debug_print(
            "_get_shelves_from_device - bookshelf_column_label=",
            bookshelf_column_label,
        )
        debug_print(
            "_get_shelves_from_device - bookshelf_column_is_multiple=",
            bookshelf_column_is_multiple,
        )

        cursor = connection.cursor()
        for book in books:
            self.set_progressbar_label(_("Getting shelves for ") + book.title)
            self.increment_progressbar()
            count_books += 1
            shelf_names = []
            update_library = False
            for contentID in book.contentIDs:
                debug_print(
                    "_get_shelves_from_device - title='%s' contentId='%s'"
                    % (book.title, contentID)
                )
                fetch_values = (contentID,)
                debug_print(
                    "_get_shelves_from_device - tetch_query='%s'" % (fetch_query)
                )
                cursor.execute(fetch_query, fetch_values)

                for row in cursor:
                    debug_print("_get_shelves_from_device - result=", row)
                    shelf_names.append(row[1])
                    update_library = True

            if len(shelf_names) > 0:
                books_with_shelves += 1
            else:
                books_without_shelves += 1
                continue

            if update_library and len(shelf_names) > 0:
                debug_print(
                    "_get_shelves_from_device - device shelf_names='%s'" % (shelf_names)
                )
                debug_print(
                    "_get_shelves_from_device - device set(shelf_names)='%s'"
                    % (set(shelf_names))
                )
                old_value = book.get_user_metadata(bookshelf_column_name, True)[
                    "#value#"
                ]
                debug_print(
                    "_get_shelves_from_device - library shelf names='%s'" % (old_value)
                )
                if old_value is None or not set(old_value) == set(shelf_names):
                    debug_print("_get_shelves_from_device - shelves are not the same")
                    shelf_names = (
                        list(set(shelf_names))
                        if bookshelf_column_is_multiple
                        else ", ".join(shelf_names)
                    )
                    debug_print(
                        "_get_shelves_from_device - device shelf_names='%s'"
                        % (shelf_names)
                    )
                    if replace_shelves or old_value is None:
                        new_value = shelf_names
                    elif bookshelf_column_is_multiple:
                        new_value = old_value + shelf_names
                    else:
                        new_value = old_value + ", " + shelf_names
                    debug_print(
                        "_get_shelves_from_device - new shelf names='%s'" % (new_value)
                    )
                    library_db.set_custom(
                        book.calibre_id,
                        new_value,
                        label=bookshelf_column_label,
                        commit=False,
                    )

            else:
                books_with_shelves -= 1
                books_without_shelves += 1

        library_db.commit()
        self.hide_progressbar()

        return (books_with_shelves, books_without_shelves, count_books)

    def fetch_book_fonts(self):
        debug_print("fetch_book_fonts - start")
        connection = self.device_database_connection()
        book_options = {}

        fetch_query = (
            "SELECT  "
            '"ReadingFontFamily", '
            '"ReadingFontSize", '
            '"ReadingAlignment", '
            '"ReadingLineHeight", '
            '"ReadingLeftMargin", '
            '"ReadingRightMargin"  '
            "FROM content_settings "
            "WHERE ContentType = ? "
            "AND ContentId = ?"
        )
        fetch_values = (
            self.CONTENTTYPE,
            self.single_contentID,
        )

        cursor = connection.cursor()
        cursor.execute(fetch_query, fetch_values)
        try:
            result = next(cursor)
        except StopIteration:
            result = None
        if result is not None:
            book_options["readingFontFamily"] = result[0]
            book_options["readingFontSize"] = result[1]
            book_options["readingAlignment"] = result[2].title() if result[2] else "Off"
            book_options["readingLineHeight"] = result[3]
            book_options["readingLeftMargin"] = result[4]
            book_options["readingRightMargin"] = result[5]

        return book_options

    @property
    def device_timestamp_string(self):
        if not self.timestamp_string:
            if (
                self.device is not None
                and isinstance(self.device.device, KOBOTOUCH)
                and "TIMESTAMP_STRING" in dir(self.device)
            ):
                self.timestamp_string = self.device.device.TIMESTAMP_STRING
            else:
                self.timestamp_string = "%Y-%m-%dT%H:%M:%SZ"
        return self.timestamp_string

    def _set_reader_fonts(self, contentIDs, delete=False):
        debug_print("_set_reader_fonts - start")
        updated_fonts = 0
        added_fonts = 0
        deleted_fonts = 0
        count_books = 0

        connection = self.device_database_connection()
        debug_print("_set_reader_fonts - connected to device database")

        test_query = (
            "SELECT 1 "
            "FROM content_settings "
            "WHERE ContentType = ? "
            "AND ContentId = ?"
        )  # fmt: skip
        delete_query = (
            "DELETE "
            "FROM content_settings "
            "WHERE ContentType = ? "
            "AND ContentId = ?"
        )  # fmt: skip

        add_query = None
        add_values = ()
        update_query = None
        update_values = ()
        if not delete:
            font_face = self.options[cfg.KEY_READING_FONT_FAMILY]
            justification = self.options[cfg.KEY_READING_ALIGNMENT].lower()
            justification = (
                None if justification == "Off" or justification == "" else justification
            )
            font_size = self.options[cfg.KEY_READING_FONT_SIZE]
            line_spacing = self.options[cfg.KEY_READING_LINE_HEIGHT]
            left_margins = self.options[cfg.KEY_READING_LEFT_MARGIN]
            right_margins = self.options[cfg.KEY_READING_RIGHT_MARGIN]

            add_query = (
                "INSERT INTO content_settings ( "
                '"ContentType", '
                '"DateModified", '
                '"ReadingFontFamily", '
                '"ReadingFontSize", '
                '"ReadingAlignment", '
                '"ReadingLineHeight", '
                '"ReadingLeftMargin", '
                '"ReadingRightMargin", '
                '"ContentID" '
                ") "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            add_values = (
                self.CONTENTTYPE,
                time.strftime(self.device_timestamp_string, time.gmtime()),
                font_face,
                font_size,
                justification,
                line_spacing,
                left_margins,
                right_margins,
            )
            update_query = (
                "UPDATE content_settings "
                'SET "DateModified" = ?, '
                '"ReadingFontFamily" = ?, '
                '"ReadingFontSize" = ?, '
                '"ReadingAlignment" = ?, '
                '"ReadingLineHeight" = ?, '
                '"ReadingLeftMargin" = ?, '
                '"ReadingRightMargin" = ? '
                "WHERE ContentType = ?  "
                "AND ContentId = ?"
            )
            update_values = (
                time.strftime(self.device_timestamp_string, time.gmtime()),
                font_face,
                font_size,
                justification,
                line_spacing,
                left_margins,
                right_margins,
                self.CONTENTTYPE,
            )

        cursor = connection.cursor()

        for contentID in contentIDs:
            test_values = (
                self.CONTENTTYPE,
                contentID,
            )
            if delete:
                cursor.execute(delete_query, test_values)
                deleted_fonts += 1
            else:
                cursor.execute(test_query, test_values)
                try:
                    result = next(cursor)
                    debug_print("_set_reader_fonts - found existing row:", result)
                    if not self.options[cfg.KEY_DO_NOT_UPDATE_IF_SET]:
                        cursor.execute(update_query, update_values + (contentID,))
                        updated_fonts += 1
                except StopIteration:
                    cursor.execute(add_query, add_values + (contentID,))
                    added_fonts += 1
            count_books += 1

        return updated_fonts, added_fonts, deleted_fonts, count_books

    def get_config_file(self):
        assert self.device is not None
        assert self.device.device._main_prefix is not None
        config_file_path = self.device.device.normalize_path(
            self.device.device._main_prefix + ".kobo/Kobo/Kobo eReader.conf"
        )
        assert config_file_path is not None
        koboConfig = ConfigParser(allow_no_value=True)
        koboConfig.optionxform = str  # type: ignore[reportAttributeAccessIssue]
        debug_print("get_config_file - config_file_path=", config_file_path)
        try:
            koboConfig.read(config_file_path)
        except Exception as e:
            debug_print("get_config_file - exception=", e)
            raise

        return koboConfig, config_file_path

    def _update_config_reader_settings(self, options):
        config_section_reading = "Reading"

        koboConfig, config_file_path = self.get_config_file()

        if not koboConfig.has_section(config_section_reading):
            koboConfig.add_section(config_section_reading)

        koboConfig.set(
            config_section_reading,
            cfg.KEY_READING_FONT_FAMILY,
            options[cfg.KEY_READING_FONT_FAMILY],
        )
        koboConfig.set(
            config_section_reading,
            cfg.KEY_READING_ALIGNMENT,
            options[cfg.KEY_READING_ALIGNMENT],
        )
        koboConfig.set(
            config_section_reading,
            cfg.KEY_READING_FONT_SIZE,
            "%g" % options[cfg.KEY_READING_FONT_SIZE],
        )
        koboConfig.set(
            config_section_reading,
            cfg.KEY_READING_LINE_HEIGHT,
            "%g" % options[cfg.KEY_READING_LINE_HEIGHT],
        )
        koboConfig.set(
            config_section_reading,
            cfg.KEY_READING_LEFT_MARGIN,
            "%g" % options[cfg.KEY_READING_LEFT_MARGIN],
        )
        koboConfig.set(
            config_section_reading,
            cfg.KEY_READING_RIGHT_MARGIN,
            "%g" % options[cfg.KEY_READING_RIGHT_MARGIN],
        )

        with open(config_file_path, "w") as config_file:
            koboConfig.write(config_file)

    def _backup_annotation_files(self, books, dest_path):
        annotations_found = 0
        kepubs = 0
        no_annotations = 0
        count_books = 0

        device = self.device
        assert device is not None

        debug_print("_backup_annotation_files - self.device.path='%s'" % (device.path))
        kepub_dir = device.device.normalize_path(".kobo/kepub/")
        annotations_dir = device.device.normalize_path(
            device.path + "Digital Editions/Annotations/"
        )
        annotations_ext = ".annot"

        for book in books:
            count_books += 1

            for book_path in book.paths:
                relative_path = book_path.replace(device.path, "")
                annotation_file = device.device.normalize_path(
                    annotations_dir + relative_path + annotations_ext
                )
                assert annotation_file is not None
                debug_print(
                    "_backup_annotation_files - kepub title='%s' annotation_file='%s'"
                    % (book.title, annotation_file)
                )
                if relative_path.startswith(kepub_dir):
                    debug_print(
                        "_backup_annotation_files - kepub title='%s' book_path='%s'"
                        % (book.title, book_path)
                    )
                    kepubs += 1
                elif os.path.exists(annotation_file):
                    debug_print(
                        "_backup_annotation_files - book_path='%s'" % (book_path)
                    )
                    backup_file = device.device.normalize_path(
                        dest_path + "/" + relative_path + annotations_ext
                    )
                    assert backup_file is not None
                    debug_print(
                        "_backup_annotation_files - backup_file='%s'" % (backup_file)
                    )
                    d, p = os.path.splitdrive(backup_file)
                    debug_print("_backup_annotation_files - d='%s' p='%s'" % (d, p))
                    backup_path = os.path.dirname(str(backup_file))
                    try:
                        os.makedirs(backup_path)
                    except OSError:
                        debug_print(
                            "_backup_annotation_files - path exists: backup_path='%s'"
                            % (backup_path)
                        )
                        pass
                    shutil.copyfile(annotation_file, backup_file)
                    annotations_found += 1
                else:
                    debug_print(
                        "_backup_annotation_files - book_path='%s'" % (book_path)
                    )
                    no_annotations += 1

        debug_print(
            "Backup summary: annotations_found=%d, no_annotations=%d, kepubs=%d Total=%d"
            % (annotations_found, no_annotations, kepubs, count_books)
        )

        return (annotations_found, no_annotations, kepubs, count_books)

    def _check_device_is_ready(self, function_message):
        self.device = self.get_device()

        if self.gui.job_manager.has_device_jobs(queued_also=True):
            error_dialog(
                self.gui,
                self.giu_name,
                function_message + "<br/>" + _("Device jobs are running or queued."),
                show=True,
                show_copy_button=False,
            )
            return False

        if self.device is None:
            error_dialog(
                self.gui,
                self.giu_name,
                function_message + "<br/>" + _("No device connected."),
                show=True,
                show_copy_button=False,
            )
            return False

        return True

    """
    Start of ToC Updating
    """

    """
    Compare the ToC between calibre and the device and update it.
    """

    def update_book_toc_on_device(self):
        debug_print("KoboTouchTOCUpdateBase::update_book_toc_on_device - start")

        if not self._check_device_is_ready(
            _("Cannot update the ToC of books on the device")
        ):
            return

        if len(self.gui.library_view.get_selected_ids()) == 0:
            debug_print(
                "KoboTouchTOCUpdateBase::update_book_toc_on_device - no books selected"
            )
            return

        db = self.gui.current_db

        # Use local versions as just need a few details.
        def _convert_calibre_ids_to_books(db, ids):
            return [_convert_calibre_id_to_book(db, book_id) for book_id in ids]

        def _convert_calibre_id_to_book(db, book_id, get_cover=False):
            mi = db.get_metadata(book_id, index_is_id=True, get_cover=get_cover)
            book = {}
            book["good"] = True
            book["calibre_id"] = mi.id
            book["title"] = mi.title
            book["author"] = authors_to_string(mi.authors)
            book["author_sort"] = mi.author_sort
            book["comment"] = ""
            book["url"] = ""
            book["added"] = False
            return book

        book_ids = self.gui.library_view.get_selected_ids()
        books = _convert_calibre_ids_to_books(db, book_ids)
        self.progressbar(_("Getting ToC status for books"), on_top=True)
        self.set_progressbar_label(_("Number of books: {0}").format(len(books)))
        self.show_progressbar(len(books))

        self._get_chapter_status(db, books)

        self.hide_progressbar()

        d = UpdateBooksToCDialog(
            self.gui,
            self,
            self.qaction.icon(),
            books,
        )
        d.exec_()
        if d.result() != d.Accepted:
            return

        update_books = d.books_to_update_toc
        debug_print(
            "update_book_toc_on_device - len(update_books)=%s" % len(update_books)
        )

        debug_print("update_book_toc_on_device - update_books=%d" % len(update_books))
        # only if there's some good ones.
        update_books = list(filter(lambda x: not x["good"], update_books))
        debug_print(
            "update_book_toc_on_device - filtered update_books=%d" % len(update_books)
        )
        if len(update_books) > 0:
            self.options = {}
            self.options["version"] = self.version
            debug_print("version=%s" % self.version)

            self.update_device_toc_for_books(update_books)

    def load_ebook(self, pathtoebook):
        debug_print("KoboUtilities::load_ebook - creating container")
        try:
            container = EpubContainer(pathtoebook, default_log)
        except DRMError:
            container = None
            raise

        return container

    def _read_toc(self, toc, toc_depth=1, format_on_device="EPUB", container=None):
        chapters = []
        debug_print("KoboUtilities::_read_toc")
        debug_print("_read_toc - toc.title=", toc.title)
        debug_print("_read_toc - toc_depth=", toc_depth)
        debug_print("KoboUtilities::_read_toc - parsing ToC")
        for item in toc:
            debug_print("_read_toc - item.title=", item.title)
            debug_print("_read_toc - item.depth=", item.depth)
            if item.dest is not None:
                chapter = {}
                chapter["title"] = item.title
                chapter["path"] = item.dest
                if format_on_device == "KEPUB" and container is not None:
                    chapter["path"] = container.name_to_href(
                        item.dest, container.opf_name
                    )
                chapter["toc_depth"] = toc_depth
                if item.frag:
                    chapter["fragment"] = item.frag
                    chapter["path"] = "{0}#{1}".format(chapter["path"], item.frag)
                if format_on_device == "KEPUB":
                    chapter["path"] = "{0}-{1}".format(chapter["path"], toc_depth)
                chapter["added"] = False
                chapters.append(chapter)
            chapters += self._read_toc(
                item,
                toc_depth + 1,
                format_on_device=format_on_device,
                container=container,
            )

        debug_print("KoboUtilities::_read_toc - finished")
        return chapters

    def _get_manifest_entries(self, container):
        debug_print("KoboUtilities::_get_manifest_entries")

        total_spine_size = 0
        manifest_entries = []
        debug_print(
            "KoboUtilities::_get_manifest_entries - spine_items - manifest_entries=",
            manifest_entries,
        )
        for spine_name, _spine_linear in container.spine_names:
            spine_path = container.name_to_href(spine_name, container.opf_name)
            file_size = container.filesize(spine_name)
            total_spine_size += file_size
            manifest_entries.append(
                {"path": spine_path, "file_size": file_size, "name": spine_name}
            )
        debug_print(
            "KoboUtilities::_get_manifest_entries - manifest_entries=", manifest_entries
        )
        return manifest_entries

    def _get_chapter_list(
        self, book, pathtoebook, book_location, format_on_device="EPUB"
    ):
        debug_print("KoboUtilities::_get_chapter_list - for %s" % book_location)
        from calibre.ebooks.oeb.polish.toc import get_toc

        container = self.load_ebook(pathtoebook)
        debug_print(
            "KoboUtilities::_get_chapter_list - container.opf_dir='%s'"
            % container.opf_dir
        )
        debug_print(
            "KoboUtilities::_get_chapter_list - container.opf_name='%s'"
            % container.opf_name
        )
        book[book_location + "_opf_name"] = container.opf_name
        book[book_location + "_opf_dir"] = container.opf_dir
        last_slash_index = book[book_location + "_opf_name"].rfind("/")
        book[book_location + "_opf_dir"] = (
            book[book_location + "_opf_name"][:last_slash_index]
            if last_slash_index >= 0
            else ""
        )
        debug_print(
            "KoboUtilities::_get_chapter_list - book[book_location + '_opf_dir']='%s'"
            % book[book_location + "_opf_dir"]
        )
        toc = get_toc(container)
        debug_print("KoboUtilities::_get_chapter_list - toc=", toc)

        book[book_location + "_chapters"] = self._read_toc(
            toc, format_on_device=format_on_device, container=container
        )
        debug_print(
            "KoboUtilities::_get_chapter_list - chapters=",
            book[book_location + "_chapters"],
        )
        book[book_location + "_manifest"] = self._get_manifest_entries(container)
        book[book_location + "_container"] = container
        return

    def _get_chapter_status(self, db, books):
        debug_print("Starting check of chapter status for {0} books".format(len(books)))
        assert self.device is not None
        connection = self.device_database_connection(use_row_factory=True)
        i = 0
        debug_print(
            "_get_chapter_status - device format_map='{0}".format(
                self.device.device.settings().format_map  # type: ignore[reportAttributeAccessIssue]
            )
        )
        for book in books:
            self.increment_progressbar()
            debug_print("\nHandling book: {0}".format(book))
            debug_print(
                "Getting chapters for book number {0}, title={1}, author={2}".format(
                    i, book["title"], book["author"]
                )
            )
            book["library_chapters"] = []
            book["kobo_chapters"] = []
            book["kobo_database_chapters"] = []
            book["kobo_format_status"] = False
            book["kobo_database_status"] = False
            book["can_update_toc"] = False

            book_id = book["calibre_id"]

            debug_print("Finding book on device...")
            device_book_path = self.get_device_path_from_id(book_id)
            if device_book_path is None:
                book["comment"] = _("eBook is not on Kobo eReader")
                book["good"] = False
                book["icon"] = "window-close.png"
                book["can_update_toc"] = False
                continue
            extension = os.path.splitext(device_book_path)[1]
            ContentType = (
                self.device.device.get_content_type_from_extension(extension)
                if extension != ""
                else self.device.device.get_content_type_from_path(device_book_path)
            )
            book["ContentID"] = self.device.device.contentid_from_path(
                device_book_path, ContentType
            )
            if ".kepub.epub" in book["ContentID"]:
                book["kobo_format"] = "KEPUB"
            elif ".epub" in book["ContentID"]:
                book["kobo_format"] = "EPUB"
            else:
                book["kobo_format"] = extension[1:].upper()
                book["comment"] = _("eBook on Kobo eReader is not supported format")
                book["good"] = True
                book["icon"] = "window-close.png"
                book["can_update_toc"] = False
                book["kobo_format_status"] = True
                continue

            debug_print("Checking for book in library...")
            if db.has_format(book_id, book["kobo_format"], index_is_id=True):
                book["library_format"] = book["kobo_format"]
            elif (
                book["kobo_format"] == "KEPUB"
                and "EPUB".lower() in self.device.device.settings().format_map  # type: ignore[reportAttributeAccessIssue]
                and db.has_format(book_id, "EPUB", index_is_id=True)
            ):
                book["library_format"] = "EPUB"
            else:
                book["comment"] = _(
                    "No suitable format in library for book. The format of the device is {0}"
                ).format(book["kobo_format"])
                book["good"] = False
                continue

            debug_print("Getting path to book in library...")
            pathtoebook = db.format_abspath(
                book_id, book["library_format"], index_is_id=True
            )
            debug_print("Getting chapters from library...")
            try:
                self._get_chapter_list(
                    book,
                    pathtoebook,
                    "library",
                    format_on_device=book["kobo_format"],
                )
            except DRMError:
                book["comment"] = _("eBook in library has DRM")
                book["good"] = False
                book["icon"] = "window-close.png"
                continue

            debug_print("Getting chapters from book on device...")
            try:
                self._get_chapter_list(
                    book,
                    device_book_path,
                    "kobo",
                    format_on_device=book["kobo_format"],
                )
            except DRMError:
                book["comment"] = _("eBook on Kobo eReader has DRM")
                book["good"] = False
                book["icon"] = "window-close.png"
                continue

            debug_print("Getting chapters from device database...")
            if book["kobo_format"] == "KEPUB":
                book["kobo_database_chapters"] = self._get_database_chapters(
                    connection, book["ContentID"], book["kobo_format"], 899
                )
                debug_print(
                    "_get_chapter_status - book['kobo_database_chapters']=",
                    book["kobo_database_chapters"],
                )
                book["kobo_database_manifest"] = self._get_database_chapters(
                    connection, book["ContentID"], book["kobo_format"], 9
                )
                debug_print(
                    "_get_chapter_status - book['kobo_database_manifest']=",
                    book["kobo_database_manifest"],
                )
            else:
                book["kobo_database_chapters"] = self._get_database_chapters(
                    connection, book["ContentID"], book["kobo_format"], 9
                )

            koboDatabaseReadingLocation = self._get_database_current_chapter(
                book["ContentID"], connection
            )
            if (
                koboDatabaseReadingLocation is not None
                and len(koboDatabaseReadingLocation) > 0
            ):
                book["koboDatabaseReadingLocation"] = koboDatabaseReadingLocation
                if (
                    isinstance(self.device.device, KOBOTOUCH)
                    and (
                        self.device.device.fwversion
                        < self.device.device.min_fwversion_epub_location
                    )  # type: ignore[reportOperatorIssue]
                ):
                    reading_location_match = re.match(
                        r"\((\d+)\)(.*)\#?.*", koboDatabaseReadingLocation
                    )
                    assert reading_location_match is not None
                    reading_location_volumeIndex, reading_location_file = (
                        reading_location_match.groups()
                    )
                    reading_location_volumeIndex = int(reading_location_volumeIndex)
                    try:
                        debug_print(
                            "_get_chapter_status - reading_location_volumeIndex =%d, reading_location_file='%s'"
                            % (reading_location_volumeIndex, reading_location_file)
                        )
                        debug_print(
                            "_get_chapter_status - chapter location='%s'"
                            % (
                                book["kobo_database_chapters"][
                                    reading_location_volumeIndex
                                ]["path"],
                            )
                        )
                    except Exception:
                        debug_print(
                            "_get_chapter_status - exception logging reading location details."
                        )
                    new_toc_readingposition_index = self._get_readingposition_index(
                        book, koboDatabaseReadingLocation
                    )
                    if new_toc_readingposition_index is not None:
                        try:
                            real_path, chapter_position = book[
                                "kobo_database_chapters"
                            ][reading_location_volumeIndex]["path"].split("#")
                            debug_print(
                                "_get_chapter_status - chapter_location='%s'"
                                % (chapter_position,)
                            )
                            book["kobo_database_chapters"][
                                reading_location_volumeIndex
                            ]["path"] = real_path
                            new_chapter_position = "{0}#{1}".format(
                                book["library_chapters"][new_toc_readingposition_index][
                                    "path"
                                ],
                                chapter_position,
                            )
                            book["library_chapters"][new_toc_readingposition_index][
                                "chapter_position"
                            ] = new_chapter_position
                            book["readingposition_index"] = (
                                new_toc_readingposition_index
                            )
                            debug_print(
                                "_get_chapter_status - new chapter_location='%s'"
                                % (new_chapter_position,)
                            )
                        except Exception:
                            debug_print(
                                "_get_chapter_status - current chapter has not location. Not setting it."
                            )
            debug_print(
                "_get_chapter_status - len(book['library_chapters']) =",
                len(book["library_chapters"]),
            )
            debug_print(
                "_get_chapter_status - len(book['kobo_chapters']) =",
                len(book["kobo_chapters"]),
            )
            debug_print(
                "_get_chapter_status - len(book['kobo_database_chapters']) =",
                len(book["kobo_database_chapters"]),
            )
            if len(book["library_chapters"]) == len(book["kobo_database_chapters"]):
                debug_print(
                    "_get_chapter_status - ToC lengths the same in library and database."
                )
                book["good"] = True
                book["icon"] = "ok.png"
                book["comment"] = "Chapters match in all places"

            if len(book["library_chapters"]) != len(book["kobo_chapters"]):
                debug_print(
                    "_get_chapter_status - ToC lengths different between library and device."
                )
                book["kobo_format_status"] = False
                book["comment"] = _("Book needs to be updated on Kobo eReader")
                book["icon"] = "toc.png"
            else:
                book["kobo_format_status"] = self._compare_toc_entries(
                    book, book_format1="library", book_format2="kobo"
                )
                if book["kobo_format"] == "KEPUB":
                    book["kobo_format_status"] = book[
                        "kobo_format_status"
                    ] and self._compare_manifest_entries(
                        book, book_format1="library", book_format2="kobo"
                    )
                if book["kobo_format_status"]:
                    book["comment"] = (
                        "Chapters in the book on the device do not match the library"
                    )
            book["good"] = book["good"] and book["kobo_format_status"]

            if len(book["kobo_database_chapters"]) == 0:
                debug_print("_get_chapter_status - No chapters in database for book.")
                book["can_update_toc"] = False
                book["kobo_database_status"] = False
                book["comment"] = "Book needs to be imported on the device"
                book["icon"] = "window-close.png"
                continue
            elif len(book["kobo_chapters"]) != len(book["kobo_database_chapters"]):
                debug_print(
                    "_get_chapter_status - ToC lengths different between book on device and the database."
                )
                book["kobo_database_status"] = False
                book["comment"] = "Chapters need to be updated in Kobo eReader database"
                book["icon"] = "toc.png"
                book["can_update_toc"] = True
            else:
                book["kobo_database_status"] = self._compare_toc_entries(
                    book, book_format1="kobo", book_format2="kobo_database"
                )
                if book["kobo_format"] == "KEPUB":
                    book["kobo_database_status"] = book[
                        "kobo_database_status"
                    ] and self._compare_manifest_entries(
                        book, book_format1="kobo", book_format2="kobo_database"
                    )
                if book["kobo_database_status"]:
                    book["comment"] = (
                        "Chapters need to be updated in Kobo eReader database"
                    )
                book["can_update_toc"] = True
            book["good"] = book["good"] and book["kobo_database_status"]

            if book["good"]:
                book["icon"] = "ok.png"
                book["comment"] = "Chapters match in all places"
            else:
                book["icon"] = "toc.png"
                if not book["kobo_format_status"]:
                    book["comment"] = _("Book needs to be updated on Kobo eReader")
                elif not book["kobo_database_status"]:
                    book["comment"] = (
                        "Chapters need to be updated in Kobo eReader database"
                    )

            debug_print("\nFinished with book\n")  # {0}\n".format(book))
            i += 1

    def _get_database_chapters(
        self, connection, koboContentId, book_format="EPUB", contentId=9
    ):
        chapters = []
        debug_print(
            "KoboUtilities::_get_database_chapters - koboContentId='%s', book_format='%s', contentId='%s'"
            % (koboContentId, book_format, contentId)
        )
        chapterQuery = (
            "SELECT ContentID, Title, adobe_location, VolumeIndex, Depth, ChapterIDBookmarked "
            "FROM content "
            "WHERE BookID = ?"
            "AND ContentType = ?"
        )
        cursor = connection.cursor()
        t = (koboContentId, contentId)
        cursor.execute(chapterQuery, t)
        for row in cursor:
            chapter = {}
            debug_print(
                "_get_database_chapters - chapterContentId=%s" % (row["ContentID"],)
            )
            chapter["chapterContentId"] = row["ContentID"]
            chapter["VolumeIndex"] = row["VolumeIndex"]
            chapter["title"] = row["Title"]
            if book_format == "KEPUB":
                path_separator_index = row["ContentID"].find("!")
                path_separator_index = row["ContentID"].find(
                    "!", path_separator_index + 1
                )
                chapter["path"] = row["ContentID"][path_separator_index + 1 :]
            else:
                chapter["path"] = row["ContentID"][len(koboContentId) + 1 :]
                path_separator_index = chapter["path"].find(")")
                chapter["path"] = chapter["path"][path_separator_index + 1 :]
            chapter["adobe_location"] = row["adobe_location"]
            chapter["ChapterIDBookmarked"] = row["ChapterIDBookmarked"]
            chapter["toc_depth"] = row["Depth"]
            chapter["added"] = True
            debug_print("_get_database_chapters - chapter= ", chapter)
            chapters.append(chapter)

        chapters.sort(key=lambda x: x["VolumeIndex"])

        return chapters

    def _get_database_current_chapter(
        self, koboContentId: str, connection
    ) -> Optional[str]:
        debug_print("KoboUtilities::_get_database_current_chapter")
        readingLocationchapterQuery = "SELECT ContentID, ChapterIDBookmarked, ReadStatus FROM content WHERE ContentID = ?"
        cursor = connection.cursor()
        t = (koboContentId,)
        cursor.execute(readingLocationchapterQuery, t)
        try:
            result = next(cursor)
            debug_print(
                "KoboUtilities::_get_database_current_chapter - result='%s'" % (result,)
            )
            if result["ChapterIDBookmarked"] is None:
                reading_location = None
            else:
                reading_location = result["ChapterIDBookmarked"]
                assert self.device is not None
                if (
                    isinstance(self.device.device, KOBOTOUCH)
                    and (
                        self.device.device.fwversion
                        < self.device.device.min_fwversion_epub_location
                    )  # type: ignore[reportOperatorIssue]
                ):
                    reading_location = (
                        reading_location[len(koboContentId) + 1 :]
                        if (result["ReadStatus"] == 1)
                        else None
                    )
        except StopIteration:
            debug_print(
                "_check_book_in_database - no match for contentId='%s'"
                % (koboContentId,)
            )
            reading_location = None
        debug_print(
            "KoboUtilities::_get_database_current_chapter - reading_location='%s'"
            % (reading_location,)
        )

        return reading_location

    def _get_readingposition_index(self, book, koboDatabaseReadingLocation):
        new_toc_readingposition_index = None
        reading_location_match = re.match(
            r"\((\d+)\)(.*)\#?.*", koboDatabaseReadingLocation
        )
        assert reading_location_match is not None
        reading_location_volumeIndex, reading_location_file = (
            reading_location_match.groups()
        )
        reading_location_volumeIndex = int(reading_location_volumeIndex)
        try:
            debug_print(
                "_get_readingposition_index - reading_location_volumeIndex =%d, reading_location_file='%s'"
                % (reading_location_volumeIndex, reading_location_file)
            )
            debug_print(
                "_get_readingposition_index - chapter location='%s'"
                % (
                    book["kobo_database_chapters"][reading_location_volumeIndex][
                        "path"
                    ],
                )
            )
            debug_print(
                "_get_readingposition_index - library file='%s'"
                % (book["library_chapters"][reading_location_volumeIndex]["path"],)
            )
        except Exception as e:
            debug_print(
                "_get_readingposition_index - exception getting reading location details. Exception:",
                e,
            )
            return None

        for i, library_chapter in enumerate(book["library_chapters"]):
            if library_chapter["path"] == reading_location_file:
                new_toc_readingposition_index = i
                debug_print(
                    "_get_readingposition_index - found file='%s', index=%s"
                    % (library_chapter["path"], i)
                )
                break

        return new_toc_readingposition_index

    def _compare_toc_entries(self, book, book_format1="library", book_format2="kobo"):
        debug_print(
            "_compare_toc_entries - book_format1='%s', book_format2: %s, count ToC entries: %d"
            % (book_format1, book_format2, len(book[book_format1 + "_chapters"]))
        )
        for i, chapter_format1 in enumerate(book[book_format1 + "_chapters"]):
            chapter_format1_path = chapter_format1["path"]
            chapter_format2_path = book[book_format2 + "_chapters"][i]["path"]

            if not (chapter_format1_path == chapter_format2_path):
                debug_print(
                    "_compare_toc_entries - path different for chapter index: %d" % i
                )
                debug_print(
                    "_compare_toc_entries - format1=%s, path='%s'"
                    % (book_format1, chapter_format1_path)
                )
                debug_print(
                    "_compare_toc_entries - format2=%s, path='%s'"
                    % (book_format2, chapter_format2_path)
                )
                return False
            if not (
                chapter_format1["title"] == book[book_format2 + "_chapters"][i]["title"]
            ):
                debug_print(
                    "_compare_toc_entries - title different for chapter index: %d" % i
                )
                debug_print(
                    "_compare_toc_entries - format1=%s, path='%s'"
                    % (book_format1, chapter_format1["title"])
                )
                debug_print(
                    "_compare_toc_entries - format2=%s, path='%s'"
                    % (book_format2, book[book_format1 + "_chapters"][i]["title"])
                )
                return False
        debug_print("_compare_toc_entries - chapter paths and titles the same.")
        return True

    def _compare_manifest_entries(
        self, book, book_format1="library", book_format2="kobo"
    ):
        debug_print(
            "_compare_manifest_entries - book_format1='%s', book_format2:'%s', count ToC entries: %d"
            % (book_format1, book_format2, len(book[book_format1 + "_manifest"]))
        )
        try:
            for i, manifest_item in enumerate(book[book_format1 + "_manifest"]):
                manifest_format1_path = manifest_item["path"]
                manifest_format2_path = book[book_format2 + "_manifest"][i]["path"]

                if not (manifest_format1_path == manifest_format2_path):
                    debug_print(
                        "_compare_manifest_entries - path different for manifest index: %d"
                        % i
                    )
                    debug_print(
                        "_compare_manifest_entries - format1=%s, path='%s'"
                        % (book_format1, manifest_format1_path)
                    )
                    debug_print(
                        "_compare_manifest_entries - format2=%s, path='%s'"
                        % (book_format2, manifest_format2_path)
                    )
                    return False
            debug_print("_compare_manifest_entries - manifest paths are same.")
            return True
        except Exception:
            return False

    def update_device_toc_for_books(self, books):
        self.gui.status_bar.show_message(
            _("Updating ToC in device database for {0} books.").format(len(books)), 3000
        )
        debug_print("update_device_toc_for_books - books=", books)
        self.progressbar(_("Updating ToC in device database"), on_top=False)
        self.set_progressbar_label(
            _("Number of books to update {0}").format(len(books))
        )
        self.show_progressbar(len(books))
        connection = self.device_database_connection()
        for book in books:
            debug_print("update_device_toc_for_books - book=", book)
            debug_print("update_device_toc_for_books - ContentID=", book["ContentID"])
            self.increment_progressbar()

            if len(book["kobo_chapters"]) > 0:
                self.remove_all_toc_entries(connection, book["ContentID"])

                self.update_device_toc_for_book(
                    connection,
                    book,
                    book["ContentID"],
                    book["title"],
                    book["kobo_format"],
                )

        self.hide_progressbar()

    def update_device_toc_for_book(
        self, connection, book, bookID, bookTitle, book_format="EPUB"
    ):
        debug_print(
            "update_device_toc_for_book - bookTitle=%s, len(book['library_chapters'])=%d"
            % (bookTitle, len(book["library_chapters"]))
        )
        num_chapters = len(book["kobo_chapters"])
        for i, chapter in enumerate(book["kobo_chapters"]):
            debug_print("update_device_toc_for_book - chapter=", (chapter))
            if book_format == "KEPUB":
                chapterContentId = "{0}!{1}!{2}".format(
                    book["ContentID"], book["kobo_opf_dir"], chapter["path"]
                )
            else:
                chapterContentId = (
                    book["ContentID"] + "#({0})".format(i) + chapter["path"]
                )
            debug_print(
                "update_device_toc_for_book - chapterContentId=", chapterContentId
            )
            databaseChapterId = self.getDatabaseChapterId(
                book["ContentID"], chapter["path"], connection
            )
            has_chapter = databaseChapterId is not None
            debug_print("update_device_toc_for_book - has_chapter=", has_chapter)
            if (
                has_chapter
                and chapter["path"].endswith("finish.xhtml")
                and not chapterContentId == databaseChapterId
            ):
                debug_print("update_device_toc_for_book - removing SOL finish chapter")
                self.removeChapterFromDatabase(databaseChapterId, bookID, connection)
                has_chapter = False
            if not has_chapter:
                self.addChapterToDatabase(
                    chapterContentId,
                    chapter,
                    bookID,
                    bookTitle,
                    i,
                    connection,
                    book_format,
                )
                chapter["added"] = True

        if book_format == "KEPUB":
            num_chapters = len(book["kobo_manifest"])
            file_offset = 0
            total_file_size = sum(
                [
                    manifest_entry["file_size"]
                    for manifest_entry in book["kobo_manifest"]
                ]
            )
            for i, manifest_entry in enumerate(book["kobo_manifest"]):
                file_size = manifest_entry["file_size"] * 100 / total_file_size
                manifest_entry_ContentId = "{0}!{1}!{2}".format(
                    book["ContentID"][len("file://") :],
                    book["kobo_opf_dir"],
                    manifest_entry["path"],
                )
                self.addManifestEntryToDatabase(
                    manifest_entry_ContentId,
                    bookID,
                    bookTitle,
                    manifest_entry["path"],
                    i,
                    connection,
                    book_format,
                    file_size=int(file_size),
                    file_offset=int(file_offset),
                )
                file_offset += file_size

        self.update_database_content_entry(connection, book["ContentID"], num_chapters)
        return 0

    def getDatabaseChapterId(self, bookId, toc_file, connection):
        cursor = connection.cursor()
        t = ("{0}%{1}%".format(bookId, toc_file),)
        cursor.execute("select ContentID from Content where ContentID like ?", t)
        try:
            result = next(cursor)
            chapterContentId = result[0]
        except StopIteration:
            chapterContentId = None

        debug_print("getDatabaseChapterId - chapterContentId=%s" % chapterContentId)
        return chapterContentId

    def removeChapterFromDatabase(self, chapterContentId, bookID, connection):
        cursor = connection.cursor()
        t = (chapterContentId,)
        cursor.execute("delete from Content where ContentID = ?", t)
        t = (
            bookID,
            chapterContentId,
        )
        cursor.execute(
            "delete from volume_shortcovers where volumeId = ? and shortcoverId = ?", t
        )

        return

    def update_database_content_entry(self, connection, contentId, num_chapters):
        cursor = connection.cursor()
        t = (contentId, num_chapters)
        cursor.execute("UPDATE content SET NumShortcovers = ? where ContentID = ?", t)

        return

    def remove_all_toc_entries(self, connection, contentId):
        debug_print("remove_all_toc_entries - contentId=", contentId)

        cursor = connection.cursor()
        t = (contentId,)

        cursor.execute("DELETE FROM Content WHERE BookID = ?", t)
        cursor.execute("DELETE FROM volume_shortcovers WHERE volumeId = ?", t)

        return

    def addChapterToDatabase(
        self,
        chapterContentId,
        chapter,
        bookID,
        bookTitle,
        volumeIndex,
        connection,
        book_format="EPUB",
    ):
        cursorContent = connection.cursor()
        insertContentQuery = (
            "INSERT INTO content "
            "(ContentID, ContentType, MimeType, BookID, BookTitle, Title, Attribution, adobe_location"
            ", IsEncrypted, FirstTimeReading, ParagraphBookmarked, BookmarkWordOffset, VolumeIndex, ___NumPages"
            ", ReadStatus, ___UserID, ___FileOffset, ___FileSize, ___PercentRead"
            ", Depth, ChapterIDBookmarked"
            ") VALUES ("
            "?, ?, ?, ?, ?, ?, null, ?"
            ", 'false', 'true', 0, 0, ?, -1"
            ", 0, ?, 0, 0, 0"
            ", ?, ?"
            ")"
        )

        if book_format == "KEPUB":
            mime_type = "application/x-kobo-epub+zip"
            content_type = 899
            content_userid = ""
            adobe_location = None
            matches = re.match(
                r"(?:file://)?((.*?)(?:\#.*)?(?:-\d+))$", chapterContentId
            )
            assert matches is not None
            debug_print("addChapterToDatabase - regex matches=", matches.groups())
            chapterContentId = chapterContentId[len("file://") :]
            chapterContentId = matches.group(1)
            fragment_start = chapterContentId.rfind("#")
            chapter_id_bookmarked = (
                chapterContentId
                if fragment_start < 0
                else chapterContentId[:fragment_start]
            )
            chapter_id_bookmarked = matches.group(2)
        else:
            mime_type = "application/epub+zip"
            content_type = 9
            content_userid = "adobe_user"
            chapter_id_bookmarked = None
            if "chapter_location" in chapter:
                adobe_location = chapter["chapter_location"]
            else:
                adobe_location = chapter["path"]

        insertContentData = (
            chapterContentId,
            content_type,
            mime_type,
            bookID,
            bookTitle,
            chapter["title"],
            adobe_location,
            volumeIndex,
            content_userid,
            chapter["toc_depth"],
            chapter_id_bookmarked,
        )

        debug_print("addChapterToDatabase - insertContentData=", insertContentData)
        cursorContent.execute(insertContentQuery, insertContentData)
        cursorContent.close()

        if book_format == "EPUB":
            cursorShortCover = connection.cursor()
            insertShortCoverQuery = "INSERT INTO volume_shortcovers (volumeId, shortcoverId, VolumeIndex) VALUES (?,?,?)"
            insertShortCoverData = (
                bookID,
                chapterContentId,
                volumeIndex,
            )
            debug_print(
                "addChapterToDatabase - insertShortCoverData=", insertShortCoverData
            )
            cursorShortCover.execute(insertShortCoverQuery, insertShortCoverData)

            cursorShortCover.close()

    def addManifestEntryToDatabase(
        self,
        manifest_entry,
        bookID,
        bookTitle,
        title,
        volumeIndex,
        connection,
        book_format="EPUB",
        file_size=None,
        file_offset=None,
    ):
        cursorContent = connection.cursor()
        insertContentQuery = (
            "INSERT INTO content "
            "(ContentID, ContentType, MimeType, BookID, BookTitle, Title, Attribution, adobe_location"
            ", IsEncrypted, FirstTimeReading, ParagraphBookmarked, BookmarkWordOffset, VolumeIndex, ___NumPages"
            ", ReadStatus, ___UserID, ___FileOffset, ___FileSize, ___PercentRead"
            ", Depth, ChapterIDBookmarked"
            ") VALUES ("
            "?, ?, ?, ?, ?, ?, null, ?"
            ", 'false', 'true', 0, 0, ?, -1"
            ", 0, ?, ?, ?, 0"
            ", ?, ?"
            ")"
        )

        mime_type = "application/xhtml+xml"
        content_type = 9
        content_userid = ""
        adobe_location = None

        insertContentData = (
            manifest_entry,
            content_type,
            mime_type,
            bookID,
            bookTitle,
            title,
            adobe_location,
            volumeIndex,
            content_userid,
            file_offset,
            file_size,
            0,
            None,
        )
        debug_print(
            "addManifestEntryToDatabase - insertContentData=", insertContentData
        )
        cursorContent.execute(insertContentQuery, insertContentData)

        cursorShortCover = connection.cursor()
        insertShortCoverQuery = "INSERT INTO volume_shortcovers (volumeId, shortcoverId, VolumeIndex) VALUES (?,?,?)"
        insertShortCoverData = (
            bookID,
            manifest_entry,
            volumeIndex,
        )
        debug_print(
            "addManifestEntryToDatabase - insertShortCoverData=", insertShortCoverData
        )
        cursorShortCover.execute(insertShortCoverQuery, insertShortCoverData)

        cursorContent.close()
        cursorShortCover.close()

    """
    End ToC Updating
    """

    def device_database_path(self) -> str:
        assert self.device is not None
        kobo_root = self.device.path
        path = self.device.device.normalize_path(kobo_root + ".kobo/KoboReader.sqlite")
        assert path is not None
        return path

    def show_help(self, anchor=None):
        debug_print("show_help - anchor=", anchor)

        # Extract on demand the help file resource
        def get_help_file_resource():
            # We will write the help file out every time, in case the user upgrades the plugin zip
            # and there is a later help file contained within it.
            from calibre.utils.localization import get_lang

            lang = get_lang()
            help_file = "KoboUtilities_Help_en.html"
            if lang == "fr":
                help_file = "KoboUtilities_Help_fr.html"
            file_path = os.path.join(config_dir, "plugins", help_file).replace(
                os.sep, "/"
            )
            file_data = self.load_resources("help/" + help_file)["help/" + help_file]
            debug_print("show_help - file_path:", file_path)
            with open(file_path, "wb") as f:
                f.write(file_data)
            return file_path

        debug_print("show_help - anchor=", anchor)
        url = "file:///" + get_help_file_resource()
        url = QUrl(url)
        if anchor is not None and not anchor == "":
            url.setFragment(anchor)
        open_url(url)

    def convert_kobo_date(self, kobo_date):
        return convert_kobo_date(kobo_date)

    def progressbar(self, window_title, on_top=False):
        self.pb = ProgressBar(parent=self.gui, window_title=window_title, on_top=on_top)
        self.pb.show()

    def show_progressbar(self, maximum_count):
        if self.pb:
            self.pb.set_maximum(maximum_count)
            self.pb.set_value(0)
            self.pb.show()

    def set_progressbar_label(self, label):
        if self.pb:
            self.pb.set_label(label)

    def increment_progressbar(self):
        if self.pb:
            self.pb.increment()

    def hide_progressbar(self):
        if self.pb:
            self.pb.hide()


@dataclasses.dataclass
class KoboVersionInfo:
    serial_no: str
    fw_version: str
    model_id: str


@dataclasses.dataclass
class KoboDevice:
    device: KOBO
    is_kobotouch: bool
    profile: Optional[Dict]
    backup_config: Dict
    device_info: List[str]
    uuid: str
    version_info: Optional[KoboVersionInfo]
    supports_series: bool
    supports_series_list: bool
    supports_ratings: bool
    epub_location_like_kepub: bool
    name: str
    path: str
