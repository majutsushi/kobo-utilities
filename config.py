#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2012-2022, David Forrester <davidfor@internode.on.net>'
__docformat__ = 'restructuredtext en'

import copy, traceback

# calibre Python 3 compatibility.
import six
from six import text_type as unicode

from functools import partial

try:
    from PyQt5.Qt import (Qt, QWidget, QGridLayout, QLabel, QPushButton, QVBoxLayout, QSpinBox,
                          QGroupBox, QCheckBox, QLineEdit, QTabWidget, QTableWidget, QAbstractItemView,
                          QHBoxLayout, QIcon, QInputDialog, QComboBox, QToolButton, QSize)
except ImportError:
    from PyQt4.Qt import (Qt, QWidget, QGridLayout, QLabel, QPushButton, QVBoxLayout, QSpinBox,
                          QGroupBox, QCheckBox, QLineEdit, QTabWidget, QTableWidget, QAbstractItemView,
                          QHBoxLayout, QIcon, QInputDialog, QComboBox, QToolButton, QSize)

from calibre.gui2 import choose_dir, error_dialog, question_dialog
from calibre.gui2.dialogs.confirm_delete import confirm
from calibre.utils.config import JSONConfig
from calibre.constants import DEBUG as _DEBUG

from calibre_plugins.koboutilities.common_utils import (get_library_uuid, debug_print, get_icon,
                                     CustomColumnComboBox, KeyboardConfigDialog, SimpleComboBox, ImageTitleLayout,
                                     PrefsViewerDialog, ReadOnlyTextIconWidgetItem, CheckableTableWidgetItem,
                                     ReadOnlyTableWidgetItem, ProfileComboBox,
                                     convert_qvariant)

SUPPORTS_CREATE_CUSTOM_COLUMN = False
try:
    from calibre.gui2.preferences.create_custom_column import CreateNewCustomColumn
    debug_print("Kobo Utilities Configuration - CreateNewCustomColumn is supported")
    SUPPORTS_CREATE_CUSTOM_COLUMN = True
except ImportError as e:
    debug_print("Kobo Utilities Configuration - CreateNewCustomColumn is not supported")
    SUPPORTS_CREATE_CUSTOM_COLUMN = False

# Redefine the debug here so the jobs can see it.
DEBUG = _DEBUG

PREFS_NAMESPACE = 'KoboUtilitiesPlugin'
PREFS_KEY_SETTINGS = 'settings'

KEY_SCHEMA_VERSION = 'SchemaVersion'
DEFAULT_SCHEMA_VERSION = 0.1

STORE_LIBRARIES = 'libraries'
KEY_PROFILES                       = 'profiles'
KEY_CURRENT_LOCATION_CUSTOM_COLUMN = 'currentReadingLocationColumn'
KEY_PERCENT_READ_CUSTOM_COLUMN     = 'percentReadColumn'
KEY_RATING_CUSTOM_COLUMN           = 'ratingColumn'
KEY_LAST_READ_CUSTOM_COLUMN        = 'lastReadColumn'
KEY_STORE_ON_CONNECT               = 'storeOnConnect'
KEY_PROMPT_TO_STORE                = 'promptToStore'
KEY_STORE_IF_MORE_RECENT           = 'storeIfMoreRecent'
KEY_DO_NOT_STORE_IF_REOPENED       = 'doNotStoreIfReopened'
KEY_DO_UPDATE_CHECK                = 'doFirmwareUpdateCheck'
KEY_LAST_FIRMWARE_CHECK_TIME       = 'firmwareUpdateCheckLastTime'
KEY_DO_EARLY_FIRMWARE_CHECK        = 'doEarlyFirmwareUpdate'
KEY_FOR_DEVICE                     = 'forDevice'
KEY_INDIVIDUAL_DEVICE_OPTIONS      = 'individualDeviceOptions'

BACKUP_OPTIONS_STORE_NAME               = 'backupOptionsStore'
BOOKMARK_OPTIONS_STORE_NAME             = 'BookmarkOptions'
COMMON_OPTIONS_STORE_NAME               = 'commonOptionsStore'
CUSTOM_COLUMNS_STORE_NAME               = 'customColumnOptions'
METADATA_OPTIONS_STORE_NAME             = 'MetadataOptions'
READING_OPTIONS_STORE_NAME              = 'ReadingOptions'
STORE_OPTIONS_STORE_NAME                = 'storeOptionsStore'
DISMISSTILES_OPTIONS_STORE_NAME         = 'dismissTilesOptionsStore'
DISPLAYEXTRASTILES_OPTIONS_STORE_NAME   = 'displayExtrasTilesOptionsStore'
FIXDUPLICATESHELVES_OPTIONS_STORE_NAME  = 'fixDuplicatesOptionsStore'
ORDERSERIESSHELVES_OPTIONS_STORE_NAME   = 'orderSeriesShelvesOptionsStore'
SETRELATEDBOOKS_OPTIONS_STORE_NAME      = 'setRelatedBooksOptionsStore'
UPDATE_OPTIONS_STORE_NAME               = 'updateOptionsStore'
GET_SHELVES_OPTIONS_STORE_NAME          = 'getShelvesOptionStore'
READING_POSITION_CHANGES_STORE_NAME     = 'readingPositionChangesStore'

KEY_STORE_BOOKMARK          = 'storeBookmarks'
KEY_DATE_TO_NOW             = 'setDateToNow'
KEY_SET_RATING              = 'setRating'
KEY_CLEAR_IF_UNREAD         = 'clearIfUnread'
KEY_BACKGROUND_JOB          = 'backgroundJob'
KEY_SET_TITLE               = 'title'
KEY_USE_TITLE_SORT          = 'titleSort'
KEY_SET_AUTHOR              = 'author'
KEY_USE_AUTHOR_SORT         = 'authourSort'
KEY_SET_DESCRIPTION         = 'description'
KEY_DESCRIPTION_USE_TEMPLATE = 'descriptionUseTemplate'
KEY_DESCRIPTION_TEMPLATE    = 'descriptionTemplate'
KEY_SET_PUBLISHER           = 'publisher'
KEY_SET_RATING              = 'rating'
KEY_SET_SERIES              = 'series'
KEY_SET_SUBTITLE            = 'subtitle'
KEY_SUBTITLE_TEMPLATE       = 'subtitleTemplate'
KEY_USE_PLUGBOARD           = 'usePlugboard'
KEY_UDPATE_KOBO_EPUBS       = 'update_KoboEpubs'
KEY_SET_READING_STATUS      = 'setRreadingStatus'
KEY_READING_STATUS          = 'readingStatus'
KEY_SET_PUBLISHED_DATE      = 'published_date'
KEY_SET_ISBN                = 'isbn'
KEY_SET_NOT_INTERESTED      = 'mark_not_interested'
KEY_SET_LANGUAGE            = 'language'
KEY_SET_READING_DIRECTION   = 'set_reading_direction'
KEY_READING_DIRECTION       = 'reading_direction'
KEY_SYNC_DATE               = 'set_sync_date'
KEY_SYNC_DATE_COLUMN        = 'sync_date_library_date'
KEY_RESET_POSITION          = 'resetPosition'

KEY_TILE_OPTIONS            = 'tileOptions'
KEY_CHANGE_DISMISS_TRIGGER  = 'changeDismissTrigger'
KEY_CREATE_DISMISS_TRIGGER  = 'createDismissTrigger'
KEY_DELETE_DISMISS_TRIGGER  = 'deleteDismissTrigger'
KEY_CREATE_ANALYTICSEVENTS_TRIGGER  = 'createAnalyticsEventsTrigger'
KEY_DELETE_ANALYTICSEVENTS_TRIGGER  = 'deleteAnalyticsEventsTrigger'

KEY_REMOVE_FULLSIZE_COVERS  = 'remove_fullsize_covers'

KEY_COVERS_BLACKANDWHITE     = 'blackandwhite'
KEY_COVERS_DITHERED          = 'dithered_covers'
KEY_COVERS_KEEP_ASPECT_RATIO = 'keep_cover_aspect'
KEY_COVERS_LETTERBOX         = 'letterbox'
KEY_COVERS_LETTERBOX_COLOR   = 'letterbox_color'
KEY_DRIVER_SUPPORTS_COVERS_LETTERBOX_COLOR = 'driver_supports_cover_letterbox_colors'
KEY_COVERS_PNG               = 'png_covers'
KEY_COVERS_UPDLOAD_KEPUB     = 'kepub_covers'

KEY_DISMISS_CURRENT_EXTRAS   = 'dismissCurrentExtras'
KEY_TILE_RECENT_NEW          = 'tileRecentBooksNew'
KEY_TILE_RECENT_FINISHED     = 'tileRecentBooksFinished'
KEY_TILE_RECENT_IN_THE_CLOUD = 'tileRecentBooksInTheCLoud'
KEY_TILE_EXTRAS_BROWSER      = 'tileExtrasBrowser'
KEY_TILE_EXTRAS_CHESS        = 'tileExtrasChess'
KEY_TILE_EXTRAS_SCRAMBLE     = 'tileExtrasScramble'
KEY_TILE_EXTRAS_RUSHHOUR     = 'tileExtrasRushhour'
KEY_TILE_EXTRAS_SOLITAIRE    = 'tileExtrasSolitaire'
KEY_TILE_EXTRAS_SKETCH       = 'tileExtrasSketch'
KEY_TILE_EXTRAS_SUDOKU       = 'tileExtrasSudoku'

KEY_READING_FONT_FAMILY     = 'readingFontFamily'
KEY_READING_ALIGNMENT       = 'readingAlignment'
KEY_READING_FONT_SIZE       = 'readingFontSize'
KEY_READING_LINE_HEIGHT     = 'readingLineHeight'
KEY_READING_LEFT_MARGIN     = 'readingLeftMargin'
KEY_READING_RIGHT_MARGIN    = 'readingRightMargin'
KEY_READING_LOCK_MARGINS    = 'lockMargins'
KEY_UPDATE_CONFIG_FILE      = 'updateConfigFile'
KEY_DO_NOT_UPDATE_IF_SET    = 'doNotUpdateIfSet'

KEY_BUTTON_ACTION_DEVICE    = 'buttonActionDevice'
KEY_BUTTON_ACTION_LIBRARY   = 'buttonActionLibrary'

KEY_KEEP_NEWEST_SHELF       = 'keepNewestShelf'
KEY_PURGE_SHELVES           = 'purgeShelves'

