# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

from __future__ import annotations

__license__ = "GPL v3"
__copyright__ = "2011, Grant Drake <grant.drake@gmail.com>, 2012-2022 updates by David Forrester <davidfor@internode.on.net>"
__docformat__ = "restructuredtext en"

import inspect
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Type, Union, cast

import apsw
from calibre.constants import DEBUG, iswindows
from calibre.gui2 import Application, error_dialog, gprefs, info_dialog, ui
from calibre.gui2.actions import menu_action_unique_name
from calibre.gui2.keyboard import ShortcutConfig
from calibre.utils.config import config_dir
from calibre.utils.date import UNDEFINED_DATE, format_date, now
from qt.core import (
    QAbstractItemView,
    QAction,
    QByteArray,
    QComboBox,
    QDateTime,
    QDialog,
    QDialogButtonBox,
    QFont,
    QHBoxLayout,
    QIcon,
    QLabel,
    QListWidget,
    QMenu,
    QPixmap,
    QProgressBar,
    QPushButton,
    Qt,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    # timed_print got added in Calibre 7.2.0
    from calibre.gui2 import timed_print
except ImportError:
    timed_print = print

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from calibre.gui2.dialogs.message_box import MessageBox

    from .action import KoboUtilitiesAction
    from .config import ConfigWidget

MIMETYPE_KOBO = "application/x-kobo-epub+zip"

BOOKMARK_SEPARATOR = (
    "|@ @|"  # Spaces are included to allow wrapping in the details panel
)

# Global definition of our plugin name. Used for common functions that require this.
plugin_name = None
# Global definition of our plugin resources. Used to share between the xxxAction and xxxBase
# classes if you need any zip images to be displayed on the configuration dialog.
plugin_icon_resources = {}


def debug(*args: Any):
    if DEBUG:
        frame = inspect.currentframe()
        assert frame is not None
        frame = frame.f_back
        assert frame is not None
        code = frame.f_code
        filename = code.co_filename.replace("calibre_plugins.", "")
        # co_qualname was added in Python 3.11
        funcname = getattr(code, "co_qualname", code.co_name)
        timed_print(
            f"[DEBUG] [{filename}:{funcname}:{frame.f_lineno}]",
            *args,
        )


def set_plugin_icon_resources(name: str, resources: Dict[str, bytes]):
    """
    Set our global store of plugin name and icon resources for sharing between
    the InterfaceAction class which reads them and the ConfigWidget
    if needed for use on the customization dialog for this plugin.
    """
    global plugin_icon_resources, plugin_name
    plugin_name = name
    plugin_icon_resources = resources


def get_icon(icon_name: Optional[str]):
    """
    Retrieve a QIcon for the named image from the zip file if it exists,
    or if not then from Calibre's image cache.
    """
    if icon_name:
        pixmap = get_pixmap(icon_name)
        if pixmap is None:
            # Look in Calibre's cache for the icon
            return QIcon(I(icon_name))
        return QIcon(pixmap)
    return QIcon()


def get_pixmap(icon_name: str):
    """
    Retrieve a QPixmap for the named image
    Any icons belonging to the plugin must be prefixed with 'images/'
    """
    global plugin_icon_resources, plugin_name

    if not icon_name.startswith("images/"):
        # We know this is definitely not an icon belonging to this plugin
        pixmap = QPixmap()
        pixmap.load(I(icon_name))
        return pixmap

    # Check to see whether the icon exists as a Calibre resource
    # This will enable skinning if the user stores icons within a folder like:
    # ...\AppData\Roaming\calibre\resources\images\Plugin Name\
    if plugin_name:
        local_images_dir = get_local_images_dir(plugin_name)
        local_image_path = os.path.join(
            local_images_dir, icon_name.replace("images/", "")
        )
        if os.path.exists(local_image_path):
            pixmap = QPixmap()
            pixmap.load(local_image_path)
            return pixmap

    # As we did not find an icon elsewhere, look within our zip resources
    if icon_name in plugin_icon_resources:
        pixmap = QPixmap()
        pixmap.loadFromData(plugin_icon_resources[icon_name])
        return pixmap
    return None


def get_local_images_dir(subfolder: Optional[str] = None):
    """
    Returns a path to the user's local resources/images folder
    If a subfolder name parameter is specified, appends this to the path
    """
    images_dir = os.path.join(config_dir, "resources/images")
    if subfolder:
        images_dir = os.path.join(images_dir, subfolder)
    if iswindows:
        images_dir = os.path.normpath(images_dir)
    return images_dir


def create_menu_action_unique(
    ia: KoboUtilitiesAction,
    parent_menu: QMenu,
    menu_text: str,
    triggered: Union[Callable[[], None], Callable[[QAction], None]],
    image: Optional[str] = None,
    tooltip: Optional[str] = None,
    shortcut: Union[str, List[str], None, Literal[False]] = None,
    is_checked: Optional[bool] = None,
    shortcut_name: Optional[str] = None,
    unique_name: Optional[str] = None,
) -> QAction:
    """
    Create a menu action with the specified criteria and action, using the new
    InterfaceAction.create_menu_action() function which ensures that regardless of
    whether a shortcut is specified it will appear in Preferences->Keyboard
    """
    orig_shortcut = shortcut
    kb = ia.gui.keyboard
    if unique_name is None:
        unique_name = menu_text
    if shortcut is not False:
        full_unique_name = menu_action_unique_name(ia, unique_name)
        if full_unique_name in kb.shortcuts:
            shortcut = False
        else:
            if shortcut is not None and isinstance(shortcut, str):
                shortcut = None if len(shortcut) == 0 else _(shortcut)

    if shortcut_name is None:
        shortcut_name = menu_text.replace("&", "")

    ac = ia.create_menu_action(
        parent_menu,
        unique_name,
        menu_text,
        icon=None,
        shortcut=shortcut,
        description=tooltip,
        triggered=triggered,
        shortcut_name=shortcut_name,
    )
    if (
        shortcut is False
        and orig_shortcut is not False
        and ac.calibre_shortcut_unique_name in ia.gui.keyboard.shortcuts
    ):
        kb.replace_action(ac.calibre_shortcut_unique_name, ac)
    if image:
        ac.setIcon(get_icon(image))
    if is_checked is not None:
        ac.setCheckable(True)
        if is_checked:
            ac.setChecked(True)
    return ac


def row_factory(cursor: apsw.Cursor, row: apsw.SQLiteValues):
    return {k[0]: row[i] for i, k in enumerate(cursor.getdescription())}


# This is necessary for Calibre 8 if the driver copies the database
# to a temporary location due to filesystem limitations.
# Without a lock the copying can lead to data loss.
# In addition, transactions are generally useful when changing the device DB.
class DeviceDatabaseConnection(apsw.Connection):
    def __init__(
        self,
        database_path: str,
        device_db_path: str,
        is_db_copied: bool,
        use_row_factory: bool = False,
    ) -> None:
        self.__lock = None
        self.__copy_db: Callable[[apsw.Connection, str], None] = lambda *_args: None
        try:
            from calibre.devices.kobo.db import copy_db, kobo_db_lock

            self.__lock = kobo_db_lock
            self.__copy_db = copy_db
        except ImportError:
            pass
        super().__init__(database_path)
        if use_row_factory:
            self.setrowtrace(row_factory)
        self.__device_db_path = device_db_path
        self.__is_db_copied = is_db_copied

    def __enter__(self) -> apsw.Connection:
        if self.__lock is not None:
            self.__lock.acquire()
        return super().__enter__()

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> Optional[bool]:
        try:
            suppress_exception = super().__exit__(exc_type, exc_value, tb)
            if self.__is_db_copied and (
                suppress_exception
                or (exc_type is None and exc_value is None and tb is None)
            ):
                self.__copy_db(self, self.__device_db_path)
        finally:
            if self.__lock is not None:
                self.__lock.release()
        return suppress_exception


def check_device_database(database_path: str):
    connection = DeviceDatabaseConnection(
        database_path, database_path, is_db_copied=False
    )
    check_query = "PRAGMA integrity_check"
    cursor = connection.cursor()

    check_result = ""
    cursor.execute(check_query)
    result = cursor.fetchall()
    if result:
        for line in result:
            debug("result line=", line)
            check_result += "\n" + str(line[0])
    else:
        check_result = _("Execution of '%s' failed") % check_query

    return check_result


def convert_kobo_date(kobo_date: Optional[str]) -> Optional[datetime]:
    if kobo_date is None:
        return None

    from calibre.utils.date import local_tz, utc_tz

    try:
        converted_date = datetime.strptime(kobo_date, "%Y-%m-%dT%H:%M:%S.%f").replace(
            tzinfo=utc_tz
        )
        converted_date = datetime.strptime(
            kobo_date[0:19], "%Y-%m-%dT%H:%M:%S"
        ).replace(tzinfo=utc_tz)
    except ValueError:
        try:
            converted_date = datetime.strptime(
                kobo_date, "%Y-%m-%dT%H:%M:%S%+00:00"
            ).replace(tzinfo=utc_tz)
        except ValueError:
            try:
                converted_date = datetime.strptime(
                    kobo_date.split("+")[0], "%Y-%m-%dT%H:%M:%S"
                ).replace(tzinfo=utc_tz)
            except ValueError:
                try:
                    converted_date = datetime.strptime(
                        kobo_date.split("+")[0], "%Y-%m-%d"
                    ).replace(tzinfo=utc_tz)
                except ValueError:
                    try:
                        from calibre.utils.date import parse_date

                        converted_date = parse_date(kobo_date, assume_utc=True)
                    except ValueError:
                        # The date is in some unknown format. Return now in the local timezone
                        converted_date = datetime.now(tz=local_tz)
                        debug("datetime.now() - kobo_date={0}'".format(kobo_date))
    return converted_date


class ImageTitleLayout(QHBoxLayout):
    """
    A reusable layout widget displaying an image followed by a title
    """

    def __init__(
        self,
        parent: Union[SizePersistedDialog, ConfigWidget],
        icon_name: str,
        title: str,
    ):
        super(ImageTitleLayout, self).__init__()
        self.title_image_label = QLabel(parent)
        self.update_title_icon(icon_name)
        self.addWidget(self.title_image_label)

        title_font = QFont()
        title_font.setPointSize(16)
        shelf_label = QLabel(title, parent)
        shelf_label.setFont(title_font)
        self.addWidget(shelf_label)

        help_layout = QHBoxLayout()

        help_pixmap = get_pixmap("help.png")
        if help_pixmap is not None:
            help_pixmap = help_pixmap.scaled(16, 16)
            help_icon = QLabel()
            help_icon.setPixmap(help_pixmap)
            # help_icon.setAlignment(Qt.AlignmentFlag.AlignRight)
            help_layout.addWidget(help_icon)

        # Add hyperlink to a help file at the right. We will replace the correct name when it is clicked.
        help_label = QLabel(
            ('<a href="http://www.foo.com/">{0}</a>').format(_("Help")), parent
        )
        help_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        help_label.linkActivated.connect(parent.help_link_activated)
        help_layout.addWidget(help_label)

        help_layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        help_widget = QWidget()
        help_widget.setLayout(help_layout)
        self.addWidget(help_widget)

    def update_title_icon(self, icon_name: str):
        pixmap = get_pixmap(icon_name)
        if pixmap is None:
            error_dialog(
                self.parent(),
                _("Restart required"),
                _(
                    "Title image not found - you must restart Calibre before using this plugin!"
                ),
                show=True,
            )
        else:
            self.title_image_label.setPixmap(pixmap)
        self.title_image_label.setMaximumSize(32, 32)
        self.title_image_label.setScaledContents(True)


class SizePersistedDialog(QDialog):
    """
    This dialog is a base class for any dialogs that want their size/position
    restored when they are next opened.
    """

    def __init__(
        self,
        parent: QWidget,
        unique_pref_name: str,
        plugin_action: Optional[KoboUtilitiesAction] = None,
    ):
        super(SizePersistedDialog, self).__init__(parent)
        self.unique_pref_name = unique_pref_name
        self.geom: Optional[QByteArray] = gprefs.get(unique_pref_name, None)
        self.finished.connect(self.dialog_closing)
        self.help_anchor = None
        self.setWindowIcon(get_icon("images/icon.png"))
        self.plugin_action = plugin_action

    def resize_dialog(self):
        if self.geom is None:
            self.resize(self.sizeHint())
        else:
            self.restoreGeometry(self.geom)

    def dialog_closing(self, result: Any):
        del result
        geom = self.saveGeometry()
        gprefs[self.unique_pref_name] = geom

    def help_link_activated(self, url: str):
        del url
        if self.plugin_action is not None:
            self.plugin_action.show_help(anchor=self.help_anchor)


class ReadOnlyTableWidgetItem(QTableWidgetItem):
    def __init__(self, text: Optional[str]):
        if text is None:
            text = ""
        super(ReadOnlyTableWidgetItem, self).__init__(text)
        self.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)


