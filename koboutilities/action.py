# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import annotations

from pathlib import Path

__license__ = "GPL v3"
__copyright__ = "2012-2017, David Forrester <davidfor@internode.on.net>"
__docformat__ = "restructuredtext en"

import calendar
import dataclasses
import datetime as dt
import os
import pickle
import re
import shutil
import threading
import time
from collections import OrderedDict, defaultdict
from configparser import ConfigParser
from functools import partial
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Literal,
    Tuple,
    cast,
)

import apsw
from calibre import strftime
from calibre.constants import DEBUG
from calibre.constants import numeric_version as calibre_version
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
from calibre.gui2.device import DeviceJob, device_signals
from calibre.gui2.dialogs.message_box import ViewLog
from calibre.gui2.library.views import BooksView, DeviceBooksView
from calibre.utils.config import config_dir
from calibre.utils.icu import sort_key
from calibre.utils.logging import default_log
from qt.core import (
    QAction,
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
    DeviceDatabaseConnection,
    ProgressBar,
    check_device_database,
    convert_kobo_date,
    create_menu_action_unique,
    debug,
    get_icon,
    set_plugin_icon_resources,
)
from .dialogs import (
    AboutDialog,
    BackupAnnotationsOptionsDialog,
    BlockAnalyticsOptionsDialog,
    BookmarkOptionsDialog,
    ChangeReadingStatusOptionsDialog,
    CleanImagesDirOptionsDialog,
    CleanImagesDirProgressDialog,
    CoverUploadOptionsDialog,
    FixDuplicateShelvesDialog,
    GetShelvesFromDeviceDialog,
    ManageSeriesDeviceDialog,
    ReaderOptionsDialog,
    ReadLocationsProgressDialog,
    RemoveAnnotationsOptionsDialog,
    RemoveAnnotationsProgressDialog,
    RemoveCoverOptionsDialog,
    SetRelatedBooksDialog,
    ShowBooksNotInDeviceDatabaseDialog,
    ShowReadingPositionChangesDialog,
    UpdateBooksToCDialog,
    UpdateMetadataOptionsDialog,
)

if TYPE_CHECKING:
    from calibre.db.legacy import LibraryDatabase
    from calibre.ebooks.oeb.polish.toc import TOC
    from calibre.gui2.library.models import DeviceBooksModel

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
    "images/clock.png",
    "images/database.png",
    "images/databases.png",
    "images/vise.png",
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
    "FROM content c1 LEFT OUTER JOIN content c2 ON c1.ChapterIDBookmarked = c2.ContentID "
    "WHERE c1.ContentID = ?"
)

EPUB_FETCH_QUERY_NOTIMESPENT = (
    "SELECT c1.ChapterIDBookmarked, "
    "c2.adobe_location, "
    "c1.ReadStatus, "
    "c1.___PercentRead, "
    "c1.Attribution, "
    "c1.DateLastRead, "
    "c1.Title, "
    "c1.MimeType, "
    "r.rating, "
    "c1.contentId "
    "FROM content c1 LEFT OUTER JOIN content c2 ON c1.ChapterIDBookmarked = c2.ContentID "
    "LEFT OUTER JOIN ratings r ON c1.ContentID = r.ContentID "
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
    "FROM content c1 "
    "WHERE c1.ContentID = ?"
)

KEPUB_FETCH_QUERY_NOTIMESPENT = (
    "SELECT c1.ChapterIDBookmarked, "
    "c1.adobe_location, "
    "c1.ReadStatus, "
    "c1.___PercentRead, "
    "c1.Attribution, "
    "c1.DateLastRead, "
    "c1.Title, "
    "c1.MimeType, "
    "r.rating, "
    "c1.contentId "
    "FROM content c1 LEFT OUTER JOIN ratings r ON c1.ContentID = r.ContentID "
    "WHERE c1.ContentID = ?"
)

# Dictionary of Reading status fetch queries
# Key is earliest firmware version that supports this query.
FETCH_QUERIES: dict[tuple[int, int, int], cfg.FetchQueries] = {}
FETCH_QUERIES[(0, 0, 0)] = cfg.FetchQueries(
    KEPUB_FETCH_QUERY_NORATING, EPUB_FETCH_QUERY_NORATING
)
FETCH_QUERIES[(1, 9, 17)] = cfg.FetchQueries(
    KEPUB_FETCH_QUERY_NOTIMESPENT, EPUB_FETCH_QUERY_NOTIMESPENT
)
FETCH_QUERIES[(4, 0, 7523)] = cfg.FetchQueries(KEPUB_FETCH_QUERY, EPUB_FETCH_QUERY)
# With 4.17.13651, epub location is stored in the same way a for kepubs.
FETCH_QUERIES[(4, 17, 13651)] = cfg.FetchQueries(KEPUB_FETCH_QUERY, KEPUB_FETCH_QUERY)

KOBO_ROOT_DIR_NAME = ".kobo"
KOBO_EPOCH_CONF_NAME = "epoch.conf"

load_translations()


