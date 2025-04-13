# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

from __future__ import annotations

__license__ = "GPL v3"
__copyright__ = "2012-2022, David Forrester <davidfor@internode.on.net>"
__docformat__ = "restructuredtext en"

import copy
import traceback
from functools import partial
from typing import TYPE_CHECKING, Any, Dict, Optional, cast

from calibre.constants import DEBUG as _DEBUG
from calibre.gui2 import choose_dir, error_dialog, open_url, question_dialog
from calibre.gui2.dialogs.confirm_delete import confirm
from calibre.utils.config import JSONConfig
from qt.core import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QIcon,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSize,
    QSpinBox,
    Qt,
    QTableWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .common_utils import (
    CheckableTableWidgetItem,
    CustomColumnComboBox,
    ImageTitleLayout,
    KeyboardConfigDialog,
    PrefsViewerDialog,
    ProfileComboBox,
    ReadOnlyTableWidgetItem,
    ReadOnlyTextIconWidgetItem,
    SimpleComboBox,
    debug,
    get_icon,
)

if TYPE_CHECKING:
    from .action import KoboDevice, KoboUtilitiesAction

# Support for CreateNewCustomColumn was added in 5.35.0
try:
    from calibre.gui2.preferences.create_custom_column import CreateNewCustomColumn

    debug("CreateNewCustomColumn is supported")
    SUPPORTS_CREATE_CUSTOM_COLUMN = True
except ImportError:
    CreateNewCustomColumn: Any = object
    debug("CreateNewCustomColumn is not supported")
    SUPPORTS_CREATE_CUSTOM_COLUMN = False  # type: ignore[reportConstantRedefinition]

load_translations()


# Redefine the debug here so the jobs can see it.
DEBUG = _DEBUG

PREFS_NAMESPACE = "KoboUtilitiesPlugin"
PREFS_KEY_SETTINGS = "settings"

KEY_SCHEMA_VERSION = "SchemaVersion"
DEFAULT_SCHEMA_VERSION = 0.1

STORE_LIBRARIES = "libraries"
KEY_PROFILES = "profiles"
KEY_CURRENT_LOCATION_CUSTOM_COLUMN = "currentReadingLocationColumn"
KEY_PERCENT_READ_CUSTOM_COLUMN = "percentReadColumn"
KEY_RATING_CUSTOM_COLUMN = "ratingColumn"
KEY_LAST_READ_CUSTOM_COLUMN = "lastReadColumn"
KEY_TIME_SPENT_READING_COLUMN = "timeSpentReadingColumn"
KEY_REST_OF_BOOK_ESTIMATE_COLUMN = "restOfBookEstimateColumn"
KEY_STORE_ON_CONNECT = "storeOnConnect"
KEY_PROMPT_TO_STORE = "promptToStore"
KEY_STORE_IF_MORE_RECENT = "storeIfMoreRecent"
KEY_DO_NOT_STORE_IF_REOPENED = "doNotStoreIfReopened"

KEY_FOR_DEVICE = "forDevice"
KEY_INDIVIDUAL_DEVICE_OPTIONS = "individualDeviceOptions"

BACKUP_OPTIONS_STORE_NAME = "backupOptionsStore"
BOOKMARK_OPTIONS_STORE_NAME = "BookmarkOptions"
COMMON_OPTIONS_STORE_NAME = "commonOptionsStore"
CUSTOM_COLUMNS_STORE_NAME = "customColumnOptions"
METADATA_OPTIONS_STORE_NAME = "MetadataOptions"
READING_OPTIONS_STORE_NAME = "ReadingOptions"
STORE_OPTIONS_STORE_NAME = "storeOptionsStore"
FIXDUPLICATESHELVES_OPTIONS_STORE_NAME = "fixDuplicatesOptionsStore"
ORDERSERIESSHELVES_OPTIONS_STORE_NAME = "orderSeriesShelvesOptionsStore"
SETRELATEDBOOKS_OPTIONS_STORE_NAME = "setRelatedBooksOptionsStore"
GET_SHELVES_OPTIONS_STORE_NAME = "getShelvesOptionStore"
READING_POSITION_CHANGES_STORE_NAME = "readingPositionChangesStore"

KEY_STORE_BOOKMARK = "storeBookmarks"
KEY_DATE_TO_NOW = "setDateToNow"
KEY_CLEAR_IF_UNREAD = "clearIfUnread"
KEY_BACKGROUND_JOB = "backgroundJob"
KEY_SET_TITLE = "title"
KEY_USE_TITLE_SORT = "titleSort"
KEY_SET_AUTHOR = "author"
KEY_USE_AUTHOR_SORT = "authourSort"
KEY_SET_DESCRIPTION = "description"
KEY_DESCRIPTION_USE_TEMPLATE = "descriptionUseTemplate"
KEY_DESCRIPTION_TEMPLATE = "descriptionTemplate"
KEY_SET_PUBLISHER = "publisher"
KEY_SET_RATING = "rating"
KEY_SET_SERIES = "series"
KEY_SET_SUBTITLE = "subtitle"
KEY_SUBTITLE_TEMPLATE = "subtitleTemplate"
KEY_USE_PLUGBOARD = "usePlugboard"
KEY_UDPATE_KOBO_EPUBS = "update_KoboEpubs"
KEY_SET_READING_STATUS = "setRreadingStatus"
KEY_READING_STATUS = "readingStatus"
KEY_SET_PUBLISHED_DATE = "published_date"
KEY_SET_ISBN = "isbn"
KEY_SET_LANGUAGE = "language"
KEY_SET_READING_DIRECTION = "set_reading_direction"
KEY_READING_DIRECTION = "reading_direction"
KEY_SYNC_DATE = "set_sync_date"
KEY_SYNC_DATE_COLUMN = "sync_date_library_date"
KEY_RESET_POSITION = "resetPosition"

KEY_CREATE_ANALYTICSEVENTS_TRIGGER = "createAnalyticsEventsTrigger"
KEY_DELETE_ANALYTICSEVENTS_TRIGGER = "deleteAnalyticsEventsTrigger"

KEY_REMOVE_FULLSIZE_COVERS = "remove_fullsize_covers"

KEY_COVERS_BLACKANDWHITE = "blackandwhite"
KEY_COVERS_DITHERED = "dithered_covers"
KEY_COVERS_KEEP_ASPECT_RATIO = "keep_cover_aspect"
KEY_COVERS_LETTERBOX = "letterbox"
KEY_COVERS_LETTERBOX_COLOR = "letterbox_color"
KEY_COVERS_PNG = "png_covers"
KEY_COVERS_UPDLOAD_KEPUB = "kepub_covers"

KEY_READING_FONT_FAMILY = "readingFontFamily"
KEY_READING_ALIGNMENT = "readingAlignment"
KEY_READING_FONT_SIZE = "readingFontSize"
KEY_READING_LINE_HEIGHT = "readingLineHeight"
KEY_READING_LEFT_MARGIN = "readingLeftMargin"
KEY_READING_RIGHT_MARGIN = "readingRightMargin"
KEY_READING_LOCK_MARGINS = "lockMargins"
KEY_UPDATE_CONFIG_FILE = "updateConfigFile"
KEY_DO_NOT_UPDATE_IF_SET = "doNotUpdateIfSet"

KEY_BUTTON_ACTION_DEVICE = "buttonActionDevice"
KEY_BUTTON_ACTION_LIBRARY = "buttonActionLibrary"

KEY_KEEP_NEWEST_SHELF = "keepNewestShelf"
KEY_PURGE_SHELVES = "purgeShelves"

KEY_SORT_DESCENDING = "sortDescending"
KEY_SORT_UPDATE_CONFIG = "updateConfig"

KEY_ORDER_SHELVES_SERIES = 0
KEY_ORDER_SHELVES_TYPE = "orderShelvesType"

KEY_ORDER_SHELVES_BY_SERIES = 0
KEY_ORDER_SHELVES_PUBLISHED = 1
KEY_ORDER_SHELVES_BY = "orderShelvesBy"

KEY_RELATED_BOOKS_SERIES = 0
KEY_RELATED_BOOKS_AUTHORS = 1
KEY_RELATED_BOOKS_TYPE = "relatedBooksType"

KEY_REMOVE_ANNOT_ALL = 0
KEY_REMOVE_ANNOT_SELECTED = 1
KEY_REMOVE_ANNOT_NOBOOK = 2
KEY_REMOVE_ANNOT_EMPTY = 3
KEY_REMOVE_ANNOT_NONEMPTY = 4
KEY_REMOVE_ANNOT_ACTION = "removeAnnotAction"

KEY_DO_DAILY_BACKUP = "doDailyBackp"
KEY_BACKUP_EACH_CONNECTION = "backupEachCOnnection"
KEY_BACKUP_COPIES_TO_KEEP = "backupCopiesToKeepSpin"
KEY_BACKUP_DEST_DIRECTORY = "backupDestDirectory"
KEY_BACKUP_ZIP_DATABASE = "backupZipDatabase"

KEY_SHELVES_CUSTOM_COLUMN = "shelvesColumn"
KEY_ALL_BOOKS = "allBooks"
KEY_REPLACE_SHELVES = "replaceShelves"

KEY_SELECT_BOOKS_IN_LIBRARY = "selectBooksInLibrary"
KEY_UPDATE_GOODREADS_PROGRESS = "updeateGoodreadsProgress"