KEY_SORT_DESCENDING         = 'sortDescending'
KEY_SORT_UPDATE_CONFIG      = 'updateConfig'

KEY_ORDER_SHELVES_SERIES    = 0
KEY_ORDER_SHELVES_AUTHORS   = 1
KEY_ORDER_SHELVES_OTHER     = 2
KEY_ORDER_SHELVES_ALL       = 3
KEY_ORDER_SHELVES_TYPE      = 'orderShelvesType'

KEY_ORDER_SHELVES_BY_SERIES = 0
KEY_ORDER_SHELVES_PUBLISHED = 1
KEY_ORDER_SHELVES_BY        = 'orderShelvesBy'

KEY_RELATED_BOOKS_SERIES    = 0
KEY_RELATED_BOOKS_AUTHORS   = 1
KEY_RELATED_BOOKS_TYPE      = 'relatedBooksType'

KEY_REMOVE_ANNOT_ALL         = 0
KEY_REMOVE_ANNOT_SELECTED    = 1
KEY_REMOVE_ANNOT_NOBOOK      = 2
KEY_REMOVE_ANNOT_EMPTY       = 3
KEY_REMOVE_ANNOT_NONEMPTY    = 4
KEY_REMOVE_ANNOT_ACTION      = 'removeAnnotAction'

KEY_DO_DAILY_BACKUP         = 'doDailyBackp'
KEY_BACKUP_EACH_CONNECTION  = 'backupEachCOnnection'
KEY_BACKUP_COPIES_TO_KEEP   = 'backupCopiesToKeepSpin'
KEY_BACKUP_DEST_DIRECTORY   = 'backupDestDirectory'
KEY_BACKUP_ZIP_DATABASE     = 'backupZipDatabase'

KEY_SHELVES_CUSTOM_COLUMN   = 'shelvesColumn'
KEY_ALL_BOOKS               = 'allBooks'
KEY_REPLACE_SHELVES         = 'replaceShelves'

KEY_SELECT_BOOKS_IN_LIBRARY   = 'selectBooksInLibrary'
KEY_UPDATE_GOODREADS_PROGRESS = 'updeateGoodreadsProgress'

TOKEN_ANY_DEVICE     = '*Any Device'
TOKEN_CLEAR_SUBTITLE = '*Clear*'
TOKEN_FILE_TIMESTAMP = '*filetimestamp'
OTHER_SORTS          = {TOKEN_FILE_TIMESTAMP: _('* File timestamp')}

STORE_DEVICES = 'Devices'
# Devices store consists of:
# 'Devices': { 'dev_uuid': {'type':'xxx', 'uuid':'xxx', 'name:'xxx', 'location_code':'main',
#                           'active':True, 'collections':False} ,
# For iTunes
#              'iTunes':   {'type':'iTunes', 'uuid':iTunes', 'name':'iTunes', 'location_code':'',
#                           'active':True, 'collections':False}, ...}
DEFAULT_DEVICES_VALUES = {}

BOOKMARK_OPTIONS_DEFAULTS = {
                KEY_STORE_BOOKMARK:             True,
                KEY_READING_STATUS:             True,
                KEY_DATE_TO_NOW:                True, 
                KEY_SET_RATING:                 True, 
                KEY_CLEAR_IF_UNREAD:            False, 
                KEY_BACKGROUND_JOB:             False, 
                KEY_STORE_IF_MORE_RECENT:       False,
                KEY_DO_NOT_STORE_IF_REOPENED:   False
                }
METADATA_OPTIONS_DEFAULTS = {
                KEY_SET_TITLE:          False,
                KEY_SET_AUTHOR:         False,
                KEY_SET_DESCRIPTION:    False,
                KEY_DESCRIPTION_USE_TEMPLATE: False,
                KEY_DESCRIPTION_TEMPLATE:     None,
                KEY_SET_PUBLISHER:      False,
                KEY_SET_RATING:         False,
                KEY_SET_SERIES:         False,
                KEY_SET_READING_STATUS: False,
                KEY_READING_STATUS:     -1,
                KEY_SET_PUBLISHED_DATE: False,
                KEY_SET_ISBN:           False,
                KEY_SET_NOT_INTERESTED: False,
                KEY_SET_LANGUAGE:       False,
                KEY_RESET_POSITION:     False,
                KEY_USE_PLUGBOARD:      False,
                KEY_USE_TITLE_SORT:     False,
                KEY_USE_AUTHOR_SORT:    False,
                KEY_SET_SUBTITLE:       False,
                KEY_SUBTITLE_TEMPLATE:  None,
                KEY_UDPATE_KOBO_EPUBS:  False,
                KEY_SET_READING_DIRECTION: False,
                KEY_READING_DIRECTION:  'Default',
                KEY_SYNC_DATE:          False,
                KEY_SYNC_DATE_COLUMN:   'timestamp',
                }
READING_OPTIONS_DEFAULTS = {
                KEY_READING_FONT_FAMILY:  'Georgia',
                KEY_READING_ALIGNMENT:    'Off',
                KEY_READING_FONT_SIZE:    22,
                KEY_READING_LINE_HEIGHT:  1.3,
                KEY_READING_LEFT_MARGIN:  3,
                KEY_READING_RIGHT_MARGIN: 3,
                KEY_READING_LOCK_MARGINS: False,
                KEY_UPDATE_CONFIG_FILE:   False,
                KEY_DO_NOT_UPDATE_IF_SET: False,
                }
STORE_OPTIONS_DEFAULTS = {
                KEY_STORE_ON_CONNECT:           False,
                KEY_PROMPT_TO_STORE:            True,
                KEY_STORE_IF_MORE_RECENT:       False,
                KEY_DO_NOT_STORE_IF_REOPENED:   False,
                }
COMMON_OPTIONS_DEFAULTS = {
                KEY_BUTTON_ACTION_DEVICE:       '',
                KEY_BUTTON_ACTION_LIBRARY:      '',
                KEY_INDIVIDUAL_DEVICE_OPTIONS:  False,
                }
OLD_COMMON_OPTIONS_DEFAULTS = {
                KEY_STORE_ON_CONNECT:           False,
                KEY_PROMPT_TO_STORE:            True,
                KEY_STORE_IF_MORE_RECENT:       False,
                KEY_DO_NOT_STORE_IF_REOPENED:   False,
                KEY_BUTTON_ACTION_DEVICE:       '',
                KEY_BUTTON_ACTION_LIBRARY:      '',
                }
DISMISSTILES_OPTIONS_DEFAULTS = {
                KEY_TILE_OPTIONS:               {},
                KEY_TILE_RECENT_NEW:            False,
                KEY_TILE_RECENT_FINISHED:       False,
                KEY_TILE_RECENT_IN_THE_CLOUD:   False
                }

DISPLAYEXTRASTILES_OPTIONS_DEFAULTS = {
                KEY_TILE_OPTIONS:               {},
                KEY_DISMISS_CURRENT_EXTRAS:     False,
                }

FIXDUPLICATESHELVES_OPTIONS_DEFAULTS = {
                KEY_KEEP_NEWEST_SHELF:  True,
                KEY_PURGE_SHELVES:      False
                }

ORDERSERIESSHELVES_OPTIONS_DEFAULTS = {
                KEY_SORT_DESCENDING:    False,
                KEY_SORT_UPDATE_CONFIG: True,
                KEY_ORDER_SHELVES_TYPE: KEY_ORDER_SHELVES_SERIES,
                KEY_ORDER_SHELVES_BY:   KEY_ORDER_SHELVES_BY_SERIES
                }

SETRELATEDBOOKS_OPTIONS_DEFAULTS = {
                KEY_RELATED_BOOKS_TYPE: KEY_RELATED_BOOKS_SERIES,
                }

UPDATE_OPTIONS_DEFAULTS = {
                KEY_DO_UPDATE_CHECK: False,
                KEY_LAST_FIRMWARE_CHECK_TIME: 0,
                KEY_DO_EARLY_FIRMWARE_CHECK: False
                }

BACKUP_OPTIONS_DEFAULTS = {
                KEY_DO_DAILY_BACKUP:        False,
                KEY_BACKUP_EACH_CONNECTION: False,
                KEY_BACKUP_COPIES_TO_KEEP:  5,
                KEY_BACKUP_DEST_DIRECTORY:  '',
                KEY_BACKUP_ZIP_DATABASE:    True
                }

GET_SHELVES_OPTIONS_DEFAULTS = {
                KEY_SHELVES_CUSTOM_COLUMN: None,
                KEY_ALL_BOOKS:             True,
                KEY_REPLACE_SHELVES:       True
                }

CUSTOM_COLUMNS_OPTIONS_DEFAULTS = {
                          KEY_CURRENT_LOCATION_CUSTOM_COLUMN: None,
                          KEY_PERCENT_READ_CUSTOM_COLUMN:     None,
                          KEY_RATING_CUSTOM_COLUMN:           None,
                          KEY_LAST_READ_CUSTOM_COLUMN:        None,
                         }

DEFAULT_PROFILE_VALUES = {
                          KEY_FOR_DEVICE:               None,
                          UPDATE_OPTIONS_STORE_NAME:    UPDATE_OPTIONS_DEFAULTS,
                          STORE_OPTIONS_STORE_NAME:     STORE_OPTIONS_DEFAULTS,
                         }
DEFAULT_LIBRARY_VALUES = {
                          KEY_PROFILES: { 'Default': DEFAULT_PROFILE_VALUES },
                          KEY_SCHEMA_VERSION: DEFAULT_SCHEMA_VERSION
                         }

READING_POSITION_CHANGES_DEFAULTS = {
                                     KEY_SELECT_BOOKS_IN_LIBRARY:   False,
                                     KEY_UPDATE_GOODREADS_PROGRESS: False
                                     }

