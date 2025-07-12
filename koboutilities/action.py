# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import annotations

from pathlib import Path

__license__ = "GPL v3"
__copyright__ = "2012-2017, David Forrester <davidfor@internode.on.net>"
__docformat__ = "restructuredtext en"

import calendar
import dataclasses
import os
import pickle
import re
import shutil
import threading
import time
from functools import partial
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Tuple,
    cast,
)

from calibre.constants import numeric_version as calibre_version
from calibre.devices.kobo.driver import KOBO, KOBOTOUCH
from calibre.ebooks.metadata import authors_to_string
from calibre.ebooks.oeb.polish.container import EpubContainer
from calibre.ebooks.oeb.polish.errors import DRMError
from calibre.gui2 import (
    error_dialog,
    info_dialog,
    open_local_file,
    question_dialog,
    ui,
)
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.device import DeviceJob, device_signals
from calibre.gui2.dialogs.message_box import ViewLog
from calibre.utils.logging import default_log
from qt.core import (
    QAction,
    QIcon,
    QMenu,
    QModelIndex,
    QTimer,
    pyqtSignal,
)

from . import ActionKoboUtilities
from . import config as cfg
from .constants import BOOK_CONTENTTYPE, GUI_NAME
from .dialogs import (
    AboutDialog,
    BackupAnnotationsOptionsDialog,
    CleanImagesDirOptionsDialog,
    CleanImagesDirProgressDialog,
    CoverUploadOptionsDialog,
    GetShelvesFromDeviceDialog,
    RemoveAnnotationsOptionsDialog,
    RemoveAnnotationsProgressDialog,
    RemoveCoverOptionsDialog,
    SetRelatedBooksDialog,
    ShowBooksNotInDeviceDatabaseDialog,
    UpdateBooksToCDialog,
)
from .features import (
    analytics,
    database,
    duplicateshelves,
    locations,
    manageseries,
    metadata,
    reader,
    readingstatus,
)
from .utils import (
    DeviceDatabaseConnection,
    Dispatcher,
    LoadResources,
    ProgressBar,
    contentid_from_path,
    convert_calibre_ids_to_books,
    create_menu_action_unique,
    debug,
    get_books_for_selected,
    get_contentIDs_from_id,
    get_device_paths_from_id,
    get_icon,
    get_selected_ids,
    is_device_view,
    set_plugin_icon_resources,
    show_help,
)

if TYPE_CHECKING:
    from calibre.db.legacy import LibraryDatabase
    from calibre.devices.kobo.books import Book
    from calibre.ebooks.oeb.polish.toc import TOC

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


KOBO_ROOT_DIR_NAME = ".kobo"
KOBO_EPOCH_CONF_NAME = "epoch.conf"

load_translations()