TOKEN_ANY_DEVICE = "*Any Device"  # noqa: S105
TOKEN_CLEAR_SUBTITLE = "*Clear*"  # noqa: S105
TOKEN_FILE_TIMESTAMP = "*filetimestamp"  # noqa: S105
OTHER_SORTS = {TOKEN_FILE_TIMESTAMP: _("* File timestamp")}

STORE_DEVICES = "Devices"
# Devices store consists of:
# 'Devices': { 'dev_uuid': {'type':'xxx', 'uuid':'xxx', 'name:'xxx', 'location_code':'main',
#                           'active':True, 'collections':False} ,
# For iTunes
#              'iTunes':   {'type':'iTunes', 'uuid':iTunes', 'name':'iTunes', 'location_code':'',
#                           'active':True, 'collections':False}, ...}
DEFAULT_DEVICES_VALUES = {}

BOOKMARK_OPTIONS_DEFAULTS = {
    KEY_STORE_BOOKMARK: True,
    KEY_READING_STATUS: True,
    KEY_DATE_TO_NOW: True,
    KEY_SET_RATING: True,
    KEY_CLEAR_IF_UNREAD: False,
    KEY_BACKGROUND_JOB: False,
    KEY_STORE_IF_MORE_RECENT: False,
    KEY_DO_NOT_STORE_IF_REOPENED: False,
}
METADATA_OPTIONS_DEFAULTS = {
    KEY_SET_TITLE: False,
    KEY_SET_AUTHOR: False,
    KEY_SET_DESCRIPTION: False,
    KEY_DESCRIPTION_USE_TEMPLATE: False,
    KEY_DESCRIPTION_TEMPLATE: None,
    KEY_SET_PUBLISHER: False,
    KEY_SET_RATING: False,
    KEY_SET_SERIES: False,
    KEY_SET_READING_STATUS: False,
    KEY_READING_STATUS: -1,
    KEY_SET_PUBLISHED_DATE: False,
    KEY_SET_ISBN: False,
    KEY_SET_LANGUAGE: False,
    KEY_RESET_POSITION: False,
    KEY_USE_PLUGBOARD: False,
    KEY_USE_TITLE_SORT: False,
    KEY_USE_AUTHOR_SORT: False,
    KEY_SET_SUBTITLE: False,
    KEY_SUBTITLE_TEMPLATE: None,
    KEY_UDPATE_KOBO_EPUBS: False,
    KEY_SET_READING_DIRECTION: False,
    KEY_READING_DIRECTION: "Default",
    KEY_SYNC_DATE: False,
    KEY_SYNC_DATE_COLUMN: "timestamp",
}
READING_OPTIONS_DEFAULTS = {
    KEY_READING_FONT_FAMILY: "Georgia",
    KEY_READING_ALIGNMENT: "Off",
    KEY_READING_FONT_SIZE: 22,
    KEY_READING_LINE_HEIGHT: 1.3,
    KEY_READING_LEFT_MARGIN: 3,
    KEY_READING_RIGHT_MARGIN: 3,
    KEY_READING_LOCK_MARGINS: False,
    KEY_UPDATE_CONFIG_FILE: False,
    KEY_DO_NOT_UPDATE_IF_SET: False,
}
STORE_OPTIONS_DEFAULTS = {
    KEY_STORE_ON_CONNECT: False,
    KEY_PROMPT_TO_STORE: True,
    KEY_STORE_IF_MORE_RECENT: False,
    KEY_DO_NOT_STORE_IF_REOPENED: False,
}
COMMON_OPTIONS_DEFAULTS = {
    KEY_BUTTON_ACTION_DEVICE: "",
    KEY_BUTTON_ACTION_LIBRARY: "",
    KEY_INDIVIDUAL_DEVICE_OPTIONS: False,
}
OLD_COMMON_OPTIONS_DEFAULTS = {
    KEY_STORE_ON_CONNECT: False,
    KEY_PROMPT_TO_STORE: True,
    KEY_STORE_IF_MORE_RECENT: False,
    KEY_DO_NOT_STORE_IF_REOPENED: False,
    KEY_BUTTON_ACTION_DEVICE: "",
    KEY_BUTTON_ACTION_LIBRARY: "",
}

FIXDUPLICATESHELVES_OPTIONS_DEFAULTS = {
    KEY_KEEP_NEWEST_SHELF: True,
    KEY_PURGE_SHELVES: False,
}

ORDERSERIESSHELVES_OPTIONS_DEFAULTS = {
    KEY_SORT_DESCENDING: False,
    KEY_SORT_UPDATE_CONFIG: True,
    KEY_ORDER_SHELVES_TYPE: KEY_ORDER_SHELVES_SERIES,
    KEY_ORDER_SHELVES_BY: KEY_ORDER_SHELVES_BY_SERIES,
}

SETRELATEDBOOKS_OPTIONS_DEFAULTS = {
    KEY_RELATED_BOOKS_TYPE: KEY_RELATED_BOOKS_SERIES,
}

BACKUP_OPTIONS_DEFAULTS = {
    KEY_DO_DAILY_BACKUP: False,
    KEY_BACKUP_EACH_CONNECTION: False,
    KEY_BACKUP_COPIES_TO_KEEP: 5,
    KEY_BACKUP_DEST_DIRECTORY: "",
    KEY_BACKUP_ZIP_DATABASE: True,
}

GET_SHELVES_OPTIONS_DEFAULTS = {
    KEY_SHELVES_CUSTOM_COLUMN: None,
    KEY_ALL_BOOKS: True,
    KEY_REPLACE_SHELVES: True,
}

CUSTOM_COLUMNS_OPTIONS_DEFAULTS = {
    KEY_CURRENT_LOCATION_CUSTOM_COLUMN: None,
    KEY_PERCENT_READ_CUSTOM_COLUMN: None,
    KEY_RATING_CUSTOM_COLUMN: None,
    KEY_LAST_READ_CUSTOM_COLUMN: None,
    KEY_TIME_SPENT_READING_COLUMN: None,
    KEY_REST_OF_BOOK_ESTIMATE_COLUMN: None,
}

DEFAULT_PROFILE_VALUES = {
    KEY_FOR_DEVICE: None,
    STORE_OPTIONS_STORE_NAME: STORE_OPTIONS_DEFAULTS,
}
DEFAULT_LIBRARY_VALUES = {
    KEY_PROFILES: {"Default": DEFAULT_PROFILE_VALUES},
    KEY_SCHEMA_VERSION: DEFAULT_SCHEMA_VERSION,
}

READING_POSITION_CHANGES_DEFAULTS = {
    KEY_SELECT_BOOKS_IN_LIBRARY: False,
    KEY_UPDATE_GOODREADS_PROGRESS: False,
}

CUSTOM_COLUMN_DEFAULT_LOOKUP_READING_LOCATION = "#kobo_reading_location"
CUSTOM_COLUMN_DEFAULT_LOOKUP_LAST_READ = "#kobo_last_read"
CUSTOM_COLUMN_DEFAULT_LOOKUP_RATING = "#kobo_rating"
CUSTOM_COLUMN_DEFAULT_LOOKUP_PERCENT_READ = "#kobo_percent_read"
CUSTOM_COLUMN_DEFAULT_LOOKUP_TIME_SPENT_READING = "#kobo_time_spent_reading"
CUSTOM_COLUMN_DEFAULT_LOOKUP_REST_OF_BOOK_ESTIMATE = "#kobo_rest_of_book_estimate"
CUSTOM_COLUMN_DEFAULTS = {
    CUSTOM_COLUMN_DEFAULT_LOOKUP_READING_LOCATION: {
        "column_heading": _("Kobo reading location"),
        "datatype": "text",
        "description": _("Kobo reading location from the device."),
        "columns_list": "avail_text_columns",
        "config_label": _("Current reading location column:"),
        "config_tool_tip": _(
            "Select a custom column to store the current reading location. The column type must be 'text' or 'comments'. Leave this blank if you do not want to store or restore the current reading location."
        ),
    },
    CUSTOM_COLUMN_DEFAULT_LOOKUP_PERCENT_READ: {
        "column_heading": _("Kobo % read"),
        "datatype": "int",
        "description": _("Percentage read for the book"),
        "columns_list": "avail_number_columns",
        "config_label": _("Percent read column:"),
        "config_tool_tip": _(
            "Column used to store the current percent read. The column type must be 'integer' or 'float'. Leave this blank if you do not want to store or restore the percentage read."
        ),
    },
    CUSTOM_COLUMN_DEFAULT_LOOKUP_RATING: {
        "column_heading": _("Kobo rating"),
        "datatype": "rating",
        "description": _("Rating for the book on the Kobo device."),
        "columns_list": "avail_rating_columns",
        "config_label": _("Rating column:"),
        "config_tool_tip": _(
            "Column used to store the rating. The column type must be a 'integer'. Leave this blank if you do not want to store or restore the rating."
        ),
    },
    CUSTOM_COLUMN_DEFAULT_LOOKUP_LAST_READ: {
        "column_heading": _("Kobo last read"),
        "datatype": "datetime",
        "description": _("When the book was last read on the Kobo device."),
        "columns_list": "avail_date_columns",
        "config_label": _("Last read column:"),
        "config_tool_tip": _(
            "Column used to store when the book was last read. The column type must be a 'Date'. Leave this blank if you do not want to store the last read timestamp."
        ),
    },
    CUSTOM_COLUMN_DEFAULT_LOOKUP_TIME_SPENT_READING: {
        "column_heading": _("Kobo time spent reading"),
        "datatype": "int",
        "description": _("The time already spent reading the book, in seconds."),
        "columns_list": "avail_number_columns",
        "config_label": _("Time spent reading column:"),
        "config_tool_tip": _(
            "Column used to store how much time was spent reading the book, in seconds. The column type must be 'integer'. Leave this blank if you do not want to store the time spent reading the book."
        ),
    },
    CUSTOM_COLUMN_DEFAULT_LOOKUP_REST_OF_BOOK_ESTIMATE: {
        "column_heading": _("Kobo rest of book estimate"),
        "datatype": "int",
        "description": _("The estimate of the time left to read the book, in seconds."),
        "columns_list": "avail_number_columns",
        "config_label": _("Rest of book estimate column:"),
        "config_tool_tip": _(
            "Column used to store the estimate of how much time is left in the book, in seconds. The column type must be 'integer'. Leave this blank if you do not want to store the estimate of the time left."
        ),
    },
}