class RatingTableWidgetItem(QTableWidgetItem):
    def __init__(self, rating: Optional[int], is_read_only: bool = False):
        super(RatingTableWidgetItem, self).__init__("")
        self.setData(Qt.ItemDataRole.DisplayRole, rating)
        if is_read_only:
            self.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)


class DateTableWidgetItem(QTableWidgetItem):
    def __init__(
        self,
        date_read: Optional[datetime],
        is_read_only: bool = False,
        default_to_today: bool = False,
        fmt: Optional[str] = None,
    ):
        if date_read is None or (date_read == UNDEFINED_DATE and default_to_today):
            date_read = now()
        if is_read_only:
            super(DateTableWidgetItem, self).__init__(format_date(date_read, fmt))
            self.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            self.setData(Qt.ItemDataRole.DisplayRole, QDateTime(date_read))
        else:
            super(DateTableWidgetItem, self).__init__("")
            self.setData(Qt.ItemDataRole.DisplayRole, QDateTime(date_read))


class CheckableTableWidgetItem(QTableWidgetItem):
    def __init__(self, checked: bool = False):
        super(CheckableTableWidgetItem, self).__init__("")
        self.setFlags(
            Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsUserCheckable
            | Qt.ItemFlag.ItemIsEnabled
        )
        if checked:
            self.setCheckState(Qt.CheckState.Checked)
        else:
            self.setCheckState(Qt.CheckState.Unchecked)

    def get_boolean_value(self):
        """
        Return a boolean value indicating whether checkbox is checked
        If this is a tristate checkbox, a partially checked value is returned as None
        """
        if self.checkState() == Qt.CheckState.PartiallyChecked:
            return None
        return self.checkState() == Qt.CheckState.Checked