CUSTOM_COLUMN_DEFAULT_LOOKUP_READING_LOCATION   = '#kobo_reading_location'
CUSTOM_COLUMN_DEFAULT_LOOKUP_LAST_READ          = '#kobo_last_read'
CUSTOM_COLUMN_DEFAULT_LOOKUP_RATING             = '#kobo_rating'
CUSTOM_COLUMN_DEFAULT_LOOKUP_PERCENT_READ       = '#kobo_percent_read'
CUSTOM_COLUMN_DEFAULTS = {
                CUSTOM_COLUMN_DEFAULT_LOOKUP_READING_LOCATION : {
                    'column_heading': _("Kobo Reading Location"),
                    'datatype' : 'text',
                    'description' : _("Kobo Reading location from the device."),
                    'columns_list' : 'avail_text_columns',
                    'config_label' : _('Current Reading Location Column:'),
                    'config_tool_tip' : _("Select a custom column to store the current reading location. The column type must be 'text' or 'comments.' Leave this blank if you do not want to store or restore the current reading location."),
                },
                CUSTOM_COLUMN_DEFAULT_LOOKUP_PERCENT_READ : {
                    'column_heading': _("Kobo % Read"),
                    'datatype' : 'int',
                    'description' : _("Percentage read for the book"),
                    'columns_list' : 'avail_number_columns',
                    'config_label' : _('Percent Read Column:'),
                    'config_tool_tip' : _("Column used to store the current percent read. The column type must be a 'integer'. Leave this blank if you do not want to store or restore the percentage read."),
                },
                CUSTOM_COLUMN_DEFAULT_LOOKUP_RATING : {
                    'column_heading': _("Kobo Rating"),
                    'datatype' : 'rating',
                    'description' : _("Rating for the book on the Kobo device."),
                    'columns_list' : 'avail_rating_columns',
                    'config_label' : _('Rating Column:'),
                    'config_tool_tip' : _("Column used to store the rating. The column type must be a 'integer'. Leave this blank if you do not want to store or restore the rating."),
                },
                CUSTOM_COLUMN_DEFAULT_LOOKUP_LAST_READ : {
                    'column_heading': _("Kobo Last Read"),
                    'datatype' : 'datetime',
                    'description' : _("When the book was last read on the Kobo device."),
                    'columns_list' : 'avail_date_columns',
                    'config_label' : _('Last Read Column:'),
                    'config_tool_tip' : _("Column used to store when the book was last read. The column type must be a 'Date'. Leave this blank if you do not want to store the last read timestamp."),
                },
            }

# This is where all preferences for this plugin will be stored
plugin_prefs = JSONConfig('plugins/Kobo Utilities')

# Set defaults
plugin_prefs.defaults[BOOKMARK_OPTIONS_STORE_NAME]      = BOOKMARK_OPTIONS_DEFAULTS
plugin_prefs.defaults[METADATA_OPTIONS_STORE_NAME]      = METADATA_OPTIONS_DEFAULTS
plugin_prefs.defaults[READING_OPTIONS_STORE_NAME]       = READING_OPTIONS_DEFAULTS
plugin_prefs.defaults[COMMON_OPTIONS_STORE_NAME]        = COMMON_OPTIONS_DEFAULTS
plugin_prefs.defaults[DISMISSTILES_OPTIONS_STORE_NAME]  = DISMISSTILES_OPTIONS_DEFAULTS
plugin_prefs.defaults[DISPLAYEXTRASTILES_OPTIONS_STORE_NAME]  = DISPLAYEXTRASTILES_OPTIONS_DEFAULTS
plugin_prefs.defaults[FIXDUPLICATESHELVES_OPTIONS_STORE_NAME] = FIXDUPLICATESHELVES_OPTIONS_DEFAULTS
plugin_prefs.defaults[ORDERSERIESSHELVES_OPTIONS_STORE_NAME]  = ORDERSERIESSHELVES_OPTIONS_DEFAULTS
plugin_prefs.defaults[SETRELATEDBOOKS_OPTIONS_STORE_NAME]     = SETRELATEDBOOKS_OPTIONS_DEFAULTS
plugin_prefs.defaults[STORE_LIBRARIES]                  = {}
plugin_prefs.defaults[UPDATE_OPTIONS_STORE_NAME]        = UPDATE_OPTIONS_DEFAULTS
plugin_prefs.defaults[BACKUP_OPTIONS_STORE_NAME]        = BACKUP_OPTIONS_DEFAULTS
plugin_prefs.defaults[GET_SHELVES_OPTIONS_STORE_NAME]   = GET_SHELVES_OPTIONS_DEFAULTS
plugin_prefs.defaults[STORE_DEVICES]                    = DEFAULT_DEVICES_VALUES
plugin_prefs.defaults[CUSTOM_COLUMNS_STORE_NAME]        = CUSTOM_COLUMNS_OPTIONS_DEFAULTS
plugin_prefs.defaults[STORE_OPTIONS_STORE_NAME]         = STORE_OPTIONS_DEFAULTS
plugin_prefs.defaults[READING_POSITION_CHANGES_STORE_NAME]    = READING_POSITION_CHANGES_DEFAULTS


try:
    debug_print("KoboUtilites::action.py - loading translations")
    load_translations()
except NameError:
    debug_print("KoboUtilites::action.py - exception when loading translations")
    pass # load_translations() added in calibre 1.9

#            update_prefs = get_plugin_pref(UPDATE_OPTIONS_STORE_NAME, UPDATE_OPTIONS_DEFAULTS)

def get_plugin_pref(store_name, option):
    debug_print("get_plugin_pref - start - store_name='%s', option='%s'" % (store_name, option))
    c = plugin_prefs[store_name]
#     debug_print("get_plugin_pref - c:", c)
    default_value = plugin_prefs.defaults[store_name][option]
    return c.get(option, default_value)

def get_plugin_prefs(store_name, fill_defaults=False):
    if fill_defaults:
        c = get_prefs(plugin_prefs, store_name)
    else:
        c = plugin_prefs[store_name]
    return c

def get_prefs(prefs_store, store_name):
    debug_print("get_prefs - start - store_name='%s'" % (store_name, ))
#     debug_print("get_prefs - start - prefs_store='%s'" % (prefs_store,))
    store = {}
    if prefs_store is not None and store_name in prefs_store:
        for key in plugin_prefs.defaults[store_name].keys():
            store[key] = prefs_store[store_name].get(key, plugin_prefs.defaults[store_name][key])
    else:
        store = plugin_prefs.defaults[store_name]
    return store

def get_pref(store, store_name, option, defaults=None):
#     debug_print("get_pref - start - store_name='%s'" % (store_name, ))
#     debug_print("get_pref - start - option='%s'" % (option,))
    if defaults:
        default_value = defaults[option]
    else:
        default_value = plugin_prefs.defaults[store_name][option]
    return store.get(option, default_value)

def migrate_library_config_if_required(db, library_config):
    debug_print("migrate_library_config_if_required - start")
    schema_version = library_config.get(KEY_SCHEMA_VERSION, 0)
    if schema_version == DEFAULT_SCHEMA_VERSION:
        return
    # We have changes to be made - mark schema as updated
    library_config[KEY_SCHEMA_VERSION] = DEFAULT_SCHEMA_VERSION

    # Any migration code in future will exist in here.
    if schema_version <= 0.1 and not 'profiles' in library_config:
        print('Migrating Kobo Utilities library config')
        profile_config = {}
        profile_config[KEY_FOR_DEVICE] = TOKEN_ANY_DEVICE

        old_store_prefs = plugin_prefs[COMMON_OPTIONS_STORE_NAME]
        store_prefs = {}
        store_prefs[KEY_STORE_ON_CONNECT] = get_pref(old_store_prefs, COMMON_OPTIONS_STORE_NAME, KEY_STORE_ON_CONNECT, defaults=OLD_COMMON_OPTIONS_DEFAULTS)
        store_prefs[KEY_PROMPT_TO_STORE] = get_pref(old_store_prefs, COMMON_OPTIONS_STORE_NAME, KEY_PROMPT_TO_STORE, defaults=OLD_COMMON_OPTIONS_DEFAULTS)
        store_prefs[KEY_STORE_IF_MORE_RECENT] = get_pref(old_store_prefs, COMMON_OPTIONS_STORE_NAME, KEY_STORE_IF_MORE_RECENT, defaults=OLD_COMMON_OPTIONS_DEFAULTS)
        store_prefs[KEY_DO_NOT_STORE_IF_REOPENED] = get_pref(old_store_prefs, COMMON_OPTIONS_STORE_NAME, KEY_DO_NOT_STORE_IF_REOPENED, defaults=OLD_COMMON_OPTIONS_DEFAULTS)
        debug_print("migrate_library_config_if_required - store_prefs:", store_prefs)

        column_prefs = {}
        if library_config.get('currentReadingLocationColumn'):
            column_prefs[KEY_CURRENT_LOCATION_CUSTOM_COLUMN] = library_config['currentReadingLocationColumn']
            del library_config['currentReadingLocationColumn']
        if library_config.get('precentReadColumn'):
            column_prefs[KEY_PERCENT_READ_CUSTOM_COLUMN] = library_config['precentReadColumn']
            del library_config['precentReadColumn']
        if library_config.get('ratingColumn'):
            column_prefs[KEY_RATING_CUSTOM_COLUMN] = library_config['ratingColumn']
            del library_config['ratingColumn']
        if library_config.get('lastReadColumn'):
            column_prefs[KEY_LAST_READ_CUSTOM_COLUMN]  = library_config['lastReadColumn']
            del library_config['lastReadColumn']
        debug_print("migrate_library_config_if_required - column_prefs:", column_prefs)
        if len(column_prefs) > 0:
            profile_config[CUSTOM_COLUMNS_STORE_NAME] = column_prefs
            debug_print("migrate_library_config_if_required - profile_config:", profile_config)
            profile_config[STORE_OPTIONS_STORE_NAME]  = store_prefs
            new_profiles = {"Migrated" : profile_config}
            library_config[KEY_PROFILES] = new_profiles
        debug_print("migrate_library_config_if_required - library_config:", library_config)

    set_library_config(db, library_config)


def get_library_config(db):
    library_config = None

    if library_config is None:
        library_config = db.prefs.get_namespaced(PREFS_NAMESPACE, PREFS_KEY_SETTINGS,
                                                 copy.deepcopy(DEFAULT_LIBRARY_VALUES))
    migrate_library_config_if_required(db, library_config)
    debug_print("get_library_config - library_config:", library_config)
    return library_config

def get_profile_info(db, profile_name):
    library_config = get_library_config(db)
    profiles = library_config.get(KEY_PROFILES, {})
    profile_map = profiles.get(profile_name, DEFAULT_PROFILE_VALUES)
    return profile_map

def set_default_profile(db, profile_name):
    library_config = get_library_config(db)
#    library_config[KEY_DEFAULT_LIST] = profile_name
    set_library_config(db, library_config)