# This is where all preferences for this plugin will be stored
plugin_prefs = JSONConfig("plugins/Kobo Utilities")

# Set defaults
plugin_prefs.defaults[BOOKMARK_OPTIONS_STORE_NAME] = BOOKMARK_OPTIONS_DEFAULTS
plugin_prefs.defaults[METADATA_OPTIONS_STORE_NAME] = METADATA_OPTIONS_DEFAULTS
plugin_prefs.defaults[READING_OPTIONS_STORE_NAME] = READING_OPTIONS_DEFAULTS
plugin_prefs.defaults[COMMON_OPTIONS_STORE_NAME] = COMMON_OPTIONS_DEFAULTS
plugin_prefs.defaults[FIXDUPLICATESHELVES_OPTIONS_STORE_NAME] = (
    FIXDUPLICATESHELVES_OPTIONS_DEFAULTS
)
plugin_prefs.defaults[ORDERSERIESSHELVES_OPTIONS_STORE_NAME] = (
    ORDERSERIESSHELVES_OPTIONS_DEFAULTS
)
plugin_prefs.defaults[SETRELATEDBOOKS_OPTIONS_STORE_NAME] = (
    SETRELATEDBOOKS_OPTIONS_DEFAULTS
)
plugin_prefs.defaults[STORE_LIBRARIES] = {}
plugin_prefs.defaults[BACKUP_OPTIONS_STORE_NAME] = BACKUP_OPTIONS_DEFAULTS
plugin_prefs.defaults[GET_SHELVES_OPTIONS_STORE_NAME] = GET_SHELVES_OPTIONS_DEFAULTS
plugin_prefs.defaults[STORE_DEVICES] = DEFAULT_DEVICES_VALUES
plugin_prefs.defaults[CUSTOM_COLUMNS_STORE_NAME] = CUSTOM_COLUMNS_OPTIONS_DEFAULTS
plugin_prefs.defaults[STORE_OPTIONS_STORE_NAME] = STORE_OPTIONS_DEFAULTS
plugin_prefs.defaults[READING_POSITION_CHANGES_STORE_NAME] = (
    READING_POSITION_CHANGES_DEFAULTS
)


def get_plugin_pref(store_name: str, option: str):
    debug("start - store_name='%s', option='%s'" % (store_name, option))
    c = plugin_prefs[store_name]
    default_value = plugin_prefs.defaults[store_name][option]
    return c.get(option, default_value)


def get_plugin_prefs(store_name: str, fill_defaults: bool = False):
    if fill_defaults:
        c = get_prefs(plugin_prefs, store_name)
    else:
        c = plugin_prefs[store_name]
    return c


def get_prefs(prefs_store: Optional[Dict], store_name: str):
    debug("start - store_name='%s'" % (store_name,))
    store = {}
    if prefs_store is not None and store_name in prefs_store:
        for key in plugin_prefs.defaults[store_name]:
            store[key] = prefs_store[store_name].get(
                key, plugin_prefs.defaults[store_name][key]
            )
    else:
        store = plugin_prefs.defaults[store_name]
    return store


def get_pref(store, store_name, option, defaults=None):
    if defaults:
        default_value = defaults[option]
    else:
        default_value = plugin_prefs.defaults[store_name][option]
    return store.get(option, default_value)


def migrate_library_config_if_required(db, library_config):
    debug("start")
    schema_version = library_config.get(KEY_SCHEMA_VERSION, 0)
    if schema_version == DEFAULT_SCHEMA_VERSION:
        return
    # We have changes to be made - mark schema as updated
    library_config[KEY_SCHEMA_VERSION] = DEFAULT_SCHEMA_VERSION

    # Any migration code in future will exist in here.
    if schema_version <= 0.1 and "profiles" not in library_config:
        print("Migrating Kobo Utilities library config")
        profile_config = {}
        profile_config[KEY_FOR_DEVICE] = TOKEN_ANY_DEVICE

        old_store_prefs = plugin_prefs[COMMON_OPTIONS_STORE_NAME]
        store_prefs = {}
        store_prefs[KEY_STORE_ON_CONNECT] = get_pref(
            old_store_prefs,
            COMMON_OPTIONS_STORE_NAME,
            KEY_STORE_ON_CONNECT,
            defaults=OLD_COMMON_OPTIONS_DEFAULTS,
        )
        store_prefs[KEY_PROMPT_TO_STORE] = get_pref(
            old_store_prefs,
            COMMON_OPTIONS_STORE_NAME,
            KEY_PROMPT_TO_STORE,
            defaults=OLD_COMMON_OPTIONS_DEFAULTS,
        )
        store_prefs[KEY_STORE_IF_MORE_RECENT] = get_pref(
            old_store_prefs,
            COMMON_OPTIONS_STORE_NAME,
            KEY_STORE_IF_MORE_RECENT,
            defaults=OLD_COMMON_OPTIONS_DEFAULTS,
        )
        store_prefs[KEY_DO_NOT_STORE_IF_REOPENED] = get_pref(
            old_store_prefs,
            COMMON_OPTIONS_STORE_NAME,
            KEY_DO_NOT_STORE_IF_REOPENED,
            defaults=OLD_COMMON_OPTIONS_DEFAULTS,
        )
        debug("store_prefs:", store_prefs)

        column_prefs = {}
        if library_config.get("currentReadingLocationColumn"):
            column_prefs[KEY_CURRENT_LOCATION_CUSTOM_COLUMN] = library_config[
                "currentReadingLocationColumn"
            ]
            del library_config["currentReadingLocationColumn"]
        if library_config.get("precentReadColumn"):
            column_prefs[KEY_PERCENT_READ_CUSTOM_COLUMN] = library_config[
                "precentReadColumn"
            ]
            del library_config["precentReadColumn"]
        if library_config.get("ratingColumn"):
            column_prefs[KEY_RATING_CUSTOM_COLUMN] = library_config["ratingColumn"]
            del library_config["ratingColumn"]
        if library_config.get("lastReadColumn"):
            column_prefs[KEY_LAST_READ_CUSTOM_COLUMN] = library_config["lastReadColumn"]
            del library_config["lastReadColumn"]
        debug("column_prefs:", column_prefs)
        if len(column_prefs) > 0:
            profile_config[CUSTOM_COLUMNS_STORE_NAME] = column_prefs
            debug("profile_config:", profile_config)
            profile_config[STORE_OPTIONS_STORE_NAME] = store_prefs
            new_profiles = {"Migrated": profile_config}
            library_config[KEY_PROFILES] = new_profiles
        debug("library_config:", library_config)

    set_library_config(db, library_config)


def get_library_config(db):
    library_config = None

    if library_config is None:
        library_config = db.prefs.get_namespaced(
            PREFS_NAMESPACE, PREFS_KEY_SETTINGS, copy.deepcopy(DEFAULT_LIBRARY_VALUES)
        )
    migrate_library_config_if_required(db, library_config)
    debug("library_config:", library_config)
    return library_config


def get_profile_info(db, profile_name):
    library_config = get_library_config(db)
    profiles = library_config.get(KEY_PROFILES, {})
    return profiles.get(profile_name, DEFAULT_PROFILE_VALUES)


def get_book_profile_for_device(db, device_uuid, use_any_device=False):
    library_config = get_library_config(db)
    profiles_map = library_config.get(KEY_PROFILES, None)
    selected_profile = None
    if profiles_map is not None:
        for profile_name, profile_info in profiles_map.items():
            if profile_info[KEY_FOR_DEVICE] == device_uuid:
                profile_info["profileName"] = profile_name
                selected_profile = profile_info
                break
            if use_any_device and profile_info[KEY_FOR_DEVICE] == TOKEN_ANY_DEVICE:
                profile_info["profileName"] = profile_name
                selected_profile = profile_info

    if selected_profile is not None:
        selected_profile[STORE_OPTIONS_STORE_NAME] = get_prefs(
            selected_profile, STORE_OPTIONS_STORE_NAME
        )
    return selected_profile


def get_device_name(device_uuid: str, default_name: str = _("(Unknown device)")) -> str:
    device = get_device_config(device_uuid)
    return cast("str", device["name"]) if device else default_name


def get_device_config(device_uuid) -> Optional[Dict]:
    return plugin_prefs[STORE_DEVICES].get(device_uuid, None)


def set_library_config(db, library_config):
    debug("library_config:", library_config)
    db.prefs.set_namespaced(PREFS_NAMESPACE, PREFS_KEY_SETTINGS, library_config)