class KoboUtilitiesAction(InterfaceAction):
    interface_action_base_plugin: ActionKoboUtilities
    qaction: QAction

    name = "KoboUtilities"
    giu_name = GUI_NAME
    # Create our top-level menu/toolbar action (text, icon_path, tooltip, keyboard shortcut)
    action_spec = (name, None, ActionKoboUtilities.description, ())
    action_type = "current"

    timestamp_string = None

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
            QTimer.singleShot(
                1000,
                partial(
                    locations.auto_store_current_bookmark,
                    self.device,
                    self.gui,
                    cast("Dispatcher", self.Dispatcher),
                ),
            )

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
                locations.auto_store_current_bookmark(
                    self.device,
                    self.gui,
                    cast("Dispatcher", self.Dispatcher),
                    self.load_resources,
                )

        self.rebuild_menus()

    def rebuild_menus(self) -> None:
        def menu_wrapper(
            func: Callable[
                [KoboDevice, ui.Main, Dispatcher, LoadResources],
                None,
            ],
        ):
            def wrapper():
                if self.device is None:
                    raise AssertionError(_("No device connected."))
                func(
                    self.device,
                    self.gui,
                    cast("Dispatcher", self.Dispatcher),
                    self.load_resources,
                )

            return wrapper

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
                triggered=menu_wrapper(reader.set_reader_fonts),
                is_library_action=True,
                is_device_action=True,
                is_supported=device is not None and device.is_kobotouch,
            )

            self.create_menu_item_ex(
                self.menu,
                _("&Remove reader font for selected books"),
                unique_name="Remove reader font for selected books",
                shortcut_name=_("Remove reader font for selected books"),
                triggered=menu_wrapper(reader.remove_reader_fonts),
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
                triggered=menu_wrapper(metadata.update_metadata),
                is_library_action=True,
            )

            self.create_menu_item_ex(
                self.menu,
                _("&Change reading status in device library"),
                unique_name="Change reading status in device library",
                shortcut_name=_("Change reading status in device library"),
                triggered=menu_wrapper(readingstatus.change_reading_status),
                is_device_action=True,
            )

            self.create_menu_item_ex(
                self.menu,
                _("&Manage series information in device library"),
                unique_name="Manage series information in device library",
                shortcut_name=_("Manage series information in device library"),
                triggered=menu_wrapper(manageseries.manage_series_on_device),
                is_device_action=True,
                is_supported=device is not None and device.supports_series,
            )

            self.create_menu_item_ex(
                self.menu,
                _("&Store/restore reading positions"),
                unique_name="Store/restore reading positions",
                shortcut_name=_("Store/restore reading positions"),
                image="bookmarks.png",
                triggered=menu_wrapper(locations.handle_bookmarks),
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
                triggered=menu_wrapper(analytics.block_analytics),
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
                triggered=menu_wrapper(duplicateshelves.fix_duplicate_shelves),
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
                triggered=menu_wrapper(database.check_device_database),
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
                triggered=menu_wrapper(database.vacuum_device_database),
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
                triggered=menu_wrapper(database.backup_device_database),
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
                triggered=lambda _: show_help(self.load_resources),
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
        elif is_device_view(self.gui) and not is_device_action:
            tooltip = _("Only supported in library view")
            enabled = False
        elif not is_device_view(self.gui) and not is_library_action:
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

        if is_device_view(self.gui):
            assert self.device is not None
            if self.device.supports_series:
                button_action = cfg.plugin_prefs.commonOptionsStore.buttonActionDevice
                if button_action == "":
                    self.show_configuration()
                else:
                    self.menu_actions[button_action].trigger()
            else:
                readingstatus.change_reading_status(
                    self.device,
                    self.gui,
                    cast("Dispatcher", self.Dispatcher),
                    self.load_resources,
                )
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

        selectedIDs = get_selected_ids(self.gui)

        if len(selectedIDs) == 0:
            return

        dlg = BackupAnnotationsOptionsDialog(self.gui, self)
        dlg.exec()
        if dlg.result() != dlg.DialogCode.Accepted:
            return

        dest_path = dlg.dest_path()
        debug("selectedIDs:", selectedIDs)
        books = convert_calibre_ids_to_books(current_view.model().db, selectedIDs)
        for book in books:
            device_book_paths = get_device_paths_from_id(
                cast("int", book.calibre_id), self.gui
            )
            debug("device_book_paths:", device_book_paths)
            book.paths = device_book_paths
            book.contentIDs = [
                contentid_from_path(self.device, path, BOOK_CONTENTTYPE)
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

        books = get_books_for_selected(self.gui)

        if len(books) == 0:
            books = current_view.model().db

        books_not_in_database = self._check_book_in_database(books)

        dlg = ShowBooksNotInDeviceDatabaseDialog(self.gui, self, books_not_in_database)
        dlg.show()

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
            selectedIDs = get_selected_ids(self.gui)

        if len(selectedIDs) == 0:
            return
        debug("selectedIDs:", selectedIDs)
        books = convert_calibre_ids_to_books(library_db, selectedIDs)
        progressbar.set_label(
            _("Number of books to get collections for: {0}").format(len(books))
        )
        for book in books:
            device_book_paths = get_device_paths_from_id(
                cast("int", book.calibre_id), self.gui
            )
            debug("device_book_paths:", device_book_paths)
            book.paths = device_book_paths
            book.contentIDs = [
                contentid_from_path(self.device, path, BOOK_CONTENTTYPE)
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

        selectedIDs = get_selected_ids(self.gui)

        if len(selectedIDs) == 0:
            return
        debug("selectedIDs:", selectedIDs)
        books = convert_calibre_ids_to_books(
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
            selectedIDs = get_selected_ids(self.gui)
            books = convert_calibre_ids_to_books(current_view.model().db, selectedIDs)
        else:
            books = get_books_for_selected(self.gui)

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
            selectedIDs = get_selected_ids(self.gui)
            books = convert_calibre_ids_to_books(current_view.model().db, selectedIDs)

        else:
            books = get_books_for_selected(self.gui)

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

        timestamp_string = getattr(device, "TIMESTAMP_STRING", "%Y-%m-%dT%H:%M:%SZ")

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
            timestamp_string,
        )
        debug("kobo_device:", kobo_device)
        return kobo_device

    @property
    def device_fwversion(self) -> tuple[int, int, int] | None:
        if self.device is not None:
            return cast("Tuple[int, int, int]", self.device.driver.fwversion)
        return None

    def get_device_path_from_id(self, book_id: int) -> str | None:
        paths = get_device_paths_from_id(book_id, self.gui)
        return paths[0] if paths else None

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
                paths = get_device_paths_from_id(_id, self.gui)
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
            paths = get_device_paths_from_id(cast("int", book.calibre_id), self.gui)
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
                else get_contentIDs_from_id(cast("int", book.calibre_id), self.gui)
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
                    BOOK_CONTENTTYPE,
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
                else get_contentIDs_from_id(cast("int", book.calibre_id), self.gui)
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
                    BOOK_CONTENTTYPE,
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
                assert self.device is not None
                book.contentID = contentid_from_path(  # pyright: ignore[reportAttributeAccessIssue]
                    self.device, book.path, BOOK_CONTENTTYPE
                )

            query_values = (book.contentID,)
            cursor.execute(imageId_query, query_values)
            try:
                next(cursor)
            except StopIteration:
                debug("no match for contentId='%s'" % (book.contentID,))
                not_on_device_books.append(book)

        return not_on_device_books

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
    timestamp_string: str