def get_book_profiles_for_device(db, device_uuid, exclude_auto=True):
    library_config = get_library_config(db)
    profiles_map = library_config[KEY_PROFILES]
    device_profiles = {}
    for profile_name, profile_info in profiles_map.items():
        if profile_info[KEY_FOR_DEVICE] in [device_uuid, TOKEN_ANY_DEVICE]:
            if not exclude_auto:
                device_profiles[profile_name] = profile_info
    return device_profiles

def get_book_profile_for_device(db, device_uuid, use_any_device=False):
    library_config = get_library_config(db)
    profiles_map = library_config.get(KEY_PROFILES, None)
    selected_profile = None
    if profiles_map is not None:
        for profile_name, profile_info in profiles_map.items():
            if profile_info[KEY_FOR_DEVICE] == device_uuid:
                profile_info['profileName'] = profile_name
                selected_profile = profile_info
                break
            elif use_any_device and profile_info[KEY_FOR_DEVICE] == TOKEN_ANY_DEVICE:
                profile_info['profileName'] = profile_name
                selected_profile = profile_info

    if selected_profile is not None:
        selected_profile[STORE_OPTIONS_STORE_NAME] = get_prefs(selected_profile, STORE_OPTIONS_STORE_NAME)
    return selected_profile

def get_profile_names(db, exclude_auto=True):
    library_config = get_library_config(db)
    profiles = library_config[KEY_PROFILES]
    if not exclude_auto:
        return sorted(list(profiles.keys()))

    profile_names = []
    for profile_name, profile_info in profiles.items():
        if profile_info.get(KEY_FOR_DEVICE, DEFAULT_PROFILE_VALUES[KEY_FOR_DEVICE]) == 'POPMANUAL':
            profile_names.append(profile_name)
    return sorted(profile_names)

def get_device_name(device_uuid, default_name=_("(Unknown device)")):
    device = get_device_config(device_uuid)
    device_name = device['name'] if device else default_name
    return device_name

def get_device_config(device_uuid):
    device_config = plugin_prefs[STORE_DEVICES].get(device_uuid, None)
    return device_config

def set_library_config(db, library_config):
    debug_print("set_library_config - library_config:", library_config)
    db.prefs.set_namespaced(PREFS_NAMESPACE, PREFS_KEY_SETTINGS, library_config)


class ProfilesTab(QWidget):

    def __init__(self, parent_dialog, plugin_action):
        self.parent_dialog = parent_dialog
        QWidget.__init__(self)
        
        self.plugin_action = plugin_action
        self.help_anchor = "configuration"
        self.library_config = get_library_config(self.plugin_action.gui.current_db)
        debug_print("ProfilesTab.__init__ - self.library_config", self.library_config)
        self.profiles = self.library_config.get(KEY_PROFILES, {})
        self.current_device_profile = self.plugin_action.current_device_profile
        self.profile_name = self.current_device_profile['profileName'] if self.current_device_profile else None

        layout = QVBoxLayout(self)
        self.setLayout(layout)
        
        # -------- Lists configuration ---------
        select_profile_layout = QHBoxLayout()
        layout.addLayout(select_profile_layout)
        profiles_label = QLabel(_('Profiles:'), self)
        select_profile_layout.addWidget(profiles_label)
        self.select_profile_combo = ProfileComboBox(self, self.profiles, self.profile_name)
        self.select_profile_combo.setMinimumSize(150, 20)
        self.select_profile_combo.currentIndexChanged.connect(self._select_profile_combo_changed)
        select_profile_layout.addWidget(self.select_profile_combo)
        self.add_profile_button = QToolButton(self)
        self.add_profile_button.setToolTip(_('Add profile'))
        self.add_profile_button.setIcon(QIcon(I('plus.png')))
        self.add_profile_button.clicked.connect(self.add_profile)
        select_profile_layout.addWidget(self.add_profile_button)
        self.delete_profile_button = QToolButton(self)
        self.delete_profile_button.setToolTip(_('Delete profile'))
        self.delete_profile_button.setIcon(QIcon(I('minus.png')))
        self.delete_profile_button.clicked.connect(self.delete_profile)
        select_profile_layout.addWidget(self.delete_profile_button)
        self.rename_profile_button = QToolButton(self)
        self.rename_profile_button.setToolTip(_('Rename profile'))
        self.rename_profile_button.setIcon(QIcon(I('edit-undo.png')))
        self.rename_profile_button.clicked.connect(self.rename_profile)
        select_profile_layout.addWidget(self.rename_profile_button)
        select_profile_layout.insertStretch(-1)

        device_layout = QHBoxLayout()
        layout.addLayout(device_layout)
        device_label = QLabel(_('&Device this profile is for:'), self)
        device_label.setToolTip(_('Select the device this profile is for.'))
        self.device_combo = DeviceColumnComboBox(self)
        device_label.setBuddy(self.device_combo)
        device_layout.addWidget(device_label)
        device_layout.addWidget(self.device_combo)

        custom_column_group = QGroupBox(_('Custom Columns'), self)
        layout.addWidget(custom_column_group )
        options_layout = QGridLayout()
        custom_column_group.setLayout(options_layout)

        self.custom_columns = {}
        self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_READING_LOCATION] = {'current_columns' : self.get_text_custom_columns}
        self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_PERCENT_READ] = {'current_columns': self.get_number_custom_columns}
        self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_RATING] = {'current_columns': self.get_rating_custom_columns}
        self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_LAST_READ] = {'current_columns': self.get_date_custom_columns}

        self.current_Location_combo = self.create_custom_column_controls(options_layout, CUSTOM_COLUMN_DEFAULT_LOOKUP_READING_LOCATION, 1)
        self.percent_read_combo = self.create_custom_column_controls(options_layout, CUSTOM_COLUMN_DEFAULT_LOOKUP_PERCENT_READ, 2)
        self.rating_combo = self.create_custom_column_controls(options_layout, CUSTOM_COLUMN_DEFAULT_LOOKUP_RATING, 3)
        self.last_read_combo = self.create_custom_column_controls(options_layout, CUSTOM_COLUMN_DEFAULT_LOOKUP_LAST_READ, 4)

        auto_store_group = QGroupBox(_('Store on connect'), self)
        layout.addWidget(auto_store_group )
        options_layout = QGridLayout()
        auto_store_group.setLayout(options_layout)

        self.store_on_connect_checkbox = QCheckBox(_("Store current bookmarks/reading position on connect"), self)
        self.store_on_connect_checkbox.setToolTip(_("When this is checked, the library will be updated with the current bookmark for all books on the device."))
        self.store_on_connect_checkbox.clicked.connect(self.store_on_connect_checkbox_clicked)
        options_layout.addWidget(self.store_on_connect_checkbox, 0, 0, 1, 3)

        self.prompt_to_store_checkbox = QCheckBox(_("Prompt to store any changes"), self)
        self.prompt_to_store_checkbox.setToolTip(_("Enable this to be prompted to save the changed bookmarks after an automatic store is done."))
        options_layout.addWidget(self.prompt_to_store_checkbox, 1, 0, 1, 1)

        self.store_if_more_recent_checkbox = QCheckBox(_("Only if more recent"), self)
        self.store_if_more_recent_checkbox.setToolTip(_("Only store the reading position if the last read timestamp on the device is more recent than in the library."))
        options_layout.addWidget(self.store_if_more_recent_checkbox, 1, 1, 1, 1)

        self.do_not_store_if_reopened_checkbox = QCheckBox(_("Not if finished in library"), self)
        self.do_not_store_if_reopened_checkbox.setToolTip(_("Do not store the reading position if the library has the book as finished. This is if the percent read is 100%."))
        options_layout.addWidget(self.do_not_store_if_reopened_checkbox, 1, 2, 1, 1)

        layout.addStretch(1)

    def create_custom_column_controls(self, options_layout, custom_col_name, row_number=1):
        current_Location_label = QLabel(CUSTOM_COLUMN_DEFAULTS[custom_col_name]['config_label'], self)
        current_Location_label.setToolTip(CUSTOM_COLUMN_DEFAULTS[custom_col_name]['config_tool_tip'])
        create_column_callback=partial(self.create_custom_column, custom_col_name) if self.parent_dialog.supports_create_custom_column else None
        avail_columns = self.custom_columns[custom_col_name]['current_columns']()
        custom_column_combo = CustomColumnComboBox(self, avail_columns, create_column_callback=create_column_callback)
        current_Location_label.setBuddy(custom_column_combo)
        options_layout.addWidget(current_Location_label, row_number, 0, 1, 1)
        options_layout.addWidget(custom_column_combo, row_number, 1, 1, 1)
        self.custom_columns[custom_col_name]['combo_box'] = custom_column_combo

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
#        import traceback
#        traceback.print_stack()
        
        debug_print('BEGIN Validate')
        valid = True
        # Only save if we were able to get data to avoid corrupting stored data
#        if self.do_daily_backp_checkbox.checkState() == Qt.Checked and not len(self.dest_directory_edit.text()):
#            error_dialog(self, 'No destination directory',
#                            'If the automatic device backup is set, there must be a destination directory.',
#                            show=True, show_copy_button=False)
#            valid = False

        debug_print('END Validate, status = %s' % valid)
        return valid

    def add_profile(self):
        debug_print("ProfilesTab:add_profile - Start")
        # Display a prompt allowing user to specify a new profile
        new_profile_name, ok = QInputDialog.getText(self, _('Add new profile'),
                    _('Enter a unique display name for this profile:'), text='Default')
        if not ok:
            # Operation cancelled
            return
        new_profile_name = unicode(new_profile_name).strip()
        # Verify it does not clash with any other profiles in the profile
        for profile_name in self.profiles.keys():
            debug_print("ProfilesTab:add_profile - existing profile: ", profile_name)
            if profile_name.lower() == new_profile_name.lower():
                return error_dialog(self,
                                    _('Add failed'),
                                    _('A profile with the same name already exists'),
                                    show=True)

        # As we are about to switch profile, persist the current profiles details if any
        self.persist_profile_config()
        self.profile_name = new_profile_name
        self.profiles[new_profile_name] = copy.deepcopy(DEFAULT_PROFILE_VALUES)
        debug_print("ProfilesTab:add_profile - new profile: ", self.profiles[new_profile_name])
        # Now update the profiles combobox
        self.select_profile_combo.populate_combo(self.profiles, new_profile_name)
        self.refresh_current_profile_info()
        debug_print("ProfilesTab:add_profile - End")

    def rename_profile(self):
        if not self.profile_name:
            return
        # Display a prompt allowing user to specify a rename profile
        old_profile_name = self.profile_name
        new_profile_name, ok = QInputDialog.getText(self, _('Rename profile'),
                    _('Enter a new display name for this profile:'), text=old_profile_name)
        if not ok:
            # Operation cancelled
            return
        new_profile_name = unicode(new_profile_name).strip()
        if new_profile_name == old_profile_name:
            return
        # Verify it does not clash with any other profiles in the profile
        for profile_name in self.profiles.keys():
            if profile_name == old_profile_name:
                continue
            if profile_name.lower() == new_profile_name.lower():
                return error_dialog(self, _('Add failed'), _('A profile with the same name already exists'),
                                    show=True, show_copy_button=False)

        # As we are about to rename profile, persist the current profiles details if any
        self.persist_profile_config()
        self.profiles[new_profile_name] = self.profiles[old_profile_name]