class ProfilesTab(QWidget):
    def __init__(self, parent_dialog, plugin_action: KoboUtilitiesAction):
        self.parent_dialog = parent_dialog
        QWidget.__init__(self)

        self.plugin_action = plugin_action
        self.help_anchor = "ConfigurationDialog"
        self.library_config = get_library_config(self.plugin_action.gui.current_db)
        debug("self.library_config", self.library_config)
        self.profiles = self.library_config.get(KEY_PROFILES, {})
        self.current_device_profile = (
            self.plugin_action.device.profile
            if self.plugin_action.device is not None
            else None
        )
        self.profile_name = (
            self.current_device_profile["profileName"]
            if self.current_device_profile
            else None
        )

        layout = QVBoxLayout(self)
        self.setLayout(layout)

        # -------- Lists configuration ---------
        select_profile_layout = QHBoxLayout()
        layout.addLayout(select_profile_layout)
        profiles_label = QLabel(_("Profiles:"), self)
        select_profile_layout.addWidget(profiles_label)
        self.select_profile_combo = ProfileComboBox(
            self, self.profiles, self.profile_name
        )
        self.select_profile_combo.setMinimumSize(150, 20)
        self.select_profile_combo.currentIndexChanged.connect(
            self._select_profile_combo_changed
        )
        select_profile_layout.addWidget(self.select_profile_combo)
        self.add_profile_button = QToolButton(self)
        self.add_profile_button.setToolTip(_("Add profile"))
        self.add_profile_button.setIcon(QIcon(I("plus.png")))
        self.add_profile_button.clicked.connect(self.add_profile)
        select_profile_layout.addWidget(self.add_profile_button)
        self.delete_profile_button = QToolButton(self)
        self.delete_profile_button.setToolTip(_("Delete profile"))
        self.delete_profile_button.setIcon(QIcon(I("minus.png")))
        self.delete_profile_button.clicked.connect(self.delete_profile)
        select_profile_layout.addWidget(self.delete_profile_button)
        self.rename_profile_button = QToolButton(self)
        self.rename_profile_button.setToolTip(_("Rename profile"))
        self.rename_profile_button.setIcon(QIcon(I("edit-undo.png")))
        self.rename_profile_button.clicked.connect(self.rename_profile)
        select_profile_layout.addWidget(self.rename_profile_button)
        select_profile_layout.insertStretch(-1)

        device_layout = QHBoxLayout()
        layout.addLayout(device_layout)
        device_label = QLabel(_("&Device this profile is for:"), self)
        device_label.setToolTip(_("Select the device this profile is for."))
        self.device_combo = DeviceColumnComboBox(self)
        device_label.setBuddy(self.device_combo)
        device_layout.addWidget(device_label)
        device_layout.addWidget(self.device_combo)

        custom_column_group = QGroupBox(_("Custom columns"), self)
        layout.addWidget(custom_column_group)
        options_layout = QGridLayout()
        custom_column_group.setLayout(options_layout)

        self.custom_columns = {}
        self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_READING_LOCATION] = {
            "current_columns": self.get_text_custom_columns
        }
        self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_PERCENT_READ] = {
            "current_columns": self.get_number_custom_columns
        }
        self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_RATING] = {
            "current_columns": self.get_rating_custom_columns
        }
        self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_LAST_READ] = {
            "current_columns": self.get_date_custom_columns
        }
        self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_TIME_SPENT_READING] = {
            "current_columns": self.get_number_custom_columns
        }
        self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_REST_OF_BOOK_ESTIMATE] = {
            "current_columns": self.get_number_custom_columns
        }

        self.current_Location_combo = self.create_custom_column_controls(
            options_layout, CUSTOM_COLUMN_DEFAULT_LOOKUP_READING_LOCATION, 1
        )
        self.percent_read_combo = self.create_custom_column_controls(
            options_layout, CUSTOM_COLUMN_DEFAULT_LOOKUP_PERCENT_READ, 2
        )
        self.rating_combo = self.create_custom_column_controls(
            options_layout, CUSTOM_COLUMN_DEFAULT_LOOKUP_RATING, 3
        )
        self.last_read_combo = self.create_custom_column_controls(
            options_layout, CUSTOM_COLUMN_DEFAULT_LOOKUP_LAST_READ, 4
        )
        self.time_spent_reading_combo = self.create_custom_column_controls(
            options_layout, CUSTOM_COLUMN_DEFAULT_LOOKUP_TIME_SPENT_READING, 5
        )
        self.rest_of_book_estimate_combo = self.create_custom_column_controls(
            options_layout, CUSTOM_COLUMN_DEFAULT_LOOKUP_REST_OF_BOOK_ESTIMATE, 6
        )

        auto_store_group = QGroupBox(_("Store on connect"), self)
        layout.addWidget(auto_store_group)
        options_layout = QGridLayout()
        auto_store_group.setLayout(options_layout)

        self.store_on_connect_checkbox = QCheckBox(
            _("Store current bookmarks/reading position on connect"), self
        )
        self.store_on_connect_checkbox.setToolTip(
            _(
                "When this is checked, the library will be updated with the current reading position for all books on the device."
            )
        )
        self.store_on_connect_checkbox.clicked.connect(
            self.store_on_connect_checkbox_clicked
        )
        options_layout.addWidget(self.store_on_connect_checkbox, 0, 0, 1, 3)

        self.prompt_to_store_checkbox = QCheckBox(
            _("Prompt to store any changes"), self
        )
        self.prompt_to_store_checkbox.setToolTip(
            _(
                "Enable this to be prompted to save the changed reading positions after an automatic store is done."
            )
        )
        options_layout.addWidget(self.prompt_to_store_checkbox, 1, 0, 1, 1)

        self.store_if_more_recent_checkbox = QCheckBox(_("Only if more recent"), self)
        self.store_if_more_recent_checkbox.setToolTip(
            _(
                "Only store the reading position if the last read timestamp on the device is more recent than in the library."
            )
        )
        options_layout.addWidget(self.store_if_more_recent_checkbox, 1, 1, 1, 1)

        self.do_not_store_if_reopened_checkbox = QCheckBox(
            _("Not if finished in library"), self
        )
        self.do_not_store_if_reopened_checkbox.setToolTip(
            _(
                "Do not store the reading position if the library has the book as finished. This is if the percent read is 100%."
            )
        )
        options_layout.addWidget(self.do_not_store_if_reopened_checkbox, 1, 2, 1, 1)

        layout.addWidget(
            QLabel(
                _(
                    "You can use this site to download the latest version of Kobo firmware:"
                )
            )
        )
        fwurl = "https://pgaskin.net/KoboStuff/kobofirmware.html"
        fwsite = QLabel(f'<a href="{fwurl}">{fwurl}</a>')
        fwsite.setTextInteractionFlags(
            Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard
        )
        fwsite.linkActivated.connect(open_url)
        layout.addWidget(fwsite)

        layout.addStretch(1)

    def create_custom_column_controls(
        self, options_layout, custom_col_name, row_number=1
    ):
        current_Location_label = QLabel(
            CUSTOM_COLUMN_DEFAULTS[custom_col_name]["config_label"], self
        )
        current_Location_label.setToolTip(
            CUSTOM_COLUMN_DEFAULTS[custom_col_name]["config_tool_tip"]
        )
        create_column_callback = (
            partial(self.create_custom_column, custom_col_name)
            if self.parent_dialog.supports_create_custom_column
            else None
        )
        avail_columns = self.custom_columns[custom_col_name]["current_columns"]()
        custom_column_combo = CustomColumnComboBox(
            self, avail_columns, create_column_callback=create_column_callback
        )
        current_Location_label.setBuddy(custom_column_combo)
        options_layout.addWidget(current_Location_label, row_number, 0, 1, 1)
        options_layout.addWidget(custom_column_combo, row_number, 1, 1, 1)
        self.custom_columns[custom_col_name]["combo_box"] = custom_column_combo

        return custom_column_combo

    def _select_profile_combo_changed(self):
        self.persist_profile_config()
        self.refresh_current_profile_info()

    def store_on_connect_checkbox_clicked(self, checked):
        self.prompt_to_store_checkbox.setEnabled(checked)
        self.store_if_more_recent_checkbox.setEnabled(checked)
        self.do_not_store_if_reopened_checkbox.setEnabled(checked)

    # Called by Calibre before save_settings
    def validate(self):
        debug("BEGIN Validate")
        valid = True
        debug("END Validate, status = %s" % valid)
        return valid

    def add_profile(self) -> None:
        debug("Start")
        # Display a prompt allowing user to specify a new profile
        new_profile_name, ok = QInputDialog.getText(
            self,
            _("Add new profile"),
            _("Enter a unique display name for this profile:"),
            text="Default",
        )
        if not ok:
            # Operation cancelled
            return
        new_profile_name = str(new_profile_name).strip()
        # Verify it does not clash with any other profiles in the profile
        for profile_name in self.profiles:
            debug("existing profile: ", profile_name)
            if profile_name.lower() == new_profile_name.lower():
                error_dialog(
                    self,
                    _("Add failed"),
                    _("A profile with the same name already exists"),
                    show=True,
                )
                return

        # As we are about to switch profile, persist the current profiles details if any
        self.persist_profile_config()
        self.profile_name = new_profile_name
        self.profiles[new_profile_name] = copy.deepcopy(DEFAULT_PROFILE_VALUES)
        debug("new profile: ", self.profiles[new_profile_name])
        # Now update the profiles combobox
        self.select_profile_combo.populate_combo(self.profiles, new_profile_name)
        self.refresh_current_profile_info()
        debug("End")

    def rename_profile(self) -> None:
        if not self.profile_name:
            return
        # Display a prompt allowing user to specify a rename profile
        old_profile_name = self.profile_name
        new_profile_name, ok = QInputDialog.getText(
            self,
            _("Rename profile"),
            _("Enter a new display name for this profile:"),
            text=old_profile_name,
        )
        if not ok:
            # Operation cancelled
            return
        new_profile_name = str(new_profile_name).strip()
        if new_profile_name == old_profile_name:
            return
        # Verify it does not clash with any other profiles in the profile
        for profile_name in self.profiles:
            if profile_name == old_profile_name:
                continue
            if profile_name.lower() == new_profile_name.lower():
                error_dialog(
                    self,
                    _("Add failed"),
                    _("A profile with the same name already exists"),
                    show=True,
                    show_copy_button=False,
                )
                return

        # As we are about to rename profile, persist the current profiles details if any
        self.persist_profile_config()
        self.profiles[new_profile_name] = self.profiles[old_profile_name]
        del self.profiles[old_profile_name]
        self.profile_name = new_profile_name
        # Now update the profiles combobox
        self.select_profile_combo.populate_combo(self.profiles, new_profile_name)
        self.refresh_current_profile_info()

    def delete_profile(self) -> None:
        if not self.profile_name:
            return
        if len(self.profiles) == 1:
            error_dialog(
                self,
                _("Cannot delete"),
                _("You must have at least one profile"),
                show=True,
                show_copy_button=False,
            )
            return
        if not confirm(
            _(
                "Do you want to delete the profile named '{0}'".format(
                    self.profile_name
                )
            ),
            "reading_profile_delete_profile",
            self,
        ):
            return
        del self.profiles[self.profile_name]
        # Now update the profiles combobox
        self.select_profile_combo.populate_combo(self.profiles)
        self.refresh_current_profile_info()

    def refresh_current_profile_info(self):
        debug("Start")
        # Get configuration for the selected profile
        self.profile_name = str(self.select_profile_combo.currentText()).strip()
        profile_map = get_profile_info(
            self.plugin_action.gui.current_db, self.profile_name
        )

        device_uuid = profile_map.get(KEY_FOR_DEVICE, None)

        column_prefs = profile_map.get(
            CUSTOM_COLUMNS_STORE_NAME, CUSTOM_COLUMNS_OPTIONS_DEFAULTS
        )
        current_Location_column = get_pref(
            column_prefs, CUSTOM_COLUMNS_STORE_NAME, KEY_CURRENT_LOCATION_CUSTOM_COLUMN
        )
        percent_read_column = get_pref(
            column_prefs, CUSTOM_COLUMNS_STORE_NAME, KEY_PERCENT_READ_CUSTOM_COLUMN
        )
        rating_column = get_pref(
            column_prefs, CUSTOM_COLUMNS_STORE_NAME, KEY_RATING_CUSTOM_COLUMN
        )
        last_read_column = get_pref(
            column_prefs, CUSTOM_COLUMNS_STORE_NAME, KEY_LAST_READ_CUSTOM_COLUMN
        )
        time_spent_reading_column = get_pref(
            column_prefs,
            CUSTOM_COLUMNS_STORE_NAME,
            KEY_TIME_SPENT_READING_COLUMN,
        )
        rest_of_book_estimate_column = get_pref(
            column_prefs,
            CUSTOM_COLUMNS_STORE_NAME,
            KEY_REST_OF_BOOK_ESTIMATE_COLUMN,
        )

        store_prefs = profile_map.get(STORE_OPTIONS_STORE_NAME, STORE_OPTIONS_DEFAULTS)
        store_on_connect = get_pref(
            store_prefs, STORE_OPTIONS_STORE_NAME, KEY_STORE_ON_CONNECT
        )
        prompt_to_store = get_pref(
            store_prefs, STORE_OPTIONS_STORE_NAME, KEY_PROMPT_TO_STORE
        )
        store_if_more_recent = get_pref(
            store_prefs, STORE_OPTIONS_STORE_NAME, KEY_STORE_IF_MORE_RECENT
        )
        do_not_store_if_reopened = get_pref(
            store_prefs, STORE_OPTIONS_STORE_NAME, KEY_DO_NOT_STORE_IF_REOPENED
        )

        # Display profile configuration in the controls
        self.current_Location_combo.populate_combo(
            self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_READING_LOCATION][
                "current_columns"
            ](),
            current_Location_column,
        )
        self.percent_read_combo.populate_combo(
            self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_PERCENT_READ][
                "current_columns"
            ](),
            percent_read_column,
        )
        self.rating_combo.populate_combo(
            self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_RATING][
                "current_columns"
            ](),
            rating_column,
        )
        self.last_read_combo.populate_combo(
            self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_LAST_READ][
                "current_columns"
            ](),
            last_read_column,
        )
        self.time_spent_reading_combo.populate_combo(
            self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_TIME_SPENT_READING][
                "current_columns"
            ](),
            time_spent_reading_column if time_spent_reading_column is not None else "",
        )
        self.rest_of_book_estimate_combo.populate_combo(
            self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_REST_OF_BOOK_ESTIMATE][
                "current_columns"
            ](),
            rest_of_book_estimate_column
            if rest_of_book_estimate_column is not None
            else "",
        )

        self.device_combo.populate_combo(
            self.parent_dialog.get_devices_list(), device_uuid
        )
        self.store_on_connect_checkbox.setCheckState(
            Qt.Checked if store_on_connect else Qt.Unchecked
        )
        self.prompt_to_store_checkbox.setCheckState(
            Qt.Checked if prompt_to_store else Qt.Unchecked
        )
        self.prompt_to_store_checkbox.setEnabled(store_on_connect)
        self.store_if_more_recent_checkbox.setCheckState(
            Qt.Checked if store_if_more_recent else Qt.Unchecked
        )
        self.store_if_more_recent_checkbox.setEnabled(store_on_connect)
        self.do_not_store_if_reopened_checkbox.setCheckState(
            Qt.Checked if do_not_store_if_reopened else Qt.Unchecked
        )
        self.do_not_store_if_reopened_checkbox.setEnabled(store_on_connect)

        debug("end")

    def persist_profile_config(self):
        debug("Start")
        if not self.profile_name:
            return

        profile_config = self.profiles[self.profile_name]
        debug("profile_config:", profile_config)

        profile_config[KEY_FOR_DEVICE] = self.device_combo.get_selected_device()

        store_prefs = {}
        store_prefs[KEY_STORE_ON_CONNECT] = (
            self.store_on_connect_checkbox.checkState() == Qt.Checked
        )
        store_prefs[KEY_PROMPT_TO_STORE] = (
            self.prompt_to_store_checkbox.checkState() == Qt.Checked
        )
        store_prefs[KEY_STORE_IF_MORE_RECENT] = (
            self.store_if_more_recent_checkbox.checkState() == Qt.Checked
        )
        store_prefs[KEY_DO_NOT_STORE_IF_REOPENED] = (
            self.do_not_store_if_reopened_checkbox.checkState() == Qt.Checked
        )
        profile_config[STORE_OPTIONS_STORE_NAME] = store_prefs
        debug("store_prefs:", store_prefs)

        column_prefs = {}
        column_prefs[KEY_CURRENT_LOCATION_CUSTOM_COLUMN] = (
            self.current_Location_combo.get_selected_column()
        )
        debug(
            "column_prefs[KEY_CURRENT_LOCATION_CUSTOM_COLUMN]:",
            column_prefs[KEY_CURRENT_LOCATION_CUSTOM_COLUMN],
        )
        column_prefs[KEY_PERCENT_READ_CUSTOM_COLUMN] = (
            self.percent_read_combo.get_selected_column()
        )
        column_prefs[KEY_RATING_CUSTOM_COLUMN] = self.rating_combo.get_selected_column()
        column_prefs[KEY_LAST_READ_CUSTOM_COLUMN] = (
            self.last_read_combo.get_selected_column()
        )
        column_prefs[KEY_TIME_SPENT_READING_COLUMN] = (
            self.time_spent_reading_combo.get_selected_column()
        )
        column_prefs[KEY_REST_OF_BOOK_ESTIMATE_COLUMN] = (
            self.rest_of_book_estimate_combo.get_selected_column()
        )
        profile_config[CUSTOM_COLUMNS_STORE_NAME] = column_prefs

        self.profiles[self.profile_name] = profile_config

        debug("end")

    def get_number_custom_columns(self):
        column_types = ["float", "int"]
        return self.get_custom_columns(column_types)

    def get_rating_custom_columns(self):
        column_types = ["rating", "int"]
        custom_columns = self.get_custom_columns(column_types)
        ratings_column_name = self.plugin_action.gui.library_view.model().orig_headers[
            "rating"
        ]
        custom_columns["rating"] = {"name": ratings_column_name}
        return custom_columns

    def get_text_custom_columns(self):
        column_types = ["text", "comments"]
        return self.get_custom_columns(column_types)

    def get_date_custom_columns(self):
        column_types = ["datetime"]
        return self.get_custom_columns(column_types)

    def get_custom_columns(self, column_types):
        if self.parent_dialog.supports_create_custom_column:
            custom_columns = self.parent_dialog.get_create_new_custom_column_instance.current_columns()
        else:
            custom_columns = self.plugin_action.gui.library_view.model().custom_columns
        available_columns = {}
        for key, column in custom_columns.items():
            typ = column["datatype"]
            if typ in column_types and not column["is_multiple"]:
                available_columns[key] = column
        return available_columns

    def create_custom_column(self, lookup_name):
        debug("lookup_name:", lookup_name)
        display_params = {
            "description": CUSTOM_COLUMN_DEFAULTS[lookup_name]["description"]
        }
        datatype = CUSTOM_COLUMN_DEFAULTS[lookup_name]["datatype"]
        column_heading = CUSTOM_COLUMN_DEFAULTS[lookup_name]["column_heading"]

        new_lookup_name = lookup_name

        create_new_custom_column_instance = (
            self.parent_dialog.get_create_new_custom_column_instance
        )
        result = create_new_custom_column_instance.create_column(
            new_lookup_name,
            column_heading,
            datatype,
            False,
            display=display_params,
            generate_unused_lookup_name=True,
            freeze_lookup_name=False,
        )
        debug("result:", result)
        if result[0] == CreateNewCustomColumn.Result.COLUMN_ADDED:
            self.custom_columns[lookup_name]["combo_box"].populate_combo(
                self.custom_columns[lookup_name]["current_columns"](), result[1]
            )
            return True

        return False