class ReadOnlyTextIconWidgetItem(ReadOnlyTableWidgetItem):
    def __init__(self, text: Optional[str], icon: QIcon):
        super(ReadOnlyTextIconWidgetItem, self).__init__(text)
        if icon:
            self.setIcon(icon)


class ProfileComboBox(QComboBox):
    def __init__(
        self,
        parent: QWidget,
        profiles: Dict[str, Dict[str, Any]],
        selected_text: Optional[str] = None,
    ):
        super(ProfileComboBox, self).__init__(parent)
        self.populate_combo(profiles, selected_text)

    def populate_combo(
        self, profiles: Dict[str, Dict[str, Any]], selected_text: Optional[str] = None
    ):
        self.blockSignals(True)
        self.clear()
        for list_name in sorted(profiles.keys()):
            self.addItem(list_name)
        self.select_view(selected_text)
        self.blockSignals(False)

    def select_view(self, selected_text: Optional[str]):
        self.blockSignals(True)
        if selected_text:
            idx = self.findText(selected_text)
            self.setCurrentIndex(idx)
        elif self.count() > 0:
            self.setCurrentIndex(0)
        self.blockSignals(False)


class SimpleComboBox(QComboBox):
    def __init__(self, parent: QWidget, values: List[str], selected_value: str):
        super(SimpleComboBox, self).__init__(parent)
        self.values = values
        self.populate_combo(selected_value)

    def populate_combo(self, selected_value: str):
        self.clear()
        selected_idx = idx = -1
        for value in sorted(self.values):
            idx = idx + 1
            self.addItem(value)
            if value == selected_value:
                selected_idx = idx
        self.setCurrentIndex(selected_idx)

    def selected_key(self):
        for value in list(self.values):
            if value == str(self.currentText()).strip():
                return value
        return None