#        if self.default_profile == old_profile_name:
#            self.default_profile = new_profile_name
        del self.profiles[old_profile_name]
        self.profile_name = new_profile_name
        # Now update the profiles combobox
        self.select_profile_combo.populate_combo(self.profiles, new_profile_name)
        self.refresh_current_profile_info()

    def delete_profile(self):
        if not self.profile_name:
            return
        if len(self.profiles) == 1:
            return error_dialog(self, _('Cannot delete'), _('You must have at least one profile'),
                                    show=True, show_copy_button=False)
        if not confirm(_("Do you want to delete the profile named '{0}'".format(self.profile_name)),
                        'reading_profile_delete_profile', self):
            return
        del self.profiles[self.profile_name]
#        if self.default_profile == self.profile_name:
#            self.default_profile = self.profiles.keys()[0]
        # Now update the profiles combobox
        self.select_profile_combo.populate_combo(self.profiles)
        self.refresh_current_profile_info()

    def refresh_current_profile_info(self):
        debug_print("ProfilesTab:refresh_current_profile_info - Start")
        # Get configuration for the selected profile
        self.profile_name = unicode(self.select_profile_combo.currentText()).strip()
        profile_map = get_profile_info(self.plugin_action.gui.current_db, self.profile_name)

        device_uuid = profile_map.get(KEY_FOR_DEVICE, None)

        column_prefs = profile_map.get(CUSTOM_COLUMNS_STORE_NAME, CUSTOM_COLUMNS_OPTIONS_DEFAULTS)
        current_Location_column  = get_pref(column_prefs, CUSTOM_COLUMNS_STORE_NAME, KEY_CURRENT_LOCATION_CUSTOM_COLUMN)
        percent_read_column      = get_pref(column_prefs, CUSTOM_COLUMNS_STORE_NAME, KEY_PERCENT_READ_CUSTOM_COLUMN)
        rating_column            = get_pref(column_prefs, CUSTOM_COLUMNS_STORE_NAME, KEY_RATING_CUSTOM_COLUMN)
        last_read_column         = get_pref(column_prefs, CUSTOM_COLUMNS_STORE_NAME, KEY_LAST_READ_CUSTOM_COLUMN)
#        debug_print("ProfilesTab:refresh_current_profile_info - current_Location_column=%s, percent_read_column=%s, rating_column=%s" % (current_Location_column, percent_read_column, rating_column))

        store_prefs = profile_map.get(STORE_OPTIONS_STORE_NAME, STORE_OPTIONS_DEFAULTS)
        store_on_connect         = get_pref(store_prefs, STORE_OPTIONS_STORE_NAME, KEY_STORE_ON_CONNECT)
        prompt_to_store          = get_pref(store_prefs, STORE_OPTIONS_STORE_NAME, KEY_PROMPT_TO_STORE)
        store_if_more_recent     = get_pref(store_prefs, STORE_OPTIONS_STORE_NAME, KEY_STORE_IF_MORE_RECENT)
        do_not_store_if_reopened = get_pref(store_prefs, STORE_OPTIONS_STORE_NAME, KEY_DO_NOT_STORE_IF_REOPENED)

        # Display profile configuration in the controls
        self.current_Location_combo.populate_combo(self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_READING_LOCATION]['current_columns'](), current_Location_column)
        self.percent_read_combo.populate_combo(self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_PERCENT_READ]['current_columns'](), percent_read_column)
        self.rating_combo.populate_combo(self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_RATING]['current_columns'](), rating_column)
        self.last_read_combo.populate_combo(self.custom_columns[CUSTOM_COLUMN_DEFAULT_LOOKUP_LAST_READ]['current_columns'](), last_read_column)

        self.device_combo.populate_combo(self.parent_dialog.get_devices_list(), device_uuid)
        self.store_on_connect_checkbox.setCheckState(Qt.Checked if store_on_connect else Qt.Unchecked)
        self.prompt_to_store_checkbox.setCheckState(Qt.Checked if prompt_to_store else Qt.Unchecked)
        self.prompt_to_store_checkbox.setEnabled(store_on_connect)
        self.store_if_more_recent_checkbox.setCheckState(Qt.Checked if store_if_more_recent else Qt.Unchecked)
        self.store_if_more_recent_checkbox.setEnabled(store_on_connect)
        self.do_not_store_if_reopened_checkbox.setCheckState(Qt.Checked if do_not_store_if_reopened else Qt.Unchecked)
        self.do_not_store_if_reopened_checkbox.setEnabled(store_on_connect)

        debug_print("ProfilesTab:refresh_current_profile_info - end")

    def persist_profile_config(self):
        debug_print("ProfilesTab:persist_profile_config - Start")
        if not self.profile_name:
            return

        profile_config = self.profiles[self.profile_name]
        debug_print("ProfilesTab:persist_profile_config - profile_config:", profile_config)

        profile_config[KEY_FOR_DEVICE] = self.device_combo.get_selected_device()

        store_prefs = {}
        store_prefs[KEY_STORE_ON_CONNECT]         = self.store_on_connect_checkbox.checkState() == Qt.Checked
        store_prefs[KEY_PROMPT_TO_STORE]          = self.prompt_to_store_checkbox.checkState() == Qt.Checked
        store_prefs[KEY_STORE_IF_MORE_RECENT]     = self.store_if_more_recent_checkbox.checkState() == Qt.Checked
        store_prefs[KEY_DO_NOT_STORE_IF_REOPENED] = self.do_not_store_if_reopened_checkbox.checkState() == Qt.Checked
        profile_config[STORE_OPTIONS_STORE_NAME]  = store_prefs
        debug_print("ProfilesTab:persist_profile_config - store_prefs:", store_prefs)

        column_prefs = {}
        column_prefs[KEY_CURRENT_LOCATION_CUSTOM_COLUMN] = self.current_Location_combo.get_selected_column()
        debug_print("ProfilesTab:persist_profile_config - column_prefs[KEY_CURRENT_LOCATION_CUSTOM_COLUMN]:", column_prefs[KEY_CURRENT_LOCATION_CUSTOM_COLUMN])
        column_prefs[KEY_PERCENT_READ_CUSTOM_COLUMN]     = self.percent_read_combo.get_selected_column()
        column_prefs[KEY_RATING_CUSTOM_COLUMN]           = self.rating_combo.get_selected_column()
        column_prefs[KEY_LAST_READ_CUSTOM_COLUMN]        = self.last_read_combo.get_selected_column()
        profile_config[CUSTOM_COLUMNS_STORE_NAME]        = column_prefs

        self.profiles[self.profile_name] = profile_config

        debug_print("ProfilesTab:persist_profile_config - end")

    def get_number_custom_columns(self):
        column_types = ['float','int']
        return self.get_custom_columns(column_types)

    def get_rating_custom_columns(self):
        column_types = ['rating','int']
        custom_columns = self.get_custom_columns(column_types)
        ratings_column_name = self.plugin_action.gui.library_view.model().orig_headers['rating']
        custom_columns['rating'] = {'name': ratings_column_name}
        return custom_columns

    def get_text_custom_columns(self):
        column_types = ['text','comments']
        return self.get_custom_columns(column_types)

    def get_date_custom_columns(self):
        column_types = ['datetime']
        return self.get_custom_columns(column_types)

    def get_custom_columns(self, column_types):
        if self.parent_dialog.supports_create_custom_column:
            custom_columns = self.parent_dialog.get_create_new_custom_column_instance.current_columns()
        else:
            custom_columns = self.plugin_action.gui.library_view.model().custom_columns
        available_columns = {}
        for key, column in custom_columns.items():
            typ = column['datatype']
            if typ in column_types and not column['is_multiple']:
                available_columns[key] = column
        return available_columns
    
    def create_custom_column(self, lookup_name=None):
        debug_print("ProfilesTab:create_custom_column - lookup_name:", lookup_name)
        display_params = {
            'description': CUSTOM_COLUMN_DEFAULTS[lookup_name]['description']
        }
        datatype = CUSTOM_COLUMN_DEFAULTS[lookup_name]['datatype']
        column_heading  = CUSTOM_COLUMN_DEFAULTS[lookup_name]['column_heading']
        
        # current_lookup_names = self.custom_columns[lookup_name]['current_columns'].keys()
        new_lookup_name = lookup_name
        # i = 0
        # while new_lookup_name in current_lookup_names:
        #     i += 1
        #     new_lookup_name = "{0}_{1}".format(lookup_name, i)
        # if i > 0:
        #     column_heading = "{0} {1}".format(column_heading, i)

        create_new_custom_column_instance = self.parent_dialog.get_create_new_custom_column_instance
        result = create_new_custom_column_instance.create_column(new_lookup_name, column_heading, datatype, False, display=display_params, generate_unused_lookup_name=True, freeze_lookup_name=False)
        debug_print("ProfilesTab:create_custom_column - result:", result)
        if result[0] == CreateNewCustomColumn.Result.COLUMN_ADDED:
            # print(self.get_text_custom_columns())
            # print(self.plugin_action.gui.current_db.field_metadata.custom_field_metadata())
            self.custom_columns[lookup_name]['combo_box'].populate_combo(self.custom_columns[lookup_name]['current_columns'](), result[1])
            self.parent_dialog.must_restart = True
            return True
        
        return False