class DevicesTab(QWidget):
    def __init__(self, parent_dialog, plugin_action: KoboUtilitiesAction):
        self.current_device_info = None

        self.parent_dialog = parent_dialog
        QWidget.__init__(self)

        self.plugin_action = plugin_action
        self.gui = plugin_action.gui
        self._connected_device = plugin_action.device
        self.library_config = get_library_config(self.gui.current_db)

        self.individual_device_options = get_plugin_pref(
            COMMON_OPTIONS_STORE_NAME, KEY_INDIVIDUAL_DEVICE_OPTIONS
        )

        layout = QVBoxLayout()
        self.setLayout(layout)

        # -------- Device configuration ---------
        devices_group_box = QGroupBox(_("Devices:"), self)
        layout.addWidget(devices_group_box)
        devices_group_box_layout = QVBoxLayout()
        devices_group_box.setLayout(devices_group_box_layout)

        self.devices_table = DevicesTableWidget(self)
        # Note: Do not connect the itemSlectionChanged signale here. It gets done after the table is filled the first time.
        # self.devices_table.itemSelectionChanged.connect(self._devices_table_item_selection_changed)
        devices_group_box_layout.addWidget(self.devices_table)

        buttons_layout = QHBoxLayout()
        devices_group_box_layout.addLayout(buttons_layout)

        self.add_device_btn = QPushButton(_("Add connected device"), self)
        self.add_device_btn.setToolTip(
            _(
                "If you do not have a device connected currently, either plug one\n"
                "in now or exit the dialog and connect to folder/iTunes first"
            )
        )
        self.add_device_btn.setIcon(QIcon(I("plus.png")))
        self.add_device_btn.clicked.connect(self._add_device_clicked)
        buttons_layout.addWidget(self.add_device_btn, 1)

        self.rename_device_btn = QToolButton(self)
        self.rename_device_btn.setIcon(get_icon("edit-undo.png"))
        self.rename_device_btn.setToolTip(_("Rename the currently connected device"))
        self.rename_device_btn.clicked.connect(self._rename_device_clicked)
        self.rename_device_btn.setEnabled(False)
        buttons_layout.addWidget(self.rename_device_btn)

        self.delete_device_btn = QToolButton(self)
        self.delete_device_btn.setIcon(QIcon(I("trash.png")))
        self.delete_device_btn.setToolTip(_("Delete this device from the device list"))
        self.delete_device_btn.clicked.connect(self._delete_device_clicked)
        self.delete_device_btn.setEnabled(False)
        buttons_layout.addWidget(self.delete_device_btn)

        self.device_options_for_each_checkbox = QCheckBox(
            _("Configure options for each device"), self
        )
        self.device_options_for_each_checkbox.setToolTip(
            _("Selected this option to configure backup for each device.")
        )
        self.device_options_for_each_checkbox.clicked.connect(
            self.device_options_for_each_checkbox_clicked
        )
        if self.individual_device_options:
            self.device_options_for_each_checkbox.setCheckState(Qt.Checked)
        layout.addWidget(self.device_options_for_each_checkbox)

        options_layout = QGridLayout()
        self.do_daily_backp_checkbox = QCheckBox(
            _("Back up the device database daily"), self
        )
        self.do_daily_backp_checkbox.setToolTip(
            _(
                "If this is selected the plugin will back up the device database the first time it is connected each day."
            )
        )
        self.do_daily_backp_checkbox.clicked.connect(
            self.do_daily_backp_checkbox_clicked
        )
        options_layout.addWidget(self.do_daily_backp_checkbox, 0, 0, 1, 2)

        self.backup_each_connection_checkbox = QCheckBox(
            _("Back up the device database on each connection"), self
        )
        self.backup_each_connection_checkbox.setToolTip(
            _(
                "If this is selected the plugin will back up the device database each time the device is connected."
            )
        )
        self.backup_each_connection_checkbox.clicked.connect(
            self.backup_each_connection_checkbox_clicked
        )
        options_layout.addWidget(self.backup_each_connection_checkbox, 0, 2, 1, 3)

        self.dest_directory_label = QLabel(_("Destination:"), self)
        self.dest_directory_label.setToolTip(
            _("Select the destination to back up the device database to.")
        )
        self.dest_directory_edit = QLineEdit(self)
        self.dest_directory_edit.setMinimumSize(150, 0)
        self.dest_directory_label.setBuddy(self.dest_directory_edit)
        self.dest_pick_button = QPushButton(_("..."), self)
        self.dest_pick_button.setMaximumSize(24, 20)
        self.dest_pick_button.clicked.connect(self._get_dest_directory_name)
        options_layout.addWidget(self.dest_directory_label, 1, 0, 1, 1)
        options_layout.addWidget(self.dest_directory_edit, 1, 1, 1, 1)
        options_layout.addWidget(self.dest_pick_button, 1, 2, 1, 1)

        self.copies_to_keep_checkbox = QCheckBox(_("Copies to keep"), self)
        self.copies_to_keep_checkbox.setToolTip(
            _(
                "Select this to limit the number of backups kept. If not set, the backup files must be manually deleted."
            )
        )
        self.copies_to_keep_spin = QSpinBox(self)
        self.copies_to_keep_spin.setMinimum(2)
        self.copies_to_keep_spin.setToolTip(
            _("The number of backup copies of the database to keep. The minimum is 2.")
        )
        options_layout.addWidget(self.copies_to_keep_checkbox, 1, 3, 1, 1)
        options_layout.addWidget(self.copies_to_keep_spin, 1, 4, 1, 1)
        self.copies_to_keep_checkbox.clicked.connect(
            self.copies_to_keep_checkbox_clicked
        )

        self.zip_database_checkbox = QCheckBox(
            _("Compress database with config files"), self
        )
        self.zip_database_checkbox.setToolTip(
            _(
                "If checked, the database file will be added to the zip file with configuration files."
            )
        )
        options_layout.addWidget(self.zip_database_checkbox, 2, 0, 1, 3)

        layout.addLayout(options_layout)

        self.toggle_backup_options_state(False)

        layout.insertStretch(-1)

    def on_device_connection_changed(self, is_connected):
        if not is_connected:
            self._connected_device = None
            self.update_from_connection_status()

    def on_device_metadata_available(self):
        if self.plugin_action.device is not None:
            self._connected_device = self.plugin_action.device
            self.update_from_connection_status()

    def _devices_table_item_selection_changed(self):
        debug(
            "len(self.devices_table.selectedIndexes())=",
            len(self.devices_table.selectedIndexes()),
        )
        debug(
            "self.devices_table.selectedIndexes()=",
            self.devices_table.selectedIndexes(),
        )
        if len(self.devices_table.selectedIndexes()) > 0:
            self.delete_device_btn.setEnabled(True)
        else:
            self.delete_device_btn.setEnabled(False)

        (device_info, is_connected) = self.devices_table.get_selected_device_info()
        self.rename_device_btn.setEnabled(device_info is not None and is_connected)

        if self.individual_device_options:
            self.persist_devices_config()
            self.refresh_current_device_options()

    def _add_device_clicked(self):
        devices = self.devices_table.get_data()
        if self._connected_device is None:
            debug("self._connected_device is None")
            return

        drive_info = self._connected_device.drive_info
        for location_info in drive_info.values():
            if location_info["location_code"] == "main":
                new_device = {}
                new_device["type"] = self._connected_device.device_type
                new_device["active"] = True
                new_device["uuid"] = location_info["device_store_uuid"]
                new_device["name"] = location_info["device_name"]
                new_device["location_code"] = location_info["location_code"]
                new_device["serial_no"] = self.plugin_action.device_serial_no()
                devices[new_device["uuid"]] = new_device

        self.devices_table.populate_table(devices, self._connected_device)
        self.update_from_connection_status(update_table=False)
        # Ensure the devices combo is refreshed for the current list
        self.parent_dialog.profiles_tab.refresh_current_profile_info()

    def _rename_device_clicked(self) -> None:
        (device_info, _is_connected) = self.devices_table.get_selected_device_info()
        if not device_info:
            error_dialog(
                self,
                _("Rename failed"),
                _("You must select a device first"),
                show=True,
                show_copy_button=False,
            )
            return

        old_name = device_info["name"]
        new_device_name, ok = QInputDialog.getText(
            self,
            _("Rename device"),
            _("Enter a new display name for this device:"),
            text=old_name,
        )
        if not ok:
            # Operation cancelled
            return
        new_device_name = str(new_device_name).strip()
        if new_device_name == old_name:
            return
        try:
            self.gui.device_manager.set_driveinfo_name(
                device_info["location_code"], new_device_name
            )
            self.devices_table.set_current_row_device_name(new_device_name)
            # Ensure the devices combo is refreshed for the current list
            self.parent_dialog.profiles_tab.refresh_current_profile_info()
        except Exception:
            error_dialog(
                self,
                _("Rename failed"),
                _("An error occurred while renaming."),
                det_msg=traceback.format_exc(),
                show=True,
            )

    def _delete_device_clicked(self) -> None:
        (device_info, _is_connected) = self.devices_table.get_selected_device_info()
        if not device_info:
            error_dialog(
                self,
                _("Delete failed"),
                _("You must select a device first"),
                show=True,
                show_copy_button=False,
            )
            return
        name = device_info["name"]
        if not question_dialog(
            self,
            _("Are you sure?"),
            "<p>"
            + _(
                "You are about to remove the <b>{0}</b> device from this list. ".format(
                    name
                )
            )
            + _("Are you sure you want to continue?"),
        ):
            return
        self.parent_dialog.profiles_tab.persist_profile_config()
        self.devices_table.delete_selected_row()
        self.update_from_connection_status(update_table=False)

        # Ensure any lists are no longer associated with this device
        # NOTE: As of version 1.5 we can no longer do this since we only know the lists
        #       for the current library, not all libraries. So just reset this library
        #       and put some "self-healing" logic elsewhere to ensure a user loading a
        #       list for a deleted device in another library gets it reset at that point.
        self.parent_dialog.delete_device_from_lists(
            self.library_config, device_info["uuid"]
        )
        # Ensure the devices combo is refreshed for the current list
        self.parent_dialog.profiles_tab.refresh_current_profile_info()

    def update_from_connection_status(self, first_time=False, update_table=True):
        if first_time:
            devices = plugin_prefs[STORE_DEVICES]
        else:
            devices = self.devices_table.get_data()

        if self._connected_device is None or self.plugin_action.device is None:
            self.add_device_btn.setEnabled(False)
        else:
            # Check to see whether we are connected to a device we already know about
            is_new_device = True
            drive_info = self._connected_device.drive_info
            if drive_info:
                # This is a non iTunes device that we can check to see if we have the UUID for
                device_uuid = drive_info["main"]["device_store_uuid"]
                if device_uuid in devices:
                    is_new_device = False
            else:
                # This is a device without drive info like iTunes
                device_type = self._connected_device.device_type
                if device_type in devices:
                    is_new_device = False
            self.add_device_btn.setEnabled(is_new_device)
        if update_table:
            self.devices_table.populate_table(devices, self._connected_device)
            self.refresh_current_device_options()
        if first_time:
            self.devices_table.itemSelectionChanged.connect(
                self._devices_table_item_selection_changed
            )
            self._devices_table_item_selection_changed()

    def toggle_backup_options_state(self, enabled):
        self.dest_directory_edit.setEnabled(enabled)
        self.dest_pick_button.setEnabled(enabled)
        self.dest_directory_label.setEnabled(enabled)
        self.copies_to_keep_checkbox.setEnabled(enabled)
        self.copies_to_keep_checkbox_clicked(
            enabled and self.copies_to_keep_checkbox.checkState() == Qt.Checked
        )
        self.zip_database_checkbox.setEnabled(enabled)

    def do_daily_backp_checkbox_clicked(self, checked):
        enable_backup_options = (
            checked or self.backup_each_connection_checkbox.checkState() == Qt.Checked
        )
        self.toggle_backup_options_state(enable_backup_options)
        if self.backup_each_connection_checkbox.checkState() == Qt.Checked:
            self.backup_each_connection_checkbox.setCheckState(Qt.Unchecked)

    def backup_each_connection_checkbox_clicked(self, checked):
        enable_backup_options = (
            checked or self.do_daily_backp_checkbox.checkState() == Qt.Checked
        )
        self.toggle_backup_options_state(enable_backup_options)
        if self.do_daily_backp_checkbox.checkState() == Qt.Checked:
            self.do_daily_backp_checkbox.setCheckState(Qt.Unchecked)

    def device_options_for_each_checkbox_clicked(self, checked):
        self.individual_device_options = (
            checked or self.device_options_for_each_checkbox.checkState() == Qt.Checked
        )
        self.refresh_current_device_options()

    def copies_to_keep_checkbox_clicked(self, checked):
        self.copies_to_keep_spin.setEnabled(checked)

    def _get_dest_directory_name(self):
        path = choose_dir(
            self,
            "back up annotations destination dialog",
            _("Choose backup destination"),
        )
        if path:
            self.dest_directory_edit.setText(path)

    def refresh_current_device_options(self):
        if self.individual_device_options:
            (self.current_device_info, _is_connected) = (
                self.devices_table.get_selected_device_info()
            )
            if self.current_device_info:
                backup_prefs = self.current_device_info.get(
                    BACKUP_OPTIONS_STORE_NAME, BACKUP_OPTIONS_DEFAULTS
                )
            else:
                backup_prefs = BACKUP_OPTIONS_DEFAULTS
        else:
            backup_prefs = get_plugin_prefs(BACKUP_OPTIONS_STORE_NAME)

        do_daily_backup = get_pref(
            backup_prefs, BACKUP_OPTIONS_STORE_NAME, KEY_DO_DAILY_BACKUP
        )
        backup_each_connection = get_pref(
            backup_prefs, BACKUP_OPTIONS_STORE_NAME, KEY_BACKUP_EACH_CONNECTION
        )
        dest_directory = get_pref(
            backup_prefs, BACKUP_OPTIONS_STORE_NAME, KEY_BACKUP_DEST_DIRECTORY
        )
        copies_to_keep = get_pref(
            backup_prefs, BACKUP_OPTIONS_STORE_NAME, KEY_BACKUP_COPIES_TO_KEEP
        )
        zip_database = get_pref(
            backup_prefs, BACKUP_OPTIONS_STORE_NAME, KEY_BACKUP_ZIP_DATABASE
        )

        self.do_daily_backp_checkbox.setCheckState(
            Qt.Checked if do_daily_backup else Qt.Unchecked
        )
        self.backup_each_connection_checkbox.setCheckState(
            Qt.Checked if backup_each_connection else Qt.Unchecked
        )
        self.dest_directory_edit.setText(dest_directory)
        self.zip_database_checkbox.setCheckState(
            Qt.Checked if zip_database else Qt.Unchecked
        )
        if copies_to_keep == -1:
            self.copies_to_keep_checkbox.setCheckState(Qt.Unchecked)
        else:
            self.copies_to_keep_checkbox.setCheckState(Qt.Checked)
            self.copies_to_keep_spin.setProperty("value", copies_to_keep)
        if do_daily_backup:
            self.do_daily_backp_checkbox_clicked(do_daily_backup)
        if backup_each_connection:
            self.backup_each_connection_checkbox_clicked(backup_each_connection)

    def persist_devices_config(self):
        debug("Start")

        backup_prefs = {}
        backup_prefs[KEY_DO_DAILY_BACKUP] = (
            self.do_daily_backp_checkbox.checkState() == Qt.Checked
        )
        backup_prefs[KEY_BACKUP_EACH_CONNECTION] = (
            self.backup_each_connection_checkbox.checkState() == Qt.Checked
        )
        backup_prefs[KEY_BACKUP_ZIP_DATABASE] = (
            self.zip_database_checkbox.checkState() == Qt.Checked
        )
        backup_prefs[KEY_BACKUP_DEST_DIRECTORY] = str(self.dest_directory_edit.text())
        backup_prefs[KEY_BACKUP_COPIES_TO_KEEP] = (
            int(str(self.copies_to_keep_spin.value()))
            if self.copies_to_keep_checkbox.checkState() == Qt.Checked
            else -1
        )
        debug("backup_prefs:", backup_prefs)

        if self.individual_device_options:
            if self.current_device_info:
                self.current_device_info[BACKUP_OPTIONS_STORE_NAME] = backup_prefs
        else:
            plugin_prefs[BACKUP_OPTIONS_STORE_NAME] = backup_prefs

        new_prefs = get_plugin_prefs(COMMON_OPTIONS_STORE_NAME)
        new_prefs[KEY_INDIVIDUAL_DEVICE_OPTIONS] = self.individual_device_options
        plugin_prefs[COMMON_OPTIONS_STORE_NAME] = new_prefs

        debug("end")


