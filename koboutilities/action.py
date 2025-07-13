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
from calibre.gui2 import (
    error_dialog,
    info_dialog,
    ui,
)
from calibre.gui2.actions import InterfaceAction
from calibre.gui2.device import DeviceJob, device_signals
from calibre.gui2.dialogs.message_box import ViewLog
from qt.core import (
    QAction,
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
    RemoveAnnotationsOptionsDialog,
    RemoveAnnotationsProgressDialog,
    SetRelatedBooksDialog,
    ShowBooksNotInDeviceDatabaseDialog,
)
from .features import (
    analytics,
    cleanimages,
    covers,
    database,
    duplicateshelves,
    getshelves,
    locations,
    manageseries,
    metadata,
    reader,
    readingstatus,
    toc,
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
                triggered=menu_wrapper(toc.update_book_toc_on_device),
                is_library_action=True,
            )

            self.menu.addSeparator()
            self.create_menu_item_ex(
                self.menu,
                _("&Upload covers for selected books"),
                unique_name="Upload covers for selected books",
                shortcut_name=_("Upload covers for selected books"),
                image="default_cover.png",
                triggered=menu_wrapper(covers.upload_covers),
                is_library_action=True,
            )
            self.create_menu_item_ex(
                self.menu,
                _("&Remove covers for selected books"),
                unique_name="Remove covers for selected books",
                shortcut_name=_("Remove covers for selected books"),
                triggered=menu_wrapper(covers.remove_covers),
                is_library_action=True,
                is_device_action=True,
                is_supported=device is not None and device.is_kobotouch,
            )

            self.create_menu_item_ex(
                self.menu,
                _("&Clean images directory of extra cover images"),
                unique_name="Clean images directory of extra cover images",
                shortcut_name=_("Clean images directory of extra cover images"),
                triggered=menu_wrapper(cleanimages.clean_images_dir),
                is_library_action=True,
                is_device_action=True,
            )
            self.create_menu_item_ex(
                self.menu,
                _("&Open cover image directory"),
                unique_name="Open cover image directory",
                shortcut_name=_("Open cover image directory"),
                triggered=menu_wrapper(covers.open_cover_image_directory),
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
                triggered=menu_wrapper(getshelves.get_shelves_from_device),
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