class DevicesTab(QWidget):

    def __init__(self, parent_dialog, plugin_action):
        self.parent_dialog = parent_dialog
        QWidget.__init__(self)

        self.plugin_action = plugin_action
        self.gui = plugin_action.gui
        self._connected_device_info = plugin_action.connected_device_info
        self.library_config = get_library_config(self.gui.current_db)
        
        self.individual_device_options = get_plugin_pref(COMMON_OPTIONS_STORE_NAME, KEY_INDIVIDUAL_DEVICE_OPTIONS)

        layout = QVBoxLayout()
        self.setLayout(layout)

        # -------- Device configuration ---------
        devices_group_box = QGroupBox(_('Devices:'), self)
        layout.addWidget(devices_group_box)
        devices_group_box_layout = QVBoxLayout()
        devices_group_box.setLayout(devices_group_box_layout)

        self.devices_table = DevicesTableWidget(self)
        # Note: Do not connect the itemSlectionChanged signale here. It gets done after the table is filled the first time.
        # self.devices_table.itemSelectionChanged.connect(self._devices_table_item_selection_changed)
        devices_group_box_layout.addWidget(self.devices_table)

        buttons_layout = QHBoxLayout()
        devices_group_box_layout.addLayout(buttons_layout)

        self.add_device_btn = QPushButton(_('Add connected device'), self)
        self.add_device_btn.setToolTip(
                _('If you do not have a device connected currently, either plug one\n'
                'in now or exit the dialog and connect to folder/iTunes first'))
        self.add_device_btn.setIcon(QIcon(I('plus.png')))
        self.add_device_btn.clicked.connect(self._add_device_clicked)
        buttons_layout.addWidget(self.add_device_btn, 1)
        
        self.rename_device_btn = QToolButton(self)
        self.rename_device_btn.setIcon(get_icon('edit-undo.png'))
        self.rename_device_btn.setToolTip(_('Rename the currently connected device'))
        self.rename_device_btn.clicked.connect(self._rename_device_clicked)
        self.rename_device_btn.setEnabled(False)
        buttons_layout.addWidget(self.rename_device_btn)
        
        self.delete_device_btn = QToolButton(self)
        self.delete_device_btn.setIcon(QIcon(I('trash.png')))
        self.delete_device_btn.setToolTip(_('Delete this device from the device list'))
        self.delete_device_btn.clicked.connect(self._delete_device_clicked)
        self.delete_device_btn.setEnabled(False)
        buttons_layout.addWidget(self.delete_device_btn)

        self.device_options_for_each_checkbox = QCheckBox(_('Configure options for each device'), self)
        self.device_options_for_each_checkbox.setToolTip(_('Selected this option to configure backup and firmware for each device.'))
        self.device_options_for_each_checkbox.clicked.connect(self.device_options_for_each_checkbox_clicked)
        if self.individual_device_options:
            self.device_options_for_each_checkbox.setCheckState(Qt.Checked)
        layout.addWidget(self.device_options_for_each_checkbox)

        update_options_group = QGroupBox(_('Firmware Update Options'), self)
        layout.addWidget(update_options_group)
        options_layout = QGridLayout()
        update_options_group.setLayout(options_layout)

        self.do_update_check = QCheckBox(_('Check for Kobo firmware updates daily?'), self)
        self.do_update_check.setToolTip(_('If this is selected the plugin will check for Kobo firmware updates when your Kobo device is plugged in, once per 24-hour period.'))
        options_layout.addWidget(self.do_update_check, 0, 0, 1, 1)

        self.do_early_firmware_check = QCheckBox(_('Use early firmware adopter affiliate?'), self)
        self.do_early_firmware_check.setToolTip(_('WARNING: THIS OPTION RISKS DOWNLOADING THE WRONG FIRMWARE FOR YOUR DEVICE! YOUR DEVICE MAY NOT FUNCTION PROPERLY IF THIS HAPPENS! Choose this option to attempt to download Kobo firmware updates before they are officially available for your device.'))
        options_layout.addWidget(self.do_early_firmware_check, 0, 1, 1, 1)

        backup_options_group = QGroupBox(_('Device Database Backup'), self)
        layout.addWidget(backup_options_group)
        options_layout = QGridLayout()
        backup_options_group.setLayout(options_layout)

        self.do_daily_backp_checkbox = QCheckBox(_('Backup the device database daily'), self)
        self.do_daily_backp_checkbox.setToolTip(_('If this is selected the plugin will backup the device database the first time it is connected each day.'))
        self.do_daily_backp_checkbox.clicked.connect(self.do_daily_backp_checkbox_clicked)
        options_layout.addWidget(self.do_daily_backp_checkbox, 0, 0, 1, 2)

        self.backup_each_connection_checkbox = QCheckBox(_('Backup the device database on each connection'), self)
        self.backup_each_connection_checkbox.setToolTip(_('If this is selected the plugin will backup the device database each time the device is connected.'))
        self.backup_each_connection_checkbox.clicked.connect(self.backup_each_connection_checkbox_clicked)
        options_layout.addWidget(self.backup_each_connection_checkbox, 0, 2, 1, 3)

        self.dest_directory_label = QLabel(_("Destination:"), self)
        self.dest_directory_label.setToolTip(_("Select the destination to backup the device database to."))
        self.dest_directory_edit = QLineEdit(self)
        self.dest_directory_edit.setMinimumSize(150, 0)
        self.dest_directory_label.setBuddy(self.dest_directory_edit)
        self.dest_pick_button = QPushButton(_("..."), self)
        self.dest_pick_button.setMaximumSize(24, 20)
        self.dest_pick_button.clicked.connect(self._get_dest_directory_name)
        options_layout.addWidget(self.dest_directory_label, 1, 0, 1, 1)
        options_layout.addWidget(self.dest_directory_edit, 1, 1, 1, 1)
        options_layout.addWidget(self.dest_pick_button, 1, 2, 1, 1)

        self.copies_to_keep_checkbox = QCheckBox(_('Copies to keep'), self)
        self.copies_to_keep_checkbox.setToolTip(_("Select this to limit the number of backup kept. If not set, the backup files must be manually deleted."))
        self.copies_to_keep_spin = QSpinBox(self)
        self.copies_to_keep_spin.setMinimum(2)
        self.copies_to_keep_spin.setToolTip(_("The number of backup copies of the database to keep. The minimum is 2."))
        options_layout.addWidget(self.copies_to_keep_checkbox, 1, 3, 1, 1)
        options_layout.addWidget(self.copies_to_keep_spin, 1, 4, 1, 1)
        self.copies_to_keep_checkbox.clicked.connect(self.copies_to_keep_checkbox_clicked)

        self.zip_database_checkbox = QCheckBox(_('Compress database with config files'), self)
        self.zip_database_checkbox.setToolTip(_("If checked, the database file will be added to the zip file with configuration files."))
        options_layout.addWidget(self.zip_database_checkbox, 2, 0, 1, 3)

        self.toggle_backup_options_state(False)

        layout.insertStretch(-1)

    def on_device_connection_changed(self, is_connected):
        if not is_connected:
            self._connected_device_info = None
            self.update_from_connection_status()

    def on_device_metadata_available(self):
        if self.plugin_action.have_kobo():
            self._connected_device_info = self.gui.device_manager.get_current_device_information().get('info', None)
            self.update_from_connection_status()

    def _devices_table_item_selection_changed(self):
        debug_print("_devices_table_item_selection_changed - len(self.devices_table.selectedIndexes())=", len(self.devices_table.selectedIndexes()))
        debug_print("_devices_table_item_selection_changed - self.devices_table.selectedIndexes()=", self.devices_table.selectedIndexes())
        if len(self.devices_table.selectedIndexes()) > 0:
            self.delete_device_btn.setEnabled(True)
        else:
            self.delete_device_btn.setEnabled(False)

        self.rename_device_btn.setEnabled(self.devices_table.rowCount() > 1)

        if self.individual_device_options:
            self.persist_devices_config()
            self.refresh_current_device_options()

    def _add_device_clicked(self):
        devices = self.devices_table.get_data()
        drive_info = self._connected_device_info[4]
        for location_info in drive_info.values():
            if location_info['location_code'] == 'main':
                new_device = {}
                new_device['type'] = self._connected_device_info[0]
                new_device['active'] = True
                new_device['uuid'] = location_info['device_store_uuid']
                new_device['name'] = location_info['device_name']
                new_device['location_code'] = location_info['location_code']
                new_device['serial_no'] = self.plugin_action.device_serial_no()
                devices[new_device['uuid']] = new_device

        self.devices_table.populate_table(devices, self._connected_device_info)
        self.update_from_connection_status(update_table=False)
        # Ensure the devices combo is refreshed for the current list
        self.parent_dialog.profiles_tab.refresh_current_profile_info()

    def _rename_device_clicked(self):
        (device_info, is_connected) = self.devices_table.get_selected_device_info()
        if not device_info:
            return error_dialog(self, _('Rename failed'), _('You must select a device first'),
                                show=True, show_copy_button=False)
        # if not is_connected:
        #     return error_dialog(self, _('Rename failed'),
        #                         _('You can only rename a device that is currently connected'),
        #                         show=True, show_copy_button=False)

        old_name = device_info['name']
        new_device_name, ok = QInputDialog.getText(self, _('Rename device'),
                    _('Enter a new display name for this device:'), text=old_name)
        if not ok:
            # Operation cancelled
            return
        new_device_name = unicode(new_device_name).strip()
        if new_device_name == old_name:
            return
        try:
            self.gui.device_manager.set_driveinfo_name(device_info['location_code'], new_device_name)
            self.devices_table.set_current_row_device_name(new_device_name)
            # Ensure the devices combo is refreshed for the current list
            self.parent_dialog.profiles_tab.refresh_current_profile_info()
        except:
            return error_dialog(self, _('Rename failed'), _('An error occured while renaming.'),
                                det_msg=traceback.format_exc(), show=True)

    def _delete_device_clicked(self):
        (device_info, _is_connected) = self.devices_table.get_selected_device_info()
        if not device_info:
            return error_dialog(self, _('Delete failed'), _('You must select a device first'),
                                show=True, show_copy_button=False)
        name = device_info['name']
        if not question_dialog(self, _('Are you sure?'), '<p>'+
                _('You are about to remove the <b>{0}</b> device from this list. '.format(name)) +
                _('Are you sure you want to continue?')):
            return
        self.parent_dialog.profiles_tab.persist_profile_config()
        self.devices_table.delete_selected_row()
        self.update_from_connection_status(update_table=False)

        # Ensure any lists are no longer associated with this device
        # NOTE: As of version 1.5 we can no longer do this since we only know the lists
        #       for the current library, not all libraries. So just reset this library
        #       and put some "self-healing" logic elsewhere to ensure a user loading a
        #       list for a deleted device in another library gets it reset at that point.
        self.parent_dialog.delete_device_from_lists(self.library_config, device_info['uuid'])
        # Ensure the devices combo is refreshed for the current list
        self.parent_dialog.profiles_tab.refresh_current_profile_info()

    def update_from_connection_status(self, first_time=False, update_table=True):
        if first_time:
            devices = plugin_prefs[STORE_DEVICES]
        else:
            devices = self.devices_table.get_data()

        if self._connected_device_info is None or not self.plugin_action.haveKobo():
            self.add_device_btn.setEnabled(False)
            # self.rename_device_btn.setEnabled(False)
        else:
            # Check to see whether we are connected to a device we already know about
            is_new_device = True
            can_rename = False
            drive_info = self._connected_device_info[4]
            if drive_info:
                # This is a non iTunes device that we can check to see if we have the UUID for
                device_uuid = drive_info['main']['device_store_uuid']
                if device_uuid in devices:
                    is_new_device = False
                    can_rename = True
            else:
                # This is a device without drive info like iTunes
                device_type = self._connected_device_info[0]
                if device_type in devices:
                    is_new_device = False
            self.add_device_btn.setEnabled(is_new_device)
            # self.rename_device_btn.setEnabled(can_rename)
        if update_table:
            self.devices_table.populate_table(devices, self._connected_device_info)
            self.refresh_current_device_options()
        if first_time:
            self.devices_table.itemSelectionChanged.connect(self._devices_table_item_selection_changed)


    def toggle_backup_options_state(self, enabled):
        self.dest_directory_edit.setEnabled(enabled)
        self.dest_pick_button.setEnabled(enabled)
        self.dest_directory_label.setEnabled(enabled)
        self.copies_to_keep_checkbox.setEnabled(enabled)
        self.copies_to_keep_checkbox_clicked(enabled and self.copies_to_keep_checkbox.checkState() == Qt.Checked)
        self.zip_database_checkbox.setEnabled(enabled)

    def do_daily_backp_checkbox_clicked(self, checked):
        enable_backup_options = checked or self.backup_each_connection_checkbox.checkState() ==  Qt.Checked
        self.toggle_backup_options_state(enable_backup_options)
        if self.backup_each_connection_checkbox.checkState() ==  Qt.Checked:
            self.backup_each_connection_checkbox.setCheckState(Qt.Unchecked)

    def backup_each_connection_checkbox_clicked(self, checked):
        enable_backup_options = checked or self.do_daily_backp_checkbox.checkState() ==  Qt.Checked
        self.toggle_backup_options_state(enable_backup_options)
        if self.do_daily_backp_checkbox.checkState() ==  Qt.Checked:
            self.do_daily_backp_checkbox.setCheckState(Qt.Unchecked)

    def device_options_for_each_checkbox_clicked(self, checked):
        self.individual_device_options = checked or self.device_options_for_each_checkbox.checkState() ==  Qt.Checked
        self.refresh_current_device_options()

    def copies_to_keep_checkbox_clicked(self, checked):
        self.copies_to_keep_spin.setEnabled(checked)

    def _get_dest_directory_name(self):
        path = choose_dir(self, 'backup annotations destination dialog', _('Choose Backup Destination'))
        if path:
            self.dest_directory_edit.setText(path)

    def refresh_current_device_options(self):