class DeviceColumnComboBox(QComboBox):
    def __init__(self, parent):
        QComboBox.__init__(self, parent)
        self.device_ids = [None, TOKEN_ANY_DEVICE]

    def populate_combo(self, devices, selected_device_uuid):
        self.clear()
        self.addItem("")
        self.addItem(TOKEN_ANY_DEVICE)
        selected_idx = 0
        if selected_device_uuid == TOKEN_ANY_DEVICE:
            selected_idx = 1
        for idx, key in enumerate(devices.keys()):
            self.addItem("%s" % (devices[key]["name"]))
            self.device_ids.append(key)
            if key == selected_device_uuid:
                selected_idx = idx + 2
        self.setCurrentIndex(selected_idx)

    def get_selected_device(self):
        return self.device_ids[self.currentIndex()]


class DevicesTableWidget(QTableWidget):
    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.plugin_action: KoboUtilitiesAction = parent.plugin_action
        self.setSortingEnabled(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setMinimumSize(380, 0)

    def populate_table(self, devices, connected_device: Optional[KoboDevice]):
        self.clear()
        self.setRowCount(len(devices))
        header_labels = [
            _("Menu"),
            _("Name"),
            _("Model"),
            _("Serial number"),
            _("FW version"),
            _("Status"),
        ]
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.verticalHeader().setDefaultSectionSize(32)
        self.horizontalHeader().setStretchLastSection(False)
        self.setIconSize(QSize(32, 32))

        for row, uuid in enumerate(devices.keys()):
            self.populate_table_row(row, devices[uuid], connected_device)

        self.resizeColumnsToContents()
        self.setMinimumColumnWidth(1, 100)
        self.selectRow(0)

    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(
        self, row, device_config, connected_device: Optional[KoboDevice]
    ):
        debug("device_config:", device_config)
        device_type = device_config["type"]
        device_uuid = device_config["uuid"]
        device_icon = "reader.png"
        is_connected = False
        if connected_device is not None and self.plugin_action.device is not None:
            debug("connected_device:", connected_device)
            if device_type == connected_device.device_type:
                drive_info = connected_device.drive_info
                if not drive_info:
                    is_connected = False
                else:
                    for connected_info in drive_info.values():
                        if connected_info["device_store_uuid"] == device_uuid:
                            is_connected = True
                            break
        device = self.plugin_action.device
        version_info = device.version_info if device is not None else None
        fw_version = version_info.fw_version if is_connected and version_info else ""
        connected_icon = "images/device_connected.png" if is_connected else None
        debug("connected_icon=%s" % connected_icon)

        name_widget = ReadOnlyTextIconWidgetItem(
            device_config["name"], get_icon(device_icon)
        )
        name_widget.setData(Qt.UserRole, (device_config, is_connected))
        type_widget = ReadOnlyTableWidgetItem(device_config["type"])
        serial_no = device_config.get("serial_no", "")
        serial_no_widget = ReadOnlyTableWidgetItem(serial_no)
        version_no_widget = ReadOnlyTableWidgetItem(fw_version)
        self.setItem(row, 0, CheckableTableWidgetItem(device_config["active"]))
        self.setItem(row, 1, name_widget)
        self.setItem(row, 2, type_widget)
        self.setItem(row, 3, serial_no_widget)
        self.setItem(row, 4, version_no_widget)
        self.setItem(row, 5, ReadOnlyTextIconWidgetItem("", get_icon(connected_icon)))

    def get_data(self):
        debug("start")
        devices = {}
        for row in range(self.rowCount()):
            (device_config, _is_connected) = self.item(row, 1).data(Qt.UserRole)
            device_config["active"] = self.item(row, 0).get_boolean_value()
            devices[device_config["uuid"]] = device_config
        return devices

    def get_selected_device_info(self):
        if self.currentRow() >= 0:
            (device_config, is_connected) = self.item(self.currentRow(), 1).data(
                Qt.UserRole
            )
            return (device_config, is_connected)
        return None, None

    def set_current_row_device_name(self, device_name):
        if self.currentRow() >= 0:
            widget = self.item(self.currentRow(), 1)
            (device_config, is_connected) = widget.data(Qt.UserRole)
            device_config["name"] = device_name
            widget.setData(Qt.UserRole, (device_config, is_connected))
            widget.setText(device_name)

    def delete_selected_row(self):
        if self.currentRow() >= 0:
            self.removeRow(self.currentRow())


class OtherTab(QWidget):
    def __init__(self, parent_dialog: ConfigWidget):
        self.parent_dialog = parent_dialog
        QWidget.__init__(self)
        layout = QVBoxLayout()
        self.setLayout(layout)

        other_options_group = QGroupBox(_("Other options"), self)
        layout.addWidget(other_options_group)
        options_layout = QGridLayout()
        other_options_group.setLayout(options_layout)

        library_default_label = QLabel(_("&Library button default:"), self)
        library_default_label.setToolTip(
            _(
                "If plugin is placed as a toolbar button, choose a default action when clicked on"
            )
        )
        self.library_default_combo = SimpleComboBox(
            self,
            self.parent_dialog.plugin_action.library_actions_map,
            str(get_plugin_pref(COMMON_OPTIONS_STORE_NAME, KEY_BUTTON_ACTION_LIBRARY)),
        )
        library_default_label.setBuddy(self.library_default_combo)
        options_layout.addWidget(library_default_label, 0, 0, 1, 1)
        options_layout.addWidget(self.library_default_combo, 0, 1, 1, 2)

        device_default_label = QLabel(_("&Device button default:"), self)
        device_default_label.setToolTip(
            _(
                "If plugin is placed as a toolbar button, choose a default action when clicked on"
            )
        )
        self.device_default_combo = SimpleComboBox(
            self,
            self.parent_dialog.plugin_action.device_actions_map,
            str(get_plugin_pref(COMMON_OPTIONS_STORE_NAME, KEY_BUTTON_ACTION_DEVICE)),
        )
        device_default_label.setBuddy(self.device_default_combo)
        options_layout.addWidget(device_default_label, 1, 0, 1, 1)
        options_layout.addWidget(self.device_default_combo, 1, 1, 1, 2)

        keyboard_shortcuts_button = QPushButton(_("Keyboard shortcuts..."), self)
        keyboard_shortcuts_button.setToolTip(
            _("Edit the keyboard shortcuts associated with this plugin")
        )
        keyboard_shortcuts_button.clicked.connect(parent_dialog.edit_shortcuts)
        layout.addWidget(keyboard_shortcuts_button)

        view_prefs_button = QPushButton(_("&View library preferences..."), self)
        view_prefs_button.setToolTip(
            _("View data stored in the library database for this plugin")
        )
        view_prefs_button.clicked.connect(parent_dialog.view_prefs)
        layout.addWidget(view_prefs_button)

        layout.insertStretch(-1)

    def persist_other_config(self):
        new_prefs = get_plugin_prefs(COMMON_OPTIONS_STORE_NAME)
        new_prefs[KEY_BUTTON_ACTION_DEVICE] = str(
            self.device_default_combo.currentText()
        )
        new_prefs[KEY_BUTTON_ACTION_LIBRARY] = str(
            self.library_default_combo.currentText()
        )
        plugin_prefs[COMMON_OPTIONS_STORE_NAME] = new_prefs


class ConfigWidget(QWidget):
    def __init__(self, plugin_action: KoboUtilitiesAction):
        debug("Initializing...")
        QWidget.__init__(self)
        self.plugin_action = plugin_action
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        self.help_anchor = "ConfigurationDialog"

        self._get_create_new_custom_column_instance = None
        self.supports_create_custom_column = SUPPORTS_CREATE_CUSTOM_COLUMN

        title_layout = ImageTitleLayout(
            self, "images/icon.png", _("Kobo Utilities options")
        )
        layout.addLayout(title_layout)

        tab_widget = QTabWidget(self)
        layout.addWidget(tab_widget)

        self.profiles_tab = ProfilesTab(self, plugin_action)
        self.devices_tab = DevicesTab(self, plugin_action)
        self.other_tab = OtherTab(self)
        tab_widget.addTab(self.profiles_tab, _("Profiles"))
        tab_widget.addTab(self.devices_tab, _("Devices"))
        tab_widget.addTab(self.other_tab, _("Other"))

        # Force an initial display of list information
        self.devices_tab.update_from_connection_status(first_time=True)
        self.profiles_tab.refresh_current_profile_info()

        self.connect_signals()

    def connect_signals(self):
        self.plugin_action.plugin_device_connection_changed.connect(
            self.devices_tab.on_device_connection_changed
        )
        self.plugin_action.plugin_device_metadata_available.connect(
            self.devices_tab.on_device_metadata_available
        )

    def get_devices_list(self):
        return self.devices_tab.devices_table.get_data()

    def delete_device_from_lists(self, library_config, device_uuid):
        del device_uuid
        set_library_config(self.plugin_action.gui.current_db, library_config)

    def save_settings(self):
        device_prefs = self.get_devices_list()
        plugin_prefs[STORE_DEVICES] = device_prefs

        # We only need to update the store for the current list, as switching lists
        # will have updated the other lists
        self.profiles_tab.persist_profile_config()
        self.other_tab.persist_other_config()
        self.devices_tab.persist_devices_config()

        library_config = self.profiles_tab.library_config
        library_config[KEY_PROFILES] = self.profiles_tab.profiles
        set_library_config(self.plugin_action.gui.current_db, library_config)

    def edit_shortcuts(self):
        self.save_settings()
        # Force the menus to be rebuilt immediately, so we have all our actions registered
        self.plugin_action.rebuild_menus()
        d = KeyboardConfigDialog(
            self.plugin_action.gui, self.plugin_action.action_spec[0]
        )
        if d.exec_() == d.Accepted:
            self.plugin_action.gui.keyboard.finalize()

    def view_prefs(self):
        d = PrefsViewerDialog(self.plugin_action.gui, PREFS_NAMESPACE)
        d.exec_()

    def help_link_activated(self, url):
        del url
        self.plugin_action.show_help(anchor="ConfigurationDialog")

    @property
    def get_create_new_custom_column_instance(self):
        if (
            self._get_create_new_custom_column_instance is None
            and self.supports_create_custom_column
        ):
            self._get_create_new_custom_column_instance = CreateNewCustomColumn(
                self.plugin_action.gui
            )
        return self._get_create_new_custom_column_instance