class CustomColumnComboBox(QComboBox):
    CREATE_NEW_COLUMN_ITEM = _("Create new column")

    def __init__(
        self,
        parent: QWidget,
        custom_columns: Optional[Dict[str, Dict[str, Any]]] = None,
        selected_column: str = "",
        initial_items: Optional[List[str]] = None,
        create_column_callback: Optional[Callable[[], bool]] = None,
    ):
        if custom_columns is None:
            custom_columns = {}
        if initial_items is None:
            initial_items = [""]
        super(CustomColumnComboBox, self).__init__(parent)
        debug("create_column_callback=", create_column_callback)
        self.create_column_callback = create_column_callback
        self.current_index = 0
        if create_column_callback is not None:
            self.currentTextChanged.connect(self.current_text_changed)
        self.populate_combo(custom_columns, selected_column, initial_items)

    def populate_combo(
        self,
        custom_columns: Dict[str, Dict[str, Any]],
        selected_column: str,
        initial_items: Optional[Union[Dict[str, str], List[str]]] = None,
        show_lookup_name: bool = True,
    ):
        if initial_items is None:
            initial_items = [""]
        self.clear()
        self.column_names = []
        selected_idx = 0

        for key in sorted(custom_columns.keys()):
            self.column_names.append(key)
            display_name = (
                "%s (%s)" % (key, custom_columns[key]["name"])
                if show_lookup_name
                else custom_columns[key]["name"]
            )
            self.addItem(display_name)
            if key == selected_column:
                selected_idx = len(self.column_names) - 1

        if isinstance(initial_items, dict):
            for key in sorted(initial_items.keys()):
                self.column_names.append(key)
                display_name = initial_items[key]
                self.addItem(display_name)
                if key == selected_column:
                    selected_idx = len(self.column_names) - 1
        else:
            for display_name in initial_items:
                self.column_names.append(display_name)
                self.addItem(display_name)
                if display_name == selected_column:
                    selected_idx = len(self.column_names) - 1

        debug("create_column_callback=", self.create_column_callback)
        if self.create_column_callback is not None:
            self.addItem(self.CREATE_NEW_COLUMN_ITEM)

        self.setCurrentIndex(selected_idx)

    def get_selected_column(self) -> str:
        return self.column_names[self.currentIndex()]

    def current_text_changed(self, new_text: str):
        debug("new_text='%s'" % new_text)
        debug(
            "new_text == self.CREATE_NEW_COLUMN_ITEM='%s'"
            % (new_text == self.CREATE_NEW_COLUMN_ITEM)
        )
        if (
            new_text == self.CREATE_NEW_COLUMN_ITEM
            and self.create_column_callback is not None
        ):
            debug("calling callback")
            result = self.create_column_callback()
            if not result:
                debug(
                    "column not created, setting back to original value - ",
                    self.current_index,
                )
                self.setCurrentIndex(self.current_index)
        else:
            self.current_index = self.currentIndex()