#         debug_print("DevicesTab:refresh_current_device_options - Start")

        if self.individual_device_options:
            (self.current_device_info, _is_connected) = self.devices_table.get_selected_device_info()
            if self.current_device_info:
                update_prefs = self.current_device_info.get(UPDATE_OPTIONS_STORE_NAME, UPDATE_OPTIONS_DEFAULTS)
                backup_prefs = self.current_device_info.get(BACKUP_OPTIONS_STORE_NAME, BACKUP_OPTIONS_DEFAULTS)
            else:
                update_prefs = UPDATE_OPTIONS_DEFAULTS
                backup_prefs = BACKUP_OPTIONS_DEFAULTS
        else:
            update_prefs = get_plugin_prefs(UPDATE_OPTIONS_STORE_NAME)
            backup_prefs = get_plugin_prefs(BACKUP_OPTIONS_STORE_NAME)

        do_check_for_firmware_updates = get_pref(update_prefs, UPDATE_OPTIONS_STORE_NAME, KEY_DO_UPDATE_CHECK)
        do_early_firmware_updates     = get_pref(update_prefs, UPDATE_OPTIONS_STORE_NAME, KEY_DO_EARLY_FIRMWARE_CHECK)
        self.update_check_last_time   = get_pref(update_prefs, UPDATE_OPTIONS_STORE_NAME, KEY_LAST_FIRMWARE_CHECK_TIME)

        do_daily_backup          = get_pref(backup_prefs, BACKUP_OPTIONS_STORE_NAME, KEY_DO_DAILY_BACKUP)
        backup_each_connection   = get_pref(backup_prefs, BACKUP_OPTIONS_STORE_NAME, KEY_BACKUP_EACH_CONNECTION)
        dest_directory           = get_pref(backup_prefs, BACKUP_OPTIONS_STORE_NAME, KEY_BACKUP_DEST_DIRECTORY)
        copies_to_keep           = get_pref(backup_prefs, BACKUP_OPTIONS_STORE_NAME, KEY_BACKUP_COPIES_TO_KEEP)
        zip_database             = get_pref(backup_prefs, BACKUP_OPTIONS_STORE_NAME, KEY_BACKUP_ZIP_DATABASE)

        self.do_update_check.setCheckState(Qt.Checked if do_check_for_firmware_updates else Qt.Unchecked)
        self.do_early_firmware_check.setCheckState(Qt.Checked if do_early_firmware_updates else Qt.Unchecked)
        self.do_daily_backp_checkbox.setCheckState(Qt.Checked if do_daily_backup else Qt.Unchecked)
        self.backup_each_connection_checkbox.setCheckState(Qt.Checked if backup_each_connection else Qt.Unchecked)
        self.dest_directory_edit.setText(dest_directory)
        self.zip_database_checkbox.setCheckState(Qt.Checked if zip_database else Qt.Unchecked)
        if copies_to_keep == -1:
            self.copies_to_keep_checkbox.setCheckState(Qt.Unchecked)
        else:
            self.copies_to_keep_checkbox.setCheckState(Qt.Checked)
            self.copies_to_keep_spin.setProperty('value', copies_to_keep)
#         debug_print("DevicesTab:refresh_current_device_options - do_daily_backup=%s, backup_each_connection=%s" % (do_daily_backup, backup_each_connection))
        if do_daily_backup:
            self.do_daily_backp_checkbox_clicked(do_daily_backup)
        if backup_each_connection:
            self.backup_each_connection_checkbox_clicked(backup_each_connection)
#         debug_print("DevicesTab:refresh_current_device_options - end")

    def persist_devices_config(self):
        debug_print("DevicesTab:persist_devices_config - Start")

        update_prefs = {}
        update_prefs[KEY_DO_UPDATE_CHECK]          = self.do_update_check.checkState() == Qt.Checked
        update_prefs[KEY_DO_EARLY_FIRMWARE_CHECK]  = self.do_early_firmware_check.checkState() == Qt.Checked
        update_prefs[KEY_LAST_FIRMWARE_CHECK_TIME] = self.update_check_last_time
        debug_print("DevicesTab:persist_devices_config - update_prefs:", update_prefs)

        backup_prefs = {}
        backup_prefs[KEY_DO_DAILY_BACKUP]       = self.do_daily_backp_checkbox.checkState() == Qt.Checked
        backup_prefs[KEY_BACKUP_EACH_CONNECTION]= self.backup_each_connection_checkbox.checkState() == Qt.Checked
        backup_prefs[KEY_BACKUP_ZIP_DATABASE]   = self.zip_database_checkbox.checkState() == Qt.Checked
        backup_prefs[KEY_BACKUP_DEST_DIRECTORY] = unicode(self.dest_directory_edit.text())
        backup_prefs[KEY_BACKUP_COPIES_TO_KEEP] = int(unicode(self.copies_to_keep_spin.value())) if self.copies_to_keep_checkbox.checkState() == Qt.Checked else -1 
        debug_print("DevicesTab:persist_devices_config - backup_prefs:", backup_prefs)

        if self.individual_device_options:
            if self.current_device_info:
                self.current_device_info[UPDATE_OPTIONS_STORE_NAME] = update_prefs
                self.current_device_info[BACKUP_OPTIONS_STORE_NAME] = backup_prefs
        else:
            plugin_prefs[UPDATE_OPTIONS_STORE_NAME] = update_prefs
            plugin_prefs[BACKUP_OPTIONS_STORE_NAME] = backup_prefs

        new_prefs = get_plugin_prefs(COMMON_OPTIONS_STORE_NAME)
        new_prefs[KEY_INDIVIDUAL_DEVICE_OPTIONS] = self.individual_device_options
        plugin_prefs[COMMON_OPTIONS_STORE_NAME]  = new_prefs

        debug_print("DevicesTab:persist_devices_config - end")


class DeviceColumnComboBox(QComboBox):

    def __init__(self, parent):
        QComboBox.__init__(self, parent)

    def populate_combo(self, devices, selected_device_uuid):
        self.clear()
        self.device_ids = [None, TOKEN_ANY_DEVICE]
        self.addItem('')
        self.addItem(TOKEN_ANY_DEVICE)
        selected_idx = 0
        if selected_device_uuid == TOKEN_ANY_DEVICE:
            selected_idx = 1
        for idx, key in enumerate(devices.keys()):
            self.addItem('%s'%(devices[key]['name']))
            self.device_ids.append(key)
            if key == selected_device_uuid:
                selected_idx = idx + 2
        self.setCurrentIndex(selected_idx)

    def get_selected_device(self):
        return self.device_ids[self.currentIndex()]


class NoWheelComboBox(QComboBox):

    def wheelEvent (self, event):
        # Disable the mouse wheel on top of the combo box changing selection as plays havoc in a grid
        event.ignore()