class KoboUtilitiesAction(InterfaceAction):
    interface_action_base_plugin: ActionKoboUtilities
    qaction: QAction

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

        self.device: KoboDevice | None = None

        debug(f"Running in {'normal' if __debug__ else 'optimized'} mode")

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

    def library_changed(self, db: LibraryDatabase):
        del db
        # We need to reset our menus after switching libraries
        self.device = self.get_device()

        self.rebuild_menus()
        if (
            self.device is not None
            and self.device.profile
            and self.device.profile.storeOptionsStore.storeOnConnect
        ):
            debug("About to do auto store")
            QTimer.singleShot(1000, self.auto_store_current_bookmark)

    def set_toolbar_button_tooltip(self):
        text = ActionKoboUtilities.description
        text += "\n"
        if self.device is not None:
            debug(
                "device connected. self.device.fwversion=",
                self.device.driver.fwversion,
            )
            text += "\n"
            text += _("Connected device: ")
            text += self.device.name
            text += "\n"
            text += _("Firmware version: ")
            text += ".".join([str(i) for i in self.device.driver.fwversion])
        text += "\n"
        text += _("Driver: ")
        text += self.device_driver_name

        debug("setting to text='%s'" % text)
        a = self.qaction
        a.setToolTip(text)

    def _on_device_connection_changed(self, is_connected: bool):
        debug(
            "self.plugin_device_connection_changed.__class__: ",
            self.plugin_device_connection_changed.__class__,
        )
        debug(
            "Methods for self.plugin_device_connection_changed: ",
            dir(self.plugin_device_connection_changed),
        )

        self.plugin_device_connection_changed.emit(is_connected)
        if not is_connected:
            debug("Device disconnected")
            self.device = None
            self.rebuild_menus()
        else:
            self.device = self.get_device()

        self.set_toolbar_button_tooltip()

    def _on_device_metadata_available(self):
        debug("Start")
        self.device = self.get_device()
        self.plugin_device_metadata_available.emit()
        self.set_toolbar_button_tooltip()

        if self.device is not None:
            profile = self.device.profile
            backup_config = self.device.backup_config
            debug("profile:", profile)
            debug("backup_config:", backup_config)
            if backup_config.doDailyBackp or backup_config.backupEachCOnnection:
                debug("About to start auto backup")
                self.auto_backup_device_database()

            if profile and profile.storeOptionsStore.storeOnConnect:
                debug("About to start auto store")
                self.auto_store_current_bookmark()

        self.rebuild_menus()

    def rebuild_menus(self) -> None:
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

            device = self.device
            self.menu.setToolTipsVisible(True)
            self.set_toolbar_button_tooltip()

            self.create_menu_item_ex(
                self.menu,
                _("&Set reader font for selected books"),
                unique_name="Set reader font for selected books",
                shortcut_name=_("Set reader font for selected books"),
                image="embed-fonts.png",
                triggered=self.set_reader_fonts,
                is_library_action=True,
                is_device_action=True,
                is_supported=device is not None and device.is_kobotouch,
            )

            self.create_menu_item_ex(
                self.menu,
                _("&Remove reader font for selected books"),
                unique_name="Remove reader font for selected books",
                shortcut_name=_("Remove reader font for selected books"),
                triggered=self.remove_reader_fonts,
                is_library_action=True,
                is_device_action=True,
                is_supported=device is not None and device.is_kobotouch,
            )

            self.menu.addSeparator()

            self.create_menu_item_ex(
                self.menu,
                _("Update &metadata in device library"),
                unique_name="Update metadata in device library",
                shortcut_name=_("Update metadata in device library"),
                image="metadata.png",
                triggered=self.update_metadata,
                is_library_action=True,
            )

            self.create_menu_item_ex(
                self.menu,
                _("&Change reading status in device library"),
                unique_name="Change reading status in device library",
                shortcut_name=_("Change reading status in device library"),
                triggered=self.change_reading_status,
                is_device_action=True,
            )

            self.create_menu_item_ex(
                self.menu,
                _("&Manage series information in device library"),
                unique_name="Manage series information in device library",
                shortcut_name=_("Manage series information in device library"),
                triggered=self.manage_series_on_device,
                is_device_action=True,
                is_supported=device is not None and device.supports_series,
            )

            self.create_menu_item_ex(
                self.menu,
                _("&Store/restore reading positions"),
                unique_name="Store/restore reading positions",
                shortcut_name=_("Store/restore reading positions"),
                image="bookmarks.png",
                triggered=self.handle_bookmarks,
                is_library_action=True,
            )

            self.menu.addSeparator()
            self.create_menu_item_ex(
                self.menu,
                _("&Update ToC for selected books"),
                image="toc.png",
                unique_name="Update ToC for selected books",
                shortcut_name=_("Update ToC for selected books"),
                triggered=self.update_book_toc_on_device,
                is_library_action=True,
            )

            self.menu.addSeparator()
            self.create_menu_item_ex(
                self.menu,
                _("&Upload covers for selected books"),
                unique_name="Upload covers for selected books",
                shortcut_name=_("Upload covers for selected books"),
                image="default_cover.png",
                triggered=self.upload_covers,
                is_library_action=True,
            )
            self.create_menu_item_ex(
                self.menu,
                _("&Remove covers for selected books"),
                unique_name="Remove covers for selected books",
                shortcut_name=_("Remove covers for selected books"),
                triggered=self.remove_covers,
                is_library_action=True,
                is_device_action=True,
                is_supported=device is not None and device.is_kobotouch,
            )

            self.create_menu_item_ex(
                self.menu,
                _("&Clean images directory of extra cover images"),
                unique_name="Clean images directory of extra cover images",
                shortcut_name=_("Clean images directory of extra cover images"),
                triggered=self.clean_images_dir,
                is_library_action=True,
                is_device_action=True,
            )
            self.create_menu_item_ex(
                self.menu,
                _("&Open cover image directory"),
                unique_name="Open cover image directory",
                shortcut_name=_("Open cover image directory"),
                triggered=self.open_cover_image_directory,
                is_library_action=True,
                is_device_action=True,
                is_supported=device is not None and device.is_kobotouch,
            )
            self.menu.addSeparator()

            self.create_menu_item_ex(
                self.menu,
                _("Get collections from device"),
                unique_name="Get collections from device",
                shortcut_name=_("Get collections from device"),
                image="catalog.png",
                triggered=self.get_shelves_from_device,
                is_library_action=True,
                is_supported=device is not None and device.is_kobotouch,
            )
            if device is not None and device.driver.fwversion < (4, 4, 0):
                self.create_menu_item_ex(
                    self.menu,
                    _("Set related books"),
                    unique_name="Set related books",
                    shortcut_name=_("Set related books"),
                    triggered=self.set_related_books,
                    is_library_action=True,
                    is_device_action=True,
                    is_supported=device.supports_series,
                )
            self.menu.addSeparator()
            self.create_menu_item_ex(
                self.menu,
                _("Copy annotation for selected book"),
                image="edit_input.png",
                unique_name="Copy annotation for selected book",
                shortcut_name=_("Copy annotation for selected book"),
                triggered=self.getAnnotationForSelected,
                is_library_action=True,
            )
            self.create_menu_item_ex(
                self.menu,
                _("Back up annotation file"),
                unique_name="Back up annotation file",
                shortcut_name=_("Back up annotation file"),
                triggered=self.backup_annotation_files,
                is_library_action=True,
            )
            self.create_menu_item_ex(
                self.menu,
                _("Remove annotation files"),
                unique_name="Remove annotation files",
                shortcut_name=_("Remove annotation files"),
                triggered=self.remove_annotations_files,
                is_library_action=True,
                is_device_action=True,
            )

            self.menu.addSeparator()

            self.create_menu_item_ex(
                self.menu,
                _("Show books not in the device database"),
                unique_name="Show books not in the device database",
                shortcut_name=_("Show books not in the device database"),
                triggered=self.show_books_not_in_database,
                is_device_action=True,
            )

            self.create_menu_item_ex(
                self.menu,
                _("Refresh the list of books on the device"),
                unique_name="Refresh the list of books on the device",
                shortcut_name=_("Refresh the list of books on the device"),
                image="view-refresh.png",
                triggered=self.refresh_device_books,
                is_library_action=True,
                is_device_action=True,
            )
            databaseMenu = cast("QMenu", self.menu.addMenu(_("Database")))
            databaseMenu.setIcon(get_icon("images/database.png"))
            self.create_menu_item_ex(
                databaseMenu,
                _("Block analytics events"),
                unique_name="Block analytics events",
                shortcut_name=_("Block analytics events"),
                triggered=self.block_analytics,
                is_library_action=True,
                is_device_action=True,
                is_supported=device is not None and device.is_kobotouch,
            )
            databaseMenu.addSeparator()
            self.create_menu_item_ex(
                databaseMenu,
                _("Fix duplicate collections"),
                unique_name="Fix duplicate collections",
                shortcut_name=_("Fix duplicate collections"),
                triggered=self.fix_duplicate_shelves,
                is_library_action=True,
                is_device_action=True,
                is_supported=device is not None and device.is_kobotouch,
            )
            self.create_menu_item_ex(
                databaseMenu,
                _("Check the device database"),
                unique_name="Check the device database",
                shortcut_name=_("Check the device database"),
                image="ok.png",
                triggered=self.check_device_database,
                is_library_action=True,
                is_device_action=True,
                is_supported=device is not None and not device.is_db_copied,
                not_supported_reason=_("Not supported for this connection mode"),
            )
            self.create_menu_item_ex(
                databaseMenu,
                _("Compress the device database"),
                unique_name="Compress the device database",
                shortcut_name=_("Compress the device database"),
                image="images/vise.png",
                triggered=self.vacuum_device_database,
                is_library_action=True,
                is_device_action=True,
                is_supported=device is not None and not device.is_db_copied,
                not_supported_reason=_("Not supported for this connection mode"),
            )
            self.create_menu_item_ex(
                databaseMenu,
                _("Back up device database"),
                unique_name="Back up device database",
                shortcut_name=_("Back up device database"),
                image="images/databases.png",
                triggered=self.backup_device_database,
                is_library_action=True,
                is_device_action=True,
            )

            self.menu.addSeparator()
            self.create_menu_item_ex(
                self.menu,
                _("Set time on device"),
                unique_name="Set time on device",
                shortcut_name=_("Set time on device"),
                image="images/clock.png",
                tooltip=_(
                    "Creates a file on the device which will be used to set the time when the device is disconnected."
                ),
                triggered=self.set_time_on_device,
                is_library_action=True,
                is_device_action=True,
            )

            self.menu.addSeparator()

            def create_configure_driver_item(menu: QMenu, menu_text: str):
                self.create_menu_item_ex(
                    menu,
                    menu_text,
                    unique_name="Configure driver",
                    shortcut_name=_("Configure driver"),
                    image="config.png",
                    triggered=self.configure_device,
                    is_library_action=True,
                    is_device_action=True,
                    is_no_device_action=True,
                )

            # Calibre 8 integrates the functionality of the KoboTouchExtended driver
            # and disables the plugin, so there is no need to switch between drivers
            if calibre_version >= (8, 0, 0):  # pyright: ignore[reportOperatorIssue]
                create_configure_driver_item(self.menu, _("&Configure driver..."))
            else:
                driver_menu = self.menu.addMenu(_("Driver"))
                assert driver_menu is not None
                create_configure_driver_item(
                    driver_menu,
                    _("&Configure current driver") + " - " + self.device_driver_name,
                )
                self.create_menu_item_ex(
                    driver_menu,
                    _("Switch between main and extended driver"),
                    unique_name="Switch between main and extended driver",
                    shortcut_name=_("Switch between main and extended driver"),
                    image="config.png",
                    triggered=self.switch_device_driver,
                    is_library_action=True,
                    is_device_action=True,
                    is_no_device_action=True,
                )
            self.menu.addSeparator()

            self.create_menu_item_ex(
                self.menu,
                _("&Customize plugin") + "...",  # shortcut=False,
                unique_name="Customize plugin",
                shortcut_name=_("Customize plugin"),
                image="config.png",
                triggered=self.show_configuration,
                is_library_action=True,
                is_device_action=True,
                is_no_device_action=True,
            )

            self.create_menu_item_ex(
                self.menu,
                _("&Help"),  # shortcut=False,
                unique_name="Help",
                shortcut_name=_("Help"),
                image="help.png",
                triggered=lambda _: self.show_help(),
                is_library_action=True,
                is_device_action=True,
                is_no_device_action=True,
            )

            self.create_menu_item_ex(
                self.menu,
                _("&About plugin"),  # shortcut=False,
                image="images/icon.png",
                unique_name="About KoboUtilities",
                shortcut_name=_("About KoboUtilities"),
                triggered=self.about,
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
        debug("self.version=", self.version)
        debug("about_text=", about_text)
        AboutDialog(self.gui, self.qaction.icon(), about_text).exec()

    def create_menu_item_ex(
        self,
        parent_menu: QMenu,
        menu_text: str,
        triggered: Callable[[], None] | Callable[[QAction], None],
        image: str | None = None,
        shortcut: str | list[str] | None | Literal[False] = None,
        is_checked: bool | None = None,
        shortcut_name: str | None = None,
        unique_name: str | None = None,
        tooltip: str | None = None,
        is_library_action: bool = False,
        is_device_action: bool = False,
        is_no_device_action: bool = False,
        is_supported: bool = True,
        not_supported_reason: str = _("Not supported for this device"),
    ) -> QAction:
        if self.device is None and not is_no_device_action:
            tooltip = _("No device connected")
            enabled = False
        elif self.device is not None and not is_supported:
            tooltip = not_supported_reason
            enabled = False
        elif self.isDeviceView() and not is_device_action:
            tooltip = _("Only supported in library view")
            enabled = False
        elif not self.isDeviceView() and not is_library_action:
            tooltip = _("Only supported in device view")
            enabled = False
        else:
            tooltip = tooltip
            enabled = True

        ac = create_menu_action_unique(
            self,
            parent_menu,
            menu_text,
            triggered,
            image,
            tooltip,
            shortcut,
            is_checked,
            shortcut_name,
            unique_name,
        )
        ac.setEnabled(enabled)
        self.menu_actions[shortcut_name] = ac

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
                button_action = cfg.plugin_prefs.commonOptionsStore.buttonActionDevice
                if button_action == "":
                    self.show_configuration()
                else:
                    self.menu_actions[button_action].trigger()
            else:
                self.change_reading_status()
        else:
            button_action = cfg.plugin_prefs.commonOptionsStore.buttonActionLibrary
            if button_action == "":
                debug("no button action")
                self.show_configuration()
            else:
                try:
                    debug("self.no_device_actions_map=", self.no_device_actions_map)
                    if self.device or button_action in self.no_device_actions_map:
                        self.menu_actions[button_action].trigger()
                    else:
                        self.show_configuration()
                except Exception as e:
                    debug(
                        "exception running button action:",
                        button_action,
                        " exception: ",
                        e,
                    )
                    self.show_configuration()

    def isDeviceView(self):
        view = self.gui.current_view()
        return isinstance(view, DeviceBooksView)

    def _get_contentIDs_for_selected(self) -> list[str]:
        view = self.gui.current_view()
        if view is None:
            return []
        if self.isDeviceView():
            rows = view.selectionModel().selectedRows()
            books = [view.model().db[view.model().map[r.row()]] for r in rows]
            contentIDs = [book.contentID for book in books]
        else:
            book_ids: list[int] = view.get_selected_ids()
            contentIDs = self.get_contentIDs_for_books(book_ids)
            debug("contentIDs=", contentIDs)

        return contentIDs

    @property
    def device_driver_name(self) -> str:
        if self.device:
            device_driver_name = self.device.driver.name
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
                debug("could not load extended driver. Exception=", e)
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
                debug("could not load extended driver. Exception=", e)
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
            debug("could not load extended driver. Exception=", e)
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
        debug(
            "using is_disabled: main_disabled=%s, extended_disabled=%s"
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
        debug("before do_user_config")
        restart_message = _(
            "Calibre must be restarted before the plugin can be configured."
        )
        # Check if a restart is needed. If the restart is needed, but the user does not
        # trigger it, the result is true and we do not do the configuration.
        if self.check_if_restart_needed(restart_message=restart_message):
            return

        self.interface_action_base_plugin.do_user_config(self.gui)
        debug("after do_user_config")
        restart_message = _(
            "New custom columns have been created."
            "\nYou will need to restart calibre for this change to be applied."
        )
        self.check_if_restart_needed(restart_message=restart_message)

    def check_if_restart_needed(
        self, restart_message: str | None = None, restart_needed: bool = False
    ):
        if self.gui.must_restart_before_config or restart_needed:
            if restart_message is None:
                restart_message = _(
                    "Calibre must be restarted before the plugin can be configured."
                )
            from calibre.gui2 import show_restart_warning

            do_restart = show_restart_warning(restart_message)
            if do_restart:
                debug("restarting calibre...")
                self.gui.quit(restart=True)
            else:
                debug("calibre needs to be restarted, do not open configuration")
                return True
        return False

    def set_reader_fonts(self) -> None:
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot set reader font settings."),
                _("No device connected."),
                show=True,
            )
            return

        contentIDs = self._get_contentIDs_for_selected()

        debug("contentIDs", contentIDs)

        if len(contentIDs) == 0:
            return

        dlg = ReaderOptionsDialog(
            self.gui, self, contentIDs[0] if len(contentIDs) == 1 else None
        )
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            return

        options = cfg.plugin_prefs.ReadingOptions
        if options.updateConfigFile:
            self._update_config_reader_settings(options)

        updated_fonts, added_fonts, _deleted_fonts, count_books = (
            self._set_reader_fonts(contentIDs, options)
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

    def remove_reader_fonts(self) -> None:
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot remove reader font settings"),
                _("No device connected."),
                show=True,
            )
            return

        contentIDs = self._get_contentIDs_for_selected()

        if len(contentIDs) == 0:
            return

        mb = question_dialog(
            self.gui,
            _("Remove reader settings"),
            _("Do you want to remove the reader settings for the selected books?"),
            show_copy_button=False,
        )
        if not mb:
            return

        options = cfg.plugin_prefs.ReadingOptions
        _updated_fonts, _added_fonts, deleted_fonts, _count_books = (
            self._set_reader_fonts(contentIDs, options, delete=True)
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

    def update_metadata(self) -> None:
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot update metadata in device library."),
                _("No device connected."),
                show=True,
            )
            return

        selectedIDs = self._get_selected_ids()
        if len(selectedIDs) == 0:
            return

        progressbar = ProgressBar(parent=self.gui, window_title=_("Getting book list"))
        progressbar.set_label(
            _("Number of selected books: {0}").format(len(selectedIDs))
        )
        progressbar.show_with_maximum(len(selectedIDs))
        debug("selectedIDs:", selectedIDs)
        books = self._convert_calibre_ids_to_books(current_view.model().db, selectedIDs)
        for book in books:
            progressbar.increment()
            device_book_paths = self.get_device_paths_from_id(
                cast("int", book.calibre_id)
            )
            debug("device_book_paths:", device_book_paths)
            book.paths = device_book_paths
            book.contentIDs = [
                self.contentid_from_path(path, self.CONTENTTYPE)
                for path in device_book_paths
            ]
        progressbar.hide()

        dlg = UpdateMetadataOptionsDialog(self.gui, self, books[0])
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            return

        progressbar = ProgressBar(
            parent=self.gui, window_title=_("Updating metadata on device")
        )
        progressbar.show()
        progressbar.set_label(
            _("Number of books to update metadata for: {0}").format(len(books))
        )
        options = cfg.plugin_prefs.MetadataOptions
        updated_books, unchanged_books, not_on_device_books, count_books = (
            self._update_metadata(books, progressbar, options)
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

    def handle_bookmarks(self) -> None:
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot store or restore current reading position."),
                _("No device connected."),
                show=True,
            )
            return

        selectedIDs = self._get_selected_ids()

        if len(selectedIDs) == 0:
            return

        dlg = BookmarkOptionsDialog(self.gui, self)
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            return
        profile_name = dlg.profile_name
        # We know that this cannot be none if the dialog succeeded
        assert profile_name is not None

        if cfg.plugin_prefs.BookmarkOptions.storeBookmarks:
            self.store_current_bookmark(profile_name)
        else:
            self.restore_current_bookmark(profile_name)

    def auto_store_current_bookmark(self):
        debug("start")
        self.device = self.get_device()
        assert self.device is not None

        library_db = self.gui.current_db

        fetch_queries = self._get_fetch_query_for_firmware_version(
            cast("Tuple[int, int, int]", self.device_fwversion)
        )
        assert fetch_queries is not None
        profile = self.device.profile
        custom_columns = self.get_column_names()

        bookmark_options = cfg.BookmarkOptionsConfig()
        bookmark_options.backgroundJob = True
        bookmark_options.clearIfUnread = False
        bookmark_options.storeBookmarks = True

        profile_name = None
        prompt_to_store = False
        if profile is not None:
            profile_name = profile.profileName
            prompt_to_store = profile.storeOptionsStore.promptToStore
            bookmark_options.storeIfMoreRecent = (
                profile.storeOptionsStore.storeIfMoreRecent
            )
            bookmark_options.doNotStoreIfReopened = (
                profile.storeOptionsStore.doNotStoreIfReopened
            )
        options = cfg.ReadLocationsJobOptions(
            bookmark_options,
            self.device.epub_location_like_kepub,
            fetch_queries,
            self.device.db_path,
            self.device.device_db_path,
            self.device.is_db_copied,
            profile_name,
            custom_columns,
            self.device.supports_ratings,
            allOnDevice=True,
            prompt_to_store=prompt_to_store,
        )

        kobo_chapteridbookmarked_column = custom_columns.current_location
        kobo_percentRead_column = custom_columns.percent_read
        rating_column = custom_columns.rating
        last_read_column = custom_columns.last_read
        time_spent_reading_column = custom_columns.time_spent_reading
        rest_of_book_estimate_column = custom_columns.rest_of_book_estimate

        if options.bookmark_options.doNotStoreIfReopened:
            search_condition = f"and ({kobo_percentRead_column}:false or {kobo_percentRead_column}:<100)"
        else:
            search_condition = ""

        progressbar = ProgressBar(
            parent=self.gui,
            window_title=_("Queuing books for storing reading position"),
        )
        progressbar.set_label(_("Getting list of books"))
        progressbar.show_with_maximum(0)

        search_condition = f"ondevice:True {search_condition}"
        debug("search_condition=", search_condition)
        onDeviceIds = set(
            library_db.search_getting_ids(
                search_condition, None, sort_results=False, use_virtual_library=False
            )
        )
        debug("onDeviceIds:", len(onDeviceIds))
        onDevice_book_paths = self.get_books_from_ids(onDeviceIds)
        debug("onDevice_book_paths:", len(onDevice_book_paths))

        books = self._convert_calibre_ids_to_books(library_db, onDeviceIds)
        progressbar.show_with_maximum(len(books))
        progressbar.set_label(_("Queuing books"))
        books_to_scan = []

        for book in books:
            progressbar.increment()
            device_book_paths = [
                x.path for x in onDevice_book_paths[cast("int", book.calibre_id)]
            ]
            book.contentIDs = [
                self.contentid_from_path(path, self.CONTENTTYPE)
                for path in device_book_paths
            ]
            if len(book.contentIDs) > 0:
                title = book.title
                progressbar.set_label(_("Queueing {}").format(title))
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
            self._store_queue_job(options, books_to_scan)

        progressbar.hide()

        debug("Finish")

    def set_time_on_device(self):
        debug("start")
        now = calendar.timegm(time.gmtime())
        debug("time=%s" % now)
        assert self.device is not None
        epoch_conf_path = os.path.join(
            self.device.path, KOBO_ROOT_DIR_NAME, KOBO_EPOCH_CONF_NAME
        )
        with open(epoch_conf_path, "w") as epoch_conf:
            epoch_conf.write("%s" % now)
        self.gui.status_bar.show_message(
            _("Kobo Utilities") + " - " + _("Time file created on device."), 3000
        )
        debug("end")

    def device_serial_no(self) -> str:
        version_info = self.device.version_info if self.device is not None else None
        return version_info.serial_no if version_info else "Unknown"

    def auto_backup_device_database(self):
        debug("start")
        if not self.device or not self.device.backup_config:
            debug("no backup configuration")
            return
        backup_config = self.device.backup_config

        dest_dir = backup_config.backupDestDirectory
        debug("destination directory=", dest_dir)
        if not dest_dir or len(dest_dir) == 0:
            debug("destination directory not set, not doing backup")
            return

        # Backup file names will be KoboReader-devicename-serialnumber-timestamp.sqlite
        backup_file_template = "KoboReader-{0}-{1}-{2}"
        debug("about to get version info from device...")
        version_info = self.device.version_info
        debug("version_info=", version_info)
        serial_number = self.device_serial_no()
        device_name = "".join(self.device.driver.gui_name.split())
        debug("device_information=", self.device.driver.get_device_information())
        debug("device_name=", device_name)
        debug(
            "backup_file_template=",
            backup_file_template.format(device_name, serial_number, ""),
        )

        job_options = cfg.DatabaseBackupJobOptions(
            backup_config,
            device_name,
            serial_number,
            backup_file_template,
            self.device.db_path,
            str(self.device.driver._main_prefix),
        )
        debug("backup_options=", job_options)

        self._device_database_backup(job_options)
        debug("end")

    def store_current_bookmark(self, profile_name: str) -> None:
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot update metadata in device library."),
                _("No device connected."),
                show=True,
            )
            return

        fetch_queries = self._get_fetch_query_for_firmware_version(
            cast("Tuple[int, int, int]", self.device_fwversion)
        )
        if fetch_queries is None:
            error_dialog(
                self.gui,
                _("Cannot update metadata in device library."),
                _("No fetch queries found for firmware version."),
                show=True,
            )
            return

        options = cfg.ReadLocationsJobOptions(
            cfg.plugin_prefs.BookmarkOptions,
            self.device.epub_location_like_kepub,
            fetch_queries,
            self.device.db_path,
            self.device.device_db_path,
            self.device.is_db_copied,
            profile_name,
            None,
            self.device.supports_ratings,
            allOnDevice=False,
            prompt_to_store=True,
        )
        debug("options:", options)

        if cfg.plugin_prefs.BookmarkOptions.backgroundJob:
            ReadLocationsProgressDialog(
                self.gui,
                options,
                self._store_queue_job,
                current_view.model().db,
                plugin_action=self,
            )
        else:
            selectedIDs = self._get_selected_ids()

            if len(selectedIDs) == 0:
                return
            debug("selectedIDs:", selectedIDs)
            books = self._convert_calibre_ids_to_books(
                current_view.model().db, selectedIDs
            )
            for book in books:
                device_book_paths = self.get_device_paths_from_id(
                    cast("int", book.calibre_id)
                )
                book.paths = device_book_paths
                book.contentIDs = [
                    self.contentid_from_path(path, self.CONTENTTYPE)
                    for path in device_book_paths
                ]

            reading_locations_updated, books_without_reading_locations, count_books = (
                self._store_current_bookmark(books, options)
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

    def restore_current_bookmark(self, profile_name: str) -> None:
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot set bookmark in device library."),
                _("No device connected."),
                show=True,
            )
            return

        selectedIDs = self._get_selected_ids()

        if len(selectedIDs) == 0:
            return
        debug("selectedIDs:", selectedIDs)
        books = self._convert_calibre_ids_to_books(current_view.model().db, selectedIDs)
        for book in books:
            device_book_paths = self.get_device_paths_from_id(
                cast("int", book.calibre_id)
            )
            debug("device_book_paths:", device_book_paths)
            book.paths = device_book_paths
            book.contentIDs = [
                self.contentid_from_path(path, self.CONTENTTYPE)
                for path in device_book_paths
            ]

        updated_books, not_on_device_books, count_books = (
            self._restore_current_bookmark(
                books, cfg.plugin_prefs.BookmarkOptions, profile_name
            )
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
        self, current_firmware_version: tuple[int, int, int]
    ) -> cfg.FetchQueries | None:
        fetch_queries = None
        for fw_version in sorted(FETCH_QUERIES.keys()):
            if current_firmware_version < fw_version:
                break
            fetch_queries = FETCH_QUERIES[fw_version]

        debug("using fetch_queries:", fetch_queries)
        return fetch_queries

    def backup_device_database(self) -> None:
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot back up the device database."),
                _("No device connected."),
                show=True,
            )
            return

        fd = FileDialog(
            parent=self.gui,
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
        source_file = self.device.db_path
        shutil.copyfile(source_file, backup_file)

    def backup_annotation_files(self) -> None:
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return

        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot back up annotation files from device."),
                _("No device connected."),
                show=True,
            )
            return

        selectedIDs = self._get_selected_ids()

        if len(selectedIDs) == 0:
            return

        dlg = BackupAnnotationsOptionsDialog(self.gui, self)
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            return

        dest_path = dlg.dest_path()
        debug("selectedIDs:", selectedIDs)
        books = self._convert_calibre_ids_to_books(current_view.model().db, selectedIDs)
        for book in books:
            device_book_paths = self.get_device_paths_from_id(
                cast("int", book.calibre_id)
            )
            debug("device_book_paths:", device_book_paths)
            book.paths = device_book_paths
            book.contentIDs = [
                self.contentid_from_path(path, self.CONTENTTYPE)
                for path in device_book_paths
            ]

        debug("dest_path=", dest_path)
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

    def remove_annotations_files(self) -> None:
        self.device = self.get_device()
        current_view = self.gui.current_view()
        if current_view is None:
            return

        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot remove files from device."),
                _("No device connected."),
                show=True,
            )
            return

        dlg = RemoveAnnotationsOptionsDialog(self.gui, self)
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            return

        debug("self.device.path='%s'" % (self.device.path))

        options = cfg.RemoveAnnotationsJobOptions(
            str(
                self.device.driver.normalize_path(
                    self.device.path + "Digital Editions/Annotations/"
                )
            ),
            ".annot",
            self.device.path,
            cfg.plugin_prefs.removeAnnotations.removeAnnotAction,
        )

        debug("options=", options)
        RemoveAnnotationsProgressDialog(
            self.gui,
            options,
            self._remove_annotations_job,
            current_view.model().db,
            plugin_action=self,
        )

        return

    def refresh_device_books(self):
        self.gui.device_detected(True, KOBOTOUCH)

    def change_reading_status(self) -> None:
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot change reading status in device library."),
                _("No device connected."),
                show=True,
            )
            return

        books = self._get_books_for_selected()

        if len(books) == 0:
            return
        for book in books:
            debug("book:", book)
            book.contentIDs = [book.contentID]
        debug("books:", books)

        dlg = ChangeReadingStatusOptionsDialog(self.gui, self)
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            return
        options = dlg.options
        options.usePlugboard = False
        options.titleSort = False
        options.authourSort = False
        options.subtitle = False
        debug("options:", options)

        progressbar = ProgressBar(
            parent=self.gui, window_title=_("Changing reading status on device")
        )
        progressbar.show()

        updated_books, unchanged_books, not_on_device_books, count_books = (
            self._update_metadata(books, progressbar, options)
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

    def show_books_not_in_database(self) -> None:
        current_view = self.gui.current_view()
        if current_view is None:
            return

        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot list books not in device library."),
                _("No device connected."),
                show=True,
            )
            return

        books = self._get_books_for_selected()

        if len(books) == 0:
            books = current_view.model().db

        books_not_in_database = self._check_book_in_database(books)

        dlg = ShowBooksNotInDeviceDatabaseDialog(self.gui, books_not_in_database)
        dlg.show()

    def fix_duplicate_shelves(self) -> None:
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot fix the duplicate collections in the device library."),
                _("No device connected."),
                show=True,
            )
            return

        shelves = self._get_shelf_count()
        dlg = FixDuplicateShelvesDialog(self.gui, self, shelves)
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            debug("dialog cancelled")
            return

        options = cfg.plugin_prefs.fixDuplicatesOptionsStore
        debug(f"about to fix shelves - options={options}")

        starting_shelves, shelves_removed, finished_shelves = (
            self._remove_duplicate_shelves(shelves, options)
        )
        result_message = (
            _("Update summary:")
            + "\n\t"
            + _(
                "Starting number of collections={0}\n\tCollections removed={1}\n\tTotal collections={2}"
            ).format(starting_shelves, shelves_removed, finished_shelves)
        )
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Duplicate collections fixed"),
            result_message,
            show=True,
        )

    def set_related_books(self) -> None:
        debug("start")
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot set the related books."),
                _("No device connected."),
                show=True,
            )
            return

        shelves = []
        dlg = SetRelatedBooksDialog(self.gui, self, shelves)
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            debug("dialog cancelled")
            return
        options = cfg.plugin_prefs.setRelatedBooksOptionsStore
        debug("options=%s" % options)
        if dlg.deleteAllRelatedBooks:
            self._delete_related_books()
            result_message = _("Deleted all related books for sideloaded books.")
        else:
            related_types = dlg.get_related_types()
            debug("related_types=", related_types)

            categories_count, books_count = self._set_related_books(
                related_types, options
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
            _("Kobo Utilities") + " - " + _("Set related books"),
            result_message,
            show=True,
        )

    def get_shelves_from_device(self) -> None:
        current_view = self.gui.current_view()
        if current_view is None:
            return

        debug("start")
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot get the collections from device."),
                _("No device connected."),
                show=True,
            )
            return

        dlg = GetShelvesFromDeviceDialog(self.gui, self)
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            debug("dialog cancelled")
            return

        shelves_column = cfg.get_library_config(self.gui.current_db).shelvesColumn

        # Check if driver is configured to manage shelves. If so, warn if selected column is one of
        # the configured columns.
        driver_shelves = self.device.driver.get_collections_attributes()
        debug("driver_shelves=", driver_shelves)
        debug("selected column=", shelves_column)
        if shelves_column in driver_shelves:
            debug(
                "selected column is one of the columns used in the driver configuration!"
            )
            details_msg = _(
                "The selected column is {0}."
                "\n"
                "The driver collection management columns are: {1}"
            ).format(shelves_column, ", ".join(driver_shelves))
            mb = question_dialog(
                self.gui,
                _("Getting collections from device"),
                _(
                    "The column selected is one of the columns used in the driver configuration for collection management. "
                    "Updating this column might affect the collection management the next time you connect the device. "
                    "\n\nAre you sure you want to do this?"
                ),
                override_icon=QIcon(I("dialog_warning.png")),
                show_copy_button=False,
                det_msg=details_msg,
            )
            if not mb:
                debug("User cancelled because of column used.")
                return

        progressbar = ProgressBar(
            parent=self.gui, window_title=_("Getting collections from device")
        )
        progressbar.show()
        progressbar.set_label(_("Getting list of collections"))

        library_db = current_view.model().db
        options = cfg.plugin_prefs.getShelvesOptionStore
        if options.allBooks:
            selectedIDs = set(
                library_db.search_getting_ids(
                    "ondevice:True", None, sort_results=False, use_virtual_library=False
                )
            )
        else:
            selectedIDs = self._get_selected_ids()

        if len(selectedIDs) == 0:
            return
        debug("selectedIDs:", selectedIDs)
        books = self._convert_calibre_ids_to_books(library_db, selectedIDs)
        progressbar.set_label(
            _("Number of books to get collections for: {0}").format(len(books))
        )
        for book in books:
            device_book_paths = self.get_device_paths_from_id(
                cast("int", book.calibre_id)
            )
            debug("device_book_paths:", device_book_paths)
            book.paths = device_book_paths
            book.contentIDs = [
                self.contentid_from_path(path, self.CONTENTTYPE)
                for path in device_book_paths
            ]

        debug("about get shelves - options=%s" % options)

        books_with_shelves, books_without_shelves, count_books = (
            self._get_shelves_from_device(books, options, progressbar)
        )
        result_message = (
            _("Update summary:")
            + "\n\t"
            + _(
                "Books processed={0}\n\tBooks with collections={1}\n\tBooks without collections={2}"
            ).format(count_books, books_with_shelves, books_without_shelves)
        )
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Get collections from device"),
            result_message,
            show=True,
        )

    def check_device_database(self) -> None:
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot check Kobo device database."),
                _("No device connected."),
                show=True,
            )
            return

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
        d.exec()

    def block_analytics(self) -> None:
        # Some background info:
        # https://www.mobileread.com/forums/showpost.php?p=3934039&postcount=44
        debug("start")
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot block analytics events."),
                _("No device connected."),
                show=True,
            )
            return

        dlg = BlockAnalyticsOptionsDialog(self.gui, self)
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            return

        block_analytics_result = self._block_analytics(dlg.createAnalyticsEventsTrigger)
        if block_analytics_result:
            info_dialog(
                self.gui,
                _("Kobo Utilities") + " - " + _("Block analytics events"),
                block_analytics_result,
                show=True,
            )
        else:
            result_message = _("Failed to block analytics events.")
            d = ViewLog(
                _("Kobo Utilities") + " - " + _("Block analytics events"),
                result_message,
                parent=self.gui,
            )
            d.setWindowIcon(self.qaction.icon())
            d.exec()

    def vacuum_device_database(self) -> None:
        debug("start")
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot compress Kobo device database."),
                _("No device connected."),
                show=True,
            )
            return

        uncompressed_db_size = os.path.getsize(self.device.db_path)

        connection = self.device_database_connection()
        connection.execute("VACUUM")

        compressed_db_size = os.path.getsize(self.device.db_path)
        result_message = _(
            "The database on the device has been compressed.\n\tOriginal size = {0}MB\n\tCompressed size = {1}MB"
        ).format(
            "%.3f" % (uncompressed_db_size / 1024 / 1024),
            "%.3f" % (compressed_db_size / 1024 / 1024),
        )
        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Compress device database"),
            result_message,
            show=True,
        )

    def manage_series_on_device(self) -> None:
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return

        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot manage series in device library."),
                _("No device connected."),
                show=True,
            )
            return
        series_columns = self.get_series_columns()

        books = self._get_books_for_selected()
        debug("books[0].__class__=", books[0].__class__)

        if len(books) == 0:
            return
        seriesBooks = [SeriesBook(book, series_columns) for book in books]
        seriesBooks = sorted(seriesBooks, key=lambda k: k.sort_key(sort_by_name=True))
        debug("seriesBooks[0]._mi.__class__=", seriesBooks[0]._mi.__class__)
        debug("seriesBooks[0]._mi.kobo_series=", seriesBooks[0]._mi.kobo_series)
        debug(
            "seriesBooks[0]._mi.kobo_series_number=",
            seriesBooks[0]._mi.kobo_series_number,
        )
        debug("books:", seriesBooks)

        library_db = self.gui.library_view.model().db
        all_series = library_db.all_series()
        all_series.sort(key=lambda x: sort_key(x[1]))

        d = ManageSeriesDeviceDialog(
            self.gui, self, seriesBooks, all_series, series_columns
        )
        d.exec()
        if d.result() != d.DialogCode.Accepted:
            return

        debug("done series management - books:", seriesBooks)

        options = cfg.MetadataOptionsConfig()
        books = []
        for seriesBook in seriesBooks:
            debug("seriesBook._mi.contentID=", seriesBook._mi.contentID)
            if (
                seriesBook.is_title_changed()
                or seriesBook.is_pubdate_changed()
                or seriesBook.is_series_changed()
            ):
                book = seriesBook._mi
                book.series_index_string = seriesBook.series_index_string()
                book.kobo_series_number = seriesBook.series_index_string()  # pyright: ignore[reportAttributeAccessIssue]
                book.kobo_series = seriesBook.series_name()  # pyright: ignore[reportAttributeAccessIssue]
                book.contentIDs = [book.contentID]
                books.append(book)
                options.title = options.title or seriesBook.is_title_changed()
                options.series = options.series or seriesBook.is_series_changed()
                options.published_date = (
                    options.published_date or seriesBook.is_pubdate_changed()
                )
                debug("seriesBook._mi.__class__=", seriesBook._mi.__class__)
                debug(
                    "seriesBook.is_pubdate_changed()=%s"
                    % seriesBook.is_pubdate_changed()
                )
                debug("book.kobo_series=", book.kobo_series)
                debug("book.kobo_series_number=", book.kobo_series_number)
                debug("book.series=", book.series)
                debug("book.series_index=%s" % book.series_index)

        if options.title or options.series or options.published_date:
            progressbar = ProgressBar(
                parent=self.gui,
                window_title=_("Updating series information on device"),
                on_top=True,
            )
            progressbar.show()
            updated_books, unchanged_books, not_on_device_books, count_books = (
                self._update_metadata(books, progressbar, options)
            )

            debug("about to call sync_booklists")
            USBMS.sync_booklists(
                self.device.driver, (current_view.model().db, None, None)
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
            _("Kobo Utilities") + " - " + _("Manage series on device"),
            result_message,
            show=True,
        )

    def get_series_columns(self) -> dict[str, str]:
        custom_columns = cast(
            "Dict[str, Dict[str, Any]]", self.gui.library_view.model().custom_columns
        )
        series_columns = OrderedDict()
        for key, column in list(custom_columns.items()):
            typ = column["datatype"]
            if typ == "series":
                series_columns[key] = column["name"]
        return series_columns

    def upload_covers(self) -> None:
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot upload covers."),
                _("No device connected."),
                show=True,
            )
            return

        selectedIDs = self._get_selected_ids()

        if len(selectedIDs) == 0:
            return
        debug("selectedIDs:", selectedIDs)
        books = self._convert_calibre_ids_to_books(
            current_view.model().db, selectedIDs, get_cover=True
        )

        dlg = CoverUploadOptionsDialog(self.gui, self)
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            return

        options = cfg.plugin_prefs.coverUpload
        total_books, uploaded_covers, not_on_device_books = self._upload_covers(
            books, options
        )
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

    def remove_covers(self) -> None:
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot remove covers."),
                _("No device connected."),
                show=True,
            )
            return
        debug("self.device.path", self.device.path)

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
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            return

        options = cfg.plugin_prefs.removeCovers
        removed_covers, not_on_device_books, total_books = self._remove_covers(
            books, options
        )
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

    def open_cover_image_directory(self) -> None:
        current_view = self.gui.current_view()
        if current_view is None:
            return
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot open cover directory"),
                _("No device connected."),
                show=True,
            )
            return
        debug("self.device.path", self.device.path)

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

    def clean_images_dir(self) -> None:
        debug("start")

        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot clean covers directory."),
                _("No device connected."),
                show=True,
            )
            return
        debug("self.device.path", self.device.path)

        dlg = CleanImagesDirOptionsDialog(self.gui, self)
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            return

        main_prefix = self.device.driver._main_prefix
        assert isinstance(main_prefix, str), f"_main_prefix is type {type(main_prefix)}"
        if (
            isinstance(self.device.driver, KOBOTOUCH)
            and self.device.driver.fwversion
            >= self.device.driver.min_fwversion_images_tree
        ):
            main_image_path = os.path.join(main_prefix, ".kobo-images")
            sd_image_path = (
                os.path.join(
                    self.device.driver._card_a_prefix, "koboExtStorage/images-cache/"
                )
                if self.device.driver._card_a_prefix
                else None
            )
            images_tree = True
        else:
            main_image_path = os.path.join(main_prefix, ".kobo/images")
            sd_image_path = (
                os.path.join(self.device.driver._card_a_prefix, "koboExtStorage/images")
                if self.device.driver._card_a_prefix
                else None
            )
            images_tree = False

        options = cfg.CleanImagesDirJobOptions(
            str(self.device.driver.normalize_path(main_image_path)),
            str(self.device.driver.normalize_path(sd_image_path)),
            self.device.db_path,
            self.device.device_db_path,
            self.device.is_db_copied,
            cfg.plugin_prefs.cleanImagesDir.delete_extra_covers,
            images_tree,
        )
        debug("options=", options)
        CleanImagesDirProgressDialog(self.gui, options, self._clean_images_dir_job)

    def getAnnotationForSelected(self) -> None:
        current_view = self.gui.current_view()
        if (
            current_view is None
            or len(current_view.selectionModel().selectedRows()) == 0
        ):
            return
        self.device = self.get_device()
        if self.device is None:
            error_dialog(
                self.gui,
                _("Cannot upload covers."),
                _("No device connected."),
                show=True,
            )
            return

        self._getAnnotationForSelected()

    def _get_selected_ids(self) -> list[int]:
        current_view = self.gui.current_view()
        if current_view is None:
            return []
        rows: list[QModelIndex] = current_view.selectionModel().selectedRows()
        if not rows or len(rows) == 0:
            return []
        debug("self.gui.current_view().model()", current_view.model())
        return list(map(current_view.model().id, rows))

    def contentid_from_path(self, path: str, content_type: int):
        assert self.device is not None
        main_prefix = self.device.driver._main_prefix
        assert isinstance(main_prefix, str), f"_main_prefix is type {type(main_prefix)}"
        if content_type == 6:
            extension = os.path.splitext(path)[1]
            if extension == ".kobo":
                ContentID = os.path.splitext(path)[0]
                # Remove the prefix on the file.  it could be either
                ContentID = ContentID.replace(main_prefix, "")
            elif extension == "":
                ContentID = path
                kepub_path = self.device.driver.normalize_path(".kobo/kepub/")
                assert kepub_path is not None
                ContentID = ContentID.replace(main_prefix + kepub_path, "")
            else:
                ContentID = path
                ContentID = ContentID.replace(main_prefix, "file:///mnt/onboard/")

            if self.device.driver._card_a_prefix is not None:
                ContentID = ContentID.replace(
                    self.device.driver._card_a_prefix, "file:///mnt/sd/"
                )
        else:  # ContentType = 16
            ContentID = path
            ContentID = ContentID.replace(main_prefix, "file:///mnt/onboard/")
            if self.device.driver._card_a_prefix is not None:
                ContentID = ContentID.replace(
                    self.device.driver._card_a_prefix, "file:///mnt/sd/"
                )
        return ContentID.replace("\\", "/")

    def get_contentIDs_for_books(self, book_ids: list[int]) -> list[str]:
        contentIDs = []
        for book_id in book_ids:
            contentIDs_for_book = self.get_contentIDs_from_id(book_id)
            debug("contentIDs", contentIDs_for_book)
            contentIDs.extend(contentIDs_for_book)
        return contentIDs

    def _get_books_for_selected(self) -> list[Book]:
        view: DeviceBooksView | BooksView | None = self.gui.current_view()  # pyright: ignore[reportGeneralTypeIssues]
        if view is None:
            return []
        if isinstance(view, DeviceBooksView):
            rows = view.selectionModel().selectedRows()
            books = []
            for r in rows:
                book = view.model().db[view.model().map[r.row()]]
                book.calibre_id = r.row()
                books.append(book)
        else:
            books = []

        return books

    def _convert_calibre_ids_to_books(
        self, db: LibraryDatabase, ids: Iterable[int], get_cover: bool = False
    ) -> list[Book]:
        books = []
        for book_id in ids:
            book = self._convert_calibre_id_to_book(db, book_id, get_cover=get_cover)
            books.append(book)
        return books

    def _convert_calibre_id_to_book(
        self, db: LibraryDatabase, book_id: int, get_cover: bool = False
    ) -> Book:
        mi = db.get_metadata(book_id, index_is_id=True, get_cover=get_cover)
        book = Book("", "lpath", title=mi.title, other=mi)
        book.calibre_id = mi.id
        return book

    def get_device_path(self) -> str:
        debug("BEGIN Get Device Path")

        device_path = ""
        try:
            device_connected = self.gui.library_view.model().device_connected
        except Exception:
            debug("No device connected")
            device_connected = None

        # If there is a device connected, test if we can retrieve the mount point from Calibre
        if device_connected is not None:
            try:
                connected_device = self.gui.device_manager.connected_device
                assert connected_device is not None
                # _main_prefix is not reset when device is ejected so must be sure device_connected above
                device_path = connected_device._main_prefix
                debug("Root path of device: %s" % device_path)
            except Exception:
                debug("A device appears to be connected, but device path not defined")
        else:
            debug("No device appears to be connected")

        debug("END Get Device Path")
        return device_path

    def get_device(self):
        try:
            device = self.gui.device_manager.connected_device
            debug(f"Connected device: {device}")
            if device is None or not isinstance(device, KOBO):
                debug("No supported Kobo device appears to be connected")
                return None
        except Exception:
            debug("No device connected")
            return None

        version_info = None
        try:
            # This method got added in Calibre 5.41
            device_version_info = device.device_version_info()
        except AttributeError:
            debug(
                "no KOBO.device_version_info() method found; assuming old Calibre version"
            )
            version_file = Path(str(device._main_prefix), ".kobo/version")
            device_version_info = version_file.read_text().strip().split(",")
            debug("manually read version:", device_version_info)

        if device_version_info:
            serial_no, _, fw_version, _, _, model_id = device_version_info
            version_info = KoboVersionInfo(serial_no, fw_version, model_id)

        device_path = self.get_device_path()
        debug('device_path="%s"' % device_path)
        current_device_information = (
            self.gui.device_manager.get_current_device_information()
        )
        if device_path == "" or not current_device_information:
            # No device actually connected or it isn't ready
            return None
        connected_device_info = current_device_information.get("info", None)
        assert connected_device_info is not None
        debug("device_info:", connected_device_info)
        device_type = connected_device_info[0]
        drive_info = cast("Dict[str, Dict[str, str]]", connected_device_info[4])
        library_db = self.gui.library_view.model().db
        device_uuid = drive_info["main"]["device_store_uuid"]
        current_device_profile = cfg.get_book_profile_for_device(
            library_db, device_uuid, use_any_device=True
        )
        current_device_config = cfg.get_device_config(device_uuid)
        device_name = cfg.get_device_name(device_uuid, device.gui_name)
        debug("device_name:", device_name)
        individual_device_options = (
            cfg.plugin_prefs.commonOptionsStore.individualDeviceOptions
        )
        if individual_device_options and current_device_config is not None:
            current_backup_config = current_device_config.backupOptionsStore
        else:
            current_backup_config = cfg.plugin_prefs.backupOptionsStore

        supports_series = (
            isinstance(device, KOBOTOUCH)
            and "supports_series" in dir(device)
            and device.supports_series()
        )
        supports_series_list = (
            isinstance(device, KOBOTOUCH)
            and "supports_series_list" in dir(device)
            and device.supports_series_list
        ) or device.dbversion > 136
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

        device_db_path = cast(
            "str", device.normalize_path(device_path + ".kobo/KoboReader.sqlite")
        )
        if isinstance(device, KOBOTOUCH) and hasattr(device, "db_manager"):
            db_path = device.db_manager.dbpath
            is_db_copied = device.db_manager.needs_copy
        else:
            db_path = device_db_path
            is_db_copied = False
        debug("db_path:", db_path)

        kobo_device = KoboDevice(
            device,
            isinstance(device, KOBOTOUCH),
            current_device_profile,
            current_backup_config,
            device_type,
            drive_info,
            device_uuid,
            version_info,
            supports_series,
            supports_series_list,
            supports_ratings,
            epub_location_like_kepub,
            device_name,
            device_path,
            db_path,
            device_db_path,
            is_db_copied,
        )
        debug("kobo_device:", kobo_device)
        return kobo_device

    @property
    def device_fwversion(self) -> tuple[int, int, int] | None:
        if self.device is not None:
            return cast("Tuple[int, int, int]", self.device.driver.fwversion)
        return None

    def get_device_path_from_id(self, book_id: int) -> str | None:
        paths = self.get_device_paths_from_id(book_id)
        return paths[0] if paths else None

    def get_device_paths_from_id(self, book_id: int) -> list[str]:
        books = self.get_books_from_ids({book_id})
        return [book.path for book in books[book_id]]

    def get_books_from_ids(self, book_ids: Iterable[int]) -> dict[int, list[Book]]:
        books = defaultdict(list)
        for view in (self.gui.memory_view, self.gui.card_a_view):
            model: DeviceBooksModel = view.model()
            view_books = cast(
                "Dict[int, List[Book]]", model.paths_for_db_ids(book_ids, as_map=True)
            )
            for book_id in view_books:
                books[book_id].extend(view_books[book_id])
        debug("books=", books)
        return books

    def get_device_path_from_contentID(self, contentID: str, mimetype: str) -> str:
        assert self.device is not None
        card = "carda" if contentID.startswith("file:///mnt/sd/") else "main"
        return self.device.driver.path_from_contentid(contentID, "6", mimetype, card)

    def get_contentIDs_from_id(self, book_id: int) -> list[str | None]:
        debug("book_id=", book_id)
        paths = []
        for x in ("memory", "card_a"):
            x = getattr(self.gui, x + "_view").model()
            paths += x.paths_for_db_ids({book_id}, as_map=True)[book_id]
        debug("paths=", paths)
        return [r.contentID for r in paths]

    def device_database_connection(
        self, use_row_factory: bool = False
    ) -> DeviceDatabaseConnection:
        assert self.device is not None
        return DeviceDatabaseConnection(
            self.device.db_path,
            self.device.device_db_path,
            self.device.is_db_copied,
            use_row_factory,
        )

    def _store_queue_job(
        self,
        options: cfg.ReadLocationsJobOptions,
        books_to_modify: list[tuple[Any]],
    ):
        debug("Start")
        cpus = 1  # self.gui.device_manager.server.pool_size
        from .jobs import do_read_locations

        args = [books_to_modify, options, cpus]
        desc = _("Storing reading positions for {0} books").format(len(books_to_modify))
        self.gui.device_manager.create_job(
            do_read_locations,
            self.Dispatcher(self._read_completed),
            description=desc,
            args=args,
        )
        self.gui.status_bar.show_message(self.giu_name + " - " + desc, 3000)

    def _read_completed(self, job: DeviceJob):
        if job.failed:
            self.gui.job_exception(
                job, dialog_title=_("Failed to get reading positions")
            )
            return
        modified_epubs_map: dict[int, dict[str, Any]]
        options: cfg.ReadLocationsJobOptions
        modified_epubs_map, options = job.result
        debug("options", options)

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
            if options.prompt_to_store:
                profile_name = options.profile_name
                db = self.gui.current_db

                if "Goodreads Sync" in self.gui.iactions:
                    goodreads_sync_plugin = self.gui.iactions["Goodreads Sync"]

                dlg = ShowReadingPositionChangesDialog(
                    self.gui,
                    self,
                    modified_epubs_map,
                    db,
                    profile_name,
                    goodreads_sync_plugin is not None,
                )
                dlg.exec()
                if dlg.result() != dlg.DialogCode.Accepted:
                    debug("dialog cancelled")
                    return
                modified_epubs_map = dlg.reading_locations
            self._update_database_columns(modified_epubs_map)

            if options.prompt_to_store:
                library_config = cfg.get_library_config(self.gui.current_db)
                if (
                    library_config.readingPositionChangesStore.selectBooksInLibrary
                    or library_config.readingPositionChangesStore.updeateGoodreadsProgress
                ):
                    self.gui.library_view.select_rows(list(modified_epubs_map.keys()))
                if (
                    goodreads_sync_plugin
                    and library_config.readingPositionChangesStore.updeateGoodreadsProgress
                ):
                    debug(
                        "goodreads_sync_plugin.users.keys()=",
                        list(goodreads_sync_plugin.users.keys()),
                    )
                    goodreads_sync_plugin.update_reading_progress(
                        "progress", sorted(goodreads_sync_plugin.users.keys())[0]
                    )

    def _device_database_backup(self, backup_options: cfg.DatabaseBackupJobOptions):
        debug("Start")

        from .jobs import do_device_database_backup

        args = [pickle.dumps(backup_options)]
        desc = _("Backing up Kobo device database")
        self.gui.device_manager.create_job(
            do_device_database_backup,
            self.Dispatcher(self._device_database_backup_completed),
            description=desc,
            args=args,
        )
        self.gui.status_bar.show_message(_("Kobo Utilities") + " - " + desc, 3000)

    def _device_database_backup_completed(self, job: DeviceJob):
        if job.failed:
            self.gui.job_exception(
                job, dialog_title=_("Failed to back up device database")
            )
            return

    def _clean_images_dir_job(self, options: cfg.CleanImagesDirJobOptions):
        debug("Start")
        from .jobs import do_clean_images_dir

        func = "arbitrary_n"
        cpus = self.gui.job_manager.server.pool_size
        args = [
            do_clean_images_dir.__module__,
            do_clean_images_dir.__name__,
            (pickle.dumps(options), cpus),
        ]
        desc = _("Cleaning images directory")
        self.gui.job_manager.run_job(
            self.Dispatcher(partial(self._clean_images_dir_completed, options)),
            func,
            args=args,
            description=desc,
        )
        self.gui.status_bar.show_message(_("Cleaning images directory") + "...")

    def _clean_images_dir_completed(
        self, options: cfg.CleanImagesDirJobOptions, job: DeviceJob
    ) -> None:
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
            if options.delete_extra_covers:
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

        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Finished"),
            msg,
            show_copy_button=True,
            show=True,
            det_msg=details,
        )

    def _remove_annotations_job(
        self, options: cfg.RemoveAnnotationsJobOptions, books: list[tuple[Any]]
    ):
        debug("Start")
        from .jobs import do_remove_annotations

        func = "arbitrary_n"
        cpus = self.gui.job_manager.server.pool_size
        args = [
            do_remove_annotations.__module__,
            do_remove_annotations.__name__,
            (pickle.dumps(options), books, cpus),
        ]
        desc = _("Removing annotations files")
        self.gui.job_manager.run_job(
            self.Dispatcher(self._remove_annotations_completed),
            func,
            args=args,
            description=desc,
        )
        self.gui.status_bar.show_message(_("Removing annotations files") + "...")

    def _remove_annotations_completed(self, job: DeviceJob) -> None:
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

        info_dialog(
            self.gui,
            _("Kobo Utilities") + " - " + _("Finished"),
            msg,
            show_copy_button=True,
            show=True,
            det_msg=details,
        )

    def validate_profile(self, profile_name: str):
        columns_config = None
        if profile_name:
            profile = cfg.get_profile_info(self.gui.current_db, profile_name)
            columns_config = profile.customColumnOptions
        elif self.device is not None and self.device.profile is not None:
            columns_config = self.device.profile.customColumnOptions

        if columns_config is None:
            return "{0}\n\n{1}".format(
                _('Profile "{0}" does not exist.').format(profile_name),
                _("Select another profile to proceed."),
            )

        custom_cols = self.gui.current_db.field_metadata.custom_field_metadata(
            include_composites=False
        )

        def check_column_name(column_name: str | None):
            return (
                None
                if column_name is None or len(column_name.strip()) == 0
                else column_name
            )

        def check_column_exists(column_name: str | None):
            return column_name is not None and column_name in custom_cols

        debug("columns_config:", columns_config)
        kobo_chapteridbookmarked_column = columns_config.currentReadingLocationColumn
        kobo_percentRead_column = columns_config.percentReadColumn
        rating_column = columns_config.ratingColumn
        last_read_column = columns_config.lastReadColumn

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
                [f'"{invalid_column}"' for invalid_column in invalid_columns]
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

    def get_column_names(self, profile_name: str | None = None):
        if profile_name:
            profile = cfg.get_profile_info(self.gui.current_db, profile_name)
            columns_config = profile.customColumnOptions
        elif self.device is not None and self.device.profile is not None:
            columns_config = self.device.profile.customColumnOptions
        else:
            return cfg.CustomColumns(None, None, None, None, None, None)

        debug("columns_config:", columns_config)
        kobo_chapteridbookmarked_column = columns_config.currentReadingLocationColumn
        kobo_percentRead_column = columns_config.percentReadColumn
        rating_column = columns_config.ratingColumn
        last_read_column = columns_config.lastReadColumn
        time_spent_reading_column = columns_config.timeSpentReadingColumn
        rest_of_book_estimate_column = columns_config.restOfBookEstimateColumn

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

        return cfg.CustomColumns(
            kobo_chapteridbookmarked_column,
            kobo_percentRead_column,
            rating_column,
            last_read_column,
            time_spent_reading_column,
            rest_of_book_estimate_column,
        )

    def _update_database_columns(self, reading_locations: dict[int, dict[str, Any]]):
        assert self.device is not None
        debug("reading_locations=", reading_locations)
        debug("start number of reading_locations= %d" % (len(reading_locations)))
        progressbar = ProgressBar(
            parent=self.gui, window_title=_("Storing reading positions"), on_top=True
        )
        total_books = len(reading_locations)
        progressbar.show_with_maximum(total_books)

        library_db = self.gui.current_db

        def value_changed(old_value: object | None, new_value: object | None):
            return bool(
                (old_value is not None and new_value is None)
                or (old_value is None and new_value is not None)
                or old_value != new_value
            )

        custom_columns = self.get_column_names()
        kobo_chapteridbookmarked_column_name = custom_columns.current_location
        kobo_percentRead_column_name = custom_columns.percent_read
        rating_column_name = custom_columns.rating
        last_read_column_name = custom_columns.last_read
        time_spent_reading_column_name = custom_columns.time_spent_reading
        rest_of_book_estimate_column_name = custom_columns.rest_of_book_estimate

        if kobo_chapteridbookmarked_column_name is not None:
            debug(
                "kobo_chapteridbookmarked_column_name=",
                kobo_chapteridbookmarked_column_name,
            )
            kobo_chapteridbookmarked_col_label = library_db.field_metadata.key_to_label(
                kobo_chapteridbookmarked_column_name
            )
            debug(
                "kobo_chapteridbookmarked_col_label=",
                kobo_chapteridbookmarked_col_label,
            )

        debug(
            "kobo_chapteridbookmarked_column_name=",
            kobo_chapteridbookmarked_column_name,
        )
        debug(
            "_update_database_columns - kobo_percentRead_column_name=",
            kobo_percentRead_column_name,
        )
        debug("rating_column_name=", rating_column_name)
        debug("last_read_column_name=", last_read_column_name)
        debug("time_spent_reading_column_name=", time_spent_reading_column_name)
        debug("rest_of_book_estimate_column_name=", rest_of_book_estimate_column_name)
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
            progressbar.set_label(_("Updating {}").format(book_mi.title))
            progressbar.increment()

            kobo_chapteridbookmarked = None
            kobo_adobe_location = None
            kobo_percentRead = None
            last_read = None
            time_spent_reading = None
            rest_of_book_estimate = None
            debug("reading_location=", reading_location)
            if (
                reading_location["MimeType"] == MIMETYPE_KOBO
                or self.device.epub_location_like_kepub
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

            book_updated = False
            if last_read_column_name is not None:
                last_read_metadata = book.get_user_metadata(last_read_column_name, True)
                assert last_read_metadata is not None
                current_last_read = last_read_metadata["#value#"]
                debug(
                    "book.get_user_metadata(last_read_column_name, True)['#value#']=",
                    current_last_read,
                )
                debug("setting mi.last_read=", last_read)
                debug("current_last_read == last_read=", current_last_read == last_read)

                if value_changed(current_last_read, last_read):
                    id_map_last_read[book_id] = last_read
                    book_updated = True
                else:
                    book_updated = book_updated or False

            if kobo_chapteridbookmarked_column_name is not None:
                debug("kobo_chapteridbookmarked='%s'" % (kobo_chapteridbookmarked))
                debug("kobo_adobe_location='%s'" % (kobo_adobe_location))
                debug("kobo_percentRead=", kobo_percentRead)
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
                    debug("setting bookmark column to None")
                debug("chapterIdBookmark - on kobo=", new_value)
                metadata = book.get_user_metadata(
                    kobo_chapteridbookmarked_column_name, True
                )
                assert metadata is not None
                old_value = metadata["#value#"]
                debug("chapterIdBookmark - in library=", old_value)
                debug(
                    "chapterIdBookmark - on kobo==in library=", new_value == old_value
                )

                if value_changed(old_value, new_value):
                    id_map_chapteridbookmarked[book_id] = new_value
                    book_updated = True
                else:
                    book_updated = book_updated or False

            if kobo_percentRead_column_name is not None:
                debug("setting kobo_percentRead=", kobo_percentRead)
                metadata = book.get_user_metadata(kobo_percentRead_column_name, True)
                assert metadata is not None
                current_percentRead = metadata["#value#"]
                debug("percent read - in book=", current_percentRead)

                if value_changed(current_percentRead, kobo_percentRead):
                    id_map_percentRead[book_id] = kobo_percentRead
                    book_updated = True
                else:
                    book_updated = book_updated or False

            if rating_column_name is not None and kobo_rating > 0:
                debug("setting rating_column_name=", rating_column_name)
                if rating_column_name == "rating":
                    current_rating = book.rating
                    debug("rating - in book=", current_rating)
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
                debug(
                    "book.get_user_metadata(time_spent_reading_column_name, True)['#value#']=",
                    current_time_spent_reading,
                )
                debug("setting mi.time_spent_reading=", time_spent_reading)
                debug(
                    "current_time_spent_reading == time_spent_reading=",
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
                debug(
                    "book.get_user_metadata(rest_of_book_estimate_column_name , True)['#value#']=",
                    current_rest_of_book_estimate,
                )
                debug("setting mi.rest_of_book_estimate=", rest_of_book_estimate)
                debug(
                    "current_rest_of_book_estimate == rest_of_book_estimate=",
                    current_rest_of_book_estimate == rest_of_book_estimate,
                )

                if value_changed(current_rest_of_book_estimate, rest_of_book_estimate):
                    id_map_rest_of_book_estimate[book_id] = rest_of_book_estimate
                    book_updated = True
                else:
                    book_updated = book_updated or False

            id_map[book_id] = mi

        if kobo_chapteridbookmarked_column_name:
            debug(
                "Updating metadata - for column: %s number of changes=%d"
                % (
                    kobo_chapteridbookmarked_column_name,
                    len(id_map_chapteridbookmarked),
                )
            )
            library_db.new_api.set_field(
                kobo_chapteridbookmarked_column_name, id_map_chapteridbookmarked
            )
        if kobo_percentRead_column_name:
            debug(
                "Updating metadata - for column: %s number of changes=%d"
                % (kobo_percentRead_column_name, len(id_map_percentRead))
            )
            library_db.new_api.set_field(
                kobo_percentRead_column_name, id_map_percentRead
            )
        if rating_column_name:
            debug(
                "Updating metadata - for column: %s number of changes=%d"
                % (rating_column_name, len(id_map_rating))
            )
            library_db.new_api.set_field(rating_column_name, id_map_rating)
        if last_read_column_name:
            debug(
                "Updating metadata - for column: %s number of changes=%d"
                % (last_read_column_name, len(id_map_last_read))
            )
            library_db.new_api.set_field(last_read_column_name, id_map_last_read)
        if time_spent_reading_column_name:
            debug(
                "Updating metadata - for column: %s number of changes=%d"
                % (time_spent_reading_column_name, len(id_map_time_spent_reading))
            )
            library_db.new_api.set_field(
                time_spent_reading_column_name, id_map_time_spent_reading
            )
        if rest_of_book_estimate_column_name:
            debug(
                "Updating metadata - for column: %s number of changes=%d"
                % (
                    rest_of_book_estimate_column_name,
                    len(id_map_rest_of_book_estimate),
                )
            )
            library_db.new_api.set_field(
                rest_of_book_estimate_column_name, id_map_rest_of_book_estimate
            )

        debug("Updating GUI - new DB engine")
        self.gui.iactions["Edit Metadata"].refresh_gui(list(reading_locations))
        debug("finished")

        progressbar.hide()
        self.gui.status_bar.show_message(
            _("Kobo Utilities")
            + " - "
            + _("Storing reading positions completed - {0} changed.").format(
                len(reading_locations)
            ),
            3000,
        )

    def _getAnnotationForSelected(self) -> None:
        assert self.device is not None

        # Generate a path_map from selected ids
        def get_ids_from_selected_rows() -> list[int]:
            rows = self.gui.library_view.selectionModel().selectedRows()
            if not rows or len(rows) < 1:
                rows = range(self.gui.library_view.model().rowCount(QModelIndex()))
            return list(map(self.gui.library_view.model().id, rows))

        def get_formats(_id: int) -> list[str]:
            formats = db.formats(_id, index_is_id=True)
            return [fmt.lower() for fmt in formats.split(",")]

        def generate_annotation_paths(
            ids: list[int],
        ) -> dict[int, dict[str, str | list[str]]]:
            # Generate path templates
            # Individual storage mount points scanned/resolved in driver.get_annotations()
            path_map = {}
            for _id in ids:
                paths = self.get_device_paths_from_id(_id)
                debug("paths=", paths)
                if len(paths) > 0:
                    the_path = paths[0]
                    if len(paths) > 1 and (
                        len(os.path.splitext(paths[0])) > 1
                    ):  # No extension - is kepub
                        the_path = paths[1]
                    path_map[_id] = {"path": the_path, "fmts": get_formats(_id)}
            return path_map

        annotationText = []

        if self.gui.current_view() is not self.gui.library_view:
            error_dialog(
                self.gui,
                _("Use library only"),
                _("User annotations generated from main library only"),
                show=True,
            )
            return
        db = self.gui.library_view.model().db

        # Get the list of ids
        ids = get_ids_from_selected_rows()
        if not ids:
            error_dialog(
                self.gui,
                _("No books selected"),
                _("No books selected to fetch annotations from"),
                show=True,
            )
            return

        debug("ids=", ids)
        # Map ids to paths
        path_map = generate_annotation_paths(ids)
        debug("path_map=", path_map)
        if len(path_map) == 0:
            error_dialog(
                self.gui,
                _("No books on device selected"),
                _(
                    "None of the books selected were on the device. Annotations can only be copied for books on the device."
                ),
                show=True,
            )
            return

        from calibre.ebooks.metadata import authors_to_string

        # Dispatch to the device get_annotations()
        debug("path_map=", path_map)
        bookmarked_books = self.device.driver.get_annotations(path_map)
        debug("bookmarked_books=", bookmarked_books)

        for id_ in bookmarked_books:
            bm = self.device.driver.UserAnnotation(
                bookmarked_books[id_][0], bookmarked_books[id_][1]
            )

            mi = db.get_metadata(id_, index_is_id=True)

            user_notes_soup = self.device.driver.generate_annotation_html(bm.value)
            book_heading = "<b>%(title)s</b> by <b>%(author)s</b>" % {
                "title": mi.title,
                "author": authors_to_string(mi.authors),
            }
            bookmark_html = str(user_notes_soup.div)
            debug("bookmark_html:", bookmark_html)
            annotationText.append(book_heading + bookmark_html)

        d = ViewLog(
            "Kobo Touch Annotation", "\n<hr/>\n".join(annotationText), parent=self.gui
        )
        d.setWindowIcon(self.qaction.icon())
        d.exec()

    def _upload_covers(self, books: list[Book], options: cfg.CoverUploadConfig):
        uploaded_covers = 0
        total_books = 0
        not_on_device_books = len(books)
        device = self.device
        assert device is not None

        kobo_kepub_dir = cast("str", device.driver.normalize_path(".kobo/kepub/"))
        sd_kepub_dir = cast(
            "str", device.driver.normalize_path("koboExtStorage/kepub/")
        )
        debug("kobo_kepub_dir=", kobo_kepub_dir)
        # Extra cover upload options were added in calibre 3.45.
        driver_supports_extended_cover_options = hasattr(self.device, "dithered_covers")
        driver_supports_cover_letterbox_colors = hasattr(
            self.device, "letterbox_fs_covers_color"
        )

        for book in books:
            total_books += 1
            paths = self.get_device_paths_from_id(cast("int", book.calibre_id))
            not_on_device_books -= 1 if len(paths) > 0 else 0
            for path in paths:
                debug("path=", path)
                if (
                    kobo_kepub_dir not in path and sd_kepub_dir not in path
                ) or options.kepub_covers:
                    if isinstance(device.driver, KOBOTOUCH):
                        if driver_supports_cover_letterbox_colors:
                            device.driver._upload_cover(
                                path,
                                "",
                                book,
                                path,
                                options.blackandwhite,
                                dithered_covers=options.dithered_covers,
                                keep_cover_aspect=options.keep_cover_aspect,
                                letterbox_fs_covers=options.letterbox,
                                letterbox_color=options.letterbox_color,
                                png_covers=options.png_covers,
                            )
                        elif driver_supports_extended_cover_options:
                            device.driver._upload_cover(
                                path,
                                "",
                                book,
                                path,
                                options.blackandwhite,
                                dithered_covers=options.dithered_covers,
                                keep_cover_aspect=options.keep_cover_aspect,
                                letterbox_fs_covers=options.letterbox,
                                png_covers=options.png_covers,
                            )
                        else:
                            device.driver._upload_cover(
                                path,
                                "",
                                book,
                                path,
                                options.blackandwhite,
                                keep_cover_aspect=options.keep_cover_aspect,
                            )
                    else:
                        device.driver._upload_cover(
                            path,
                            "",
                            book,
                            path,
                            options.blackandwhite,
                        )
                    uploaded_covers += 1

        return total_books, uploaded_covers, not_on_device_books

    def _remove_covers(self, books: list[Book], options: cfg.RemoveCoversConfig):
        connection = self.device_database_connection()
        total_books = 0
        removed_covers = 0
        not_on_device_books = 0

        device = self.device
        # These should have been checked in the calling method
        assert device is not None
        assert isinstance(device.driver, KOBOTOUCH)

        remove_fullsize_covers = options.remove_fullsize_covers
        debug("remove_fullsize_covers=", remove_fullsize_covers)

        imageId_query = (
            "SELECT ImageId "
            "FROM content "
            "WHERE ContentType = ? "
            "AND ContentId = ?"
        )  # fmt: skip
        cursor = connection.cursor()

        for book in books:
            debug("book=", book)
            debug("book.__class__=", book.__class__)
            debug("book.contentID=", book.contentID)
            debug("book.lpath=", book.lpath)
            debug("book.path=", book.path)
            contentIDs = (
                [book.contentID]
                if book.contentID is not None
                else self.get_contentIDs_from_id(cast("int", book.calibre_id))
            )
            debug("contentIDs=", contentIDs)
            for contentID in contentIDs:
                debug("contentID=", contentID)
                if not contentID or (
                    "file:///" not in contentID and not options.kepub_covers
                ):
                    continue

                if contentID.startswith("file:///mnt/sd/"):
                    path = device.driver._card_a_prefix
                else:
                    path = device.driver._main_prefix

                query_values = (
                    self.CONTENTTYPE,
                    contentID,
                )
                cursor.execute(imageId_query, query_values)
                try:
                    result = next(cursor)
                    debug("contentId='%s', imageId='%s'" % (contentID, result[0]))
                    image_id = result[0]
                    debug("image_id=", image_id)
                    if image_id is not None:
                        image_path = device.driver.images_path(path, image_id)
                        debug("image_path=%s" % image_path)

                        for ending in list(device.driver.cover_file_endings().keys()):
                            debug("ending='%s'" % ending)
                            if remove_fullsize_covers and ending != " - N3_FULL.parsed":
                                debug("not the full sized cover. Skipping")
                                continue
                            fpath = image_path + ending
                            fpath = device.driver.normalize_path(fpath)
                            assert isinstance(fpath, str)
                            debug("fpath=%s" % fpath)

                            if os.path.exists(fpath):
                                debug("Image File Exists")
                                os.unlink(fpath)

                        try:
                            os.removedirs(os.path.dirname(image_path))
                        except Exception as e:
                            debug(
                                "unable to remove dir '%s': %s"
                                % (os.path.dirname(image_path), e)
                            )
                    removed_covers += 1
                except StopIteration:
                    debug("no match for contentId='%s'" % (contentID,))
                    not_on_device_books += 1
                total_books += 1

        return removed_covers, not_on_device_books, total_books

    def _open_cover_image_directory(self, books: list[Book]):
        connection = self.device_database_connection(use_row_factory=True)
        total_books = 0
        removed_covers = 0
        not_on_device_books = 0

        device = self.device
        assert device is not None
        assert isinstance(device.driver, KOBOTOUCH)

        imageId_query = (
            "SELECT ImageId "
            "FROM content "
            "WHERE ContentType = ? "
            "AND ContentId = ?"
        )  # fmt: skip
        cursor = connection.cursor()

        for book in books:
            debug("book=", book)
            debug("book.__class__=", book.__class__)
            debug("book.contentID=", book.contentID)
            debug("book.lpath=", book.lpath)
            debug("book.path=", book.path)
            contentIDs = (
                [book.contentID]
                if book.contentID is not None
                else self.get_contentIDs_from_id(cast("int", book.calibre_id))
            )
            debug("contentIDs=", contentIDs)
            for contentID in contentIDs:
                debug("contentID=", contentID)

                if contentID is None:
                    debug("Book does not have a content id.")
                    continue
                if contentID.startswith("file:///mnt/sd/"):
                    path = device.driver._card_a_prefix
                else:
                    path = device.driver._main_prefix

                query_values = (
                    self.CONTENTTYPE,
                    contentID,
                )
                cursor.execute(imageId_query, query_values)
                image_id = None
                try:
                    result = next(cursor)
                    debug(
                        "contentId='%s', imageId='%s'" % (contentID, result["ImageId"])
                    )
                    image_id = result["ImageId"]
                except StopIteration:
                    debug("no match for contentId='%s'" % (contentID,))
                    image_id = device.driver.imageid_from_contentid(contentID)

                if image_id:
                    cover_image_file = device.driver.images_path(path, image_id)
                    debug("cover_image_file='%s'" % (cover_image_file))
                    cover_dir = os.path.dirname(os.path.abspath(cover_image_file))
                    debug("cover_dir='%s'" % (cover_dir))
                    if os.path.exists(cover_dir):
                        open_local_file(cover_dir)
                total_books += 1

        return removed_covers, not_on_device_books, total_books

    def _check_book_in_database(self, books: list[Book]) -> list[Book]:
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
                book.contentID = self.contentid_from_path(book.path, self.CONTENTTYPE)  # pyright: ignore[reportAttributeAccessIssue]

            query_values = (book.contentID,)
            cursor.execute(imageId_query, query_values)
            try:
                next(cursor)
            except StopIteration:
                debug("no match for contentId='%s'" % (book.contentID,))
                not_on_device_books.append(book)

        return not_on_device_books

    def _get_shelf_count(self) -> list[list[Any]]:
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
            debug("row:", i, row[0], row[1], row[2], row[3], row[4])
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

    def _get_related_books_count(self, related_category: int) -> list[dict[str, Any]]:
        debug("order_shelf_type:", related_category)
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
        debug("related_books_query:", related_books_query)

        cursor = connection.cursor()
        cursor.execute(related_books_query)

        for i, row in enumerate(cursor):
            debug("row:", i, row[0], row[1])
            shelf = {}
            shelf["name"] = row[0]
            shelf["count"] = int(row[1])
            related_books.append(shelf)

        debug("related_books:", related_books)
        return related_books

    def _set_related_books(
        self,
        related_books: list[dict[str, Any]],
        options: cfg.SetRelatedBooksOptionsStoreConfig,
    ):
        debug("related_books:", related_books, " options:", options)

        categories_count = 0
        books_count = 0

        progressbar = ProgressBar(parent=self.gui, window_title=_("Set related books"))
        total_related_books = len(related_books)
        progressbar.show_with_maximum(total_related_books)
        progressbar.left_align_label()

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
        if options.relatedBooksType == cfg.RelatedBooksType.Series:
            get_query = series_query
        else:
            get_query = author_query
        insert_query = "INSERT INTO volume_tabs VALUES ( ?, ? )"
        delete_query = "DELETE FROM volume_tabs WHERE tabId = ? "

        with self.device_database_connection(use_row_factory=True) as connection:
            cursor = connection.cursor()
            for related_type in related_books:
                progressbar.set_label(
                    _("Setting related books for {}").format(related_type["name"])
                )
                progressbar.increment()

                categories_count += 1
                debug(
                    "related_type=%s, count=%d"
                    % (related_type["name"], related_type["count"])
                )
                if related_type["count"] <= 1:
                    continue
                related_type_data = (related_type["name"],)
                debug("related_type_data:", related_type_data)
                cursor.execute(get_query, related_type_data)
                related_type_contentIds = []
                for i, row in enumerate(cursor):
                    debug(
                        "row:",
                        i,
                        row["ContentID"],
                        row["Title"],
                        row["Attribution"],
                        row["Series"],
                        row["SeriesNumber"],
                    )
                    related_type_contentIds.append(row["ContentID"])

                debug("related_type_contentIds:", related_type_contentIds)
                for tab_contentId in related_type_contentIds:
                    cursor.execute(delete_query, (tab_contentId,))
                    books_count += 1
                    for volume_contentId in related_type_contentIds:
                        if tab_contentId != volume_contentId:
                            insert_data = (volume_contentId, tab_contentId)
                            debug("insert_data:", insert_data)
                            cursor.execute(insert_query, insert_data)

        progressbar.hide()
        debug("end")
        return categories_count, books_count

    def _delete_related_books(self) -> None:
        progressbar = ProgressBar(
            parent=self.gui, window_title=_("Delete related books")
        )
        progressbar.show_with_maximum(100)
        progressbar.left_align_label()

        connection = self.device_database_connection()
        delete_query = (
            "DELETE FROM volume_tabs  "
            "WHERE tabId LIKE 'file%' "
            "OR volumeId LIKE 'file%' "
        )

        cursor = connection.cursor()
        progressbar.set_label(_("Delete related books"))
        progressbar.increment()

        cursor.execute(delete_query)

        progressbar.hide()
        debug("end")

    def _remove_duplicate_shelves(
        self, shelves: list[list[Any]], options: cfg.FixDuplicatesOptionsStoreConfig
    ):
        debug("total shelves=%d: options=%s" % (len(shelves), options))
        starting_shelves = 0
        shelves_removed = 0
        finished_shelves = 0
        progressbar = ProgressBar(
            parent=self.gui, window_title=_("Duplicate collections in device database")
        )
        total_shelves = len(shelves)
        progressbar.show_with_maximum(total_shelves)
        progressbar.left_align_label()

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

        purge_shelves = options.purgeShelves
        keep_newest = options.keepNewestShelf

        with self.device_database_connection() as connection:
            cursor = connection.cursor()
            for shelf in shelves:
                starting_shelves += shelf[3]
                finished_shelves += 1
                progressbar.set_label(
                    _("Removing duplicates of collection {}").format(shelf[0])
                )
                progressbar.increment()

                if shelf[3] > 1:
                    debug(
                        "shelf: %s, '%s', '%s', '%s', '%s'"
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
                    debug("marking as deleted:", shelves_update_values)
                    debug("shelves_update_query:", shelves_update_query)
                    debug("shelves_delete_query:", shelves_delete_query)
                    debug("shelves_delete_values:", shelves_delete_values)
                    cursor.execute(shelves_update_query, shelves_update_values)
                    cursor.execute(shelves_delete_query, shelves_delete_values)
                    shelves_removed += shelf[3] - 1

            if purge_shelves:
                debug("purging all shelves marked as deleted")
                cursor.execute(shelves_purge)

        progressbar.hide()
        return starting_shelves, shelves_removed, finished_shelves

    def _check_device_database(self):
        assert self.device is not None
        return check_device_database(self.device.db_path)

    def _block_analytics(self, create_trigger: bool):
        connection = self.device_database_connection()
        block_result = "The trigger on the AnalyticsEvents table has been removed."

        cursor = connection.cursor()

        cursor.execute("DROP TRIGGER IF EXISTS BlockAnalyticsEvents")
        # Delete the Extended drvier version if it is there.
        cursor.execute("DROP TRIGGER IF EXISTS KTE_BlockAnalyticsEvents")

        if create_trigger:
            try:
                cursor.execute("DELETE FROM AnalyticsEvents")
                debug("creating trigger.")
                trigger_query = (
                    "CREATE TRIGGER IF NOT EXISTS BlockAnalyticsEvents "
                    "AFTER INSERT ON AnalyticsEvents "
                    "BEGIN "
                    "DELETE FROM AnalyticsEvents; "
                    "END"
                )
                cursor.execute(trigger_query)
            except apsw.SQLError as e:
                debug("exception=", e)
                block_result = None
            else:
                block_result = "AnalyticsEvents have been blocked in the database."

        return block_result

    def generate_metadata_query(self):
        assert self.device is not None
        debug(
            "self.device.supports_series=%s, self.device.supports_series_list%s"
            % (self.device.supports_series, self.device.supports_series_list)
        )

        test_query_columns = []
        test_query_columns.append("Title")
        test_query_columns.append("Attribution")
        test_query_columns.append("Description")
        test_query_columns.append("Publisher")
        test_query_columns.append("MimeType")

        if self.device.supports_series:
            debug("supports series is true")
            test_query_columns.append("Series")
            test_query_columns.append("SeriesNumber")
            test_query_columns.append("Subtitle")
        else:
            test_query_columns.append("null as Series")
            test_query_columns.append("null as SeriesNumber")
        if self.device.supports_series_list:
            debug("supports series list is true")
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
        debug("test_query=%s" % test_query)
        return test_query

    def _update_metadata(
        self,
        books: list[Book],
        progressbar: ProgressBar,
        options: cfg.MetadataOptionsConfig,
    ):
        assert self.device is not None
        from calibre.ebooks.metadata import authors_to_string
        from calibre.utils.localization import canonicalize_lang, lang_as_iso639_1

        debug("number books=", len(books), "options=", options)

        updated_books = 0
        not_on_device_books = 0
        unchanged_books = 0
        count_books = 0

        total_books = len(books)
        progressbar.show_with_maximum(total_books)

        from calibre.library.save_to_disk import find_plugboard

        plugboards = self.gui.library_view.model().db.prefs.get("plugboards", {})
        debug("plugboards=", plugboards)
        debug(
            "self.device.driver.__class__.__name__=",
            self.device.driver.__class__.__name__,
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

        with self.device_database_connection(use_row_factory=True) as connection:
            test_query = self.generate_metadata_query()
            cursor = connection.cursor()
            kobo_series_dict = {}
            if self.device.supports_series_list:
                cursor.execute(series_id_query)
                rows = list(cursor)
                debug("series_id_query result=", rows)
                for row in rows:
                    kobo_series_dict[row["Series"]] = row["SeriesID"]
                debug("kobo_series_list=", kobo_series_dict)

            for book in books:
                progressbar.set_label(_("Updating metadata for {}").format(book.title))
                progressbar.increment()

                for contentID in cast("List[str]", book.contentIDs):
                    debug("searching for contentId='%s'" % (contentID))
                    if not contentID:
                        contentID = self.contentid_from_path(
                            book.path, self.CONTENTTYPE
                        )
                    debug("options.update_KoboEpubs=", options.update_KoboEpubs)
                    debug("contentID.startswith('file')=", contentID.startswith("file"))
                    if not options.update_KoboEpubs and not contentID.startswith(
                        "file"
                    ):
                        debug("skipping book")
                        continue

                    count_books += 1
                    query_values = (contentID,)
                    cursor.execute(test_query, query_values)
                    try:
                        result = next(cursor)
                    except StopIteration:
                        result = None
                    if result is not None:
                        debug("found contentId='%s'" % (contentID))
                        debug("    result=", result)
                        debug("    result['Title']='%s'" % (result["Title"]))
                        debug(
                            "    result['Attribution']='%s'" % (result["Attribution"])
                        )

                        title_string = None
                        authors_string = None
                        newmi = book.deepcopy_metadata()
                        if options.usePlugboard and plugboards is not None:
                            book_format = os.path.splitext(contentID)[1][1:]
                            debug("format='%s'" % (book_format))
                            plugboard = find_plugboard(
                                self.device.driver.__class__.__name__,
                                book_format,
                                plugboards,
                            )
                            debug("plugboard=", plugboard)

                            if plugboard is not None:
                                debug("applying plugboard")
                                newmi.template_to_attribute(book, plugboard)
                            debug("newmi.title=", newmi.title)
                            debug("newmi.authors=", newmi.authors)
                            debug("newmi.comments=", newmi.comments)
                        else:
                            if options.titleSort:
                                title_string = newmi.title_sort
                            if options.authourSort:
                                debug("author=", newmi.authors)
                                debug("using author_sort=", newmi.author_sort)
                                debug("using author_sort - author=", newmi.authors)
                                authors_string = newmi.author_sort
                        debug("title_string=", title_string)
                        title_string = (
                            newmi.title if title_string is None else title_string
                        )
                        debug("title_string=", title_string)
                        debug("authors_string=", authors_string)
                        authors_string = (
                            authors_to_string(newmi.authors)
                            if authors_string is None
                            else authors_string
                        )
                        debug("authors_string=", authors_string)
                        newmi.series_index_string = getattr(
                            book, "series_index_string", None
                        )

                        update_query = "UPDATE content SET "
                        update_values = []
                        set_clause_columns = []
                        changes_found = False
                        rating_values = []
                        rating_change_query = None

                        if options.title and result["Title"] != title_string:
                            set_clause_columns.append("Title=?")
                            debug("set_clause=", set_clause_columns)
                            update_values.append(title_string)

                        if options.author and result["Attribution"] != authors_string:
                            set_clause_columns.append("Attribution=?")
                            debug("set_clause_columns=", set_clause_columns)
                            update_values.append(authors_string)

                        if options.description:
                            new_comments = library_comments = newmi.comments
                            if options.descriptionUseTemplate:
                                new_comments = self._render_synopsis(
                                    newmi, book, template=options.descriptionTemplate
                                )
                                if len(new_comments) == 0:
                                    new_comments = library_comments
                            if (
                                new_comments
                                and len(new_comments) > 0
                                and result["Description"] != new_comments
                            ):
                                set_clause_columns.append("Description=?")
                                update_values.append(new_comments)
                            else:
                                debug("Description not changed - not updating.")

                        if options.publisher and result["Publisher"] != newmi.publisher:
                            set_clause_columns.append("Publisher=?")
                            update_values.append(newmi.publisher)

                        if options.published_date:
                            pubdate_string = strftime(
                                self.device_timestamp_string, newmi.pubdate
                            )
                            if result["DateCreated"] != pubdate_string:
                                set_clause_columns.append("DateCreated=?")
                                debug(
                                    "convert_kobo_date(result['DateCreated'])=",
                                    convert_kobo_date(result["DateCreated"]),
                                )
                                debug("newmi.pubdate  =", newmi.pubdate)
                                debug(
                                    "result['DateCreated']     =", result["DateCreated"]
                                )
                                debug("pubdate_string=", pubdate_string)
                                debug(
                                    "newmi.pubdate.__class__=", newmi.pubdate.__class__
                                )
                                update_values.append(pubdate_string)

                        if options.isbn and result["ISBN"] != newmi.isbn:
                            set_clause_columns.append("ISBN=?")
                            update_values.append(newmi.isbn)

                        if options.language and result["Language"] != lang_as_iso639_1(
                            newmi.language
                        ):
                            debug("newmi.language =", newmi.language)
                            debug(
                                "lang_as_iso639_1(newmi.language)=",
                                lang_as_iso639_1(newmi.language),
                            )
                            debug(
                                "canonicalize_lang(newmi.language)=",
                                canonicalize_lang(newmi.language),
                            )

                        debug("options.rating= ", options.rating)
                        if options.rating:
                            rating_column = self.get_column_names().rating

                            if rating_column:
                                if rating_column == "rating":
                                    rating = newmi.rating
                                else:
                                    metadata = newmi.get_user_metadata(
                                        rating_column, True
                                    )
                                    assert metadata is not None
                                    rating = metadata["#value#"]
                                debug(
                                    "rating=",
                                    rating,
                                    "result[Rating]=",
                                    result["Rating"],
                                )
                                assert isinstance(rating, int)
                                rating = (
                                    None if not rating or rating == 0 else rating / 2
                                )
                                debug(
                                    "rating=",
                                    rating,
                                    "result[Rating]=",
                                    result["Rating"],
                                )
                                rating_values.append(rating)
                                rating_values.append(
                                    strftime(
                                        self.device_timestamp_string, time.gmtime()
                                    )
                                )
                                rating_values.append(contentID)
                                if rating != result["Rating"]:
                                    if not rating:
                                        rating_change_query = rating_delete
                                        rating_values = (contentID,)
                                    elif (
                                        result["DateModified"] is None
                                    ):  # If the date modified column does not have a value, there is no rating column
                                        rating_change_query = rating_insert
                                    else:
                                        rating_change_query = rating_update

                        debug("options.series=", options.series)
                        if self.device.supports_series and options.series:
                            debug(
                                "newmi.series= ='%s' newmi.series_index='%s' newmi.series_index_string='%s'"
                                % (
                                    newmi.series,
                                    newmi.series_index,
                                    newmi.series_index_string,
                                )
                            )
                            debug(
                                "result['Series'] ='%s' result['SeriesNumber'] =%s"
                                % (result["Series"], result["SeriesNumber"])
                            )
                            debug(
                                "result['SeriesID'] ='%s' result['SeriesNumberFloat'] =%s"
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

                            series_changed = new_series != result["Series"]
                            series_number_changed = (
                                new_series_number != result["SeriesNumber"]
                            )
                            debug('new_series="%s"' % (new_series,))
                            debug('new_series_number="%s"' % (new_series_number,))
                            debug(
                                'series_number_changed="%s"' % (series_number_changed,)
                            )
                            debug('series_changed="%s"' % (series_changed,))
                            if series_changed or series_number_changed:
                                debug("setting series")
                                set_clause_columns.append("Series=?")
                                update_values.append(new_series)
                                set_clause_columns.append("SeriesNumber=?")
                                update_values.append(new_series_number)
                            debug(
                                "self.device.supports_series_list='%s'"
                                % self.device.supports_series_list
                            )
                            if self.device.supports_series_list:
                                debug("supports_series_list")
                                series_id = kobo_series_dict.get(
                                    newmi.series, newmi.series
                                )
                                debug("series_id='%s'" % series_id)
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
                                    debug("setting SeriesID")
                                    set_clause_columns.append("SeriesID=?")
                                    set_clause_columns.append("SeriesNumberFloat=?")
                                    if series_id is None or series_id == "":
                                        update_values.append(None)
                                        update_values.append(None)
                                    else:
                                        update_values.append(series_id)
                                        update_values.append(newmi.series_index)

                        if options.subtitle:
                            debug(
                                "setting subtitle - column name =",
                                options.subtitleTemplate,
                            )
                            subtitle_template = options.subtitleTemplate
                            if subtitle_template == cfg.TOKEN_CLEAR_SUBTITLE:
                                new_subtitle = None
                            elif subtitle_template and subtitle_template[0] == "#":
                                metadata = newmi.get_user_metadata(
                                    subtitle_template, True
                                )
                                assert metadata is not None
                                new_subtitle = metadata["#value#"]
                            else:
                                pb = [
                                    (
                                        subtitle_template,
                                        "subtitle",
                                    )
                                ]
                                book.template_to_attribute(book, pb)
                                debug("after - mi.subtitle=", book.subtitle)
                                assert book.subtitle is not None
                                new_subtitle = (
                                    book.subtitle if len(book.subtitle) > 0 else None
                                )
                                if new_subtitle and subtitle_template == new_subtitle:
                                    new_subtitle = None
                                debug(
                                    'setting subtitle - subtitle ="%s"' % new_subtitle
                                )
                                debug(
                                    'setting subtitle - result["Subtitle"] = "%s"'
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
                            ) or (new_subtitle and result["Subtitle"] != new_subtitle):
                                update_values.append(new_subtitle)
                                set_clause_columns.append("Subtitle=?")

                        debug(
                            "options.set_reading_direction",
                            options.set_reading_direction,
                        )
                        debug("options.reading_direction", options.reading_direction)
                        if options.set_reading_direction and (
                            result["PageProgressDirection"] != options.reading_direction
                        ):
                            set_clause_columns.append("PageProgressDirection=?")
                            update_values.append(options.reading_direction)

                        debug("options.set_sync_date", options.set_sync_date)
                        debug(
                            "options.sync_date_library_date",
                            options.sync_date_library_date,
                        )
                        new_timestamp = None
                        if options.set_sync_date:
                            if options.sync_date_library_date == "timestamp":
                                new_timestamp = newmi.timestamp
                            elif options.sync_date_library_date == "last_modified":
                                new_timestamp = newmi.last_modified
                            elif options.sync_date_library_date == "pubdate":
                                new_timestamp = newmi.pubdate
                            elif options.sync_date_library_date[0] == "#":
                                metadata = newmi.get_user_metadata(
                                    options.sync_date_library_date, True
                                )
                                assert metadata is not None
                                new_timestamp = metadata["#value#"]
                            elif (
                                options.sync_date_library_date
                                == cfg.TOKEN_FILE_TIMESTAMP
                            ):
                                debug("Using book file timestamp for Date Added sort.")
                                debug("book=", book)
                                device_book_path = self.get_device_path_from_contentID(
                                    contentID, result["MimeType"]
                                )
                                debug("device_book_path=", device_book_path)
                                new_timestamp = dt.datetime.fromtimestamp(
                                    os.path.getmtime(device_book_path),
                                    tz=dt.timezone.utc,
                                )
                                debug("new_timestamp=", new_timestamp)

                            if new_timestamp is not None:
                                synctime_string = strftime(
                                    self.device_timestamp_string, new_timestamp
                                )
                                if result["___SyncTime"] != synctime_string:
                                    set_clause_columns.append("___SyncTime=?")
                                    debug(
                                        "convert_kobo_date(result['___SyncTime'])=",
                                        convert_kobo_date(result["___SyncTime"]),
                                    )
                                    debug(
                                        "convert_kobo_date(result['___SyncTime']).__class__=",
                                        convert_kobo_date(
                                            result["___SyncTime"]
                                        ).__class__,
                                    )
                                    debug("new_timestamp  =", new_timestamp)
                                    debug(
                                        "result['___SyncTime']     =",
                                        result["___SyncTime"],
                                    )
                                    debug("synctime_string=", synctime_string)
                                    update_values.append(synctime_string)

                        if options.setRreadingStatus and (
                            result["ReadStatus"] != options.readingStatus
                            or options.resetPosition
                        ):
                            set_clause_columns.append("ReadStatus=?")
                            update_values.append(options.readingStatus)
                            if options.resetPosition:
                                set_clause_columns.append("DateLastRead=?")
                                update_values.append(None)
                                set_clause_columns.append("ChapterIDBookmarked=?")
                                update_values.append(None)
                                set_clause_columns.append("___PercentRead=?")
                                update_values.append(0)
                                set_clause_columns.append("FirstTimeReading=?")
                                update_values.append(options.readingStatus < 2)

                        if len(set_clause_columns) > 0:
                            update_query += ",".join(set_clause_columns)
                            changes_found = True

                        if not (changes_found or rating_change_query):
                            debug(
                                "no changes found to selected metadata. No changes being made."
                            )
                            unchanged_books += 1
                            continue

                        update_query += " WHERE ContentID = ? AND BookID IS NULL"
                        update_values.append(contentID)
                        debug("update_query=%s" % update_query)
                        debug("update_values= ", update_values)
                        try:
                            if changes_found:
                                cursor.execute(update_query, update_values)

                            if rating_change_query:
                                debug("rating_change_query=%s" % rating_change_query)
                                debug("rating_values= ", rating_values)
                                cursor.execute(rating_change_query, rating_values)

                            updated_books += 1
                        except:
                            debug("    Database Exception:  Unable to set series info")
                            raise
                    else:
                        debug(
                            "no match for title='%s' contentId='%s'"
                            % (book.title, contentID)
                        )
                        not_on_device_books += 1
        debug(
            "Update summary: Books updated=%d, unchanged books=%d, not on device=%d, Total=%d"
            % (updated_books, unchanged_books, not_on_device_books, count_books)
        )

        progressbar.hide()

        return (updated_books, unchanged_books, not_on_device_books, count_books)

    def _render_synopsis(self, mi: Metadata, book: Book, template: str | None = None):
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

        debug('start - book.comments="%s"' % book.comments)

        if not template:
            try:
                data = P("kobo_template.xhtml", data=True)
                assert isinstance(data, bytes), f"data is of type {type(data)}"
                template = data.decode("utf-8")
            except Exception:
                template = ""
        debug("template=", template)

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
            debug("using jacket style template.")

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
            debug("tags=", tags)

            comments = mi.comments.strip() if mi.comments else ""
            if comments:
                comments = comments_to_html(comments)
            debug("comments=", comments)
            try:
                author = mi.format_authors()
            except Exception:
                author = ""
            author = escape(author)
            publisher = cast("str", mi.publisher) if mi.publisher else ""
            publisher = escape(publisher)
            title_str = mi.title if mi.title else _("Unknown")
            title_str = escape(title_str)
            series = Series(mi.series, mi.series_index)

            try:
                if is_date_undefined(mi.pubdate):
                    pubdate = ""
                else:
                    pubdate = strftime("%Y", cast("dt.date", mi.pubdate).timetuple())
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
                    debug("key=%s, display_name=%s, val=%s" % (key, display_name, val))
                    key = key.replace("#", "_")
                    args[key + "_label"] = escape(display_name)
                    debug("display_name arg=", (args[key + "_label"]))
                    args[key] = escape(val)
                except Exception:  # noqa: PERF203, S110
                    # if the val (custom column contents) is None, don't add to args
                    pass

            if DEBUG:
                debug("Custom column values available in jacket template:")
                for key in list(args.keys()):
                    if key.startswith("_") and not key.endswith("_label"):
                        debug(" %s: %s" % ("#" + key[1:], args[key]))

            # Used in the comment describing use of custom columns in templates
            # Don't change this unless you also change it in template.xhtml
            args["_genre_label"] = args.get("_genre_label", "{_genre_label}")
            args["_genre"] = args.get("_genre", "{_genre}")

            formatter = SafeFormatter()
            rendered_comments = formatter.format(template, **args)
            debug("generated_html=", rendered_comments)

        else:
            pb = [(template, "comments")]
            debug("before - mi.comments=", mi.comments)
            debug("book.comments=", book.comments)
            debug("pb=", pb)
            mi.template_to_attribute(book, pb)
            debug("after - mi.comments=", mi.comments)
            rendered_comments = mi.comments

        return rendered_comments

    def _store_current_bookmark(
        self, books: list[Book], options: cfg.ReadLocationsJobOptions
    ):
        assert self.device is not None

        reading_locations_updated = 0
        books_without_reading_locations = 0
        count_books = 0

        def value_changed(old_value: object | None, new_value: object | None):
            return (
                (old_value is not None and new_value is None)
                or (old_value is None and new_value is not None)
                or old_value != new_value
            )

        debug("profile_name=", options.profile_name)
        clear_if_unread = options.bookmark_options.clearIfUnread
        store_if_more_recent = options.bookmark_options.storeIfMoreRecent
        do_not_store_if_reopened = options.bookmark_options.doNotStoreIfReopened

        connection = self.device_database_connection(use_row_factory=True)
        progressbar = ProgressBar(
            parent=self.gui, window_title=_("Storing reading positions"), on_top=True
        )
        progressbar.show_with_maximum(len(books))

        library_db = self.gui.current_db
        custom_columns = self.get_column_names(options.profile_name)
        kobo_chapteridbookmarked_column_name = custom_columns.current_location
        kobo_percentRead_column_name = custom_columns.percent_read
        rating_column_name = custom_columns.rating
        last_read_column_name = custom_columns.last_read
        time_spent_reading_column_name = custom_columns.time_spent_reading
        rest_of_book_estimate_column_name = custom_columns.rest_of_book_estimate

        debug(
            "kobo_chapteridbookmarked_column_name=",
            kobo_chapteridbookmarked_column_name,
        )
        debug("kobo_percentRead_column_name=", kobo_percentRead_column_name)
        debug("rating_column_name=", rating_column_name)
        debug("last_read_column_name=", last_read_column_name)
        debug("time_spent_reading_column_name=", time_spent_reading_column_name)
        debug("rest_of_book_estimate_column_name=", rest_of_book_estimate_column_name)

        rating_col_label = None
        if rating_column_name is not None:
            if rating_column_name != "rating":
                rating_col_label = (
                    library_db.field_metadata.key_to_label(rating_column_name)
                    if rating_column_name
                    else ""
                )
            debug("rating_col_label=", rating_col_label)

        id_map = {}
        id_map_percentRead = {}
        id_map_chapteridbookmarked = {}
        id_map_rating = {}
        id_map_last_read = {}
        id_map_time_spent_reading = {}
        id_map_rest_of_book_estimate = {}

        debug("Starting to look at selected books...")
        cursor = connection.cursor()
        for book in books:
            count_books += 1
            mi = Metadata("Unknown")
            debug("Looking at book: %s" % book.title)
            progressbar.set_label(_("Checking {}").format(book.title))
            progressbar.increment()
            book_updated = False

            if len(cast("List[str]", book.contentIDs)) == 0:
                books_without_reading_locations += 1
                continue

            for contentID in cast("List[str]", book.contentIDs):
                debug("contentId='%s'" % (contentID))
                fetch_values = (contentID,)
                assert self.device_fwversion is not None
                fetch_queries = self._get_fetch_query_for_firmware_version(
                    self.device_fwversion
                )
                assert fetch_queries is not None
                if contentID.endswith(".kepub.epub"):
                    fetch_query = fetch_queries.kepub
                else:
                    fetch_query = fetch_queries.epub
                debug("fetch_query='%s'" % (fetch_query))
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
                    debug("result=", result)
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
                            debug("result['DateLastRead']=", result["DateLastRead"])
                            last_read = convert_kobo_date(result["DateLastRead"])
                            debug("last_read=", last_read)

                        if last_read_column_name is not None and store_if_more_recent:
                            metadata = book.get_user_metadata(
                                last_read_column_name, True
                            )
                            assert metadata is not None
                            current_last_read = metadata["#value#"]
                            debug(
                                "book.get_user_metadata(last_read_column_name, True)['#value#']=",
                                current_last_read,
                            )
                            debug("setting mi.last_read=", last_read)
                            if current_last_read is not None and last_read is not None:
                                debug(
                                    "store_if_more_recent - current_last_read < last_read=",
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
                            metadata = book.get_user_metadata(
                                kobo_percentRead_column_name, True
                            )
                            assert metadata is not None
                            current_percentRead = metadata["#value#"]
                            debug(
                                "do_not_store_if_reopened - current_percentRead=",
                                current_percentRead,
                            )
                            if (
                                current_percentRead is not None
                                and current_percentRead >= 100
                            ):
                                continue

                        if (
                            result["MimeType"] == MIMETYPE_KOBO
                            or self.device.epub_location_like_kepub
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

                        kobo_rating = result["Rating"] * 2 if result["Rating"] else 0

                        time_spent_reading = result.get("TimeSpentReading")
                        rest_of_book_estimate = result.get("RestOfBookEstimate")

                else:
                    books_without_reading_locations += 1
                    continue

                debug("kobo_chapteridbookmarked='%s'" % (kobo_chapteridbookmarked))
                debug("kobo_adobe_location='%s'" % (kobo_adobe_location))
                debug("kobo_percentRead=", kobo_percentRead)
                debug("time_spent_reading='%s'" % (time_spent_reading))
                debug("rest_of_book_estimate='%s'" % (rest_of_book_estimate))

                if last_read_column_name is not None:
                    metadata = book.get_user_metadata(last_read_column_name, True)
                    assert metadata is not None
                    current_last_read = metadata["#value#"]
                    debug(
                        "book.get_user_metadata(last_read_column_name, True)['#value#']=",
                        current_last_read,
                    )
                    debug("setting mi.last_read=", last_read)
                    debug(
                        "current_last_read == last_read=",
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
                        debug("setting bookmark column to None")
                    debug("chapterIdBookmark - on kobo=", new_value)
                    metadata = book.get_user_metadata(
                        kobo_chapteridbookmarked_column_name, True
                    )
                    assert metadata is not None
                    old_value = metadata["#value#"]
                    debug("chapterIdBookmark - in library=", old_value)
                    debug(
                        "chapterIdBookmark - on kobo==in library=",
                        new_value == old_value,
                    )

                    if value_changed(old_value, new_value):
                        id_map_chapteridbookmarked[book.calibre_id] = new_value
                        book_updated = True
                    else:
                        book_updated = book_updated or False

                if kobo_percentRead_column_name is not None:
                    debug("setting kobo_percentRead=", kobo_percentRead)
                    metadata = book.get_user_metadata(
                        kobo_percentRead_column_name, True
                    )
                    assert metadata is not None
                    current_percentRead = metadata["#value#"]
                    debug("percent read - in book=", current_percentRead)

                    if value_changed(current_percentRead, kobo_percentRead):
                        id_map_percentRead[book.calibre_id] = kobo_percentRead
                        book_updated = True
                    else:
                        book_updated = book_updated or False

                if rating_column_name is not None and kobo_rating > 0:
                    debug("setting rating_column_name=", rating_column_name)
                    if rating_column_name == "rating":
                        current_rating = book.rating
                        debug("rating - in book=", current_rating)
                        if current_rating != kobo_rating:
                            library_db.set_rating(
                                book.calibre_id, kobo_rating, commit=False
                            )
                    else:
                        metadata = book.get_user_metadata(rating_column_name, True)
                        assert metadata is not None
                        current_rating = metadata["#value#"]
                        if current_rating != kobo_rating:
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
                    debug("setting time_spent_reading=", time_spent_reading)
                    metadata = book.get_user_metadata(
                        time_spent_reading_column_name, True
                    )
                    assert metadata is not None
                    current_time_spent_reading = metadata["#value#"]
                    debug("time spent reading - in book=", current_time_spent_reading)

                    if value_changed(current_time_spent_reading, time_spent_reading):
                        id_map_time_spent_reading[book.calibre_id] = time_spent_reading
                        book_updated = True
                    else:
                        book_updated = book_updated or False

                if rest_of_book_estimate_column_name is not None:
                    debug("setting rest_of_book_estimate=", rest_of_book_estimate)
                    metadata = book.get_user_metadata(
                        time_spent_reading_column_name, True
                    )
                    assert metadata is not None
                    current_rest_of_book_estimate = metadata["#value#"]
                    debug(
                        "rest of book estimate - in book=",
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

        debug("Updating GUI - new DB engine")
        if kobo_chapteridbookmarked_column_name and len(id_map_chapteridbookmarked) > 0:
            debug(
                "Updating metadata - for column: %s number of changes=%d"
                % (
                    kobo_chapteridbookmarked_column_name,
                    len(id_map_chapteridbookmarked),
                )
            )
            library_db.new_api.set_field(
                kobo_chapteridbookmarked_column_name, id_map_chapteridbookmarked
            )
        if kobo_percentRead_column_name and len(id_map_percentRead) > 0:
            debug(
                "Updating metadata - for column: %s number of changes=%d"
                % (kobo_percentRead_column_name, len(id_map_percentRead))
            )
            library_db.new_api.set_field(
                kobo_percentRead_column_name, id_map_percentRead
            )
        if rating_column_name and len(id_map_rating) > 0:
            debug(
                "Updating metadata - for column: %s number of changes=%d"
                % (rating_column_name, len(id_map_rating))
            )
            library_db.new_api.set_field(rating_column_name, id_map_rating)
        if last_read_column_name and len(id_map_last_read) > 0:
            debug(
                "Updating metadata - for column: %s number of changes=%d"
                % (last_read_column_name, len(id_map_last_read))
            )
            library_db.new_api.set_field(last_read_column_name, id_map_last_read)
        if time_spent_reading_column_name and len(id_map_time_spent_reading) > 0:
            debug(
                "Updating metadata - for column: %s number of changes=%d"
                % (time_spent_reading_column_name, len(id_map_time_spent_reading))
            )
            library_db.new_api.set_field(
                time_spent_reading_column_name, id_map_time_spent_reading
            )
        if rest_of_book_estimate_column_name and len(id_map_rest_of_book_estimate) > 0:
            debug(
                "Updating metadata - for column: %s number of changes=%d"
                % (
                    rest_of_book_estimate_column_name,
                    len(id_map_rest_of_book_estimate),
                )
            )
            library_db.new_api.set_field(
                rest_of_book_estimate_column_name, id_map_rest_of_book_estimate
            )
        self.gui.iactions["Edit Metadata"].refresh_gui(list(id_map))

        progressbar.hide()
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

        debug("finished")

        return (reading_locations_updated, books_without_reading_locations, count_books)

    def _restore_current_bookmark(
        self,
        books: list[Book],
        options: cfg.BookmarkOptionsConfig,
        profile_name: str | None,
    ):
        assert self.device is not None
        updated_books = 0
        not_on_device_books = 0
        count_books = 0

        custom_columns = self.get_column_names(profile_name)
        kobo_chapteridbookmarked_column = custom_columns.current_location
        kobo_percentRead_column = custom_columns.percent_read
        rating_column = custom_columns.rating
        last_read_column = custom_columns.last_read
        time_spent_reading_column = custom_columns.time_spent_reading
        rest_of_book_estimate_column = custom_columns.rest_of_book_estimate
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
        debug("chapter_query= ", chapter_query)

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

        with self.device_database_connection(use_row_factory=True) as connection:
            cursor = connection.cursor()
            for book in books:
                count_books += 1
                for contentID in cast("List[str]", book.contentIDs):
                    chapter_values = (contentID,)
                    cursor.execute(chapter_query, chapter_values)
                    try:
                        result = next(cursor)
                    except StopIteration:
                        result = None

                    if result is not None:
                        debug("result= ", result)
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
                            metadata = book.get_user_metadata(
                                kobo_chapteridbookmarked_column, True
                            )
                            assert metadata is not None
                            reading_location_string = metadata["#value#"]
                            debug("reading_location_string=", reading_location_string)
                            if reading_location_string is not None:
                                if result["MimeType"] == MIMETYPE_KOBO:
                                    kobo_chapteridbookmarked = reading_location_string
                                    kobo_adobe_location = None
                                else:
                                    reading_location_parts = (
                                        reading_location_string.split(
                                            BOOKMARK_SEPARATOR
                                        )
                                    )
                                    debug(
                                        "reading_location_parts=",
                                        reading_location_parts,
                                    )
                                    debug(
                                        "self.device.epub_location_like_kepub=",
                                        self.device.epub_location_like_kepub,
                                    )
                                    if self.device.epub_location_like_kepub:
                                        kobo_chapteridbookmarked = (
                                            reading_location_parts[1]
                                            if len(reading_location_parts) == 2
                                            else reading_location_string
                                        )
                                        kobo_adobe_location = None
                                    else:
                                        if len(reading_location_parts) == 2:
                                            kobo_chapteridbookmarked = (
                                                contentID
                                                + "#"
                                                + reading_location_parts[0]
                                            )
                                            kobo_adobe_location = (
                                                reading_location_parts[1]
                                            )
                                        else:
                                            cursor.execute(
                                                volume_zero_query, [contentID]
                                            )
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
                                debug(
                                    "reading_location_string=", reading_location_string
                                )

                        if kobo_percentRead_column:
                            metadata = book.get_user_metadata(
                                kobo_percentRead_column, True
                            )
                            assert metadata is not None
                            kobo_percentRead = metadata["#value#"]
                            kobo_percentRead = (
                                kobo_percentRead
                                if kobo_percentRead
                                else result["___PercentRead"]
                            )
                            chapter_values.append(kobo_percentRead)
                            chapter_set_clause += ", ___PercentRead  = ? "

                        if options.readingStatus and kobo_percentRead:
                            debug("chapter_values= ", chapter_values)
                            if kobo_percentRead == 100:
                                chapter_values.append(2)
                                debug("chapter_values= ", chapter_values)
                            else:
                                chapter_values.append(1)
                                debug("chapter_values= ", chapter_values)
                            chapter_set_clause += ", ReadStatus  = ? "
                            chapter_values.append("false")
                            chapter_set_clause += ", FirstTimeReading = ? "

                        last_read = None
                        if options.setDateToNow:
                            last_read = strftime(
                                self.device_timestamp_string, time.gmtime()
                            )
                            debug("setting to now - last_read= ", last_read)
                        elif last_read_column:
                            metadata = book.get_user_metadata(last_read_column, True)
                            assert metadata is not None
                            last_read = metadata["#value#"]
                            if last_read is not None:
                                last_read = last_read.strftime(
                                    self.device_timestamp_string
                                )
                            debug("setting from library - last_read= ", last_read)
                        debug("last_read= ", last_read)
                        debug("result['___SyncTime']= ", result["___SyncTime"])
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
                                debug("setting ___SyncTime to same as DateLastRead")
                                chapter_values.append(last_read)
                                chapter_set_clause += ", ___SyncTime  = ? "

                        debug("options.rating= ", options.rating)
                        rating = None
                        if rating_column is not None and options.rating:
                            if rating_column == "rating":
                                rating = book.rating
                            else:
                                metadata = book.get_user_metadata(rating_column, True)
                                assert metadata is not None
                                rating = metadata["#value#"]
                            assert isinstance(rating, int)
                            rating = None if not rating or rating == 0 else rating / 2
                            debug(
                                "rating=",
                                rating,
                                " result['Rating']=",
                                result["Rating"],
                            )
                            rating_values.append(rating)
                            if last_read is not None:
                                rating_values.append(last_read)
                            else:
                                rating_values.append(
                                    strftime(
                                        self.device_timestamp_string, time.gmtime()
                                    )
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
                            metadata = book.get_user_metadata(
                                time_spent_reading_column, True
                            )
                            assert metadata is not None
                            kobo_time_spent_reading = metadata["#value#"]
                            kobo_time_spent_reading = (
                                kobo_time_spent_reading
                                if kobo_time_spent_reading is not None
                                else 0
                            )
                            chapter_values.append(kobo_time_spent_reading)
                            chapter_set_clause += ", TimeSpentReading = ? "

                        if rest_of_book_estimate_column:
                            metadata = book.get_user_metadata(
                                rest_of_book_estimate_column, True
                            )
                            assert metadata is not None
                            kobo_rest_of_book_estimate = metadata["#value#"]
                            kobo_rest_of_book_estimate = (
                                kobo_rest_of_book_estimate
                                if kobo_rest_of_book_estimate is not None
                                else 0
                            )
                            chapter_values.append(kobo_rest_of_book_estimate)
                            chapter_set_clause += ", RestOfBookEstimate = ? "

                        debug("found contentId='%s'" % (contentID))
                        debug("kobo_chapteridbookmarked=", kobo_chapteridbookmarked)
                        debug("kobo_adobe_location=", kobo_adobe_location)
                        debug("kobo_percentRead=", kobo_percentRead)
                        debug("rating=", rating)
                        debug("last_read=", last_read)
                        debug("kobo_time_spent_reading=", kobo_time_spent_reading)
                        debug("kobo_rest_of_book_estimate=", kobo_rest_of_book_estimate)

                        if len(chapter_set_clause) > 0:
                            chapter_update += chapter_set_clause[1:]
                            chapter_update += "WHERE ContentID = ? AND BookID IS NULL"
                            chapter_values.append(contentID)
                        else:
                            debug(
                                "no changes found to selected metadata. No changes being made."
                            )
                            not_on_device_books += 1
                            continue

                        debug("chapter_update=%s" % chapter_update)
                        debug("chapter_values= ", chapter_values)
                        try:
                            cursor.execute(chapter_update, chapter_values)
                            if len(location_set_clause) > 0 and not (
                                result["MimeType"] == MIMETYPE_KOBO
                                or self.device.epub_location_like_kepub
                            ):
                                location_update += location_set_clause[1:]
                                location_update += (
                                    " WHERE ContentID = ? AND BookID IS NOT NULL"
                                )
                                location_values.append(kobo_chapteridbookmarked)
                                debug("location_update=%s" % location_update)
                                debug("location_values= ", location_values)
                                cursor.execute(location_update, location_values)
                            if rating_change_query:
                                debug("rating_change_query=%s" % rating_change_query)
                                debug("rating_values= ", rating_values)
                                cursor.execute(rating_change_query, rating_values)

                            updated_books += 1
                        except:
                            debug(
                                "    Database Exception:  Unable to set bookmark info."
                            )
                            raise
                    else:
                        debug(
                            "no match for title='%s' contentId='%s'"
                            % (book.title, book.contentID)
                        )
                        not_on_device_books += 1
        debug(
            "Update summary: Books updated=%d, not on device=%d, Total=%d"
            % (updated_books, not_on_device_books, count_books)
        )

        return (updated_books, not_on_device_books, count_books)

    def _get_shelves_from_device(
        self,
        books: list[Book],
        options: cfg.GetShelvesOptionStoreConfig,
        progressbar: ProgressBar,
    ):
        count_books = 0
        books_with_shelves = 0
        books_without_shelves = 0
        replace_shelves = options.replaceShelves

        total_books = len(books)
        progressbar.show_with_maximum(total_books)

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
        bookshelf_column_name = library_config.shelvesColumn
        debug("bookshelf_column_name=", bookshelf_column_name)
        bookshelf_column = library_db.field_metadata[bookshelf_column_name]
        bookshelf_column_label = library_db.field_metadata.key_to_label(
            bookshelf_column_name
        )
        bookshelf_column_is_multiple = (
            bookshelf_column["is_multiple"] is not None
            and len(bookshelf_column["is_multiple"]) > 0
        )
        debug("bookshelf_column_label=", bookshelf_column_label)
        debug("bookshelf_column_is_multiple=", bookshelf_column_is_multiple)

        cursor = connection.cursor()
        for book in books:
            progressbar.set_label(_("Getting collections for {}").format(book.title))
            progressbar.increment()
            count_books += 1
            shelf_names = []
            update_library = False
            for contentID in cast("List[str]", book.contentIDs):
                debug("title='%s' contentId='%s'" % (book.title, contentID))
                fetch_values = (contentID,)
                debug("tetch_query='%s'" % (fetch_query))
                cursor.execute(fetch_query, fetch_values)

                for row in cursor:
                    debug("result=", row)
                    shelf_names.append(row[1])
                    update_library = True

            if len(shelf_names) > 0:
                books_with_shelves += 1
            else:
                books_without_shelves += 1
                continue

            if update_library and len(shelf_names) > 0:
                debug("device shelf_names='%s'" % (shelf_names))
                debug("device set(shelf_names)='%s'" % (set(shelf_names)))
                metadata = book.get_user_metadata(bookshelf_column_name, True)
                assert metadata is not None
                old_value = metadata["#value#"]
                debug("library shelf names='%s'" % (old_value))
                if old_value is None or set(old_value) != set(shelf_names):
                    debug("shelves are not the same")
                    shelf_names = (
                        list(set(shelf_names))
                        if bookshelf_column_is_multiple
                        else ", ".join(shelf_names)
                    )
                    debug("device shelf_names='%s'" % (shelf_names))
                    if replace_shelves or old_value is None:
                        new_value = shelf_names
                    elif bookshelf_column_is_multiple:
                        new_value = old_value + shelf_names
                    else:
                        new_value = old_value + ", " + shelf_names
                    debug("new shelf names='%s'" % (new_value))
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
        progressbar.hide()

        return (books_with_shelves, books_without_shelves, count_books)

    def fetch_book_fonts(self, contentID: str) -> cfg.ReadingOptionsConfig | None:
        debug("start")
        connection = self.device_database_connection()
        book_options = cfg.ReadingOptionsConfig()

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
            contentID,
        )

        cursor = connection.cursor()
        cursor.execute(fetch_query, fetch_values)
        try:
            result = next(cursor)
        except StopIteration:
            return None

        book_options.readingFontFamily = result[0]
        book_options.readingFontSize = result[1]
        book_options.readingAlignment = result[2].title() if result[2] else "Off"
        book_options.readingLineHeight = result[3]
        book_options.readingLeftMargin = result[4]
        book_options.readingRightMargin = result[5]

        return book_options

    @property
    def device_timestamp_string(self):
        if not self.timestamp_string:
            if (
                self.device is not None
                and isinstance(self.device.driver, KOBOTOUCH)
                and "TIMESTAMP_STRING" in dir(self.device)
            ):
                self.timestamp_string = self.device.driver.TIMESTAMP_STRING
            else:
                self.timestamp_string = "%Y-%m-%dT%H:%M:%SZ"
        return self.timestamp_string

    def _set_reader_fonts(
        self,
        contentIDs: list[str],
        options: cfg.ReadingOptionsConfig,
        delete: bool = False,
    ):
        debug("start")
        updated_fonts = 0
        added_fonts = 0
        deleted_fonts = 0
        count_books = 0

        debug("connected to device database")

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
            font_face = options.readingFontFamily
            justification = options.readingAlignment.lower()
            justification = (
                None if justification == "Off" or justification == "" else justification
            )
            font_size = options.readingFontSize
            line_spacing = options.readingLineHeight
            left_margins = options.readingLeftMargin
            right_margins = options.readingRightMargin

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

        with self.device_database_connection() as connection:
            cursor = connection.cursor()
            for contentID in contentIDs:
                test_values = (
                    self.CONTENTTYPE,
                    contentID,
                )
                if delete:
                    cursor.execute(delete_query, test_values)
                    deleted_fonts += 1
                elif update_query is not None and add_query is not None:
                    cursor.execute(test_query, test_values)
                    try:
                        result = next(cursor)
                        debug("found existing row:", result)
                        if not options.doNotUpdateIfSet:
                            cursor.execute(update_query, (*update_values, contentID))
                            updated_fonts += 1
                    except StopIteration:
                        cursor.execute(add_query, (*add_values, contentID))
                        added_fonts += 1
                count_books += 1

        return updated_fonts, added_fonts, deleted_fonts, count_books

    def get_config_file(self) -> tuple[ConfigParser, str]:
        assert self.device is not None
        assert self.device.driver._main_prefix is not None
        config_file_path = self.device.driver.normalize_path(
            self.device.driver._main_prefix + ".kobo/Kobo/Kobo eReader.conf"
        )
        assert config_file_path is not None
        koboConfig = ConfigParser(allow_no_value=True)
        koboConfig.optionxform = str  # type: ignore[reportAttributeAccessIssue]
        debug("config_file_path=", config_file_path)
        try:
            koboConfig.read(config_file_path)
        except Exception as e:
            debug("exception=", e)
            raise

        return koboConfig, config_file_path

    def _update_config_reader_settings(self, options: cfg.ReadingOptionsConfig):
        config_section_reading = "Reading"

        koboConfig, config_file_path = self.get_config_file()

        if not koboConfig.has_section(config_section_reading):
            koboConfig.add_section(config_section_reading)

        koboConfig.set(
            config_section_reading,
            cfg.KEY_READING_FONT_FAMILY,
            options.readingFontFamily,
        )
        koboConfig.set(
            config_section_reading, cfg.KEY_READING_ALIGNMENT, options.readingAlignment
        )
        koboConfig.set(
            config_section_reading,
            cfg.KEY_READING_FONT_SIZE,
            "%g" % options.readingFontSize,
        )
        koboConfig.set(
            config_section_reading,
            cfg.KEY_READING_LINE_HEIGHT,
            "%g" % options.readingLineHeight,
        )
        koboConfig.set(
            config_section_reading,
            cfg.KEY_READING_LEFT_MARGIN,
            "%g" % options.readingLeftMargin,
        )
        koboConfig.set(
            config_section_reading,
            cfg.KEY_READING_RIGHT_MARGIN,
            "%g" % options.readingRightMargin,
        )

        with open(config_file_path, "w") as config_file:
            koboConfig.write(config_file)

    def _backup_annotation_files(self, books: list[Book], dest_path: str):
        annotations_found = 0
        kepubs = 0
        no_annotations = 0
        count_books = 0

        device = self.device
        assert device is not None

        debug("self.device.path='%s'" % (device.path))
        kepub_dir = cast("str", device.driver.normalize_path(".kobo/kepub/"))
        annotations_dir = cast(
            "str",
            device.driver.normalize_path(device.path + "Digital Editions/Annotations/"),
        )
        annotations_ext = ".annot"

        for book in books:
            count_books += 1

            for book_path in cast("List[str]", book.paths):
                relative_path = book_path.replace(device.path, "")
                annotation_file = device.driver.normalize_path(
                    annotations_dir + relative_path + annotations_ext
                )
                assert annotation_file is not None
                debug(
                    "kepub title='%s' annotation_file='%s'"
                    % (book.title, annotation_file)
                )
                if relative_path.startswith(kepub_dir):
                    debug("kepub title='%s' book_path='%s'" % (book.title, book_path))
                    kepubs += 1
                elif os.path.exists(annotation_file):
                    debug("book_path='%s'" % (book_path))
                    backup_file = device.driver.normalize_path(
                        dest_path + "/" + relative_path + annotations_ext
                    )
                    assert backup_file is not None
                    debug("backup_file='%s'" % (backup_file))
                    d, p = os.path.splitdrive(backup_file)
                    debug("d='%s' p='%s'" % (d, p))
                    backup_path = os.path.dirname(str(backup_file))
                    try:
                        os.makedirs(backup_path)
                    except OSError:
                        debug("path exists: backup_path='%s'" % (backup_path))
                    shutil.copyfile(annotation_file, backup_file)
                    annotations_found += 1
                else:
                    debug("book_path='%s'" % (book_path))
                    no_annotations += 1

        debug(
            "Backup summary: annotations_found=%d, no_annotations=%d, kepubs=%d Total=%d"
            % (annotations_found, no_annotations, kepubs, count_books)
        )

        return (annotations_found, no_annotations, kepubs, count_books)

    def _check_device_is_ready(self, function_message: str):
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
        debug("start")

        if not self._check_device_is_ready(
            _("Cannot update the ToC of books on the device")
        ):
            return

        if len(self.gui.library_view.get_selected_ids()) == 0:
            debug("no books selected")
            return

        db: LibraryDatabase = self.gui.current_db

        # Use local versions as just need a few details.
        def _convert_calibre_ids_to_books(db: LibraryDatabase, ids: list[int]):
            return [_convert_calibre_id_to_book(db, book_id) for book_id in ids]

        def _convert_calibre_id_to_book(
            db: LibraryDatabase, book_id: int, get_cover: bool = False
        ):
            mi = db.get_metadata(book_id, index_is_id=True, get_cover=get_cover)
            book: dict[str, Any] = {}
            book["good"] = True
            book["calibre_id"] = mi.id
            book["title"] = mi.title
            book["author"] = authors_to_string(mi.authors)
            book["author_sort"] = mi.author_sort
            book["comment"] = ""
            book["url"] = ""
            book["added"] = False
            return book

        book_ids: list[int] = self.gui.library_view.get_selected_ids()
        books = _convert_calibre_ids_to_books(db, book_ids)
        progressbar = ProgressBar(
            parent=self.gui, window_title=_("Getting ToC status for books"), on_top=True
        )
        progressbar.set_label(_("Number of books: {0}").format(len(books)))
        progressbar.show_with_maximum(len(books))

        self._get_chapter_status(db, books, progressbar)

        progressbar.hide()

        d = UpdateBooksToCDialog(
            self.gui,
            self,
            self.qaction.icon(),
            books,
        )
        d.exec()
        if d.result() != d.DialogCode.Accepted:
            return

        update_books = d.books_to_update_toc
        debug("len(update_books)=%s" % len(update_books))

        debug("update_books=%d" % len(update_books))
        # only if there's some good ones.
        update_books = list(filter(lambda x: not x["good"], update_books))
        debug("filtered update_books=%d" % len(update_books))
        if len(update_books) > 0:
            debug("version=%s" % self.version)

            self.update_device_toc_for_books(update_books)

    def load_ebook(self, pathtoebook: str) -> EpubContainer:
        debug("creating container")
        try:
            container = EpubContainer(pathtoebook, default_log)
        except DRMError:
            container = None
            raise

        return container

    def _read_toc(
        self,
        toc: TOC,
        toc_depth: int = 1,
        format_on_device: str = "EPUB",
        container: EpubContainer | None = None,
    ) -> list[dict[str, Any]]:
        chapters = []
        debug("toc.title=", toc.title)
        debug("toc_depth=", toc_depth)
        debug("parsing ToC")
        for item in toc:
            debug("item.title=", item.title)
            debug("item.depth=", item.depth)
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

        debug("finished")
        return chapters

    def _get_manifest_entries(self, container: EpubContainer) -> list[dict[str, Any]]:
        debug("start")
        manifest_entries = []
        for spine_name, _spine_linear in container.spine_names:
            spine_path = container.name_to_href(spine_name, container.opf_name)
            file_size = container.filesize(spine_name)
            manifest_entries.append(
                {"path": spine_path, "file_size": file_size, "name": spine_name}
            )
        debug("manifest_entries=", manifest_entries)
        return manifest_entries

    def _get_chapter_list(
        self,
        book: dict[str, Any],
        pathtoebook: str,
        book_location: str,
        format_on_device: str = "EPUB",
    ):
        debug("for %s" % book_location)
        from calibre.ebooks.oeb.polish.toc import get_toc

        container = self.load_ebook(pathtoebook)
        debug("container.opf_dir='%s'" % container.opf_dir)
        debug("container.opf_name='%s'" % container.opf_name)
        book[book_location + "_opf_name"] = container.opf_name
        book[book_location + "_opf_dir"] = container.opf_dir
        last_slash_index = book[book_location + "_opf_name"].rfind("/")
        book[book_location + "_opf_dir"] = (
            book[book_location + "_opf_name"][:last_slash_index]
            if last_slash_index >= 0
            else ""
        )
        debug(
            "book[book_location + '_opf_dir']='%s'" % book[book_location + "_opf_dir"]
        )
        toc = get_toc(container)
        debug("toc=", toc)

        book[book_location + "_chapters"] = self._read_toc(
            toc, format_on_device=format_on_device, container=container
        )
        debug("chapters=", book[book_location + "_chapters"])
        book[book_location + "_manifest"] = self._get_manifest_entries(container)
        book[book_location + "_container"] = container
        return

    def _get_chapter_status(
        self, db: LibraryDatabase, books: list[dict[str, Any]], progressbar: ProgressBar
    ):
        debug(f"Starting check of chapter status for {len(books)} books")
        assert self.device is not None
        connection = self.device_database_connection(use_row_factory=True)
        i = 0
        debug(
            "device format_map='{0}".format(
                self.device.driver.settings().format_map  # type: ignore[reportAttributeAccessIssue]
            )
        )
        for book in books:
            progressbar.increment()
            debug(f"Handling book: {book}")
            debug(
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

            debug("Finding book on device...")
            device_book_path = self.get_device_path_from_id(book_id)
            if device_book_path is None:
                book["comment"] = _("eBook is not on Kobo eReader")
                book["good"] = False
                book["icon"] = "window-close.png"
                book["can_update_toc"] = False
                continue
            extension = os.path.splitext(device_book_path)[1]
            ContentType = (
                self.device.driver.get_content_type_from_extension(extension)
                if extension != ""
                else self.device.driver.get_content_type_from_path(device_book_path)
            )
            book["ContentID"] = self.device.driver.contentid_from_path(
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

            debug("Checking for book in library...")
            if db.has_format(book_id, book["kobo_format"], index_is_id=True):
                book["library_format"] = book["kobo_format"]
            elif (
                book["kobo_format"] == "KEPUB"
                and "EPUB".lower() in self.device.driver.settings().format_map  # type: ignore[reportAttributeAccessIssue]
                and db.has_format(book_id, "EPUB", index_is_id=True)
            ):
                book["library_format"] = "EPUB"
            else:
                book["comment"] = _(
                    "No suitable format in library for book. The format of the device is {0}"
                ).format(book["kobo_format"])
                book["good"] = False
                continue

            debug("Getting path to book in library...")
            pathtoebook = db.format_abspath(
                book_id, book["library_format"], index_is_id=True
            )
            assert isinstance(pathtoebook, str)
            debug("Getting chapters from library...")
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

            debug("Getting chapters from book on device...")
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

            debug("Getting chapters from device database...")
            if book["kobo_format"] == "KEPUB":
                book["kobo_database_chapters"] = self._get_database_chapters(
                    connection, book["ContentID"], book["kobo_format"], 899
                )
                debug("book['kobo_database_chapters']=", book["kobo_database_chapters"])
                book["kobo_database_manifest"] = self._get_database_chapters(
                    connection, book["ContentID"], book["kobo_format"], 9
                )
                debug("book['kobo_database_manifest']=", book["kobo_database_manifest"])
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
                    isinstance(self.device.driver, KOBOTOUCH)
                    and (
                        self.device.driver.fwversion
                        < self.device.driver.min_fwversion_epub_location
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
                        debug(
                            "reading_location_volumeIndex =%d, reading_location_file='%s'"
                            % (reading_location_volumeIndex, reading_location_file)
                        )
                        debug(
                            "chapter location='%s'"
                            % (
                                book["kobo_database_chapters"][
                                    reading_location_volumeIndex
                                ]["path"],
                            )
                        )
                    except Exception:
                        debug("exception logging reading location details.")
                    new_toc_readingposition_index = self._get_readingposition_index(
                        book, koboDatabaseReadingLocation
                    )
                    if new_toc_readingposition_index is not None:
                        try:
                            real_path, chapter_position = book[
                                "kobo_database_chapters"
                            ][reading_location_volumeIndex]["path"].split("#")
                            debug("chapter_location='%s'" % (chapter_position,))
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
                            debug("new chapter_location='%s'" % (new_chapter_position,))
                        except Exception:
                            debug("current chapter has not location. Not setting it.")
            debug("len(book['library_chapters']) =", len(book["library_chapters"]))
            debug("len(book['kobo_chapters']) =", len(book["kobo_chapters"]))
            debug(
                "len(book['kobo_database_chapters']) =",
                len(book["kobo_database_chapters"]),
            )
            if len(book["library_chapters"]) == len(book["kobo_database_chapters"]):
                debug("ToC lengths the same in library and database.")
                book["good"] = True
                book["icon"] = "ok.png"
                book["comment"] = "Chapters match in all places"

            if len(book["library_chapters"]) != len(book["kobo_chapters"]):
                debug("ToC lengths different between library and device.")
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
                debug("No chapters in database for book.")
                book["can_update_toc"] = False
                book["kobo_database_status"] = False
                book["comment"] = "Book needs to be imported on the device"
                book["icon"] = "window-close.png"
                continue
            if len(book["kobo_chapters"]) != len(book["kobo_database_chapters"]):
                debug("ToC lengths different between book on device and the database.")
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

            debug("Finished with book")
            i += 1

    def _get_database_chapters(
        self,
        connection: DeviceDatabaseConnection,
        koboContentId: str,
        book_format: str = "EPUB",
        contentId: int = 9,
    ) -> list[dict[str, Any]]:
        chapters = []
        debug(
            "koboContentId='%s', book_format='%s', contentId='%s'"
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
            debug("chapterContentId=%s" % (row["ContentID"],))
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
            debug("chapter= ", chapter)
            chapters.append(chapter)

        chapters.sort(key=lambda x: x["VolumeIndex"])

        return chapters

    def _get_database_current_chapter(
        self, koboContentId: str, connection: DeviceDatabaseConnection
    ) -> str | None:
        debug("start")
        readingLocationchapterQuery = "SELECT ContentID, ChapterIDBookmarked, ReadStatus FROM content WHERE ContentID = ?"
        cursor = connection.cursor()
        t = (koboContentId,)
        cursor.execute(readingLocationchapterQuery, t)
        try:
            result = next(cursor)
            debug("result='%s'" % (result,))
            if result["ChapterIDBookmarked"] is None:
                reading_location = None
            else:
                reading_location = result["ChapterIDBookmarked"]
                assert self.device is not None
                if (
                    isinstance(self.device.driver, KOBOTOUCH)
                    and (
                        self.device.driver.fwversion
                        < self.device.driver.min_fwversion_epub_location
                    )  # type: ignore[reportOperatorIssue]
                ):
                    reading_location = (
                        reading_location[len(koboContentId) + 1 :]
                        if (result["ReadStatus"] == 1)
                        else None
                    )
        except StopIteration:
            debug("no match for contentId='%s'" % (koboContentId,))
            reading_location = None
        debug("reading_location='%s'" % (reading_location,))

        return reading_location

    def _get_readingposition_index(
        self, book: dict[str, Any], koboDatabaseReadingLocation: str
    ):
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
            debug(
                "reading_location_volumeIndex =%d, reading_location_file='%s'"
                % (reading_location_volumeIndex, reading_location_file)
            )
            debug(
                "chapter location='%s'"
                % (
                    book["kobo_database_chapters"][reading_location_volumeIndex][
                        "path"
                    ],
                )
            )
            debug(
                "library file='%s'"
                % (book["library_chapters"][reading_location_volumeIndex]["path"],)
            )
        except Exception as e:
            debug("exception getting reading location details. Exception:", e)
            return None

        for i, library_chapter in enumerate(book["library_chapters"]):
            if library_chapter["path"] == reading_location_file:
                new_toc_readingposition_index = i
                debug("found file='%s', index=%s" % (library_chapter["path"], i))
                break

        return new_toc_readingposition_index

    def _compare_toc_entries(
        self,
        book: dict[str, Any],
        book_format1: str = "library",
        book_format2: str = "kobo",
    ):
        debug(
            "book_format1='%s', book_format2: %s, count ToC entries: %d"
            % (book_format1, book_format2, len(book[book_format1 + "_chapters"]))
        )
        for i, chapter_format1 in enumerate(book[book_format1 + "_chapters"]):
            chapter_format1_path = chapter_format1["path"]
            chapter_format2_path = book[book_format2 + "_chapters"][i]["path"]

            if chapter_format1_path != chapter_format2_path:
                debug("path different for chapter index: %d" % i)
                debug("format1=%s, path='%s'" % (book_format1, chapter_format1_path))
                debug("format2=%s, path='%s'" % (book_format2, chapter_format2_path))
                return False
            if chapter_format1["title"] != book[book_format2 + "_chapters"][i]["title"]:
                debug("title different for chapter index: %d" % i)
                debug(
                    "format1=%s, path='%s'" % (book_format1, chapter_format1["title"])
                )
                debug(
                    "format2=%s, path='%s'"
                    % (book_format2, book[book_format1 + "_chapters"][i]["title"])
                )
                return False
        debug("chapter paths and titles the same.")
        return True

    def _compare_manifest_entries(
        self,
        book: dict[str, Any],
        book_format1: str = "library",
        book_format2: str = "kobo",
    ):
        debug(
            "book_format1='%s', book_format2:'%s', count ToC entries: %d"
            % (book_format1, book_format2, len(book[book_format1 + "_manifest"]))
        )
        try:
            for i, manifest_item in enumerate(book[book_format1 + "_manifest"]):
                manifest_format1_path = manifest_item["path"]
                manifest_format2_path = book[book_format2 + "_manifest"][i]["path"]

                if manifest_format1_path != manifest_format2_path:
                    debug("path different for manifest index: %d" % i)
                    debug(
                        "format1=%s, path='%s'" % (book_format1, manifest_format1_path)
                    )
                    debug(
                        "format2=%s, path='%s'" % (book_format2, manifest_format2_path)
                    )
                    return False
            debug("manifest paths are same.")
            return True
        except Exception:
            return False

    def update_device_toc_for_books(self, books: list[dict[str, Any]]):
        self.gui.status_bar.show_message(
            _("Updating ToC in device database for {0} books.").format(len(books)), 3000
        )
        debug("books=", books)
        progressbar = ProgressBar(
            parent=self.gui, window_title=_("Updating ToC in device database")
        )
        progressbar.set_label(_("Number of books to update: {0}").format(len(books)))
        progressbar.show_with_maximum(len(books))
        connection = self.device_database_connection()
        for book in books:
            debug("book=", book)
            debug("ContentID=", book["ContentID"])
            progressbar.increment()

            if len(book["kobo_chapters"]) > 0:
                self.remove_all_toc_entries(connection, book["ContentID"])

                self.update_device_toc_for_book(
                    connection,
                    book,
                    book["ContentID"],
                    book["title"],
                    book["kobo_format"],
                )

        progressbar.hide()

    def update_device_toc_for_book(
        self,
        connection: DeviceDatabaseConnection,
        book: dict[str, Any],
        bookID: str,
        bookTitle: str,
        book_format: str = "EPUB",
    ):
        debug(
            "bookTitle=%s, len(book['library_chapters'])=%d"
            % (bookTitle, len(book["library_chapters"]))
        )
        num_chapters = len(book["kobo_chapters"])
        for i, chapter in enumerate(book["kobo_chapters"]):
            debug("chapter=", (chapter))
            if book_format == "KEPUB":
                chapterContentId = "{0}!{1}!{2}".format(
                    book["ContentID"], book["kobo_opf_dir"], chapter["path"]
                )
            else:
                chapterContentId = book["ContentID"] + f"#({i})" + chapter["path"]
            debug("chapterContentId=", chapterContentId)
            databaseChapterId = self.getDatabaseChapterId(
                book["ContentID"], chapter["path"], connection
            )
            has_chapter = databaseChapterId is not None
            debug("has_chapter=", has_chapter)
            if (
                databaseChapterId is not None
                and chapter["path"].endswith("finish.xhtml")
                and chapterContentId != databaseChapterId
            ):
                debug("removing SOL finish chapter")
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
                    file_size=int(file_size),
                    file_offset=int(file_offset),
                )
                file_offset += file_size

        self.update_database_content_entry(connection, book["ContentID"], num_chapters)
        return 0

    def getDatabaseChapterId(
        self, bookId: str, toc_file: str, connection: DeviceDatabaseConnection
    ) -> str | None:
        cursor = connection.cursor()
        t = (f"{bookId}%{toc_file}%",)
        cursor.execute("select ContentID from Content where ContentID like ?", t)
        try:
            result = next(cursor)
            chapterContentId = result[0]
        except StopIteration:
            chapterContentId = None

        debug("chapterContentId=%s" % chapterContentId)
        return chapterContentId

    def removeChapterFromDatabase(
        self, chapterContentId: str, bookID: str, connection: DeviceDatabaseConnection
    ):
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

    def update_database_content_entry(
        self, connection: DeviceDatabaseConnection, contentId: str, num_chapters: int
    ):
        cursor = connection.cursor()
        t = (contentId, num_chapters)
        cursor.execute("UPDATE content SET NumShortcovers = ? where ContentID = ?", t)

        return

    def remove_all_toc_entries(
        self, connection: DeviceDatabaseConnection, contentId: str
    ):
        debug("contentId=", contentId)

        cursor = connection.cursor()
        t = (contentId,)

        cursor.execute("DELETE FROM Content WHERE BookID = ?", t)
        cursor.execute("DELETE FROM volume_shortcovers WHERE volumeId = ?", t)

        return

    def addChapterToDatabase(
        self,
        chapterContentId: str,
        chapter: dict[str, Any],
        bookID: str,
        bookTitle: str,
        volumeIndex: int,
        connection: DeviceDatabaseConnection,
        book_format: str = "EPUB",
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
            debug("regex matches=", matches.groups())
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

        debug("insertContentData=", insertContentData)
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
            debug("insertShortCoverData=", insertShortCoverData)
            cursorShortCover.execute(insertShortCoverQuery, insertShortCoverData)

            cursorShortCover.close()

    def addManifestEntryToDatabase(
        self,
        manifest_entry: str,
        bookID: str,
        bookTitle: str,
        title: str,
        volumeIndex: int,
        connection: DeviceDatabaseConnection,
        file_size: int,
        file_offset: int,
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
        debug("insertContentData=", insertContentData)
        cursorContent.execute(insertContentQuery, insertContentData)

        cursorShortCover = connection.cursor()
        insertShortCoverQuery = "INSERT INTO volume_shortcovers (volumeId, shortcoverId, VolumeIndex) VALUES (?,?,?)"
        insertShortCoverData = (
            bookID,
            manifest_entry,
            volumeIndex,
        )
        debug("insertShortCoverData=", insertShortCoverData)
        cursorShortCover.execute(insertShortCoverQuery, insertShortCoverData)

        cursorContent.close()
        cursorShortCover.close()

    """
    End ToC Updating
    """

    def show_help(self, anchor: str | None = None):
        debug("anchor=", anchor)

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
            debug("file_path:", file_path)
            with open(file_path, "wb") as f:
                f.write(file_data)
            return file_path

        debug("anchor=", anchor)
        url = "file:///" + get_help_file_resource()
        url = QUrl(url)
        if anchor is not None and anchor != "":
            url.setFragment(anchor)
        open_url(url)


@dataclasses.dataclass
class KoboVersionInfo:
    serial_no: str
    fw_version: str
    model_id: str


@dataclasses.dataclass
class KoboDevice:
    driver: KOBO
    is_kobotouch: bool
    profile: cfg.ProfileConfig | None
    backup_config: cfg.BackupOptionsStoreConfig
    device_type: str
    drive_info: dict[str, dict[str, str]]
    uuid: str
    version_info: KoboVersionInfo | None
    supports_series: bool
    supports_series_list: bool
    supports_ratings: bool
    epub_location_like_kepub: bool
    name: str
    path: str
    db_path: str
    device_db_path: str
    is_db_copied: bool