class KeyboardConfigDialog(SizePersistedDialog):
    """
    This dialog is used to allow editing of keyboard shortcuts.
    """

    def __init__(self, gui: ui.Main, group_name: str):
        super(KeyboardConfigDialog, self).__init__(gui, "Keyboard shortcut dialog")
        self.gui = gui
        self.setWindowTitle("Keyboard shortcuts")
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        self.keyboard_widget = ShortcutConfig(self)
        layout.addWidget(self.keyboard_widget)
        self.group_name = group_name

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.commit)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()
        self.initialize()

    def initialize(self):
        self.keyboard_widget.initialize(self.gui.keyboard)
        self.keyboard_widget.highlight_group(self.group_name)

    def commit(self):
        self.keyboard_widget.commit()
        self.accept()


class ProgressBar(QDialog):
    def __init__(
        self,
        parent: Optional[QWidget] = None,
        max_items: int = 100,
        window_title: str = "Progress Bar",
        label: str = "Label goes here",
        on_top: bool = False,
    ):
        if on_top:
            super(ProgressBar, self).__init__(
                parent=parent, flags=Qt.WindowType.WindowStaysOnTopHint
            )
        else:
            super(ProgressBar, self).__init__(parent=parent)
        self.application = Application
        self.setWindowTitle(window_title)
        self.l = QVBoxLayout(self)
        self.setLayout(self.l)

        self.label = QLabel(label)
        self.l.addWidget(self.label)

        self.progressBar = QProgressBar(self)
        self.progressBar.setRange(0, max_items)
        self.progressBar.setValue(0)
        self.l.addWidget(self.progressBar)

    def show_with_maximum(self, maximum_count: int):
        self.set_maximum(maximum_count)
        self.set_value(0)
        self.show()

    def increment(self):
        self.progressBar.setValue(self.progressBar.value() + 1)
        self.refresh()

    def refresh(self):
        self.application.processEvents()

    def set_label(self, value: str):
        self.label.setText(value)
        self.refresh()

    def left_align_label(self):
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft)

    def set_maximum(self, value: int):
        self.progressBar.setMaximum(value)
        self.refresh()

    def set_value(self, value: int):
        self.progressBar.setValue(value)
        self.refresh()


def prompt_for_restart(parent: QWidget, title: str, message: str):
    dialog_box = cast(
        "MessageBox", info_dialog(parent, title, message, show_copy_button=False)
    )
    bb = cast("QDialogButtonBox", dialog_box.bb)  # type: ignore[reportAttributeAccessIssue]
    button = cast(
        "QPushButton", bb.addButton(_("Restart calibre now"), bb.ButtonRole.AcceptRole)
    )
    button.setIcon(QIcon(I("lt.png")))

    class Restart:
        do_restart = False

    def rf():
        Restart.do_restart = True

    button.clicked.connect(rf)
    dialog_box.set_details("")
    dialog_box.exec()
    button.clicked.disconnect()
    return Restart.do_restart