class BoolColumnComboBox(NoWheelComboBox):

    def __init__(self, parent, selected=True):
        NoWheelComboBox.__init__(self, parent)
        self.populate_combo(selected)

    def populate_combo(self, selected):
        self.clear()
        self.addItem(QIcon(I('ok.png')), 'Y')
        self.addItem(QIcon(I('list_remove.png')), 'N')
        if selected:
            self.setCurrentIndex(0)
        else:
            self.setCurrentIndex(1)


class DevicesTableWidget(QTableWidget):

    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.plugin_action = parent.plugin_action
        self.setSortingEnabled(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setMinimumSize(380, 0)

    def populate_table(self, devices, connected_device_info):
        self.clear()
        self.setRowCount(len(devices))
        header_labels = [ _('Menu'), _('Name'), _('Model'), _('Serial Number'), _('Version'), _('Status')]
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.verticalHeader().setDefaultSectionSize(32)
        self.horizontalHeader().setStretchLastSection(False)
        self.setIconSize(QSize(32, 32))

        for row, uuid in enumerate(devices.keys()):
            self.populate_table_row(row, uuid, devices[uuid], connected_device_info)

        self.resizeColumnsToContents()
        self.setMinimumColumnWidth(1, 100)
        self.selectRow(0)

    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, uuid, device_config, connected_device_info):
        debug_print("DevicesTableWidget:populate_table_row - device_config:", device_config)
        device_type = device_config['type']
        device_uuid = device_config['uuid']
        device_icon = 'reader.png'
        is_connected = False
        if connected_device_info is not None and self.plugin_action.haveKobo():
            debug_print("DevicesTableWidget:populate_table_row - connected_device_info:", connected_device_info)
            if device_type == connected_device_info[0]:
                drive_info = connected_device_info[4]
                if not drive_info:
                    is_connected = False
                else:
                    for connected_info in drive_info.values():
                        if connected_info['device_store_uuid'] == device_uuid:
                            is_connected = True
                            break
        version_no = self.plugin_action.device_version_info()[2] if is_connected and self.plugin_action.device_version_info() else ''
        connected_icon = 'images/device_connected.png' if is_connected else None
        debug_print("DevicesTableWidget:populate_table_row - connected_icon=%s" % connected_icon)

        name_widget = ReadOnlyTextIconWidgetItem(device_config['name'], get_icon(device_icon))
        name_widget.setData(Qt.UserRole, (device_config, is_connected))
        type_widget = ReadOnlyTableWidgetItem(device_config['type'])
        serial_no = device_config.get('serial_no', '')
        serial_no_widget = ReadOnlyTableWidgetItem(serial_no)
        version_no_widget = ReadOnlyTableWidgetItem(version_no)
        self.setItem(row, 0, CheckableTableWidgetItem(device_config['active']))
        self.setItem(row, 1, name_widget)
        self.setItem(row, 2, type_widget)
        self.setItem(row, 3, serial_no_widget)
        self.setItem(row, 4, version_no_widget)
        self.setItem(row, 5, ReadOnlyTextIconWidgetItem('', get_icon(connected_icon)))

    def get_data(self):
        debug_print("DevicesTableWidget::get_data - start")
        devices = {}
        for row in range(self.rowCount()):
            (device_config, _is_connected) = convert_qvariant(self.item(row, 1).data(Qt.UserRole))
#            debug_print("DevicesTableWidget::get_data - device_config", device_config)
#            debug_print("DevicesTableWidget::get_data - _is_connected", _is_connected)
            device_config['active'] = self.item(row, 0).get_boolean_value()
            devices[device_config['uuid']] = device_config
#        debug_print("DevicesTableWidget::get_data - devices:", devices)
        return devices

    def get_selected_device_info(self):
        if self.currentRow() >= 0:
            (device_config, is_connected) = convert_qvariant(self.item(self.currentRow(), 1).data(Qt.UserRole))
            return (device_config, is_connected)
        return None, None

    def set_current_row_device_name(self, device_name):
        if self.currentRow() >= 0:
            widget = self.item(self.currentRow(), 1)
            (device_config, is_connected) = convert_qvariant(widget.data(Qt.UserRole))
            device_config['name'] = device_name
            widget.setData(Qt.UserRole, (device_config, is_connected))
            widget.setText(device_name)

    def delete_selected_row(self):
        if self.currentRow() >= 0:
            self.removeRow(self.currentRow())


class OtherTab(QWidget):

    def __init__(self, parent_dialog):
        self.parent_dialog = parent_dialog
        QWidget.__init__(self)
        layout = QVBoxLayout()
        self.setLayout(layout)

        other_options_group = QGroupBox(_('Other Options'), self)
        layout.addWidget(other_options_group )
        options_layout = QGridLayout()
        other_options_group.setLayout(options_layout)

        library_default_label = QLabel(_('&Library Button default:'), self)
        library_default_label.setToolTip(_('If plugin is placed as a toolbar button, choose a default action when clicked on'))
        self.library_default_combo = SimpleComboBox(self, self.parent_dialog.plugin_action.library_actions_map, unicode(get_plugin_pref(COMMON_OPTIONS_STORE_NAME, KEY_BUTTON_ACTION_LIBRARY)))
        library_default_label.setBuddy(self.library_default_combo)
        options_layout.addWidget(library_default_label, 0, 0, 1, 1)
        options_layout.addWidget(self.library_default_combo, 0, 1, 1, 2)

        device_default_label = QLabel(_('&Device Button default:'), self)
        device_default_label.setToolTip(_('If plugin is placed as a toolbar button, choose a default action when clicked on'))
        self.device_default_combo = SimpleComboBox(self, self.parent_dialog.plugin_action.device_actions_map, unicode(get_plugin_pref(COMMON_OPTIONS_STORE_NAME, KEY_BUTTON_ACTION_DEVICE)))
        device_default_label.setBuddy(self.device_default_combo)
        options_layout.addWidget(device_default_label, 1, 0, 1, 1)
        options_layout.addWidget(self.device_default_combo, 1, 1, 1, 2)

        keyboard_shortcuts_button = QPushButton(_('Keyboard shortcuts...'), self)
        keyboard_shortcuts_button.setToolTip(
                    _('Edit the keyboard shortcuts associated with this plugin'))
        keyboard_shortcuts_button.clicked.connect(parent_dialog.edit_shortcuts)
        layout.addWidget(keyboard_shortcuts_button)

        view_prefs_button = QPushButton(_('&View library preferences...'), self)
        view_prefs_button.setToolTip(_('View data stored in the library database for this plugin'))
        view_prefs_button.clicked.connect(parent_dialog.view_prefs)
        layout.addWidget(view_prefs_button)

        layout.insertStretch(-1)

    def persist_other_config(self):

        new_prefs = get_plugin_prefs(COMMON_OPTIONS_STORE_NAME)
        new_prefs[KEY_BUTTON_ACTION_DEVICE]     = unicode(self.device_default_combo.currentText())
        new_prefs[KEY_BUTTON_ACTION_LIBRARY]    = unicode(self.library_default_combo.currentText())
        plugin_prefs[COMMON_OPTIONS_STORE_NAME] = new_prefs


class ConfigWidget(QWidget):

    def __init__(self, plugin_action):
        debug_print("ConfigWidget - Initializing...")
        QWidget.__init__(self)
        self.plugin_action = plugin_action
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        self.help_anchor = "configuration"

        self.must_restart = False
        self._get_create_new_custom_column_instance = None
        self.supports_create_custom_column = SUPPORTS_CREATE_CUSTOM_COLUMN

        title_layout = ImageTitleLayout(self, 'images/icon.png', _('Kobo Utilities Options'))
        layout.addLayout(title_layout)

        tab_widget = QTabWidget(self)
        layout.addWidget(tab_widget)

        self.profiles_tab = ProfilesTab(self, plugin_action)
        self.devices_tab = DevicesTab(self, plugin_action)
        self.other_tab = OtherTab(self)
        tab_widget.addTab(self.profiles_tab, _('Profiles'))
        tab_widget.addTab(self.devices_tab, _('Devices'))
        tab_widget.addTab(self.other_tab, _('Other'))

        # Force an initial display of list information
        self.devices_tab.update_from_connection_status(first_time=True)
        self.profiles_tab.refresh_current_profile_info()

    def connect_signals(self):
        self.plugin_action.plugin_device_connection_changed.connect(self.devices_tab.on_device_connection_changed)
        self.plugin_action.plugin_device_metadata_available.connect(self.devices_tab.on_device_metadata_available)

    def disconnect_signals(self):
        self.plugin_action.plugin_device_connection_changed.disconnect()
        self.plugin_action.plugin_device_metadata_available.disconnect()

    def refresh_devices_dropdown(self):
        self.profiles_tab.refresh_current_profile_info()

    def get_devices_list(self):
        return self.devices_tab.devices_table.get_data()

    def delete_device_from_lists(self, library_config, device_uuid):
#        for list_info in library_config[KEY_PROFILES].itervalues():
#            if list_info[KEY_FOR_DEVICE] == device_uuid:
#                list_info[KEY_FOR_DEVICE] = DEFAULT_PROFILE_VALUES[KEY_FOR_DEVICE]
#                list_info[KEY_SYNC_AUTO] = DEFAULT_PROFILE_VALUES[KEY_SYNC_AUTO]
#                list_info[KEY_SYNC_CLEAR] = DEFAULT_PROFILE_VALUES[KEY_SYNC_CLEAR]
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
#        library_config[KEY_DEFAULT_LIST] = self.profiles_tab.default_list
        set_library_config(self.plugin_action.gui.current_db, library_config)


    def edit_shortcuts(self):
        self.save_settings()
        # Force the menus to be rebuilt immediately, so we have all our actions registered
        self.plugin_action.rebuild_menus()
        d = KeyboardConfigDialog(self.plugin_action.gui, self.plugin_action.action_spec[0])
        if d.exec_() == d.Accepted:
            self.plugin_action.gui.keyboard.finalize()

    def view_prefs(self):
        d = PrefsViewerDialog(self.plugin_action.gui, PREFS_NAMESPACE)
        d.exec_()

    def help_link_activated(self, url):
        self.plugin_action.show_help(anchor="configuration")

    @property
    def get_create_new_custom_column_instance(self):
        if self._get_create_new_custom_column_instance is None and self.supports_create_custom_column:
            self._get_create_new_custom_column_instance = CreateNewCustomColumn(self.plugin_action.gui)
        return self._get_create_new_custom_column_instance