class PrefsViewerDialog(SizePersistedDialog):
    def __init__(self, gui: ui.Main, namespace: str):
        super(PrefsViewerDialog, self).__init__(gui, _("Prefs viewer dialog"))
        self.setWindowTitle(_("Preferences for: {}").format(namespace))

        self.gui = gui
        self.db = gui.current_db
        self.namespace = namespace
        self._init_controls()
        self.resize_dialog()

        self._populate_settings()

        if self.keys_list.count():
            self.keys_list.setCurrentRow(0)

    def _init_controls(self):
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        ml = QHBoxLayout()
        layout.addLayout(ml, 1)

        self.keys_list = QListWidget(self)
        self.keys_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.keys_list.setFixedWidth(150)
        self.keys_list.setAlternatingRowColors(True)
        ml.addWidget(self.keys_list)
        self.value_text = QTextEdit(self)
        self.value_text.setReadOnly(False)
        ml.addWidget(self.value_text, 1)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._apply_changes)
        button_box.rejected.connect(self.reject)
        self.clear_button = button_box.addButton(
            _("Clear"), QDialogButtonBox.ButtonRole.ResetRole
        )
        assert self.clear_button is not None
        self.clear_button.setIcon(get_icon("trash.png"))
        self.clear_button.setToolTip(_("Clear all settings for this plugin"))
        self.clear_button.clicked.connect(self._clear_settings)
        layout.addWidget(button_box)

    def _populate_settings(self):
        self.keys_list.clear()
        ns_prefix = self._get_ns_prefix()
        keys = sorted(
            [
                k[len(ns_prefix) :]
                for k in list(self.db.prefs.keys())
                if k.startswith(ns_prefix)
            ]
        )
        for key in keys:
            self.keys_list.addItem(key)
        self.keys_list.setMinimumWidth(self.keys_list.sizeHintForColumn(0))
        self.keys_list.currentRowChanged[int].connect(self._current_row_changed)

    def _current_row_changed(self, new_row: int):
        if new_row < 0:
            self.value_text.clear()
            return
        current_item = self.keys_list.currentItem()
        assert current_item is not None
        key = str(current_item.text())
        val = self.db.prefs.get_namespaced(self.namespace, key, "")
        self.value_text.setPlainText(self.db.prefs.to_raw(val))

    def _get_ns_prefix(self):
        return "namespaced:%s:" % self.namespace

    def _apply_changes(self):
        from calibre.gui2.dialogs.confirm_delete import confirm

        message = (
            "<p>Are you sure you want to change your settings in this library for this plugin?</p>"
            "<p>Any settings in other libraries or stored in a JSON file in your calibre plugins "
            "folder will not be touched.</p>"
            "<p>You must restart calibre afterwards.</p>"
        )
        if not confirm(message, self.namespace + "_clear_settings", self):
            return

        val = self.db.prefs.raw_to_object(str(self.value_text.toPlainText()))
        current_item = self.keys_list.currentItem()
        assert current_item is not None
        key = str(current_item.text())
        self.db.prefs.set_namespaced(self.namespace, key, val)

        restart = prompt_for_restart(
            self,
            "Settings changed",
            "<p>Settings for this plugin in this library have been changed.</p>"
            "<p>Please restart calibre now.</p>",
        )
        self.close()
        if restart:
            self.gui.quit(restart=True)

    def _clear_settings(self):
        from calibre.gui2.dialogs.confirm_delete import confirm

        message = (
            "<p>Are you sure you want to clear your settings in this library for this plugin?</p>"
            "<p>Any settings in other libraries or stored in a JSON file in your calibre plugins "
            "folder will not be touched.</p>"
            "<p>You must restart calibre afterwards.</p>"
        )
        if not confirm(message, self.namespace + "_clear_settings", self):
            return

        ns_prefix = self._get_ns_prefix()
        keys = [k for k in list(self.db.prefs.keys()) if k.startswith(ns_prefix)]
        for k in keys:
            del self.db.prefs[k]
        self._populate_settings()
        restart = prompt_for_restart(
            self,
            _("Settings deleted"),
            _("<p>All settings for this plugin in this library have been cleared.</p>")
            + _("<p>Please restart calibre now.</p>"),
        )
        self.close()
        if restart:
            self.gui.quit(restart=True)
