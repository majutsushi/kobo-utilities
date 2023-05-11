#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)
#from constants import debug
#from common_utils import debug_print

__license__   = 'GPL v3'
__copyright__ = '2012-2020, David Forrester <davidfor@internode.on.net>'
__docformat__ = 'restructuredtext en'

import os, traceback, re
from datetime import datetime

# calibre Python 3 compatibility.
import six
from six import text_type as unicode

from calibre_plugins.koboutilities.common_utils import debug_print
try:
    from PyQt5.Qt import (QWidget, QDialog, QVBoxLayout, QLabel, QCheckBox, QGridLayout, QRadioButton, QComboBox, QSpinBox,
                          QGroupBox, Qt, QDialogButtonBox, QHBoxLayout, QPixmap, QTableWidget, QAbstractItemView,
                          QProgressDialog, QTimer, QLineEdit, QPushButton, QDoubleSpinBox, QButtonGroup,
                          QSpacerItem, QToolButton, QTableWidgetItem, QAction, QApplication, QUrl)
    from PyQt5.QtWidgets import QSizePolicy
except ImportError as e:
    debug_print("Error loading QT5: ", e)
    from PyQt4.Qt import (QWidget, QDialog, QVBoxLayout, QLabel, QCheckBox, QGridLayout, QRadioButton, QComboBox, QSpinBox,
                          QGroupBox, Qt, QDialogButtonBox, QHBoxLayout, QPixmap, QTableWidget, QAbstractItemView,
                          QProgressDialog, QTimer, QLineEdit, QPushButton, QDoubleSpinBox, QButtonGroup,
                          QSpacerItem, QToolButton, QTableWidgetItem, QAction, QApplication, QUrl)
    from PyQt4.QtGui import QSizePolicy

import six
from six.moves.configparser import SafeConfigParser
from six import text_type as unicode
from six.moves.urllib.parse import quote_plus

from calibre.ebooks.metadata import authors_to_string
from calibre.gui2 import gprefs, warning_dialog, error_dialog, question_dialog, open_url, choose_dir
from calibre.gui2.dialogs.template_dialog import TemplateDialog
from calibre.gui2.dialogs.confirm_delete import confirm

from functools import partial

from calibre.gui2.complete2 import EditWithComplete
from calibre.gui2.widgets2 import ColorButton
from calibre.utils.config import tweaks, JSONConfig
from calibre.utils.date import qt_to_dt, utc_tz
from calibre.utils.icu import sort_key

from calibre_plugins.koboutilities.common_utils import (SizePersistedDialog, 
                    ImageTitleLayout, DateDelegate, CustomColumnComboBox, ProfileComboBox,
                    CheckableTableWidgetItem, DateTableWidgetItem, RatingTableWidgetItem,
                    ReadOnlyTableWidgetItem, ReadOnlyTextIconWidgetItem,
                    get_icon, get_library_uuid, convert_qvariant)

from calibre_plugins.koboutilities.book import SeriesBook
import calibre_plugins.koboutilities.config as cfg
#from calibre_plugins.koboutilities.action import (convert_kobo_date)

# Checked with FW2.5.2
LINE_SPACINGS =     [1.3, 1.35, 1.4, 1.6, 1.775, 1.9, 2, 2.2, 3 ]
LINE_SPACINGS_020901 = [1, 1.05, 1.07, 1.1, 1.2, 1.4,  1.5, 1.7, 1.8, 2, 2.2, 2.4, 2.6, 2.8, 3 ]
LINE_SPACINGS_030200 = [1, 1.05, 1.07, 1.1, 1.2, 1.35, 1.5, 1.7, 1.8, 2, 2.2, 2.4, 2.6, 2.8, 3 ]
FONT_SIZES    = [12, 14, 16, 17, 18, 19, 20, 21, 22, 24, 25, 26, 28, 32, 36, 40, 44, 46, 48, 50, 52, 54, 56, 58 ]
KOBO_FONTS = {
            (0, 0 ,0): { # Format is: Display name, setting name
                 'Document Default':  'default', 
                 'Amasis':            'Amasis', 
                 'Avenir':            'Avenir Next', 
                 'Caecilia':          'Caecilia',
                 'Georgia':           'Georgia', 
                 'Gill Sans':         'Gill Sans', 
                 'Kobo Nickel':       'Kobo Nickel', 
                 'Malabar':           'Malabar', 
                 'Rockwell':          'Rockwell', 
                 'Gothic':            'A-OTF Gothic MB101 Pr6N', 
                 'Ryumin':            'A-OTF Ryumin Pr6N', 
                 'OpenDyslexic':      'OpenDyslexic', 
                 },
            (3, 19, 0): { # Format is: Display name, setting name
                 'Document Default':     'default', 
                 'Amasis':               'Amasis', 
                 'Avenir':               'Avenir Next', 
                 'Caecilia':             'Caecilia',
                 'Georgia':              'Georgia', 
                 'Gill Sans':            'Gill Sans', 
                 'Kobo Nickel':          'Kobo Nickel', 
                 'Malabar':              'Malabar', 
                 'Rockwell':             'Rockwell', 
                 'Kobo Tsukushi Mincho': 'KBJ-TsukuMin Pr6N RB', 
                 'Kobo UD Kakugo':       'KBJ-UDKakugo Pr6N M', 
                 'OpenDyslexic':         'OpenDyslexic', 
                 },
            (4, 13, 12638): { # Format is: Display name, setting name
                 'Document Default':     'default', 
                 'Amasis':               'Amasis', 
                 'Avenir':               'Avenir Next', 
                 'Caecilia':             'Caecilia',
                 'Georgia':              'Georgia', 
                 'Gill Sans':            'Gill Sans', 
                 'Kobo Nickel':          'Kobo Nickel', 
                 'Malabar':              'Malabar', 
                 'Rockwell':             'Rockwell', 
                 'AR UDJingxihei':       'AR UDJingxihei', 
                 'Kobo Tsukushi Mincho': 'KBJ-TsukuMin Pr6N RB', 
                 'Kobo UD Kakugo':       'KBJ-UDKakugo Pr6N M', 
                 'OpenDyslexic':         'OpenDyslexic', 
                 },
            }

TILE_TYPES    = {   # Format is: Activity/Tile name, Display Name, tooltip
                 ("Award",           _("Awards"),               _("Displays each award when given.")),
                 ("Bookstore",       _("Bookstore"),            _("The Kobo Bookstore.")),
                 ("CategoryFTE",     _("Browse by category"),   _("Lists several categories from the Kobo Bookstore.")),
                 ("Extras",          _("Extras"),               _("A tile is displayed for each extra when used.")),
                 ("GlobalStats",     _("Global Stats"),         _("Displays the number of finished books in your library.")),
                 ("Library",         _("Library"),              _("Shows new books added to the library.")),
                 ("QuickTour",       _("Quick Tour"),           _("The device Quick Tour that is displayed when the device is first set-up.")),
                 ("RecentPocketArticle", _("Pocket Article"),   _("Pocket articles.")),
                 ("Recommendations", _("Recommendations"),      _("Kobo's recommendations for you.")),
                 ("RelatedItems",    _("Related Items"),        _("After a sync, will show books related to any you are reading. There can be one tile for each of your books.")),
                 ("WhatsNew",        _("Release Notes"),        _("Shows that there was an update to the firmware with the new version number. You probably don't want to dismiss this.")),
                 ("Shelf",           _("Shelf"),                _("Can have a tile for each shelf.")),
                 ("Sync",            _("Sync"),                 _("Displays when a sync was last done. Does not have options to dismiss it.")),
                 ("Top50",           _("Top 50"),               _("The Top 50 books in the Kobo store.")),
                }

EXTRAS_TILES    = {   # Format is: Activity/Tile name, Display Name, tooltip
                 ("chess",      _("Chess"),         _("Take on your eReader in the classic game of strategy and skill.")),
                 ("sketch",     _("Sketch Pad"),    _("Discover your inner artist or make notes and then save your creation in your Library.")),
                 ("sudoku",     _("Sudoku"),        _("Try your wits with this logic-based number puzzle.")),
                 ("browser",    _("Web Browser"),   _("Take the on-ramp to the information superhighway, right on your eReader.")),
                 ("rushhour",   _("Unblock It"),    _("Liberate your block by moving other blocks out of the way.")),
                 ("solitaire",  _("Solitaire"),     _("Play classic solitaire games like Klondike, Spider, and Freecell.")),
                 ("scramble",   _("Word Scramble"), _("Find words in a 4x4 grid.")),
                }

DIALOG_NAME = 'Kobo Utilities'

ORDER_SHELVES_TYPE = [
                    cfg.KEY_ORDER_SHELVES_SERIES, 
                    cfg.KEY_ORDER_SHELVES_AUTHORS, 
                    cfg.KEY_ORDER_SHELVES_OTHER,
                    cfg.KEY_ORDER_SHELVES_ALL
                    ]

ORDER_SHELVES_BY = [
                    cfg.KEY_ORDER_SHELVES_BY_SERIES, 
                    cfg.KEY_ORDER_SHELVES_PUBLISHED
                    ]

READING_DIRECTIONS = {
                      _('Default'): 'default',
                      _('RTL'):     'rtl',
                      _('LTR'):     'ltr',
                      }

DATE_COLUMNS = [
                'timestamp',
                'last_modified',
                'pubdate',
                ]

KEY_REMOVE_ANNOT_ALL         = 0
KEY_REMOVE_ANNOT_NOBOOK      = 1
KEY_REMOVE_ANNOT_EMPTY       = 2
KEY_REMOVE_ANNOT_NONEMPTY    = 3
KEY_REMOVE_ANNOT_SELECTED    = 4

# This is where all preferences for this plugin will be stored
#plugin_prefs = JSONConfig('plugins/Kobo Utilities')

# pulls in translation files for _() strings
try:
    debug_print("KoboUtilites::dialogs.py - loading translations")
    load_translations()
except NameError:
    debug_print("KoboUtilites::dialogs.py - exception when loading translations")
    pass # load_translations() added in calibre 1.9

def get_plugin_pref(store_name, option):
    return cfg.plugin_prefs.get(cfg.option, cfg.METADATA_OPTIONS_DEFAULTS[cfg.KEY_SET_TITLE]) 

def have_rating_column(plugin_action):
    rating_column = plugin_action.get_rating_column()
    return not rating_column == ''

class AuthorTableWidgetItem(ReadOnlyTableWidgetItem):
    def __init__(self, text, sort_key):
        ReadOnlyTableWidgetItem.__init__(self, text)
        self.sort_key = sort_key

    #Qt uses a simple < check for sorting items, override this to use the sortKey
    def __lt__(self, other):
        return self.sort_key < other.sort_key


class QueueProgressDialog(QProgressDialog):

    def __init__(self, gui, books, tdir, options, queue, db, plugin_action=None):
        QProgressDialog.__init__(self, '', '', 0, len(books), gui)
        debug_print("QueueProgressDialog::__init__")
        self.setMinimumWidth(500)
        self.books, self.tdir, self.options, self.queue, self.db = \
            books, tdir, options, queue, db
        self.plugin_action = plugin_action
        self.gui = gui
        self.i, self.books_to_scan = 0, []
        self.profileName = self.options.get('profileName', None)

        self.options['count_selected_books'] = len(self.books) if self.books else 0
        if self.options['job_function'] == 'clean_images_dir':
            self.setWindowTitle(_("Creating queue for checking images directory"))
            QTimer.singleShot(0, self.do_clean_images_dir_queue)
        elif self.options['job_function'] == 'remove_annotations':
            self.setWindowTitle(_("Creating queue for removing annotations files"))
            QTimer.singleShot(0, self.do_remove_annotations_queue)
        else:
            self.setWindowTitle(_("Queueing books for storing reading position"))
            QTimer.singleShot(0, self.do_books)
        self.exec_()

    def do_books(self):
        debug_print("QueueProgressDialog::do_books - Start")

        library_db = self.db

        kobo_chapteridbookmarked_column, kobo_percentRead_column, rating_column, last_read_column = self.plugin_action.get_column_names()
        self.options[cfg.KEY_CURRENT_LOCATION_CUSTOM_COLUMN] = kobo_chapteridbookmarked_column
        self.options[cfg.KEY_PERCENT_READ_CUSTOM_COLUMN]     = kobo_percentRead_column
        self.options[cfg.KEY_RATING_CUSTOM_COLUMN]           = rating_column
        self.options[cfg.KEY_LAST_READ_CUSTOM_COLUMN]        = last_read_column

        debug_print("QueueProgressDialog::do_books - kobo_percentRead_column='%s'" % kobo_percentRead_column)
        self.setLabelText(_('Preparing the list of books ...'))
        self.setValue(1)
        search_condition = ''
        if self.options[cfg.KEY_DO_NOT_STORE_IF_REOPENED]:
            search_condition = 'and ({0}:false or {0}:<100)'.format(kobo_percentRead_column)
        if self.options['allOnDevice']:
            search_condition = 'ondevice:True {0}'.format(search_condition)
            debug_print("QueueProgressDialog::do_books - search_condition=", search_condition)
            onDeviceIds = set(library_db.search_getting_ids(search_condition, None, sort_results=False, use_virtual_library=False))
        else:
            onDeviceIds = self.plugin_action._get_selected_ids()

        self.books = self.plugin_action._convert_calibre_ids_to_books(library_db, onDeviceIds)
        self.setRange(0, len(self.books))
        for book in self.books:
            self.i += 1
            device_book_paths = self.plugin_action.get_device_paths_from_id(book.calibre_id)
#            debug_print("QueueProgressDialog::do_all_books -- device_book_paths:", device_book_paths)
            book.contentIDs = [self.plugin_action.contentid_from_path(path, self.plugin_action.CONTENTTYPE) for path in device_book_paths]
            if len(book.contentIDs):
                title               = book.title
                self.setLabelText(_('Queueing ') + title)
                authors             = authors_to_string(book.authors)
                current_chapterid   = None
                current_percentRead = None
                current_rating      = None
                current_last_read   = None
                if kobo_chapteridbookmarked_column:
                    current_chapterid = book.get_user_metadata(kobo_chapteridbookmarked_column, True)['#value#']
                if kobo_percentRead_column:
                    current_percentRead = book.get_user_metadata(kobo_percentRead_column, True)['#value#']
                if rating_column:
                    if rating_column == 'rating':
                        current_rating = book.rating
                    else:
                        current_rating = book.get_user_metadata(rating_column, True)['#value#']
                if last_read_column:
                    current_last_read = book.get_user_metadata(last_read_column, True)['#value#']

#                debug_print("QueueProgressDialog::do_books - adding:", book.calibre_id, book.contentIDs, title, authors, current_chapterid, current_percentRead, current_rating, current_last_read)
                self.books_to_scan.append((book.calibre_id, book.contentIDs, title, authors, current_chapterid, current_percentRead, current_rating, current_last_read))
            self.setValue(self.i)

        debug_print("QueueProgressDialog::do_books - Finish")
        return self.do_queue()


    def do_queue(self):
        debug_print("QueueProgressDialog::do_queue")
        if self.gui is None:
            # There is a nasty QT bug with the timers/logic above which can
            # result in the do_queue method being called twice
            return
        self.hide()

        # Queue a job to process these ePub books
        self.queue(self.tdir, self.options, self.books_to_scan)

    def do_clean_images_dir_queue(self):
        debug_print("QueueProgressDialog::do_clean_images_dir_queue")
        if self.gui is None:
            # There is a nasty QT bug with the timers/logic above which can
            # result in the do_queue method being called twice
            return
        self.hide()

        # Queue a job to process these ePub books
        self.queue(self.tdir, self.options)

    def do_remove_annotations_queue(self):
        debug_print("QueueProgressDialog::do_remove_annotations_queue")
        if self.gui is None:
            # There is a nasty QT bug with the timers/logic above which can
            # result in the do_queue method being called twice
            return
        if self.options[cfg.KEY_REMOVE_ANNOT_ACTION] == cfg.KEY_REMOVE_ANNOT_SELECTED:
            library_db = self.db #self.gui.current_db

            self.setLabelText(_('Preparing the list of books ...'))
            self.setValue(1)

            if self.plugin_action.isDeviceView():
                self.books = self.plugin_action._get_books_for_selected()
            else:
                onDeviceIds = self.plugin_action._get_selected_ids()
                self.books = self.plugin_action._convert_calibre_ids_to_books(library_db, onDeviceIds)
            self.setRange(0, len(self.books))

            for book in self.books:
                self.i += 1
#                debug_print("QueueProgressDialog::do_remove_annotations_queue -- book:", book)
                if self.plugin_action.isDeviceView():
                    device_book_paths = [book.path]
                    contentIDs = [book.contentID]
                else:
                    device_book_paths = self.plugin_action.get_device_paths_from_id(book.calibre_id)
                    contentIDs = [self.plugin_action.contentid_from_path(path, self.plugin_action.CONTENTTYPE) for path in device_book_paths]
                debug_print("QueueProgressDialog::do_remove_annotations_queue -- device_book_paths:", device_book_paths)
                book.paths = device_book_paths
                book.contentIDs =  contentIDs
                if len(book.contentIDs):
                    title               = book.title
                    self.setLabelText(_('Queueing ') + title)
                    authors             = authors_to_string(book.authors)

    #                debug_print("QueueProgressDialog::do_remove_annotations_queue - adding:", book.calibre_id, book.contentIDs, title, authors)
                    self.books_to_scan.append((book.calibre_id, book.contentIDs, book.paths, title, authors))
                self.setValue(self.i)
        else:
            self.hide()

        # Queue a job to process these ePub books
        self.do_queue()

    def _authors_to_list(self, db, book_id):
        authors = db.authors(book_id, index_is_id=True)
        if authors:
            return [a.strip().replace('|',',') for a in authors.split(',')]
        return []


class ReaderOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:reader font settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "SetReaderFonts"

        debug_print("ReaderOptionsDialog:__init__ - self.plugin_action.device_fwversion=", self.plugin_action.device_fwversion)
        self.line_spacings = LINE_SPACINGS
        if self.plugin_action.device_fwversion >= (3, 2, 0):
            self.line_spacings = LINE_SPACINGS_030200
        elif self.plugin_action.device_fwversion >= (2, 9, 1):
            self.line_spacings = LINE_SPACINGS_020901
        
        self.font_list = self.get_font_list()
        self.initialize_controls()

#        self.options = gprefs.get(self.unique_pref_name+':settings', {})
        debug_print("ReaderOptionsDialog:__init__")

        # Set some default values from last time dialog was used.
        self.prefs = cfg.plugin_prefs[cfg.READING_OPTIONS_STORE_NAME]
        self.change_settings(self.prefs)
        debug_print("ReaderOptionsDialog:__init__ - ", self.prefs)
        if self.prefs.get(cfg.KEY_READING_LOCK_MARGINS, False):
            self.lock_margins_checkbox.click()
        if self.prefs.get(cfg.KEY_UPDATE_CONFIG_FILE, False):
            self.update_config_file_checkbox.setCheckState(Qt.Checked)
        if self.prefs.get(cfg.KEY_DO_NOT_UPDATE_IF_SET, False):
            self.do_not_update_if_set_checkbox.setCheckState(Qt.Checked)
        self.get_book_settings_pushbutton.setEnabled(self.plugin_action.singleSelected)


        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Kobo eReader Font Settings')
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("Reader font settings"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)
        
        options_layout.addWidget(QLabel(_("Font Face")), 0, 0, 1, 1)
        self.font_choice = FontChoiceComboBox(self, self.font_list)
        options_layout.addWidget(self.font_choice, 0, 1, 1, 4)
        options_layout.addWidget(QLabel(_("Font Size")), 1, 0, 1, 1)
        self.font_size_spin = QSpinBox(self)
        self.font_size_spin.setMinimum(12)
        self.font_size_spin.setMaximum(58)
        self.font_size_spin.setToolTip(_("Font size to use when reading. The device default is about 22."))
        options_layout.addWidget(self.font_size_spin, 1, 1, 1, 1)
        
        options_layout.addWidget(QLabel(_("Line Spacing")), 2, 0, 1, 1)
        self.line_spacing_spin = QSpinBox(self)
        self.line_spacing_spin.setMinimum(0)
        self.line_spacing_spin.setMaximum(len(self.line_spacings) - 1)
        options_layout.addWidget(self.line_spacing_spin, 2, 1, 1, 1)
        self.line_spacing_spin.setToolTip(_("The line spacing number is how many times the right arrow is pressed on the device."))
        self.line_spacing_spin.valueChanged.connect(self.line_spacing_spin_changed)

        self.custom_line_spacing_checkbox = QCheckBox(_("Custom setting"), self)
        options_layout.addWidget(self.custom_line_spacing_checkbox, 2, 2, 1, 1)
        self.custom_line_spacing_checkbox.setToolTip(_("If you want to try a line spacing other than the Kobo specified, check this and enter a number."))
        self.custom_line_spacing_checkbox.clicked.connect(self.custom_line_spacing_checkbox_clicked)

        self.custom_line_spacing_edit = QLineEdit(self)
        self.custom_line_spacing_edit.setEnabled(False)
        options_layout.addWidget(self.custom_line_spacing_edit, 2, 3, 1, 2)
        self.custom_line_spacing_edit.setToolTip(_("Kobo use from 1.3 to 4.0. Any number can be entered, but whether the device will use it, is another matter."))

        options_layout.addWidget(QLabel(_("Left margins")), 3, 0, 1, 1)
        self.left_margins_spin = QSpinBox(self)
        self.left_margins_spin.setMinimum(0)
        self.left_margins_spin.setMaximum(16)
        self.left_margins_spin.setToolTip(_("Margins on the device are set in multiples of two, but single steps work."))
        options_layout.addWidget(self.left_margins_spin, 3, 1, 1, 1)
        self.left_margins_spin.valueChanged.connect(self.left_margins_spin_changed)

        self.lock_margins_checkbox = QCheckBox(_("Lock margins"), self)
        options_layout.addWidget(self.lock_margins_checkbox, 3, 2, 1, 1)
        self.lock_margins_checkbox.setToolTip(_("Lock the left and right margins to the same value. Changing the left margin will also set the right margin."))
        self.lock_margins_checkbox.clicked.connect(self.lock_margins_checkbox_clicked)

        options_layout.addWidget(QLabel(_("Right margins")), 3, 3, 1, 1)
        self.right_margins_spin = QSpinBox(self)
        self.right_margins_spin.setMinimum(0)
        self.right_margins_spin.setMaximum(16)
        self.right_margins_spin.setToolTip(_("Margins on the device are set in multiples of three, but single steps work."))
        options_layout.addWidget(self.right_margins_spin, 3, 4, 1, 1)

        options_layout.addWidget(QLabel(_("Justification")), 5, 0, 1, 1)
        self.justification_choice = JustificationChoiceComboBox(self)
        options_layout.addWidget(self.justification_choice, 5, 1, 1, 1)

        self.update_config_file_checkbox = QCheckBox(_("Update config file"), self)
        options_layout.addWidget(self.update_config_file_checkbox, 5, 2, 1, 1)
        self.update_config_file_checkbox.setToolTip(_("Update the 'Kobo eReader.conf' file with the new settings. These will be used when opening new books or books that do not have stored settings."))

        self.do_not_update_if_set_checkbox = QCheckBox(_("Do not update if set"), self)
        options_layout.addWidget(self.do_not_update_if_set_checkbox, 5, 3, 1, 2)
        self.do_not_update_if_set_checkbox.setToolTip(_("Do not upate the font settings if it is already set for the book."))

        layout.addStretch(1)

        button_layout = QHBoxLayout(self)
        layout.addLayout(button_layout)
        self.get_device_settings_pushbutton = QPushButton(_("&Get configuration from device"), self)
        button_layout.addWidget(self.get_device_settings_pushbutton)
        self.get_device_settings_pushbutton.setToolTip(_("Read the device configuration file to get the current default settings."))
        self.get_device_settings_pushbutton.clicked.connect(self.get_device_settings)
        
        self.get_book_settings_pushbutton = QPushButton(_("&Get settings from device"), self)
        button_layout.addWidget(self.get_book_settings_pushbutton)
        self.get_book_settings_pushbutton.setToolTip(_("Fetches the current for the selected book from the device."))
        self.get_book_settings_pushbutton.clicked.connect(self.get_book_settings)
        
        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)


    def ok_clicked(self):

        self.prefs = cfg.READING_OPTIONS_DEFAULTS
        self.prefs[cfg.KEY_READING_FONT_FAMILY] = self.font_list[unicode(self.font_choice.currentText()).strip()]
        self.prefs[cfg.KEY_READING_ALIGNMENT]   = unicode(self.justification_choice.currentText()).strip()
        self.prefs[cfg.KEY_READING_FONT_SIZE]   = int(unicode(self.font_size_spin.value()))
        if self.custom_line_spacing_is_checked():
            self.prefs[cfg.KEY_READING_LINE_HEIGHT] = float(unicode(self.custom_line_spacing_edit.text()))
            debug_print("ReaderOptionsDialog:ok_clicked - custom -self.prefs[cfg.KEY_READING_LINE_HEIGHT]=", self.prefs[cfg.KEY_READING_LINE_HEIGHT])
        else:
            self.prefs[cfg.KEY_READING_LINE_HEIGHT] = self.line_spacings[int(unicode(self.line_spacing_spin.value()))]
            debug_print("ReaderOptionsDialog:ok_clicked - spin - self.prefs[cfg.KEY_READING_LINE_HEIGHT]=", self.prefs[cfg.KEY_READING_LINE_HEIGHT])
        self.prefs[cfg.KEY_READING_LEFT_MARGIN]  = int(unicode(self.left_margins_spin.value()))
        self.prefs[cfg.KEY_READING_RIGHT_MARGIN] = int(unicode(self.right_margins_spin.value()))
        self.prefs[cfg.KEY_READING_LOCK_MARGINS] = self.lock_margins_checkbox_is_checked()
        self.prefs[cfg.KEY_UPDATE_CONFIG_FILE]   = self.update_config_file_checkbox.checkState() == Qt.Checked
        self.prefs[cfg.KEY_DO_NOT_UPDATE_IF_SET] = self.do_not_update_if_set_checkbox.checkState() == Qt.Checked

        gprefs.set(self.unique_pref_name+':settings', self.prefs)
        self.accept()

    def custom_line_spacing_checkbox_clicked(self, checked):
        self.line_spacing_spin.setEnabled(not checked)
        self.custom_line_spacing_edit.setEnabled(checked)
        if not self.custom_line_spacing_is_checked():
            self.line_spacing_spin_changed(None)

    def lock_margins_checkbox_clicked(self, checked):
        self.right_margins_spin.setEnabled(not checked)
        if checked: #not self.custom_line_spacing_is_checked():
            self.right_margins_spin.setProperty('value', int(unicode(self.left_margins_spin.value())))

    def line_spacing_spin_changed(self, checked):
        self.custom_line_spacing_edit.setText(unicode(self.line_spacings[int(unicode(self.line_spacing_spin.value()))]))

    def left_margins_spin_changed(self, checked):
        if self.lock_margins_checkbox_is_checked():
            self.right_margins_spin.setProperty('value', int(unicode(self.left_margins_spin.value())))

    def custom_line_spacing_is_checked(self):
        return self.custom_line_spacing_checkbox.checkState() == Qt.Checked

    def lock_margins_checkbox_is_checked(self):
        return self.lock_margins_checkbox.checkState() == Qt.Checked

    def get_device_settings(self):
        koboConfig = SafeConfigParser(allow_no_value=True)
        device = self.parent().device_manager.connected_device
        device_path = self.parent().device_manager.connected_device._main_prefix
        debug_print("get_device_settings - device_path=", device_path)
        koboConfig.read(device.normalize_path(device_path + '.kobo/Kobo/Kobo eReader.conf'))
        
        device_settings = {}
        device_settings[cfg.KEY_READING_FONT_FAMILY] = koboConfig.get('Reading', cfg.KEY_READING_FONT_FAMILY) \
                                                    if koboConfig.has_option('Reading', cfg.KEY_READING_FONT_FAMILY) \
                                                    else cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_FONT_FAMILY]
        device_settings[cfg.KEY_READING_ALIGNMENT]  = koboConfig.get('Reading', cfg.KEY_READING_ALIGNMENT) \
                                                    if koboConfig.has_option('Reading', cfg.KEY_READING_ALIGNMENT)  \
                                                    else cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_ALIGNMENT]
        device_settings[cfg.KEY_READING_FONT_SIZE]   = koboConfig.get('Reading', cfg.KEY_READING_FONT_SIZE) \
                                                    if koboConfig.has_option('Reading', cfg.KEY_READING_FONT_SIZE) \
                                                    else cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_FONT_SIZE]
        device_settings[cfg.KEY_READING_LINE_HEIGHT] = float(koboConfig.get('Reading', cfg.KEY_READING_LINE_HEIGHT)) \
                                                    if koboConfig.has_option('Reading', cfg.KEY_READING_LINE_HEIGHT) \
                                                    else cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_LINE_HEIGHT]
        device_settings[cfg.KEY_READING_LEFT_MARGIN] = koboConfig.get('Reading', cfg.KEY_READING_LEFT_MARGIN) \
                                                    if koboConfig.has_option('Reading', cfg.KEY_READING_LEFT_MARGIN) \
                                                    else cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_LEFT_MARGIN]
        device_settings[cfg.KEY_READING_RIGHT_MARGIN] = koboConfig.get('Reading', cfg.KEY_READING_RIGHT_MARGIN) \
                                                    if koboConfig.has_option('Reading', cfg.KEY_READING_RIGHT_MARGIN) \
                                                    else cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_RIGHT_MARGIN]

        self.change_settings(device_settings)

    def change_settings(self, reader_settings):
        font_face = reader_settings.get(cfg.KEY_READING_FONT_FAMILY, cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_FONT_FAMILY])
        debug_print("ReaderOptionsDialog:change_settings - font_face=", font_face)
        self.font_choice.select_text(font_face)
        
        justification = reader_settings.get(cfg.KEY_READING_ALIGNMENT, cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_ALIGNMENT])
        self.justification_choice.select_text(justification)
        
        font_size = reader_settings.get(cfg.KEY_READING_FONT_SIZE, cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_FONT_SIZE])
        self.font_size_spin.setProperty('value', font_size)
        
        line_spacing = reader_settings.get(cfg.KEY_READING_LINE_HEIGHT, cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_LINE_HEIGHT])
        debug_print("ReaderOptionsDialog:change_settings - line_spacing='%s'" % line_spacing)
        if line_spacing in self.line_spacings:
            line_spacing_index = self.line_spacings.index(line_spacing)
            debug_print("ReaderOptionsDialog:change_settings - line_spacing_index=", line_spacing_index)
            self.custom_line_spacing_checkbox.setCheckState(Qt.Checked)
        else:
            self.custom_line_spacing_checkbox.setCheckState(Qt.Unchecked)
            debug_print("ReaderOptionsDialog:change_settings - line_spacing_index not found")
            line_spacing_index = 0
        self.custom_line_spacing_checkbox.click()
        self.custom_line_spacing_edit.setText(unicode(line_spacing))
        self.line_spacing_spin.setProperty('value', line_spacing_index)
        
        left_margins = reader_settings.get(cfg.KEY_READING_LEFT_MARGIN, cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_LEFT_MARGIN])
        self.left_margins_spin.setProperty('value', left_margins)
        right_margins = reader_settings.get(cfg.KEY_READING_RIGHT_MARGIN, cfg.READING_OPTIONS_DEFAULTS[cfg.KEY_READING_RIGHT_MARGIN])
        self.right_margins_spin.setProperty('value', right_margins)

    def get_book_settings(self):
        book_options = self.plugin_action.fetch_book_fonts()
        
        if len(book_options) > 0:
            self.change_settings(book_options)

    def get_font_list(self):

        font_list = KOBO_FONTS[(0,0,0)]
        for fw_version, fw_font_list in sorted(KOBO_FONTS.items()):
            debug_print("ReaderOptionsDialog:get_font_list - fw_version=", fw_version)
            if fw_version <= self.plugin_action.device_fwversion:
                debug_print("ReaderOptionsDialog:get_font_list - found version?=", fw_version)
                font_list = fw_font_list
            else:
                break
        debug_print("ReaderOptionsDialog:get_font_list - font_list=", font_list)

        return font_list


class UpdateMetadataOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action, book):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:update metadata settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "UpdateMetadata"
        self.test_book = book

        self.initialize_controls()

        # Set some default values from last time dialog was used.
        title = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_TITLE)
        self.title_checkbox.setCheckState(Qt.Checked if title else Qt.Unchecked)
        self.title_checkbox_clicked(title)
        
        title_sort = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_USE_TITLE_SORT)
        self.title_sort_checkbox.setCheckState(Qt.Checked if title_sort else Qt.Unchecked)
        
        author = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_AUTHOR)
        self.author_checkbox.setCheckState(Qt.Checked if author else Qt.Unchecked)

        author_sort = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_USE_AUTHOR_SORT)
        self.author_sort_checkbox.setCheckState(Qt.Checked if author_sort else Qt.Unchecked)
        self.author_checkbox_clicked(author)
        
        description = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_DESCRIPTION)
        self.description_checkbox.setCheckState(Qt.Checked if description else Qt.Unchecked)
        
        description_use_template = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_DESCRIPTION_USE_TEMPLATE)
        self.description_use_template_checkbox.setCheckState(Qt.Checked if description_use_template else Qt.Unchecked)
        self.description_checkbox_clicked(description)
        description_template = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_DESCRIPTION_TEMPLATE)
        self.description_template_edit.template = description_template
        
        publisher = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_PUBLISHER)
        self.publisher_checkbox.setCheckState(Qt.Checked if publisher else Qt.Unchecked)
        
        published = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_PUBLISHED_DATE)
        self.published_checkbox.setCheckState(Qt.Checked if published else Qt.Unchecked)
        
        isbn = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_ISBN)
        self.isbn_checkbox.setCheckState(Qt.Checked if isbn and self.plugin_action.supports_ratings else Qt.Unchecked)
        self.isbn_checkbox.setEnabled(self.plugin_action.supports_ratings)

        rating = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_RATING)
        self.rating_checkbox.setCheckState(Qt.Checked if rating and self.plugin_action.supports_ratings else Qt.Unchecked)
        self.rating_checkbox.setEnabled(have_rating_column(self.plugin_action) and self.plugin_action.supports_ratings)

        series = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_SERIES)
        self.series_checkbox.setCheckState(Qt.Checked if series and self.plugin_action.supports_series else Qt.Unchecked)
        self.series_checkbox.setEnabled(self.plugin_action.supports_series)

        subtitle = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_SUBTITLE)
        self.subtitle_checkbox.setCheckState(Qt.Checked if subtitle else Qt.Unchecked)
        self.subtitle_checkbox_clicked(subtitle)

        subtitle_template = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SUBTITLE_TEMPLATE)
        self.subtitle_template_edit.template = subtitle_template

        reading_direction = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_READING_DIRECTION)
        self.reading_direction_checkbox.setCheckState(Qt.Checked if reading_direction else Qt.Unchecked)
        self.reading_direction_checkbox_clicked(reading_direction)
        reading_direction = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_READING_DIRECTION)
        self.reading_direction_combo.select_text(reading_direction)

        date_added = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SYNC_DATE)
        self.date_added_checkbox.setCheckState(Qt.Checked if date_added else Qt.Unchecked)
        date_added_column = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SYNC_DATE_COLUMN)
        self.date_added_column_combo.populate_combo(
                                self.get_date_columns(DATE_COLUMNS), 
                                date_added_column, 
                                initial_items=cfg.OTHER_SORTS, 
                                show_lookup_name=False
                            )
        self.date_added_checkbox_clicked(date_added)

        use_plugboard = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_USE_PLUGBOARD)
        self.use_plugboard_checkbox.setCheckState(Qt.Checked if use_plugboard else Qt.Unchecked)
        self.use_plugboard_checkbox_clicked(use_plugboard)

        update_kepubs = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_UDPATE_KOBO_EPUBS)
        self.update_kepubs_checkbox.setCheckState(Qt.Checked if update_kepubs else Qt.Unchecked)

        language = cfg.get_plugin_pref(cfg.METADATA_OPTIONS_STORE_NAME, cfg.KEY_SET_LANGUAGE)
        self.language_checkbox.setCheckState(Qt.Checked if language else Qt.Unchecked)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Update metadata in Device Library')
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("Metadata to update"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        widget_line = 0
        self.title_checkbox = QCheckBox(_("Title"), self)
        options_layout.addWidget(self.title_checkbox, widget_line, 0, 1, 1)
        self.title_checkbox.clicked.connect(self.title_checkbox_clicked)
        self.title_sort_checkbox = QCheckBox(_("Use 'Title Sort'"), self)
        options_layout.addWidget(self.title_sort_checkbox, widget_line, 1, 1, 1)
        
        self.author_checkbox = QCheckBox(_("Author"), self)
        options_layout.addWidget(self.author_checkbox, widget_line, 2, 1, 1)
        self.author_checkbox.clicked.connect(self.author_checkbox_clicked)
        self.author_sort_checkbox = QCheckBox(_("Use 'Author Sort'"), self)
        options_layout.addWidget(self.author_sort_checkbox, widget_line, 3, 1, 1)
        
        widget_line += 1
        self.description_checkbox = QCheckBox(_("Comments/Synopsis"), self)
        options_layout.addWidget(self.description_checkbox, 1, 0, 1, 1)
        self.description_checkbox.clicked.connect(self.description_checkbox_clicked)
        self.description_use_template_checkbox = QCheckBox(_("Use template"), self)
        options_layout.addWidget(self.description_use_template_checkbox, widget_line, 1, 1, 1)
        self.description_use_template_checkbox.clicked.connect(self.description_use_template_checkbox_clicked)
        
        self.description_template_edit = TemplateConfig(mi=self.test_book)
        description_template_edit_tooltip = _("Enter a template to use to set the comment/synopsis.")
        self.description_template_edit.setToolTip(description_template_edit_tooltip)
        options_layout.addWidget(self.description_template_edit, widget_line, 2, 1, 2)
        
        widget_line += 1
        self.series_checkbox = QCheckBox(_("Series and Index"), self)
        options_layout.addWidget(self.series_checkbox, widget_line, 0, 1, 2)
        
        self.publisher_checkbox = QCheckBox(_("Publisher"), self)
        options_layout.addWidget(self.publisher_checkbox, widget_line, 2, 1, 2)
        
        widget_line += 1
        self.published_checkbox = QCheckBox(_("Published Date"), self)
        options_layout.addWidget(self.published_checkbox, widget_line, 0, 1, 2)
        
        self.isbn_checkbox = QCheckBox(_("ISBN"), self)
        options_layout.addWidget(self.isbn_checkbox, widget_line, 2, 1, 2)
        
        widget_line += 1
        self.language_checkbox = QCheckBox(_("Language"), self)
        options_layout.addWidget(self.language_checkbox, widget_line, 0, 1, 2)

        self.rating_checkbox = QCheckBox(_("Rating"), self)
        options_layout.addWidget(self.rating_checkbox, widget_line, 2, 1, 2)

        widget_line += 1
        self.subtitle_checkbox = QCheckBox(_("Subtitle"), self)
        options_layout.addWidget(self.subtitle_checkbox, widget_line, 0, 1, 2)
        self.subtitle_checkbox.clicked.connect(self.subtitle_checkbox_clicked)

        self.subtitle_template_edit = TemplateConfig(mi=self.test_book)#device_settings.save_template)
        subtitle_template_edit_tooltip = _("Enter a template to use to set the subtitle. If the template is empty, the subtitle will be cleared.")
        self.subtitle_template_edit.setToolTip(subtitle_template_edit_tooltip)
        options_layout.addWidget(self.subtitle_template_edit, widget_line, 2, 1, 2)
        
        widget_line += 1
        self.reading_direction_checkbox = QCheckBox(_("Reading Direction"), self)
        reading_direction_checkbox_tooltip = _("Set the reading direction")
        self.reading_direction_checkbox.setToolTip(reading_direction_checkbox_tooltip)
        options_layout.addWidget(self.reading_direction_checkbox, widget_line, 0, 1, 1)
        self.reading_direction_checkbox.clicked.connect(self.reading_direction_checkbox_clicked)
        
        self.reading_direction_combo = ReadingDirectionChoiceComboBox(self, READING_DIRECTIONS)
        self.reading_direction_combo.setToolTip(reading_direction_checkbox_tooltip)
        options_layout.addWidget(self.reading_direction_combo, widget_line, 1, 1, 1)

        self.date_added_checkbox = QCheckBox(_("Date Added"), self)
        date_added_checkbox_tooltip = _("Set the date added to the device. This is used when sorting.")
        self.date_added_checkbox.setToolTip(date_added_checkbox_tooltip)
        options_layout.addWidget(self.date_added_checkbox, widget_line, 2, 1, 1)
        self.date_added_checkbox.clicked.connect(self.date_added_checkbox_clicked)

        self.date_added_column_combo = CustomColumnComboBox(self)
        self.date_added_column_combo.setToolTip(date_added_checkbox_tooltip)
        options_layout.addWidget(self.date_added_column_combo, widget_line, 3, 1, 1)

        widget_line += 1
        self.use_plugboard_checkbox = QCheckBox(_("Use Plugboard"), self)
        self.use_plugboard_checkbox.setToolTip(_("Set the metadata on the device using the plugboard for the device and book format."))
        self.use_plugboard_checkbox.clicked.connect(self.use_plugboard_checkbox_clicked)
        options_layout.addWidget(self.use_plugboard_checkbox, widget_line, 0, 1, 2)

        self.update_kepubs_checkbox = QCheckBox(_("Update Kobo ePubs"), self)
        self.update_kepubs_checkbox.setToolTip(_("Update the metadata for kePubs downloaded from the Kobo server."))
        options_layout.addWidget(self.update_kepubs_checkbox, widget_line, 2, 1, 2)

        self.readingStatusGroupBox = ReadingStatusGroupBox(self.parent())
        layout.addWidget(self.readingStatusGroupBox)

        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):

        self.new_prefs = {}
        self.new_prefs = cfg.METADATA_OPTIONS_DEFAULTS
        self.new_prefs[cfg.KEY_SET_TITLE]          = self.title_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_USE_TITLE_SORT]     = self.title_sort_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_AUTHOR]         = self.author_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_USE_AUTHOR_SORT]    = self.author_sort_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_DESCRIPTION]    = self.description_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_DESCRIPTION_USE_TEMPLATE] = self.description_use_template_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_DESCRIPTION_TEMPLATE] = self.description_template_edit.template
        self.new_prefs[cfg.KEY_SET_PUBLISHER]      = self.publisher_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_PUBLISHED_DATE] = self.published_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_ISBN]           = self.isbn_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_RATING]         = self.rating_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_SERIES]         = self.series_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_USE_PLUGBOARD]      = self.use_plugboard_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_LANGUAGE]       = self.language_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_UDPATE_KOBO_EPUBS]  = self.update_kepubs_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SET_SUBTITLE]       = self.subtitle_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SUBTITLE_TEMPLATE]  = self.subtitle_template_edit.template
        self.new_prefs[cfg.KEY_SET_READING_DIRECTION] = self.reading_direction_checkbox.checkState() == Qt.Checked
        self.new_prefs[cfg.KEY_SYNC_DATE]          = self.date_added_checkbox.checkState() == Qt.Checked


        if self.new_prefs[cfg.KEY_DESCRIPTION_USE_TEMPLATE] and not self.description_template_edit.validate():
            return False

        if self.new_prefs[cfg.KEY_SET_SUBTITLE] and not self.subtitle_template_edit.validate():
            return False

        if self.new_prefs[cfg.KEY_SET_READING_DIRECTION]:
            self.new_prefs[cfg.KEY_READING_DIRECTION] = READING_DIRECTIONS[unicode(self.reading_direction_combo.currentText()).strip()]

        if self.new_prefs[cfg.KEY_SYNC_DATE]:
            self.new_prefs[cfg.KEY_SYNC_DATE_COLUMN] = self.date_added_column_combo.get_selected_column()

        self.new_prefs[cfg.KEY_SET_READING_STATUS] = self.readingStatusGroupBox.readingStatusIsChecked()
        if self.readingStatusGroupBox.readingStatusIsChecked():
            self.new_prefs[cfg.KEY_READING_STATUS] = self.readingStatusGroupBox.readingStatus()
            if self.new_prefs['readingStatus'] < 0:
                return error_dialog(self, 'No reading status option selected',
                            'If you are changing the reading status, you must select an option to continue',
                            show=True, show_copy_button=False)
            self.new_prefs[cfg.KEY_RESET_POSITION] = self.readingStatusGroupBox.reset_position_checkbox.checkState() == Qt.Checked

        # Only if the user has checked at least one option will we continue
        for key in self.new_prefs:
            debug_print("UpdateMetadataOptionsDialog:ok_clicked - key='%s' self.new_prefs[key]=%s" % (key, self.new_prefs[key]))
            if self.new_prefs[key] and not key == cfg.KEY_READING_STATUS and not key == cfg.KEY_USE_PLUGBOARD:
                cfg.plugin_prefs[cfg.METADATA_OPTIONS_STORE_NAME] = self.new_prefs
                self.accept()
                return
        return error_dialog(self,
                            _('No options selected'),
                            _('You must select at least one option to continue.'),
                            show=True, show_copy_button=False
                            )

    def title_checkbox_clicked(self, checked):
        self.title_sort_checkbox.setEnabled(checked and not self.use_plugboard_checkbox.checkState() == Qt.Checked)

    def author_checkbox_clicked(self, checked):
        self.author_sort_checkbox.setEnabled(checked and not self.use_plugboard_checkbox.checkState() == Qt.Checked)

    def description_checkbox_clicked(self, checked):
        self.description_use_template_checkbox.setEnabled(checked)
        self.description_use_template_checkbox_clicked(checked)

    def description_use_template_checkbox_clicked(self, checked):
        self.description_template_edit.setEnabled(checked and self.description_use_template_checkbox.checkState() == Qt.Checked)

    def subtitle_checkbox_clicked(self, checked):
        self.subtitle_template_edit.setEnabled(checked)

    def date_added_checkbox_clicked(self, checked):
        self.date_added_column_combo.setEnabled(checked)

    def reading_direction_checkbox_clicked(self, checked):
        self.reading_direction_combo.setEnabled(checked)

    def use_plugboard_checkbox_clicked(self, checked):
        self.title_sort_checkbox.setEnabled(not checked and self.title_checkbox.checkState() == Qt.Checked)
        self.author_sort_checkbox.setEnabled(not checked and self.author_checkbox.checkState() == Qt.Checked)

    def get_date_columns(self, column_names=DATE_COLUMNS):
        available_columns = {}
        for column_name in column_names:
            calibre_column_name = self.plugin_action.gui.library_view.model().orig_headers[column_name]
            available_columns[column_name] = {'name': calibre_column_name}
        available_columns.update(self.get_date_custom_columns())
        return available_columns

    def get_date_custom_columns(self):
        column_types = ['datetime']
        return self.get_custom_columns(column_types)

    def get_text_type_custom_columns(self):
        column_types = ['text']
        return self.get_custom_columns(column_types)

    def get_custom_columns(self, column_types):
        custom_columns = self.plugin_action.gui.library_view.model().custom_columns
        available_columns = {}
        for key, column in custom_columns.items():
            typ = column['datatype']
            if typ in column_types:
                available_columns[key] = column
        return available_columns



class GetShelvesFromDeviceDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:get shelves from device settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "GetShelvesFromDevice"

        self.initialize_controls()

        all_books = cfg.get_plugin_pref(cfg.GET_SHELVES_OPTIONS_STORE_NAME, cfg.KEY_ALL_BOOKS)
        self.all_books_checkbox.setCheckState(Qt.Checked if all_books else Qt.Unchecked)

        replace_shelves = cfg.get_plugin_pref(cfg.GET_SHELVES_OPTIONS_STORE_NAME, cfg.KEY_REPLACE_SHELVES)
        self.replace_shelves_checkbox.setCheckState(Qt.Checked if replace_shelves else Qt.Unchecked)

        shelf_column = cfg.get_plugin_pref(cfg.GET_SHELVES_OPTIONS_STORE_NAME, cfg.KEY_SHELVES_CUSTOM_COLUMN)
        self.tag_type_custom_columns = self.get_tag_type_custom_columns()
        self.shelf_column_combo.populate_combo(self.tag_type_custom_columns, shelf_column)
        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Get Shelves from Device')
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("Options"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        shelf_column_label = QLabel(_('Shelf column:'), self)
        shelf_column_tooltip = _("Select a custom column to store the retrieved shelf names. The column type must\nbe of type 'text'.")
        shelf_column_label.setToolTip(shelf_column_tooltip)
        self.shelf_column_combo = CustomColumnComboBox(self)
        self.shelf_column_combo.setToolTip(shelf_column_tooltip)
        shelf_column_label.setBuddy(self.shelf_column_combo)
        options_layout.addWidget(shelf_column_label, 0, 0, 1, 1)
        options_layout.addWidget(self.shelf_column_combo, 0, 1, 1, 1)
        
        self.all_books_checkbox = QCheckBox(_("All books on device"), self)
        self.all_books_checkbox.setToolTip(_("Get the shelves for all the books on the device that are in the library. If not checked, will only get them for the selected books."))
        options_layout.addWidget(self.all_books_checkbox, 1, 0, 1, 2)
        
        self.replace_shelves_checkbox = QCheckBox(_("Replace column with shelves"), self)
        self.replace_shelves_checkbox.setToolTip(_("If this is selected, the current value in the library, will be replaced by\nthe retrieved shelves. Otherwise, the retrieved shelves will be added to the value"))
        options_layout.addWidget(self.replace_shelves_checkbox, 2, 0, 1, 2)

        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_tag_type_custom_columns(self):
        column_types = ['text']
        return self.get_custom_columns(column_types)

    def get_custom_columns(self, column_types):
        custom_columns = self.plugin_action.gui.library_view.model().custom_columns
        available_columns = {}
        for key, column in custom_columns.items():
            typ = column['datatype']
            if typ in column_types:
                available_columns[key] = column
        return available_columns

    def ok_clicked(self):

        self.options = {}
        self.options = cfg.GET_SHELVES_OPTIONS_DEFAULTS
        self.options[cfg.KEY_SHELVES_CUSTOM_COLUMN] = self.shelf_column_combo.get_selected_column()
        self.options[cfg.KEY_ALL_BOOKS]             = self.all_books_checkbox.checkState() == Qt.Checked
        self.options[cfg.KEY_REPLACE_SHELVES]       = self.replace_shelves_checkbox.checkState() == Qt.Checked

        if not self.options[cfg.KEY_SHELVES_CUSTOM_COLUMN] or self.options[cfg.KEY_SHELVES_CUSTOM_COLUMN] == '':
            return error_dialog(self, _('No shelf column selected'),
                            'You must select a column to populate from the shelves on the device',
                            show=True, show_copy_button=False)

        cfg.plugin_prefs[cfg.GET_SHELVES_OPTIONS_STORE_NAME] = self.options
        self.accept()
        return


class DismissTilesOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:dismiss tiles settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "DismissTiles"

#        self.options = gprefs.get(self.unique_pref_name+':settings', {})
        self.options = cfg.get_plugin_prefs(cfg.DISMISSTILES_OPTIONS_STORE_NAME)
        self.initialize_controls()

        self.tiles_new_checkbox.setCheckState(Qt.Checked if self.options.get(cfg.KEY_TILE_RECENT_NEW, False) else Qt.Unchecked)
        self.tiles_finished_checkbox.setCheckState(Qt.Checked if self.options.get(cfg.KEY_TILE_RECENT_FINISHED, False) else Qt.Unchecked)
        self.tiles_inthecloud_checkbox.setCheckState(Qt.Checked if self.options.get(cfg.KEY_TILE_RECENT_IN_THE_CLOUD, False) else Qt.Unchecked)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Dismiss Tiles from Home Screen', )
        layout.addLayout(title_layout)

        main_layout = QHBoxLayout()
        layout.addLayout(main_layout, 1)
        col2_layout = QVBoxLayout()
        main_layout.addLayout(col2_layout)

        self._add_groupbox(col2_layout, 'Tile Types:', TILE_TYPES, self.options.get(cfg.KEY_TILE_OPTIONS, {}))
        col2_layout.addSpacing(5)

        options_group = QGroupBox(_("Book Tiles"), self)
        options_group.setToolTip(_("For books, you can dismiss the 'Finished' and 'New' tiles."))
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        self.tiles_new_checkbox = QCheckBox(_("New"), self)
        self.tiles_new_checkbox.setToolTip(_("Select this option if you want to dismiss new books. This will act on all tiles of this type."))
        options_layout.addWidget(self.tiles_new_checkbox, 0, 0, 1, 1)
        self.tiles_finished_checkbox = QCheckBox(_("Finished"), self)
        self.tiles_finished_checkbox.setToolTip(_("Select this option if you want to dismiss finished books."))
        options_layout.addWidget(self.tiles_finished_checkbox, 0, 1, 1, 1)
        self.tiles_inthecloud_checkbox = QCheckBox(_("In the Cloud"), self)
        self.tiles_inthecloud_checkbox.setToolTip(_("Select this option if you want to dismiss books that are 'In the Cloud'."))
        options_layout.addWidget(self.tiles_inthecloud_checkbox, 0, 2, 1, 1)

        options_group = QGroupBox(_("Database Trigger"), self)
        options_group.setToolTip(_("When a tile is added or changed, the database trigger will automatically set them to be dismissed. This will be done for the tile types selected above."))
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        self.database_trigger_checkbox = QCheckBox(_("Change database trigger"), self)
        self.database_trigger_checkbox.setToolTip(_("Select this option if you want to change the current database trigger."))
        options_layout.addWidget(self.database_trigger_checkbox, 0, 0, 1, 2)
        self.database_trigger_checkbox.clicked.connect(self.database_trigger_checkbox_clicked)

        self.create_trigger_radiobutton = QRadioButton(_("Create or change trigger"), self)
        self.create_trigger_radiobutton.setToolTip(_("To create or change the trigger, select this option."))
        options_layout.addWidget(self.create_trigger_radiobutton, 1, 0, 1, 1)
        self.create_trigger_radiobutton.setEnabled(False)

        self.delete_trigger_radiobutton = QRadioButton(_("Delete trigger"), self)
        self.delete_trigger_radiobutton.setToolTip(_("This will remove the existing trigger and let the device work as Kobo intended it."))
        options_layout.addWidget(self.delete_trigger_radiobutton, 1, 1, 1, 1)
        self.delete_trigger_radiobutton.setEnabled(False)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._ok_clicked)
        button_box.rejected.connect(self.reject)
        self.select_none_button = button_box.addButton(_("Clear all"), QDialogButtonBox.ResetRole)
        self.select_none_button.setToolTip(_("Clear all selections"))
        self.select_none_button.clicked.connect(self._select_none_clicked)
        layout.addWidget(button_box)

    def _add_groupbox(self, layout, title, option_info, options):
        groupbox = QGroupBox(title)
        groupbox.setToolTip(_("This is the list of Tile types that can be dismissed. Select the one you want to dismiss."))

        layout.addWidget(groupbox)
        groupbox_layout = QGridLayout()
        groupbox.setLayout(groupbox_layout)
        
        xpos = 0
        ypos = 0
        i    = 0

        for key, text, tooltip in sorted(option_info):
            checkbox = QCheckBox(_(text), self)
            checkbox.setToolTip(_(tooltip))
            checkbox.setCheckState(Qt.Checked if options.get(key, False) else Qt.Unchecked)
            setattr(self, key, checkbox)
            groupbox_layout.addWidget(checkbox, ypos, xpos, 1, 1)
            i += 1
            if i % 2 == 0:
                xpos = 0
                ypos += 1
            else:
                xpos = 1

    def database_trigger_checkbox_clicked(self, checked):
        self.create_trigger_radiobutton.setEnabled(checked)
        self.delete_trigger_radiobutton.setEnabled(checked)

    def _ok_clicked(self):
        self.options = {}
        self.options[cfg.KEY_TILE_OPTIONS] = {}
        for option_name, _t, _tt in TILE_TYPES:
            self.options[cfg.KEY_TILE_OPTIONS][option_name] = getattr(self, option_name).checkState() == Qt.Checked

        self.options[cfg.KEY_TILE_RECENT_NEW]          = self.tiles_new_checkbox.checkState() == Qt.Checked
        self.options[cfg.KEY_TILE_RECENT_FINISHED]     = self.tiles_finished_checkbox.checkState() == Qt.Checked
        self.options[cfg.KEY_TILE_RECENT_IN_THE_CLOUD] = self.tiles_inthecloud_checkbox.checkState() == Qt.Checked

        cfg.plugin_prefs[cfg.DISMISSTILES_OPTIONS_STORE_NAME] = self.options

        self.options[cfg.KEY_CHANGE_DISMISS_TRIGGER] = self.database_trigger_checkbox.checkState() == Qt.Checked
        self.options[cfg.KEY_CREATE_DISMISS_TRIGGER] = self.create_trigger_radiobutton.isChecked()
        self.options[cfg.KEY_DELETE_DISMISS_TRIGGER] = self.delete_trigger_radiobutton.isChecked()

        have_options = False
        # Only if the user has checked at least one option will we continue
        for key in self.options[cfg.KEY_TILE_OPTIONS]:
            have_options = have_options or self.options[cfg.KEY_TILE_OPTIONS][key]

        if have_options or self.options[cfg.KEY_TILE_RECENT_FINISHED] or self.options[cfg.KEY_TILE_RECENT_NEW] or self.options[cfg.KEY_DELETE_DISMISS_TRIGGER] or self.options[cfg.KEY_TILE_RECENT_IN_THE_CLOUD]:
            self.accept()
            return
        return error_dialog(self,
                            _('No options selected'),
                            _('You must select at least one option to continue.'),
                            show=True, show_copy_button=False
                            )

    def _select_none_clicked(self):
        for option_name, _t, _tt in TILE_TYPES:
            getattr(self, option_name).setCheckState(Qt.Unchecked)
        self.tiles_new_checkbox.setCheckState(Qt.Unchecked)
        self.tiles_finished_checkbox.setCheckState(Qt.Unchecked)


class DispayExtrasTilesDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:display extras tiles dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "DispayExtrasTiles"

#        self.options = gprefs.get(self.unique_pref_name+':settings', {})
        self.options = cfg.get_plugin_prefs(cfg.DISPLAYEXTRASTILES_OPTIONS_STORE_NAME)
        self.initialize_controls()

        self.dismiss_current_extras_checkbox.setCheckState(Qt.Checked if self.options.get(cfg.KEY_DISMISS_CURRENT_EXTRAS, False) else Qt.Unchecked)
        
        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Display Extras Tiles')
        layout.addLayout(title_layout)

        main_layout = QHBoxLayout()
        layout.addLayout(main_layout, 1)
        col2_layout = QVBoxLayout()
        main_layout.addLayout(col2_layout)

        self._add_groupbox(col2_layout, 'Extras:', EXTRAS_TILES, self.options.get(cfg.KEY_TILE_OPTIONS, {}))
        col2_layout.addSpacing(5)

        options_group = QGroupBox(_("Options"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        self.dismiss_current_extras_checkbox = QCheckBox(_("Dismiss current Extras tiles"), self)
        self.dismiss_current_extras_checkbox.setToolTip(_("Select this option if you want to dismiss the Extras tiles already on the home screen."))
        options_layout.addWidget(self.dismiss_current_extras_checkbox, 0, 0, 1, 1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._ok_clicked)
        button_box.rejected.connect(self.reject)
        self.select_none_button = button_box.addButton(_("Clear all"), QDialogButtonBox.ResetRole)
        self.select_none_button.setToolTip(_("Clear all selections"))
        self.select_none_button.clicked.connect(self._select_none_clicked)
        self.select_all_button = button_box.addButton(_("Select all"), QDialogButtonBox.ResetRole)
        self.select_all_button.setToolTip(_("Select all Extras"))
        self.select_all_button.clicked.connect(self._select_all_clicked)
        layout.addWidget(button_box)

    def _add_groupbox(self, layout, title, option_info, options):
        groupbox = QGroupBox(title)
        groupbox.setToolTip(_("This is the list of Extras tiles."))

        layout.addWidget(groupbox)
        groupbox_layout = QGridLayout()
        groupbox.setLayout(groupbox_layout)
        
        xpos = 0
        ypos = 0
        i    = 0

        for key, text, tooltip in sorted(option_info):
            checkbox = QCheckBox(_(text), self)
            checkbox.setToolTip(_(tooltip))
            checkbox.setCheckState(Qt.Checked if options.get(key, False) else Qt.Unchecked)
            setattr(self, key, checkbox)
            groupbox_layout.addWidget(checkbox, ypos, xpos, 1, 1)
            i += 1
            if i % 2 == 0:
                xpos = 0
                ypos += 1
            else:
                xpos = 1

    def _ok_clicked(self):
        have_options = False
        self.options = {}
        self.options[cfg.KEY_TILE_OPTIONS] = {}
        for option_name, _t, _tt in EXTRAS_TILES:
            self.options[cfg.KEY_TILE_OPTIONS][option_name] = getattr(self, option_name).checkState() == Qt.Checked
            have_options = have_options or self.options[cfg.KEY_TILE_OPTIONS][option_name]

        self.options[cfg.KEY_DISMISS_CURRENT_EXTRAS] = self.dismiss_current_extras_checkbox.checkState() == Qt.Checked
        cfg.plugin_prefs[cfg.DISPLAYEXTRASTILES_OPTIONS_STORE_NAME] = self.options

        if have_options or self.options[cfg.KEY_DISMISS_CURRENT_EXTRAS]:
            self.accept()
            return
        return error_dialog(self,
                            _('No options selected'),
                            _('You must select at least one option to continue.'),
                            show=True, show_copy_button=False
                            )

    def _select_none_clicked(self):
        for option_name, _t, _tt in EXTRAS_TILES:
            getattr(self, option_name).setCheckState(Qt.Unchecked)

    def _select_all_clicked(self):
        for option_name, _t, _tt in EXTRAS_TILES:
            getattr(self, option_name).setCheckState(Qt.Checked)


class BookmarkOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:bookmark options dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "StoreCurrentBookmark"

#        self.options = gprefs.get(self.unique_pref_name+':settings', {})

        # Set some default values from last time dialog was used.
        c = cfg.plugin_prefs[cfg.BOOKMARK_OPTIONS_STORE_NAME]
        store_bookmarks             = c.get(cfg.KEY_STORE_BOOKMARK,  cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_STORE_BOOKMARK])
        set_status_to_reading       = c.get(cfg.KEY_READING_STATUS,  cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_READING_STATUS])
        set_date_to_now             = c.get(cfg.KEY_DATE_TO_NOW,     cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_DATE_TO_NOW])
        set_rating                  = c.get(cfg.KEY_SET_RATING,      cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_SET_RATING])
        clear_if_unread             = c.get(cfg.KEY_CLEAR_IF_UNREAD, cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_CLEAR_IF_UNREAD])
        store_if_more_recent        = c.get(cfg.KEY_STORE_IF_MORE_RECENT,     cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_STORE_IF_MORE_RECENT])
        do_not_store_if_reopened    = c.get(cfg.KEY_DO_NOT_STORE_IF_REOPENED, cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_DO_NOT_STORE_IF_REOPENED])
        background_job              = c.get(cfg.KEY_BACKGROUND_JOB,  cfg.BOOKMARK_OPTIONS_DEFAULTS[cfg.KEY_BACKGROUND_JOB])

        library_config = cfg.get_library_config(self.plugin_action.gui.current_db)
        self.profiles = library_config.get(cfg.KEY_PROFILES, {})
        self.profile_name = self.plugin_action.current_device_profile['profileName'] if self.plugin_action.current_device_profile else None
        self.initialize_controls()

        if store_bookmarks:
            self.store_radiobutton.click()
        else:
            self.restore_radiobutton.click()
        self.status_to_reading_checkbox.setCheckState(Qt.Checked if set_status_to_reading else Qt.Unchecked)
        self.date_to_now_checkbox.setCheckState(Qt.Checked if set_date_to_now else Qt.Unchecked)
        self.set_rating_checkbox.setCheckState(Qt.Checked if set_rating and self.plugin_action.supports_ratings else Qt.Unchecked)
#        self.set_rating_checkbox.setEnabled(have_rating_column(self.plugin_action) and self.plugin_action.supports_ratings)

        self.clear_if_unread_checkbox.setCheckState(Qt.Checked if clear_if_unread else Qt.Unchecked)
        self.store_if_more_recent_checkbox.setCheckState(Qt.Checked if store_if_more_recent else Qt.Unchecked)
        self.do_not_store_if_reopened_checkbox.setCheckState(Qt.Checked if do_not_store_if_reopened else Qt.Unchecked)
        self.do_not_store_if_reopened_checkbox_clicked(do_not_store_if_reopened)
        self.background_checkbox.setCheckState(Qt.Checked if background_job else Qt.Unchecked)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Store or Restore Bookmark')
        layout.addLayout(title_layout)

        options_column_group = QGroupBox(_("Options"), self)
        layout.addWidget(options_column_group)
        options_layout = QGridLayout()
        options_column_group.setLayout(options_layout)

        self.store_radiobutton = QRadioButton(_("Store"), self)
        self.store_radiobutton.setToolTip(_("Store the current reading position in the calibre library."))
        options_layout.addWidget(self.store_radiobutton, 1, 0, 1, 1)
        self.store_radiobutton.clicked.connect(self.store_radiobutton_clicked)

        self.store_if_more_recent_checkbox = QCheckBox(_("Only if more recent"), self)
        self.store_if_more_recent_checkbox.setToolTip(_("Only store the reading position if the last read timestamp on the device is more recent than in the library."))
        options_layout.addWidget(self.store_if_more_recent_checkbox, 2, 0, 1, 1)

        self.do_not_store_if_reopened_checkbox = QCheckBox(_("Not if finished in library"), self)
        self.do_not_store_if_reopened_checkbox.setToolTip(_("Do not store the reading position if the library has the book as finished. This is if the percent read is 100%."))
        options_layout.addWidget(self.do_not_store_if_reopened_checkbox, 3, 0, 1, 1)
        self.do_not_store_if_reopened_checkbox.clicked.connect(self.do_not_store_if_reopened_checkbox_clicked)

        self.clear_if_unread_checkbox = QCheckBox(_("Clear if unread"), self)
        self.clear_if_unread_checkbox.setToolTip(_("If the book on the device is shown as unread, clear the reading position stored in the library."))
        options_layout.addWidget(self.clear_if_unread_checkbox, 4, 0, 1, 1)

        self.background_checkbox = QCheckBox(_("Run in background"), self)
        self.background_checkbox.setToolTip(_("Do store or restore as background job."))
        options_layout.addWidget(self.background_checkbox, 5, 0, 1, 2)


        self.restore_radiobutton = QRadioButton(_("Restore"), self)
        self.restore_radiobutton.setToolTip(_("Copy the current reading position back to the device."))
        options_layout.addWidget(self.restore_radiobutton, 1, 1, 1, 1)
        self.restore_radiobutton.clicked.connect(self.restore_radiobutton_clicked)
        
        self.status_to_reading_checkbox = QCheckBox(_("Set reading status"), self)
        self.status_to_reading_checkbox.setToolTip(_("If this is not set, when the current reading position is on the device, the reading status will not be changes. If the percent read is 100%, the book will be marked as finished. Otherwise, it will be in progress."))
        options_layout.addWidget(self.status_to_reading_checkbox, 2, 1, 1, 1)
        
        self.date_to_now_checkbox = QCheckBox(_("Set date to now"), self)
        self.date_to_now_checkbox.setToolTip(_("Setting the date to now will put the book at the top of the \"Recent reads\" list."))
        options_layout.addWidget(self.date_to_now_checkbox, 3, 1, 1, 1)
        
        self.set_rating_checkbox = QCheckBox(_("Update rating"), self)
        self.set_rating_checkbox.setToolTip(_("Set the book rating on the device. If the current rating in the library is zero, the rating on the device will be reset."))
        options_layout.addWidget(self.set_rating_checkbox, 4, 1, 1, 1)


        profiles_label = QLabel(_('Profile'), self)
        options_layout.addWidget(profiles_label, 6, 0, 1, 1)
        self.select_profile_combo = ProfileComboBox(self, self.profiles, self.profile_name)
        self.select_profile_combo.setMinimumSize(150, 20)
        options_layout.addWidget(self.select_profile_combo, 6, 1, 1, 1)

        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):
#        gprefs.set(self.unique_pref_name+':settings', self.options)
        profile_name = unicode(self.select_profile_combo.currentText()).strip()
        msg = self.plugin_action.validate_profile(profile_name)
        if msg is not None:
            error_dialog(self, 'Invalid profile',
                            msg,
                            show=True, show_copy_button=False)
            return
        new_prefs = {}
        new_prefs[cfg.KEY_STORE_BOOKMARK]       = self.store_radiobutton.isChecked()
        new_prefs[cfg.KEY_READING_STATUS]       = self.status_to_reading_checkbox.checkState() == Qt.Checked
        new_prefs[cfg.KEY_DATE_TO_NOW]          = self.date_to_now_checkbox.checkState() == Qt.Checked
        new_prefs[cfg.KEY_SET_RATING]           = self.set_rating_checkbox.checkState() == Qt.Checked
        new_prefs[cfg.KEY_CLEAR_IF_UNREAD]      = self.clear_if_unread_checkbox.checkState() == Qt.Checked
        new_prefs[cfg.KEY_STORE_IF_MORE_RECENT] = self.store_if_more_recent_checkbox.checkState() == Qt.Checked
        new_prefs[cfg.KEY_DO_NOT_STORE_IF_REOPENED] = self.do_not_store_if_reopened_checkbox.checkState() == Qt.Checked
        new_prefs[cfg.KEY_BACKGROUND_JOB]       = self.background_checkbox.checkState() == Qt.Checked
        cfg.plugin_prefs[cfg.BOOKMARK_OPTIONS_STORE_NAME]  = new_prefs
        new_prefs['profileName'] = unicode(profile_name)
        self.options = new_prefs
        if self.options[cfg.KEY_DO_NOT_STORE_IF_REOPENED]:
            self.options[cfg.KEY_CLEAR_IF_UNREAD] = False
        self.accept()

    def do_not_store_if_reopened_checkbox_clicked(self, checked):
        self.clear_if_unread_checkbox.setEnabled(not checked)

    def restore_radiobutton_clicked(self, checked):
        self.status_to_reading_checkbox.setEnabled(checked)
        self.date_to_now_checkbox.setEnabled(checked)
        self.set_rating_checkbox.setEnabled(checked and have_rating_column(self.plugin_action) and self.plugin_action.supports_ratings)
        self.clear_if_unread_checkbox.setEnabled(not checked)
        self.store_if_more_recent_checkbox.setEnabled(not checked)
        self.do_not_store_if_reopened_checkbox.setEnabled(not checked)
        self.background_checkbox.setEnabled(not checked)

    def store_radiobutton_clicked(self, checked):
        self.status_to_reading_checkbox.setEnabled(not checked)
        self.date_to_now_checkbox.setEnabled(not checked)
        self.set_rating_checkbox.setEnabled(not checked)
        self.clear_if_unread_checkbox.setEnabled(checked)
        self.store_if_more_recent_checkbox.setEnabled(checked)
        self.do_not_store_if_reopened_checkbox.setEnabled(checked)
        self.background_checkbox.setEnabled(checked)



class ChangeReadingStatusOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:change reading status settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "ChangeReadingStatus"

        self.options = gprefs.get(self.unique_pref_name+':settings', {})
        
        self.initialize_controls()

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Change Reading Status in Device Library')
        layout.addLayout(title_layout)

        self.readingStatusGroupBox = ReadingStatusGroupBox(self.parent())
        layout.addWidget(self.readingStatusGroupBox)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):

        self.options = self.plugin_action.default_options()

        self.options['setRreadingStatus'] = self.readingStatusGroupBox.readingStatusIsChecked()
        if self.options['setRreadingStatus']:
            self.options['readingStatus'] = self.readingStatusGroupBox.readingStatus()
            if self.options['readingStatus'] < 0:
                return error_dialog(self, 'No reading status option selected',
                           'If you are changing the reading status, you must select an option to continue',
                            show=True, show_copy_button=False)
            self.options['resetPosition'] = self.readingStatusGroupBox.reset_position_checkbox.checkState() == Qt.Checked

        # Only if the user has checked at least one option will we continue
        for key in self.options:
            if self.options[key]:
                self.accept()
                return
        return error_dialog(self,
                            _('No options selected'),
                            _('You must select at least one option to continue.'),
                            show=True, show_copy_button=False
                            )


class BackupAnnotationsOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:backup annotation files settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "BackupAnnotations"

        self.options = gprefs.get(self.unique_pref_name+':settings', {})
        
        self.initialize_controls()

        self.dest_directory_edit.setText(self.options.get('dest_directory', ''))
        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Backup Annotations Files')
        layout.addLayout(title_layout)
        options_layout = QGridLayout()
        layout.addLayout(options_layout)

        dest_directory_label = QLabel(_("Destination:"), self)
        dest_directory_label.setToolTip(_("Select the destination the annotations files are to be backed up in."))
        self.dest_directory_edit = QLineEdit(self)
        self.dest_directory_edit.setMinimumSize(200, 0)
        dest_directory_label.setBuddy(self.dest_directory_edit)
        dest_pick_button = QPushButton(_("..."), self)
        dest_pick_button.setMaximumSize(24, 20)
        dest_pick_button.clicked.connect(self._get_dest_directory_name)
        options_layout.addWidget(dest_directory_label, 0, 0, 1, 1)
        options_layout.addWidget(self.dest_directory_edit, 0, 1, 1, 1)
        options_layout.addWidget(dest_pick_button, 0, 2, 1, 1)

        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):

        if len(self.dest_directory_edit.text()) == 0:
            return error_dialog(self,'No destination',
                               'You must enter a destination directory to save the annotation files in',
                                show=True, show_copy_button=False)

        self.options['dest_directory'] = unicode(self.dest_directory_edit.text())
        gprefs.set(self.unique_pref_name+':settings', self.options)
        self.accept()

    def dest_path(self):
        return self.dest_directory_edit.text()

    def _get_dest_directory_name(self):
        path = choose_dir(self, 'backup annotations destination dialog','Choose destination directory')
        self.dest_directory_edit.setText(path)


class RemoveAnnotationsOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:remove annotation files settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "RemoveAnnotations"

        self.options = gprefs.get(self.unique_pref_name+':settings', {})
        
        self.is_device_view = self.plugin_action.isDeviceView()
        self.initialize_controls()
        self.annotation_clean_option = self.options.get(cfg.KEY_REMOVE_ANNOT_ACTION, 0)
        self.annotation_clean_option_button_group.button(self.annotation_clean_option).setChecked(True)
        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', _('Remove Annotations Files'))
        layout.addLayout(title_layout)
        options_layout = QGridLayout()
        layout.addLayout(options_layout)

        annotation_clean_option_group_box = QGroupBox(_("Remove..."), self)
        options_layout.addWidget(annotation_clean_option_group_box, 0, 0, 1, 1)

        annotation_clean_options = {
                            cfg.KEY_REMOVE_ANNOT_ALL: (_("All"), _("Remove the annotations directory and all files within it"), True),
                            cfg.KEY_REMOVE_ANNOT_SELECTED: (_("For selected books"), _("Only remove annotations files for the selected books"), False),
                            cfg.KEY_REMOVE_ANNOT_NOBOOK: (_("Where book is not on device"), _("Remove annotations files where there is no book on the device"), True), 
                            cfg.KEY_REMOVE_ANNOT_EMPTY: (_("Empty"), _("Remove all empty annotations files"), True),
                            cfg.KEY_REMOVE_ANNOT_NONEMPTY: (_("Not empty"), _("Only remove annotations files if they contain annotations"), True),
#                            (_("Remove if in database"), _("Remove annotations files if there are annotations in the datababase"),), 
                            }

        annotation_clean_option_group_box_layout = QVBoxLayout()
        annotation_clean_option_group_box.setLayout(annotation_clean_option_group_box_layout)
        self.annotation_clean_option_button_group = QButtonGroup(self)
        self.annotation_clean_option_button_group.buttonClicked[int].connect(self._annotation_clean_option_radio_clicked)
        for clean_option in annotation_clean_options.keys():
            clean_options = annotation_clean_options[clean_option]
            rdo = QRadioButton(clean_options[0], self)
            rdo.setToolTip(clean_options[1])
            self.annotation_clean_option_button_group.addButton(rdo)
            self.annotation_clean_option_button_group.setId(rdo, clean_option)
            annotation_clean_option_group_box_layout.addWidget(rdo)

        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):

        self.options[cfg.KEY_REMOVE_ANNOT_ACTION] = self.annotation_clean_option
        gprefs.set(self.unique_pref_name+':settings', self.options)
        self.accept()

    def _annotation_clean_option_radio_clicked(self, idx):
        self.annotation_clean_option = idx


class CoverUploadOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:cover upload settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "UploadCovers"

        self.initialize_controls()

        self.options = gprefs.get(self.unique_pref_name+':settings', {})

        # Set some default values from last time dialog was used.
        blackandwhite = self.options.get(cfg.KEY_COVERS_BLACKANDWHITE, False)
        self.blackandwhite_checkbox.setCheckState(Qt.Checked if blackandwhite else Qt.Unchecked)
        self.blackandwhite_checkbox_clicked(blackandwhite)
        ditheredcovers = self.options.get(cfg.KEY_COVERS_DITHERED, False)
        self.ditheredcovers_checkbox.setCheckState(Qt.Checked if ditheredcovers else Qt.Unchecked)

        # Hide options if the driver doesn't have the extended options.
        self.driver_supports_extended_cover_options = hasattr(self.plugin_action.device, 'dithered_covers')
        self.driver_supports_cover_letterbox_colors = hasattr(self.plugin_action.device, 'letterbox_fs_covers_color')
        self.ditheredcovers_checkbox.setVisible(self.driver_supports_extended_cover_options)
        self.letterbox_checkbox.setVisible(self.driver_supports_extended_cover_options)
        self.pngcovers_checkbox.setVisible(self.driver_supports_extended_cover_options)
        self.letterbox_colorbutton.setVisible(self.driver_supports_cover_letterbox_colors)

        letterbox = self.options.get(cfg.KEY_COVERS_LETTERBOX, False)
        self.letterbox_checkbox.setCheckState(Qt.Checked if letterbox else Qt.Unchecked)
        self.letterbox_checkbox_clicked(letterbox)
        keep_cover_aspect = self.options.get(cfg.KEY_COVERS_KEEP_ASPECT_RATIO, False)
        self.keep_cover_aspect_checkbox.setCheckState(Qt.Checked if keep_cover_aspect else Qt.Unchecked)
        self.keep_cover_aspect_checkbox_clicked(keep_cover_aspect)
        letterbox_color = self.options.get(cfg.KEY_COVERS_LETTERBOX_COLOR, '#000000')
        self.letterbox_colorbutton.color = letterbox_color
        pngcovers = self.options.get(cfg.KEY_COVERS_PNG, False)
        self.pngcovers_checkbox.setCheckState(Qt.Checked if pngcovers else Qt.Unchecked)
        kepub_covers = self.options.get(cfg.KEY_COVERS_UPDLOAD_KEPUB, False)
        self.kepub_covers_checkbox.setCheckState(Qt.Checked if kepub_covers else Qt.Unchecked)
        
        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'default_cover.png', 'Upload Covers')
        layout.addLayout(title_layout, stretch=0)

        options_group = QGroupBox(_("Upload Covers"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        self.blackandwhite_checkbox = QCheckBox(_("Black and White Covers"), self)
        options_layout.addWidget(self.blackandwhite_checkbox, 0, 0, 1, 1)
        self.blackandwhite_checkbox.clicked.connect(self.blackandwhite_checkbox_clicked)
        self.ditheredcovers_checkbox = QCheckBox(_("Dithered Covers"), self)
        options_layout.addWidget(self.ditheredcovers_checkbox, 0, 1, 1, 1)
        self.pngcovers_checkbox = QCheckBox(_("PNG Covers"), self)
        options_layout.addWidget(self.pngcovers_checkbox, 0, 2, 1, 2)

        self.keep_cover_aspect_checkbox = QCheckBox(_("Keep cover aspect ratio"), self)
        options_layout.addWidget(self.keep_cover_aspect_checkbox, 1, 0, 1, 1)
        self.keep_cover_aspect_checkbox.clicked.connect(self.keep_cover_aspect_checkbox_clicked)
        self.letterbox_checkbox = QCheckBox(_("Letterbox Covers"), self)
        options_layout.addWidget(self.letterbox_checkbox, 1, 1, 1, 1)
        self.letterbox_checkbox.clicked.connect(self.letterbox_checkbox_clicked)

        self.letterbox_colorbutton = ColorButton(options_layout)
        self.letterbox_colorbutton.setToolTip(_('Choose the color to use when letterboxing the cover.'
                                                ' The default color is black (#000000)'
                                                )
                                            )
        options_layout.addWidget(self.letterbox_colorbutton, 1, 2, 1, 1)

        self.kepub_covers_checkbox = QCheckBox(_("Upload Covers for Kobo ePubs"), self)
        options_layout.addWidget(self.kepub_covers_checkbox, 2, 0, 1, 3)
        options_layout.setColumnStretch(0, 0)
        options_layout.setColumnStretch(1, 0)
        options_layout.setColumnStretch(2, 0)
        
        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):

        self.options[cfg.KEY_COVERS_BLACKANDWHITE]     = self.blackandwhite_checkbox.checkState() == Qt.Checked
        self.options[cfg.KEY_COVERS_DITHERED]          = self.ditheredcovers_checkbox.checkState() == Qt.Checked
        self.options[cfg.KEY_COVERS_PNG]               = self.pngcovers_checkbox.checkState() == Qt.Checked
        self.options[cfg.KEY_COVERS_KEEP_ASPECT_RATIO] = self.keep_cover_aspect_checkbox.checkState() == Qt.Checked
        self.options[cfg.KEY_COVERS_LETTERBOX]         = self.letterbox_checkbox.checkState() == Qt.Checked
        if self.driver_supports_cover_letterbox_colors:
            self.options[cfg.KEY_COVERS_LETTERBOX_COLOR]   = self.letterbox_colorbutton.color
        self.options[cfg.KEY_COVERS_UPDLOAD_KEPUB]     = self.kepub_covers_checkbox.checkState() == Qt.Checked

        gprefs.set(self.unique_pref_name+':settings', self.options)
        self.accept()

    def blackandwhite_checkbox_clicked(self, checked):
        self.ditheredcovers_checkbox.setEnabled(checked and self.blackandwhite_checkbox.checkState() == Qt.Checked)
        self.pngcovers_checkbox.setEnabled(checked and self.blackandwhite_checkbox.checkState() == Qt.Checked)

    def keep_cover_aspect_checkbox_clicked(self, checked):
        self.letterbox_checkbox.setEnabled(checked and self.keep_cover_aspect_checkbox.checkState() == Qt.Checked)
        self.letterbox_colorbutton.setEnabled(checked and self.letterbox_checkbox.checkState() == Qt.Checked)

    def letterbox_checkbox_clicked(self, checked):
        self.letterbox_colorbutton.setEnabled(checked and self.letterbox_checkbox.checkState() == Qt.Checked)



class RemoveCoverOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:remove cover settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "RemoveCovers"

        self.initialize_controls()

        self.options = gprefs.get(self.unique_pref_name+':settings', {})

        remove_fullsize_covers = self.options.get(cfg.KEY_REMOVE_FULLSIZE_COVERS, False)
        self.remove_fullsize_covers_checkbox.setCheckState(Qt.Checked if remove_fullsize_covers else Qt.Unchecked)
        kepub_covers = self.options.get(cfg.KEY_COVERS_UPDLOAD_KEPUB, False)
        self.kepub_covers_checkbox.setCheckState(Qt.Checked if kepub_covers else Qt.Unchecked)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'default_cover.png', _("Remove Covers"))
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("Remove Covers"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        self.remove_fullsize_covers_checkbox = QCheckBox(_("Remove full size covers"), self)
        self.remove_fullsize_covers_checkbox.setToolTip(_("Check this if you want to remove just the full size cover from the device. This will save space, but, if covers are used for the sleep screen, they will not look very good."))
        options_layout.addWidget(self.remove_fullsize_covers_checkbox, 0, 0, 1, 1)

        self.kepub_covers_checkbox = QCheckBox(_("Remove covers for Kobo epubs"), self)
        self.kepub_covers_checkbox.setToolTip(_("Check this if you want to remove covers for any Kobo epubs synced from the Kobo server."))
        options_layout.addWidget(self.kepub_covers_checkbox, 2, 0, 1, 1)

        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):

        self.options[cfg.KEY_REMOVE_FULLSIZE_COVERS] = self.remove_fullsize_covers_checkbox.checkState() == Qt.Checked
        self.options[cfg.KEY_COVERS_UPDLOAD_KEPUB] = self.kepub_covers_checkbox.checkState() == Qt.Checked

        gprefs.set(self.unique_pref_name+':settings', self.options)
        self.accept()


class BlockAnalyticsOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:block analytics settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "BlockAnalyticsEvents"

        self.initialize_controls()

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Block Analytics')
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("AnalyticsEvents Database Trigger"), self)
        options_group.setToolTip(_("When an entry is added to the AnalyticsEvents, it will be removed."))
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        self.create_trigger_radiobutton = QRadioButton(_("Create or change trigger"), self)
        self.create_trigger_radiobutton.setToolTip(_("To create or change the trigger, select this option."))
        options_layout.addWidget(self.create_trigger_radiobutton, 1, 0, 1, 1)

        self.delete_trigger_radiobutton = QRadioButton(_("Delete trigger"), self)
        self.delete_trigger_radiobutton.setToolTip(_("This will remove the existing trigger and let the device work as Kobo intended it."))
        options_layout.addWidget(self.delete_trigger_radiobutton, 1, 1, 1, 1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):
        self.options = {}
        self.options[cfg.KEY_CREATE_ANALYTICSEVENTS_TRIGGER] = self.create_trigger_radiobutton.isChecked()
        self.options[cfg.KEY_DELETE_ANALYTICSEVENTS_TRIGGER] = self.delete_trigger_radiobutton.isChecked()

        # Only if the user has checked at least one option will we continue
        for key in self.options:
            if self.options[key]:
                self.accept()
                return
        return error_dialog(self,
                            _('No options selected'),
                            _('You must select at least one option to continue.'),
                            show=True, show_copy_button=False
                            )


class CleanImagesDirOptionsDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:clean images dir settings dialog')
        self.plugin_action = plugin_action
        self.help_anchor   = "CleanImagesDir"

        self.initialize_controls()

        self.options = gprefs.get(self.unique_pref_name+':settings', {})

        delete_extra_covers = self.options.get('delete_extra_covers', False)
        self.delete_extra_covers_checkbox.setCheckState(Qt.Checked if delete_extra_covers else Qt.Unchecked)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/icon.png', 'Clean Images Directory')
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("Clean Images"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)
        self.delete_extra_covers_checkbox = QCheckBox(_("Delete extra cover image files"), self)
        self.delete_extra_covers_checkbox.setToolTip(_("Check this if you want to delete the extra cover image files from the images directory on the device."))
        options_layout.addWidget(self.delete_extra_covers_checkbox, 0, 0, 1, 1)

        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):

        self.options['delete_extra_covers'] = self.delete_extra_covers_checkbox.checkState() == Qt.Checked

        gprefs.set(self.unique_pref_name+':settings', self.options)
        self.accept()


class LockSeriesDialog(SizePersistedDialog):

    def __init__(self, parent, title, initial_value):
        SizePersistedDialog.__init__(self, parent, 'Manage Series plugin:lock series dialog')
        self.initialize_controls(title, initial_value)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self, title, initial_value):
        self.setWindowTitle(_("Lock Series Index"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/lock32.png', 'Lock Series Index')
        layout.addLayout(title_layout)

        layout.addSpacing(10)
        self.title_label = QLabel('Series index for book: \'%s\''%title, self)
        layout.addWidget(self.title_label)

        hlayout = QHBoxLayout()
        layout.addLayout(hlayout)

        self.value_spinbox = QDoubleSpinBox(self)
        self.value_spinbox.setRange(0, 99000000)
        self.value_spinbox.setDecimals(2)
        self.value_spinbox.setValue(initial_value)
        self.value_spinbox.selectAll()
        hlayout.addWidget(self.value_spinbox, 0)
        hlayout.addStretch(1)

        self.assign_same_checkbox = QCheckBox(_("&Assign this index value to all remaining books"), self)
        layout.addWidget(self.assign_same_checkbox)
        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_value(self):
        return float(unicode(self.value_spinbox.value()))

    def assign_same_value(self):
        return self.assign_same_checkbox.isChecked()

class TitleWidgetItem(QTableWidgetItem):

    def __init__(self, book):
        if isinstance(book, SeriesBook):
            super(TitleWidgetItem, self).__init__(book.title())
            self.title_sort = book.title()
            if not book.is_valid():
                self.setIcon(get_icon('dialog_warning.png'))
                self.setToolTip(_("You have conflicting or out of sequence series indexes"))
            elif book.id() is None:
                self.setIcon(get_icon('add_book.png'))
                self.setToolTip(_("Empty book added to series"))
            elif book.is_title_changed() or book.is_pubdate_changed() or book.is_series_changed():
                self.setIcon(get_icon('format-list-ordered.png'))
                self.setToolTip(_("The book data has been changed"))
            else:
                self.setIcon(get_icon('ok.png'))
                self.setToolTip(_("The series data is unchanged"))
        else:
            super(TitleWidgetItem, self).__init__(book.title)
            self.title_sort = book.title_sort

    def __lt__(self, other):
        return (self.title_sort < other.title_sort)


class AuthorsTableWidgetItem(ReadOnlyTableWidgetItem):

    def __init__(self, authors, author_sort=None):
        text = ' & '.join(authors)
        ReadOnlyTableWidgetItem.__init__(self, text)
#        self.setTextColor(Qt.darkGray)
        self.setForeground(Qt.darkGray)
        self.author_sort = author_sort

    def __lt__(self, other):
        return (self.author_sort < other.author_sort)


class SeriesTableWidgetItem(ReadOnlyTableWidgetItem):

    def __init__(self, series_name, series_index, is_original=False, assigned_index=None):
        if series_name:
            text = '%s [%s]' % (series_name, series_index)
            text = '%s - %s' % (series_name, series_index)
#            text = '%s [%s]' % (series_name, fmt_sidx(series_index))
#            text = '%s - %s' % (series_name, fmt_sidx(series_index))
        else:
            text = ''
        ReadOnlyTableWidgetItem.__init__(self, text)
        if assigned_index is not None:
            self.setIcon(get_icon('images/lock.png'))
            self.setToolTip(_("Value assigned by user"))
        if is_original:
            self.setForeground(Qt.darkGray)


class SeriesColumnComboBox(QComboBox):

    def __init__(self, parent, series_columns):
        QComboBox.__init__(self, parent)
        self.series_columns = series_columns
        for key, column in series_columns.items():
            self.addItem('%s (%s)'% (key, column['name']))
        self.insertItem(0, 'Series')

    def select_text(self, selected_key):
        if selected_key == 'Series':
            self.setCurrentIndex(0)
        else:
            for idx, key in enumerate(self.seriesColumns.keys()):
                if key == selected_key:
                    self.setCurrentIndex(idx)
                    return

    def selected_value(self):
        if self.currentIndex() == 0:
            return 'Series'
        return list(self.series_columns.keys())[self.currentIndex() - 1]


class SeriesTableWidget(QTableWidget):

    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.create_context_menu()
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDropIndicatorShown(True)
        self.fmt = tweaks['gui_pubdate_display_format']
        if self.fmt is None:
            self.fmt = 'MMM yyyy'

    def create_context_menu(self):
        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.assign_original_index_action = QAction(_("Lock original series index"), self)
        self.assign_original_index_action.setIcon(get_icon('images/lock.png'))
        self.assign_original_index_action.triggered.connect(self.parent().assign_original_index)
        self.addAction(self.assign_original_index_action)
        self.assign_index_action = QAction(_("Lock series index..."), self)
        self.assign_index_action.setIcon(get_icon('images/lock.png'))
        self.assign_index_action.triggered.connect(self.parent().assign_index)
        self.addAction(self.assign_index_action)
        self.clear_index_action = QAction(_("Unlock series index"), self)
        self.clear_index_action.setIcon(get_icon('images/lock_delete.png'))
        self.clear_index_action.triggered.connect(partial(self.parent().clear_index, all_rows=False))
        self.addAction(self.clear_index_action)
        self.clear_all_index_action = QAction(_("Unlock all series index"), self)
        self.clear_all_index_action.setIcon(get_icon('images/lock_open.png'))
        self.clear_all_index_action.triggered.connect(partial(self.parent().clear_index, all_rows=True))
        self.addAction(self.clear_all_index_action)
        sep2 = QAction(self)
        sep2.setSeparator(True)
        self.addAction(sep2)
        for name in ['PubDate', 'Original Series Index', 'Original Series Name']:
            sort_action = QAction('Sort by '+name, self)
            sort_action.setIcon(get_icon('images/sort.png'))
            sort_action.triggered.connect(partial(self.parent().sort_by, name))
            self.addAction(sort_action)
        sep3 = QAction(self)
        sep3.setSeparator(True)
        self.addAction(sep3)
        for name, icon in [('FantasticFiction', 'images/ms_ff.png'),
                           ('Goodreads', 'images/ms_goodreads.png'),
                           ('Google', 'images/ms_google.png'),
                           ('Wikipedia', 'images/ms_wikipedia.png')]:
            menu_action = QAction('Search %s' % name, self)
            menu_action.setIcon(get_icon(icon))
            menu_action.triggered.connect(partial(self.parent().search_web, name))
            self.addAction(menu_action)

    def populate_table(self, books):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(books))
        header_labels = ['Title', 'Author(s)', 'PubDate', 'Series', 'New Series']
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(True)

        for row, book in enumerate(books):
            self.populate_table_row(row, book)

        self.resizeColumnToContents(0)
        self.setMinimumColumnWidth(0, 150)
        self.setColumnWidth(1, 100)
        self.resizeColumnToContents(2)
        self.setMinimumColumnWidth(2, 60)
        self.resizeColumnToContents(3)
        self.setMinimumColumnWidth(3, 120)
        self.setSortingEnabled(False)
        self.setMinimumSize(550, 0)
        self.selectRow(0)
        delegate = DateDelegate(self, self.fmt, default_to_today=False)
        self.setItemDelegateForColumn(2, delegate)

    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, book):
        self.blockSignals(True)
        self.setItem(row, 0, TitleWidgetItem(book))
        self.setItem(row, 1, AuthorsTableWidgetItem(book.authors()))
        self.setItem(row, 2, DateTableWidgetItem(book.pubdate(), is_read_only=False,
                                                 default_to_today=False, fmt=self.fmt))
        self.setItem(row, 3, SeriesTableWidgetItem(book.orig_series_name(),
#                                                   book.orig_series_index(),
                                                   book.orig_series_index_string(),
                                                   is_original=True))
        self.setItem(row, 4, SeriesTableWidgetItem(book.series_name(),
                                                   book.series_index_string(),
                                                   assigned_index=book.assigned_index()))
        self.blockSignals(False)

    def swap_row_widgets(self, src_row, dest_row):
        self.blockSignals(True)
        self.insertRow(dest_row)
        for col in range(self.columnCount()):
            self.setItem(dest_row, col, self.takeItem(src_row, col))
        self.removeRow(src_row)
        self.blockSignals(False)

    def select_and_scroll_to_row(self, row):
        self.selectRow(row)
        self.scrollToItem(self.currentItem())

    def event_has_mods(self, event=None):
        mods = event.modifiers() if event is not None else \
                QApplication.keyboardModifiers()
        return mods & Qt.ControlModifier or mods & Qt.ShiftModifier

    def mousePressEvent(self, event):
        ep = event.pos()
        if self.indexAt(ep) not in self.selectionModel().selectedIndexes() and \
                event.button() == Qt.LeftButton and not self.event_has_mods():
            self.setDragEnabled(False)
        else:
            self.setDragEnabled(True)
        return QTableWidget.mousePressEvent(self, event)

    def dropEvent(self, event):
        rows = self.selectionModel().selectedRows()
        selrows = []
        for row in rows:
            selrows.append(row.row())
        selrows.sort()
        drop_row = self.rowAt(event.pos().y())
        if drop_row == -1:
            drop_row = self.rowCount() - 1
        rows_before_drop = [idx for idx in selrows if idx < drop_row]
        rows_after_drop = [idx for idx in selrows if idx >= drop_row]

        dest_row = drop_row
        for selrow in rows_after_drop:
            dest_row += 1
            self.swap_row_widgets(selrow + 1, dest_row)
            book = self.parent().books.pop(selrow)
            self.parent().books.insert(dest_row, book)

        dest_row = drop_row + 1
        for selrow in reversed(rows_before_drop):
            self.swap_row_widgets(selrow, dest_row)
            book = self.parent().books.pop(selrow)
            self.parent().books.insert(dest_row - 1, book)
            dest_row = dest_row - 1

        event.setDropAction(Qt.CopyAction)
        # Determine the new row selection
        self.selectRow(drop_row)
        self.parent().renumber_series()

    def set_series_column_headers(self, text):
        item = self.horizontalHeaderItem(3)
        if item is not None:
            item.setText('Original '+text)
        item = self.horizontalHeaderItem(4)
        if item is not None:
            item.setText('New '+text)


class ManageSeriesDeviceDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action, books, all_series, series_columns):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:series dialog')
        self.plugin_action = plugin_action
        self.db = self.parent().library_view.model().db
        self.books = books
        self.all_series = all_series
        self.series_columns = series_columns
        self.block_events = True

        self.initialize_controls()

        # Books will have been sorted by the Calibre series column
        # Choose the appropriate series column to be editing
        initial_series_column = 'Series'
        self.series_column_combo.select_text(initial_series_column)
        if len(series_columns) == 0:
            # Will not have fired the series_column_changed event
            self.series_column_changed()
        # Renumber the books using the assigned series name/index in combos/spinbox
        self.renumber_series(display_in_table=False)

        # Display the books in the table
        self.block_events = False
        self.series_table.populate_table(books)
        if len(unicode(self.series_combo.text()).strip()) > 0:
            self.series_table.setFocus()
        else:
            self.series_combo.setFocus()
        self.update_series_headers(initial_series_column)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(_("Manage Series"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/manage_series.png', 'Manage Series on Device')
        layout.addLayout(title_layout)

        # Series name and start index layout
        series_name_layout = QHBoxLayout()
        layout.addLayout(series_name_layout)

        series_column_label = QLabel(_("Series &Column:"), self)
        series_name_layout.addWidget(series_column_label)
        self.series_column_combo = SeriesColumnComboBox(self, self.series_columns)
        self.series_column_combo.currentIndexChanged[int].connect(self.series_column_changed)
        series_name_layout.addWidget(self.series_column_combo)
        series_column_label.setBuddy(self.series_column_combo)
        series_name_layout.addSpacing(20)

        series_label = QLabel(_("Series &Name:"), self)
        series_name_layout.addWidget(series_label)
        self.series_combo = EditWithComplete(self)
        self.series_combo.setEditable(True)
        self.series_combo.setInsertPolicy(QComboBox.InsertAlphabetically)
        self.series_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.series_combo.setMinimumContentsLength(25)
        self.series_combo.currentIndexChanged[int].connect(self.series_changed)
        self.series_combo.editTextChanged.connect(self.series_changed)
        self.series_combo.set_separator(None)
        series_label.setBuddy(self.series_combo)
        series_name_layout.addWidget(self.series_combo)
        series_name_layout.addSpacing(20)
        series_start_label = QLabel(_("&Start At:"), self)
        series_name_layout.addWidget(series_start_label)
        self.series_start_number = QSpinBox(self)
        self.series_start_number.setRange(0, 99000000)
        self.series_start_number.valueChanged[int].connect(self.series_start_changed)
        series_name_layout.addWidget(self.series_start_number)
        series_start_label.setBuddy(self.series_start_number)
        series_name_layout.insertStretch(-1)

        # Series name and start index layout
        formatting_layout = QHBoxLayout()
        layout.addLayout(formatting_layout)

        self.clean_title_checkbox = QCheckBox(_("Clean titles of Kobo books"), self)
        formatting_layout.addWidget(self.clean_title_checkbox)
        self.clean_title_checkbox.setToolTip(_("Removes series information from the titles. For Kobo books, this is '(Series Name - #1)'"))
        self.clean_title_checkbox.clicked.connect(self.clean_title_checkbox_clicked)

        # Main series table layout
        table_layout = QHBoxLayout()
        layout.addLayout(table_layout)

        self.series_table = SeriesTableWidget(self)
        self.series_table.itemSelectionChanged.connect(self.item_selection_changed)
        self.series_table.cellChanged[int,int].connect(self.cell_changed)

        table_layout.addWidget(self.series_table)
        table_button_layout = QVBoxLayout()
        table_layout.addLayout(table_button_layout)
        move_up_button = QToolButton(self)
        move_up_button.setToolTip(_("Move book up in series (Alt+Up)"))
        move_up_button.setIcon(get_icon('arrow-up.png'))
        move_up_button.setShortcut(_('Alt+Up'))
        move_up_button.clicked.connect(self.move_rows_up)
        table_button_layout.addWidget(move_up_button)
        move_down_button = QToolButton(self)
        move_down_button.setToolTip(_("Move book down in series (Alt+Down)"))
        move_down_button.setIcon(get_icon('arrow-down.png'))
        move_down_button.setShortcut(_('Alt+Down'))
        move_down_button.clicked.connect(self.move_rows_down)
        table_button_layout.addWidget(move_down_button)
        spacerItem1 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        table_button_layout.addItem(spacerItem1)
        assign_index_button = QToolButton(self)
        assign_index_button.setToolTip(_("Lock to index value..."))
        assign_index_button.setIcon(get_icon('images/lock.png'))
        assign_index_button.clicked.connect(self.assign_index)
        table_button_layout.addWidget(assign_index_button)
        clear_index_button = QToolButton(self)
        clear_index_button.setToolTip(_("Unlock series index"))
        clear_index_button.setIcon(get_icon('images/lock_delete.png'))
        clear_index_button.clicked.connect(self.clear_index)
        table_button_layout.addWidget(clear_index_button)
        spacerItem2 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        table_button_layout.addItem(spacerItem2)
        delete_button = QToolButton(self)
        delete_button.setToolTip(_("Remove book from the series list"))
        delete_button.setIcon(get_icon('trash.png'))
        delete_button.clicked.connect(self.remove_book)
        table_button_layout.addWidget(delete_button)
        spacerItem3 = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        table_button_layout.addItem(spacerItem3)
        move_left_button = QToolButton(self)
        move_left_button.setToolTip(_("Move series index to left of decimal point (Alt+Left)"))
        move_left_button.setIcon(get_icon('back.png'))
        move_left_button.setShortcut(_('Alt+Left'))
        move_left_button.clicked.connect(partial(self.series_indent_change, -1))
        table_button_layout.addWidget(move_left_button)
        move_right_button = QToolButton(self)
        move_right_button.setToolTip(_("Move series index to right of decimal point (Alt+Right)"))
        move_right_button.setIcon(get_icon('forward.png'))
        move_right_button.setShortcut(_('Alt+Right'))
        move_right_button.clicked.connect(partial(self.series_indent_change, 1))
        table_button_layout.addWidget(move_right_button)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        keep_button = button_box.addButton(_(" &Restore Original Series "), QDialogButtonBox.ResetRole)
        keep_button.clicked.connect(self.restore_original_series)

    def reject(self):
        debug_print("ManageSeriesDeviceDialog:reject")
        for book in self.books:
            book.revert_changes()
        super(ManageSeriesDeviceDialog, self).reject()

    def series_column_changed(self):
        debug_print("series_column_changed - start")
        series_column = self.series_column_combo.selected_value()
        SeriesBook.series_column = series_column
        # Choose a series name and series index from the first book in the list
        initial_series_name = ''
        initial_series_index = 1
        if len(self.books) > 0:
            first_book = self.books[0]
            initial_series_name = first_book.series_name()
            debug_print("series_column_changed - initial_series_name='%s'" % initial_series_name)
            if initial_series_name is not None:
                debug_print("series_column_changed first_book.series_index()='%s'" % first_book.series_index())
                try:
                    initial_series_index = int(first_book.series_index())
                except:
                    initial_series_index = 1
        # Populate the series name combo as appropriate for that column
        self.initialize_series_name_combo(series_column, initial_series_name)
        # Populate the series index spinbox with the initial value
        self.series_start_number.setProperty('value', initial_series_index)
        self.update_series_headers(series_column)
        if self.block_events:
            return
        self.renumber_series()

    def update_series_headers(self, series_column):
        if series_column == 'Series':
            self.series_table.set_series_column_headers(series_column)
        else:
            header_text = self.series_columns[series_column]['name']
            self.series_table.set_series_column_headers(header_text)

    def initialize_series_name_combo(self, series_column, series_name):
        self.series_combo.clear()
        if series_name is None:
            series_name = ''
        values = self.all_series
        if series_column == 'Series':
            self.series_combo.update_items_cache([x[1] for x in values])
            for i in values:
                _id, name = i
                self.series_combo.addItem(name)
        else:
            label = self.db.field_metadata.key_to_label(series_column)
            values = list(self.db.all_custom(label=label))
            values.sort(key=sort_key)
            self.series_combo.update_items_cache(values)
            for name in values:
                self.series_combo.addItem(name)
        self.series_combo.setEditText(series_name)

    def series_changed(self):
        if self.block_events:
            return
        self.renumber_series()

    def series_start_changed(self):
        if self.block_events:
            return
        self.renumber_series()

    def restore_original_series(self):
        # Go through the books and overwrite the indexes with the originals, fixing in place
        for book in self.books:
            if book.orig_series_index():
                book.set_assigned_index(book.orig_series_index())
                book.set_series_name(book.orig_series_name())
                book.set_series_index(book.orig_series_index())
        # Now renumber the whole series so that anything in between gets changed
        self.renumber_series()

    def clean_title(self, remove_series):
        # Go through the books and clean the Kobo series from the title
        for book in self.books:
            if remove_series:
                series_in_title = re.findall(r"\(.*\)", book._orig_title)
                if len(series_in_title) > 0:
                    book._mi.title = book._orig_title.replace(series_in_title[len(series_in_title) - 1], "")
            else:
                book._mi.title = book._orig_title
        # Now renumber the whole series so that anything in between gets changed
        self.renumber_series()

    def clean_title_checkbox_clicked(self, checked):
#        self.clean_title = checked
        self.clean_title(checked)

    def renumber_series(self, display_in_table=True):
        if len(self.books) == 0:
            return
        series_name = unicode(self.series_combo.currentText()).strip()
        series_index = float(unicode(self.series_start_number.value()))
        last_series_indent = 0
        for row, book in enumerate(self.books):
            book.set_series_name(series_name)
            series_indent = book.series_indent()
            if book.assigned_index() is not None:
                series_index = book.assigned_index()
            else:
                if series_indent >= last_series_indent:
                    if series_indent == 0:
                        if row > 0:
                            series_index += 1.
                    elif series_indent == 1:
                        series_index += 0.1
                    else:
                        series_index += 0.01
                else:
                    # When series indent decreases, need to round to next
                    if series_indent == 1:
                        series_index = round(series_index + 0.05, 1)
                    else: # series_indent == 0:
                        series_index = round(series_index + 0.5, 0)
            book.set_series_index(series_index)
            last_series_indent = series_indent
        # Now determine whether books have a valid index or not
        self.books[0].set_is_valid(True)
        for row in range(len(self.books)-1, 0, -1):
            book = self.books[row]
            previous_book = self.books[row-1]
            if book.series_index() <= previous_book.series_index():
                book.set_is_valid(False)
            else:
                book.set_is_valid(True)
        if display_in_table:
            for row, book in enumerate(self.books):
                self.series_table.populate_table_row(row, book)

    def assign_original_index(self):
        if len(self.books) == 0:
            return
        for row in self.series_table.selectionModel().selectedRows():
            book = self.books[row.row()]
            book.set_assigned_index(book.orig_series_index())
        self.renumber_series()
        self.item_selection_changed()

    def assign_index(self):
        if len(self.books) == 0:
            return
        auto_assign_value = None
        for row in self.series_table.selectionModel().selectedRows():
            book = self.books[row.row()]
            if auto_assign_value is not None:
                book.set_assigned_index(auto_assign_value)
                continue

            d = LockSeriesDialog(self, book.title(), book.series_index())
            d.exec_()
            if d.result() != d.Accepted:
                break
            if d.assign_same_value():
                auto_assign_value = d.get_value()
                book.set_assigned_index(auto_assign_value)
            else:
                book.set_assigned_index(d.get_value())

        self.renumber_series()
        self.item_selection_changed()

    def clear_index(self, all_rows=False):
        if len(self.books) == 0:
            return
        if all_rows:
            for book in self.books:
                book.set_assigned_index(None)
        else:
            for row in self.series_table.selectionModel().selectedRows():
                book = self.books[row.row()]
                book.set_assigned_index(None)
        self.renumber_series()

    def remove_book(self):
        if not question_dialog(self, _("Are you sure?"), '<p>'+
                _("Remove the selected book(s) from the series list?"), show_copy_button=False):
            return
        rows = self.series_table.selectionModel().selectedRows()
        if len(rows) == 0:
            return
        selrows = []
        for row in rows:
            selrows.append(row.row())
        selrows.sort()
        first_sel_row = self.series_table.currentRow()
        for row in reversed(selrows):
            self.books.pop(row)
            self.series_table.removeRow(row)
        if first_sel_row < self.series_table.rowCount():
            self.series_table.select_and_scroll_to_row(first_sel_row)
        elif self.series_table.rowCount() > 0:
            self.series_table.select_and_scroll_to_row(first_sel_row - 1)
        self.renumber_series()

    def move_rows_up(self):
        self.series_table.setFocus()
        rows = self.series_table.selectionModel().selectedRows()
        if len(rows) == 0:
            return
        first_sel_row = rows[0].row()
        if first_sel_row <= 0:
            return
        # Workaround for strange selection bug in Qt which "alters" the selection
        # in certain circumstances which meant move down only worked properly "once"
        selrows = []
        for row in rows:
            selrows.append(row.row())
        selrows.sort()
        for selrow in selrows:
            self.series_table.swap_row_widgets(selrow - 1, selrow + 1)
            self.books[selrow-1], self.books[selrow] = self.books[selrow], self.books[selrow-1]

        scroll_to_row = first_sel_row - 1
        if scroll_to_row > 0:
            scroll_to_row = scroll_to_row - 1
        self.series_table.scrollToItem(self.series_table.item(scroll_to_row, 0))
        self.renumber_series()

    def move_rows_down(self):
        self.series_table.setFocus()
        rows = self.series_table.selectionModel().selectedRows()
        if len(rows) == 0:
            return
        last_sel_row = rows[-1].row()
        if last_sel_row == self.series_table.rowCount() - 1:
            return
        # Workaround for strange selection bug in Qt which "alters" the selection
        # in certain circumstances which meant move down only worked properly "once"
        selrows = []
        for row in rows:
            selrows.append(row.row())
        selrows.sort()
        for selrow in reversed(selrows):
            self.series_table.swap_row_widgets(selrow + 2, selrow)
            self.books[selrow+1], self.books[selrow] = self.books[selrow], self.books[selrow+1]

        scroll_to_row = last_sel_row + 1
        if scroll_to_row < self.series_table.rowCount() - 1:
            scroll_to_row = scroll_to_row + 1
        self.series_table.scrollToItem(self.series_table.item(scroll_to_row, 0))
        self.renumber_series()

    def series_indent_change(self, delta):
        for row in self.series_table.selectionModel().selectedRows():
            book = self.books[row.row()]
            series_indent = book.series_indent()
            if delta > 0:
                if series_indent < 2:
                    book.set_series_indent(series_indent+1)
            else:
                if series_indent > 0:
                    book.set_series_indent(series_indent-1)
            book.set_assigned_index(None)
        self.renumber_series()

    def sort_by(self, name):
        if name == 'PubDate':
            self.books = sorted(self.books, key=lambda k: k.sort_key(sort_by_pubdate=True))
        elif name == 'Original Series Name':
            self.books = sorted(self.books, key=lambda k: k.sort_key(sort_by_name=True))
        else:
            self.books = sorted(self.books, key=lambda k: k.sort_key())
        self.renumber_series()

    def search_web(self, name):
        URLS =  {
                'FantasticFiction': 'http://www.fantasticfiction.co.uk/search/?searchfor=author&keywords={author}',
                'Goodreads': 'http://www.goodreads.com/search/search?q={author}&search_type=books',
                'Google': 'http://www.google.com/#sclient=psy&q=%22{author}%22+%22{title}%22',
                'Wikipedia': 'http://en.wikipedia.org/w/index.php?title=Special%3ASearch&search={author}'
                }
        for row in self.series_table.selectionModel().selectedRows():
            book = self.books[row.row()]
            safe_title = self.convert_to_search_text(book.title())
            safe_author = self.convert_author_to_search_text(book.authors()[0])
            url = URLS[name].replace('{title}', safe_title).replace('{author}', safe_author)
            open_url(QUrl.fromEncoded(url))

    def convert_to_search_text(self, text, encoding='utf-8'):
        # First we strip characters we will definitely not want to pass through.
        # Periods from author initials etc do not need to be supplied
        text = text.replace('.', '')
        # Now encode the text using Python function with chosen encoding
        text = quote_plus(text.encode(encoding, 'ignore'))
        # If we ended up with double spaces as plus signs (++) replace them
        text = text.replace('++','+')
        return text

    def convert_author_to_search_text(self, author, encoding='utf-8'):
        # We want to convert the author name to FN LN format if it is stored LN, FN
        # We do this because some websites (Kobo) have crappy search engines that
        # will not match Adams+Douglas but will match Douglas+Adams
        # Not really sure of the best way of determining if the user is using LN, FN
        # Approach will be to check the tweak and see if a comma is in the name

        # Comma separated author will be pipe delimited in Calibre database
        fn_ln_author = author
        if author.find(',') > -1:
            # This might be because of a FN LN,Jr - check the tweak
            sort_copy_method = tweaks['author_sort_copy_method']
            if sort_copy_method == 'invert':
                # Calibre default. Hence "probably" using FN LN format.
                fn_ln_author = author
            else:
                # We will assume that we need to switch the names from LN,FN to FN LN
                parts = author.split(',')
                surname = parts.pop(0)
                parts.append(surname)
                fn_ln_author = ' '.join(parts).strip()
        return self.convert_to_search_text(fn_ln_author, encoding)

    def cell_changed(self, row, column):
        book = self.books[row]
        if column == 0:
            book.set_title(unicode(self.series_table.item(row, column).text()).strip())
        elif column == 2:
            qtdate = convert_qvariant(self.series_table.item(row, column).data(Qt.DisplayRole))
            book.set_pubdate(qt_to_dt(qtdate, as_utc=False))

    def item_selection_changed(self):
        row = self.series_table.currentRow()
        if row == -1:
            return
        has_assigned_index = False
        for row in self.series_table.selectionModel().selectedRows():
            book = self.books[row.row()]
            if book.assigned_index():
                has_assigned_index = True
        self.series_table.clear_index_action.setEnabled(has_assigned_index)
        if not has_assigned_index:
            for book in self.books:
                if book.assigned_index():
                    has_assigned_index = True
        self.series_table.clear_all_index_action.setEnabled(has_assigned_index)

class BooksNotInDeviceDatabaseTableWidget(QTableWidget):

    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.fmt = tweaks['gui_pubdate_display_format']
        if self.fmt is None:
            self.fmt = 'MMM yyyy'

    def populate_table(self, books):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(books))
        header_labels = [_('Title'), _('Author(s)'), _('File Path'), _('PubDate'), _('File Timestamp')]
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(True)

        for row, book in enumerate(books):
            self.populate_table_row(row, book)

        self.resizeColumnToContents(0)
        self.setMinimumColumnWidth(0, 150)
        self.setColumnWidth(1, 100)
        self.resizeColumnToContents(2)
        self.setMinimumColumnWidth(2, 200)
        self.setSortingEnabled(True)
        self.setMinimumSize(550, 0)
        self.selectRow(0)
        delegate = DateDelegate(self, self.fmt, default_to_today=False)
        self.setItemDelegateForColumn(3, delegate)


    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, book):
        self.blockSignals(True)
        titleColumn = TitleWidgetItem(book)
        titleColumn.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
        self.setItem(row, 0, titleColumn)
        authorColumn = AuthorsTableWidgetItem(book.authors, book.author_sort)
        self.setItem(row, 1, authorColumn)
        pathColumn = QTableWidgetItem(book.path)
        pathColumn.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
        self.setItem(row, 2, pathColumn)
        self.setItem(row, 3, DateTableWidgetItem(book.pubdate, is_read_only=True,
                                                 default_to_today=False, fmt=self.fmt))
        self.setItem(row, 4, DateTableWidgetItem(datetime(book.datetime[0], book.datetime[1], book.datetime[2], book.datetime[3], book.datetime[4], book.datetime[5], book.datetime[6], utc_tz), 
                                                 is_read_only=True, default_to_today=False))
        self.blockSignals(False)


class ShowBooksNotInDeviceDatabaseDialog(SizePersistedDialog):

    def __init__(self, parent, books):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:not in device database dialog')
        self.db = self.parent().library_view.model().db
        self.books = books
        self.block_events = True

        self.initialize_controls()

        # Display the books in the table
        self.block_events = False
        self.books_table.populate_table(books)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(_("Books not in Device Database"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/manage_series.png', 'Books not in Device Database')
        layout.addLayout(title_layout)

        # Main series table layout
        table_layout = QHBoxLayout()
        layout.addLayout(table_layout)

        self.books_table = BooksNotInDeviceDatabaseTableWidget(self)
        table_layout.addWidget(self.books_table)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

    def sort_by(self, name):
        if name == 'PubDate':
            self.books = sorted(self.books, key=lambda k: k.sort_key(sort_by_pubdate=True))


class ShowReadingPositionChangesDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action, reading_locations, db, profileName, goodreads_sync_installed=False):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:show reading position changes dialog')
        self.plugin_action      = plugin_action
        self.reading_locations, self.options  = reading_locations
        self.block_events       = True
        self.help_anchor        = "ShowReadingPositionChanges"
        self.db                 = db

        self.profileName = self.plugin_action.current_device_profile['profileName'] if not profileName else profileName
        self.deviceName = cfg.get_device_name(self.plugin_action.device_uuid)
        self.options = cfg.get_plugin_prefs(cfg.READING_POSITION_CHANGES_STORE_NAME)
        library_config = cfg.get_library_config(self.plugin_action.gui.current_db)
        self.options = library_config.get(cfg.READING_POSITION_CHANGES_STORE_NAME, cfg.READING_POSITION_CHANGES_DEFAULTS)

        self.initialize_controls()

        # Display the books in the table
        self.block_events = False
        self.reading_locations_table.populate_table(self.reading_locations)
        
        self.select_books_checkbox.setChecked(self.options.get(cfg.KEY_SELECT_BOOKS_IN_LIBRARY, cfg.READING_POSITION_CHANGES_DEFAULTS[cfg.KEY_SELECT_BOOKS_IN_LIBRARY]))
        update_goodreads_progress = self.options.get(cfg.KEY_UPDATE_GOODREADS_PROGRESS, cfg.READING_POSITION_CHANGES_DEFAULTS[cfg.KEY_UPDATE_GOODREADS_PROGRESS])
        self.update_goodreads_progress_checkbox.setChecked(update_goodreads_progress)
        if goodreads_sync_installed:
            self.update_goodreads_progress_checkbox_clicked(update_goodreads_progress)
        else:
            self.update_goodreads_progress_checkbox.setEnabled(False)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(_("Show Reading Position Changes"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/manage_series.png', 'Show Reading Position Changes')
        layout.addLayout(title_layout)

        # Main series table layout
        table_layout = QGridLayout()
        layout.addLayout(table_layout)

        table_layout.addWidget(QLabel(_("Profile: {0}").format(self.profileName)), 0, 0, 1, 1)
        table_layout.addWidget(QLabel(_("Device: {0}").format(self.deviceName)), 0, 2, 1, 1)

        self.reading_locations_table = ShowReadingPositionChangesTableWidget(self, self.db)
        table_layout.addWidget(self.reading_locations_table, 1, 0, 1, 4)

        self.select_books_checkbox = QCheckBox(_('Select updated books in library'))
        table_layout.addWidget(self.select_books_checkbox, 2, 0, 1, 2)

        self.update_goodreads_progress_checkbox = QCheckBox(_('Update Goodread reading progress'))
        self.update_goodreads_progress_checkbox.clicked.connect(self.update_goodreads_progress_checkbox_clicked)
        table_layout.addWidget(self.update_goodreads_progress_checkbox, 2, 1, 1, 2)


        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._ok_clicked)
        button_box.rejected.connect(self.reject)
#         self.select_all_button = button_box.addButton(_("Select all"), QDialogButtonBox.ResetRole)
#         self.select_all_button.setToolTip(_("Select all books to add them to the calibre library."))
#         self.select_all_button.clicked.connect(self._select_all_clicked)
        self.select_all_button = button_box.addButton(_('Select all'), QDialogButtonBox.ResetRole)
#         self.clear_all_button.setObjectName('toggle_checkmarks_button')
        self.select_all_button.clicked.connect(self._select_all_clicked)
        self.clear_all_button = button_box.addButton(_('Clear all'), QDialogButtonBox.ResetRole)
#         self.clear_all_button.setObjectName('toggle_checkmarks_button')
        self.clear_all_button.clicked.connect(self._clear_all_clicked)
        
        layout.addWidget(button_box)

    def _ok_clicked(self):
        self.prefs = cfg.READING_POSITION_CHANGES_DEFAULTS
        self.prefs[cfg.KEY_SELECT_BOOKS_IN_LIBRARY]   = self.select_books_checkbox.checkState() == Qt.Checked
        self.prefs[cfg.KEY_UPDATE_GOODREADS_PROGRESS] = self.update_goodreads_progress_checkbox.checkState() == Qt.Checked

        library_config = cfg.get_library_config(self.plugin_action.gui.current_db)
        library_config[cfg.READING_POSITION_CHANGES_STORE_NAME] = self.prefs
        cfg.set_library_config(self.plugin_action.gui.current_db, library_config)

        for i in range(len(self.reading_locations)):
            self.reading_locations_table.selectRow(i)
            enabled = bool(self.reading_locations_table.item(i, 0).checkState())
            debug_print("ShowReadingPositionChangesDialog:_ok_clicked - row=%d, enabled=%s" % (i, enabled))
            if not enabled:
                book_id = convert_qvariant(self.reading_locations_table.item(i, 7).data(Qt.DisplayRole))
                debug_print("ShowReadingPositionChangesDialog:_ok_clicked - row=%d, book_id=%s" % (i, book_id))
                del self.reading_locations[book_id]
        self.accept()
        return

    def sort_by(self, name):
        if name == 'PubDate':
            self.shelves = sorted(self.shelves, key=lambda k: k.sort_key(sort_by_pubdate=True))

    def _select_all_clicked(self):
        self.reading_locations_table.toggle_checkmarks(Qt.Checked)

    def _clear_all_clicked(self):
        self.reading_locations_table.toggle_checkmarks(Qt.Unchecked)

    def update_goodreads_progress_checkbox_clicked(self, checked):
        self.select_books_checkbox.setEnabled(not checked)

class ShowReadingPositionChangesTableWidget(QTableWidget):

    def __init__(self, parent, db):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.db = db

        self.kobo_chapteridbookmarked_column, self.kobo_percentRead_column, self.rating_column, self.last_read_column = self.parent().plugin_action.get_column_names()
        
    def populate_table(self, reading_positions):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(reading_positions))
        header_labels = ['', _('Title'), _('Authors(s)'), _('Current %'), _('New %'), _('Current Date'), _('New Date'), _("Book ID")]
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(True)

        debug_print("ShowReadingPositionChangesDialog:populate_table - reading_positions=", reading_positions)
        row = 0
        for book_id, reading_position in reading_positions.items():
#            debug_print("ShowReadingPositionChangesDialog:populate_table - reading_position=", reading_position)
            self.populate_table_row(row, book_id, reading_position)
            row += 1

        self.resizeColumnToContents(0)
        self.resizeColumnToContents(1)
        self.setMinimumColumnWidth(1, 150)
        self.setColumnWidth(2, 100)
        self.resizeColumnToContents(3)
        self.resizeColumnToContents(4)
        self.resizeColumnToContents(5)
        self.resizeColumnToContents(6)
        self.hideColumn(7)
        self.setSortingEnabled(True)
#        self.setMinimumSize(550, 0)
        self.selectRow(0)
        delegate = DateDelegate(self, default_to_today=False)
        self.setItemDelegateForColumn(5, delegate)
        self.setItemDelegateForColumn(6, delegate)


    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, book_id, reading_position):
#        debug_print("ShowReadingPositionChangesTableWidget:populate_table_row - shelf:", row, reading_position[0], reading_position[1], reading_position[2], reading_position[3])
        self.blockSignals(True)

        book = self.db.get_metadata(book_id, index_is_id=True, get_cover=False)
#        debug_print("ShowReadingPositionChangesTableWidget:populate_table_row - book_id:", book_id)
#        debug_print("ShowReadingPositionChangesTableWidget:populate_table_row - book.title:", book.title)
#        debug_print("ShowReadingPositionChangesTableWidget:populate_table_row - book:", book)
#        debug_print("ShowReadingPositionChangesTableWidget:populate_table_row - reading_position:", reading_position)

        self.setItem(row, 0, CheckableTableWidgetItem(True))

        titleColumn = QTableWidgetItem(reading_position['Title'])
        titleColumn.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.setItem(row, 1, titleColumn)

        authorColumn = AuthorsTableWidgetItem(book.authors, book.author_sort)
        self.setItem(row, 2, authorColumn)

        current_percentRead = book.get_user_metadata(self.kobo_percentRead_column, True)['#value#'] if self.kobo_percentRead_column else None
        current_percent = RatingTableWidgetItem(current_percentRead, is_read_only=True)
        current_percent.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 3, current_percent)
        
#        debug_print("ShowReadingPositionChangesTableWidget:populate_table_row - reading_position[4]:", reading_position[4])
        new_percentRead = 0 
        if reading_position['ReadStatus'] == 1:
            new_percentRead = reading_position['___PercentRead']
        elif reading_position['ReadStatus'] == 2:
            new_percentRead = 100
        new_percent = RatingTableWidgetItem(new_percentRead, is_read_only=True)
        new_percent.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 4, new_percent)
        
        current_last_read = book.get_user_metadata(self.last_read_column, True)['#value#'] if self.last_read_column else None
        if current_last_read:
            self.setItem(row, 5, DateTableWidgetItem(current_last_read,
                                                     is_read_only=True,
                                                     default_to_today=False))
        self.setItem(row, 6, DateTableWidgetItem(self.parent().plugin_action.convert_kobo_date(reading_position['DateLastRead']), 
                                                 is_read_only=True,
                                                 default_to_today=False))
        book_idColumn = RatingTableWidgetItem(book_id)
        self.setItem(row, 7, book_idColumn)
#        titleColumn.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
        self.blockSignals(False)

    def select_all(self):
        self.selectAll()

    def toggle_checkmarks(self, select):
        for i in range(self.rowCount()):
            self.item(i, 0).setCheckState(select)
#         self.repaint()


class FixDuplicateShelvesDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action, shelves):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:duplicate shelves in device database dialog')
        self.plugin_action = plugin_action
        self.shelves       = shelves
        self.block_events  = True
        self.help_anchor   = "FixDuplicateShelves"
        self.options = {}

        self.initialize_controls()

        # Display the books in the table
        self.block_events = False
        self.shelves_table.populate_table(self.shelves)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(_("Duplicate Shelves in Device Database"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/manage_series.png', _('Duplicate Shelves in Device Database'))
        layout.addLayout(title_layout)

        # Main series table layout
        table_layout = QHBoxLayout()
        layout.addLayout(table_layout)

        self.shelves_table = DuplicateShelvesInDeviceDatabaseTableWidget(self)
        table_layout.addWidget(self.shelves_table)

        options_group = QGroupBox(_("Options"), self)
#        options_group.setToolTip(_("When a tile is added or changed, the database trigger will automatically set them to be dismissed. This will be done for the tile types selected above."))
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        options_layout.addWidget(QLabel(_("Shelf to Keep")), 0, 0, 1, 1)
        self.keep_oldest_radiobutton = QRadioButton(_("Oldest"), self)
#        self.create_trigger_radiobutton.setToolTip(_("To create or change the trigger, select this option."))
        options_layout.addWidget(self.keep_oldest_radiobutton, 0, 1, 1, 1)
        self.keep_oldest_radiobutton.setEnabled(True)

        self.keep_newest_radiobutton = QRadioButton(_("Newest"), self)
#        self.delete_trigger_radiobutton.setToolTip(_("This will remove the existing trigger and let the device work as Kobo intended it."))
        options_layout.addWidget(self.keep_newest_radiobutton, 0, 2, 1, 1)
        self.keep_newest_radiobutton.setEnabled(True)
        self.keep_newest_radiobutton.click()

        self.purge_checkbox = QCheckBox(_("Purge duplicate shelves"), self)
        self.purge_checkbox.setToolTip(_(
                    "When this option is selected, the duplicated rows are deleted from the database. "
                    "If this is done, they might be restore during the next sync to the Kobo server."
                    ))
        options_layout.addWidget(self.purge_checkbox, 0, 3, 1, 1)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _ok_clicked(self):
        self.options = {}

        self.options[cfg.KEY_KEEP_NEWEST_SHELF] = self.keep_newest_radiobutton.isChecked()
        self.options[cfg.KEY_PURGE_SHELVES]     = self.purge_checkbox.checkState() == Qt.Checked

        have_options = self.keep_newest_radiobutton.isChecked() \
                    or self.keep_oldest_radiobutton.isChecked() \
                    or self.purge_checkbox.checkState() == Qt.Checked
        # Only if the user has checked at least one option will we continue
        if have_options:
            debug_print("FixDuplicateShelvesDialog:_ok_clicked - - options=%s" % self.options)
            self.accept()
            return
        return error_dialog(self,
                            _('No options selected'),
                            _('You must select at least one option to continue.'),
                            show=True, show_copy_button=False
                            )

    def sort_by(self, name):
        if name == 'PubDate':
            self.shelves = sorted(self.shelves, key=lambda k: k.sort_key(sort_by_pubdate=True))


class DuplicateShelvesInDeviceDatabaseTableWidget(QTableWidget):

    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
#        self.fmt = tweaks['gui_pubdate_display_format']
#        if self.fmt is None:
#            self.fmt = 'MMM yyyy'

    def populate_table(self, shelves):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(shelves))
        header_labels = [_('Shelf Name'), _('Oldest'), _('Newest'), _('Number'), ]
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(True)

        for row, shelf in enumerate(shelves):
            self.populate_table_row(row, shelf)

        self.resizeColumnToContents(0)
        self.setMinimumColumnWidth(0, 150)
        self.setColumnWidth(1, 150)
        self.resizeColumnToContents(2)
        self.setMinimumColumnWidth(2, 150)
        self.setSortingEnabled(True)
#        self.setMinimumSize(550, 0)
        self.selectRow(0)
        delegate = DateDelegate(self, default_to_today=False)
        self.setItemDelegateForColumn(1, delegate)
        self.setItemDelegateForColumn(2, delegate)


    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, shelf):
#        debug_print("DuplicateShelvesInDeviceDatabaseTableWidget:populate_table_row - shelf:", row, shelf[0], shelf[1], shelf[2], shelf[3])
        self.blockSignals(True)
        shelf_name = shelf[0] if shelf[0] else _("(Unnamed shelf)")
        titleColumn = QTableWidgetItem(shelf_name)
        titleColumn.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
        self.setItem(row, 0, titleColumn)
#        self.setItem(row, 1, QTableWidgetItem(shelf[1]))
#        self.setItem(row, 2, QTableWidgetItem(shelf[2]))
        self.setItem(row, 1, DateTableWidgetItem(shelf[1], is_read_only=True,
                                                 default_to_today=False))
        self.setItem(row, 2, DateTableWidgetItem(shelf[2], 
                                                 is_read_only=True, default_to_today=False))
        shelf_count = RatingTableWidgetItem(shelf[3], is_read_only=True)
        shelf_count.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 3, shelf_count)
        self.blockSignals(False)


class OrderSeriesShelvesDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action, shelves):
        super(OrderSeriesShelvesDialog, self).__init__(parent, 'kobo utilities plugin:order series shelves dialog')
        self.plugin_action = plugin_action
        self.shelves       = shelves
        self.block_events  = True
        self.help_anchor   = "OrderSeriesShelves"

        self.options = cfg.get_plugin_prefs(cfg.ORDERSERIESSHELVES_OPTIONS_STORE_NAME)
        self.initialize_controls()
        self.order_shelves_in = self.options[cfg.KEY_SORT_DESCENDING]
        if self.order_shelves_in:
#            self.descending_radiobutton.click()
            self.order_shelves_in_button_group.button(1).setChecked(True)
        else:
#            self.ascending_radiobutton.click()
            self.order_shelves_in_button_group.button(0).setChecked(True)

        if self.options.get(cfg.KEY_SORT_UPDATE_CONFIG, cfg.ORDERSERIESSHELVES_OPTIONS_DEFAULTS[cfg.KEY_SORT_UPDATE_CONFIG]):
            self.update_config_checkbox.setCheckState(Qt.Checked)

        self.order_shelves_type = self.options.get(cfg.KEY_ORDER_SHELVES_TYPE, cfg.ORDERSERIESSHELVES_OPTIONS_DEFAULTS[cfg.KEY_ORDER_SHELVES_TYPE])
        self.order_shelves_type_button_group.button(self.order_shelves_type).setChecked(True)

        self.order_shelves_by = self.options.get(cfg.KEY_ORDER_SHELVES_BY, cfg.ORDERSERIESSHELVES_OPTIONS_DEFAULTS[cfg.KEY_ORDER_SHELVES_BY])
        self.order_shelves_by_button_group.button(self.order_shelves_by).setChecked(True)

        # Display the books in the table
        self.block_events = False
        self.shelves_table.populate_table(self.shelves)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(_("Order Series Shelves"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/manage_series.png', _("Order Series Shelves"))
        layout.addLayout(title_layout)

        order_shelves_type_toolTip = [
                                    _("Order the shelves with series names."),
                                    _("Order the shelves with author names."),
                                    _("Order the shelves that do not have series or author names."),
                                    _("Order all shelves.")
                                    ]

        order_shelves_type_group_box = QGroupBox(_("Shelves to order"), self)
        layout.addWidget(order_shelves_type_group_box)
        order_shelves_type_group_box_layout = QHBoxLayout()
        order_shelves_type_group_box.setLayout(order_shelves_type_group_box_layout)
        self.order_shelves_type_button_group = QButtonGroup(self)
        self.order_shelves_type_buttons = {}
        for row, text in enumerate([_('Series'), _('Authors'), _('Other'), _('All')]):
            rdo = QRadioButton(text, self)
            rdo.setToolTip(order_shelves_type_toolTip[row])
            self.order_shelves_type_button_group.addButton(rdo)
            self.order_shelves_type_button_group.setId(rdo, row)
            order_shelves_type_group_box_layout.addWidget(rdo)
            self.order_shelves_type_buttons[rdo] = row
        self.order_shelves_type_button_group.buttonClicked.connect(self._order_shelves_type_radio_clicked)
        layout.addSpacing(5)

        self.fetch_button = QPushButton(_('Get shelves'), self)
        self.fetch_button.setToolTip(_('Edit the keyboard shortcuts associated with this plugin'))
        self.fetch_button.clicked.connect(self.fetch_button_clicked)
        order_shelves_type_group_box_layout.addWidget(self.fetch_button)

        # Main series table layout
        table_layout = QHBoxLayout()
        layout.addLayout(table_layout)

        self.shelves_table = OrderSeriesShelvesTableWidget(self)
        table_layout.addWidget(self.shelves_table)

        options_group = QGroupBox(_("Options"), self)
        options_tooltip = "The options are to set whether the shelf lists the books in series order or reverse order."
        options_group.setToolTip(options_tooltip)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        order_shelves_by_toolTip = [
                                    _("Order by series name and index and title."),
                                    _("Order by the published date.")
                                    ]

        order_shelves_by_group_box = QGroupBox(_("Order by"), self)
        options_layout.addWidget(order_shelves_by_group_box, 0, 0, 1, 1)
        order_shelves_by_group_box_layout = QVBoxLayout()
        order_shelves_by_group_box.setLayout(order_shelves_by_group_box_layout)
        self.order_shelves_by_button_group = QButtonGroup(self)
        self.order_shelves_by_buttons = {}
        for row, text in enumerate([_('Series'), _('Published date')]):
            rdo = QRadioButton(text, self)
            rdo.setToolTip(order_shelves_by_toolTip[row])
            self.order_shelves_by_button_group.addButton(rdo)
            self.order_shelves_by_button_group.setId(rdo, row)
            order_shelves_by_group_box_layout.addWidget(rdo)
            self.order_shelves_by_buttons[rdo] = row
        self.order_shelves_by_button_group.buttonClicked.connect(self._order_shelves_by_radio_clicked)

        order_shelves_in_toolTip = [
                                    _("Selecting ascending will sort the shelf in series order."),
                                    _("Selecting descending will sort the shelf in reverse series order.")
                                    ]

        order_shelves_in_group_box = QGroupBox(_("Order in"), self)
        options_layout.addWidget(order_shelves_in_group_box, 0, 1, 1, 1)
        order_shelves_in_group_box_layout = QVBoxLayout()
        order_shelves_in_group_box.setLayout(order_shelves_in_group_box_layout)
        self.order_shelves_in_button_group = QButtonGroup(self)
        self.order_shelves_in_buttons = {}
        for row, text in enumerate([_('Ascending'), _('Descending')]):
            rdo = QRadioButton(text, self)
            rdo.setToolTip(order_shelves_in_toolTip[row])
            self.order_shelves_in_button_group.addButton(rdo)
            self.order_shelves_in_button_group.setId(rdo, row)
            order_shelves_in_group_box_layout.addWidget(rdo)
            self.order_shelves_in_buttons[rdo] = row
        self.order_shelves_in_button_group.buttonClicked.connect(self._order_shelves_in_radio_clicked)


#        options_layout.addWidget(QLabel(_("Order in")), 0, 0, 1, 1)
#        self.ascending_radiobutton = QRadioButton(_("Ascending"), self)
#        self.ascending_radiobutton.setToolTip(_("Selecting ascending will sort the shelf in series order."))
#        options_layout.addWidget(self.ascending_radiobutton, 0, 1, 1, 1)
#
#        self.descending_radiobutton = QRadioButton(_("Descending"), self)
#        options_layout.addWidget(self.descending_radiobutton, 0, 2, 1, 1)
#        self.descending_radiobutton.setToolTip(_("Selecting descending will sort the shelf in reverse series order."))

        self.update_config_checkbox = QCheckBox(_("Update config file"), self)
        options_layout.addWidget(self.update_config_checkbox, 0, 2, 1, 1)
        self.update_config_checkbox.setToolTip(_("If this is selected, the configuration file is updated to set the selected sort for the shelves to 'Date Added'."))

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._ok_clicked)
        button_box.rejected.connect(self.reject)
        self.remove_selected_button = button_box.addButton(_("Remove"), QDialogButtonBox.ResetRole)
        self.remove_selected_button.setToolTip(_("Remove the selected shelves from the list. This will mean the ordering for these shelves will not be changed."))
        self.remove_selected_button.clicked.connect(self._remove_selected_clicked)
        layout.addWidget(button_box)

    def _ok_clicked(self):
        self.options = {}

        self.options[cfg.KEY_SORT_DESCENDING]    = self.order_shelves_in #self.descending_radiobutton.isChecked()
        self.options[cfg.KEY_SORT_UPDATE_CONFIG] = self.update_config_checkbox.isChecked()
        self.options[cfg.KEY_ORDER_SHELVES_TYPE] = self.order_shelves_type
        self.options[cfg.KEY_ORDER_SHELVES_BY]   = self.order_shelves_by
        cfg.plugin_prefs[cfg.ORDERSERIESSHELVES_OPTIONS_STORE_NAME]  = self.options
        self.accept()
        return

    def _order_shelves_type_radio_clicked(self, radioButton):
        self.order_shelves_type = self.order_shelves_type_buttons[radioButton]

    def _order_shelves_by_radio_clicked(self, radioButton):
        self.order_shelves_by = self.order_shelves_by_buttons[radioButton]

    def _order_shelves_in_radio_clicked(self, radioButton):
        self.order_shelves_in = self.order_shelves_in_buttons[radioButton]

    def _remove_selected_clicked(self):
        self.shelves_table.remove_selected_rows()

    def fetch_button_clicked(self):
        self.shelves = self.plugin_action._get_series_shelf_count(self.order_shelves_type)
        self.shelves_table.populate_table(self.shelves)
        return
        
    def get_shelves(self):
        return self.shelves_table.get_shelves()


class OrderSeriesShelvesTableWidget(QTableWidget):

    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.header_labels = [_('Shelf/Series Name'), _('Books on Shelf')]

    def populate_table(self, shelves):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(shelves))
        self.setColumnCount(len(self.header_labels))
        self.setHorizontalHeaderLabels(self.header_labels)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setStretchLastSection(True)

        self.shelves = {}
        for row, shelf in enumerate(shelves):
            self.populate_table_row(row, shelf)
            self.shelves[row] = shelf

        self.resizeColumnToContents(0)
        self.setMinimumColumnWidth(0, 150)
        self.setColumnWidth(1, 150)
        self.setSortingEnabled(True)
#        self.setMinimumSize(550, 0)
        self.selectRow(0)


    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, shelf):
#        debug_print("OrderSeriesShelvesTableWidget:populate_table_row - shelf:", row, shelf)
        self.blockSignals(True)
        nameColumn = QTableWidgetItem(shelf['name'])
        nameColumn.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
#        nameColumn.setData(Qt.UserRole, QVariant(row))
        nameColumn.setData(Qt.UserRole, row)
        self.setItem(row, 0, nameColumn)
        shelf_count = RatingTableWidgetItem(shelf['count'], is_read_only=True)
        shelf_count.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, 1, shelf_count)
        self.blockSignals(False)

    def get_shelves(self):
#        debug_print("OrderSeriesShelvesTableWidget:get_shelves - self.shelves:", self.shelves)
        shelves = []
        for row in range(self.rowCount()):
            rnum = convert_qvariant(self.item(row, 0).data(Qt.UserRole))
            shelf = self.shelves[rnum]
            shelves.append(shelf)
        return shelves

    def remove_selected_rows(self):
        self.setFocus()
        rows = self.selectionModel().selectedRows()
        if len(rows) == 0:
            return
        first_sel_row = self.currentRow()
        for selrow in reversed(rows):
            self.removeRow(selrow.row())
        if first_sel_row < self.rowCount():
            self.select_and_scroll_to_row(first_sel_row)
        elif self.rowCount() > 0:
            self.select_and_scroll_to_row(first_sel_row - 1)

    def select_and_scroll_to_row(self, row):
        self.selectRow(row)
        self.scrollToItem(self.currentItem())


class SetRelatedBooksDialog(SizePersistedDialog):

    def __init__(self, parent, plugin_action, related_types):
        SizePersistedDialog.__init__(self, parent, 'kobo utilities plugin:set related books dialog')
        self.plugin_action = plugin_action
        self.related_types = related_types
        self.block_events  = True
        self.help_anchor   = "SetRelatedBooks"
        self.dialog_title = _('Set Related Books')

        self.options = cfg.get_plugin_prefs(cfg.SETRELATEDBOOKS_OPTIONS_STORE_NAME)
        self.initialize_controls()

        self.related_category = self.options.get(cfg.KEY_RELATED_BOOKS_TYPE, cfg.SETRELATEDBOOKS_OPTIONS_DEFAULTS[cfg.KEY_RELATED_BOOKS_TYPE])
        self.related_categories_option_button_group.button(self.related_category).setChecked(True)

        # Display the books in the table
        self.block_events = False
        self.related_types_table.populate_table(self.related_types)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(DIALOG_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'images/manage_series.png', self.dialog_title)
        layout.addLayout(title_layout)

        related_categories_option_group_box = QGroupBox(_("Related books type"), self)
        layout.addWidget(related_categories_option_group_box)

        related_categories_options = {
                            cfg.KEY_RELATED_BOOKS_SERIES: (_("Series"), _("The related books will be all books in a series."), True),
                            cfg.KEY_RELATED_BOOKS_AUTHORS: (_("Authors"), _("The related books will be all books by the same author."), False),
                            }

        related_categories_option_group_box_layout = QHBoxLayout()
        related_categories_option_group_box.setLayout(related_categories_option_group_box_layout)
        self.related_categories_option_button_group = QButtonGroup(self)
        self.related_categories_option_button_group.buttonClicked[int].connect(self._related_categories_option_radio_clicked)
        for clean_option in related_categories_options.keys():
            clean_options = related_categories_options[clean_option]
            rdo = QRadioButton(clean_options[0], self)
            rdo.setToolTip(clean_options[1])
            self.related_categories_option_button_group.addButton(rdo)
            self.related_categories_option_button_group.setId(rdo, clean_option)
            related_categories_option_group_box_layout.addWidget(rdo)

        self.fetch_button = QPushButton(_('Get list'), self)
        self.fetch_button.setToolTip(_('Get the list of categories to use for the related books'))
        self.fetch_button.clicked.connect(self.fetch_button_clicked)
        related_categories_option_group_box_layout.addWidget(self.fetch_button)


        # Main series table layout
        table_layout = QHBoxLayout()
        layout.addLayout(table_layout)

        self.related_types_table = OrderSeriesShelvesTableWidget(self)
        self.related_types_table.header_labels = [_('Series/Author Name'), _('Number of books')]
        table_layout.addWidget(self.related_types_table)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._ok_clicked)
        button_box.rejected.connect(self.reject)
        self.remove_selected_button = button_box.addButton(_("Remove"), QDialogButtonBox.ResetRole)
        self.remove_selected_button.setToolTip(_("Remove the selected category from the list. This will mean related books will not be changed for that category."))
        self.remove_selected_button.clicked.connect(self._remove_selected_clicked)
        self.delete_related_button = button_box.addButton(_("Delete all"), QDialogButtonBox.ActionRole)
        self.delete_related_button.setToolTip(_("Delete all related books for sideloaded books."))
        self.delete_related_button.clicked.connect(self._delete_related_clicked)
        layout.addWidget(button_box)

    def _ok_clicked(self):
        self.options = {}
        self.options[cfg.KEY_RELATED_BOOKS_TYPE] = self.related_category
        cfg.plugin_prefs[cfg.SETRELATEDBOOKS_OPTIONS_STORE_NAME] = self.options
        self.options['deleteAllRelatedBooks'] = False
        self.accept()
        return

    def _related_categories_option_radio_clicked(self, idx):
        self.related_category = idx

    def fetch_button_clicked(self):
        self.related_types = self.plugin_action._get_related_books_count(self.related_category)
        self.related_types_table.populate_table(self.related_types)
        return
        
    def _remove_selected_clicked(self):
        self.related_types_table.remove_selected_rows()

    def _delete_related_clicked(self):
        mb = question_dialog(self, self.dialog_title, _("Do you want to remove related books for all sideloaded books?"), show_copy_button=False)
        if not mb:
            return

        self.options = {}
        self.options['deleteAllRelatedBooks'] = True
        self.accept()
        return

    def get_related_types(self):
        return self.related_types_table.get_shelves()


class FontChoiceComboBox(QComboBox):

    def __init__(self, parent, font_list=KOBO_FONTS):
        QComboBox.__init__(self, parent)
        for name, font in sorted(font_list.items()):
            self.addItem(name, font)

    def select_text(self, selected_text):
        idx = self.findData(selected_text)
        if idx != -1:
            self.setCurrentIndex(idx)
        else:
            self.setCurrentIndex(0)

class JustificationChoiceComboBox(QComboBox):

    def __init__(self, parent):
        QComboBox.__init__(self, parent)
        self.addItems(['Off', 'Left', 'Justify'])

    def select_text(self, selected_text):
        idx = self.findText(selected_text)
        if idx != -1:
            self.setCurrentIndex(idx)
        else:
            self.setCurrentIndex(0)

class ReadingDirectionChoiceComboBox(QComboBox):

    def __init__(self, parent, reading_direction_list=READING_DIRECTIONS):
        QComboBox.__init__(self, parent)
        for name, font in sorted(reading_direction_list.items()):
            self.addItem(name, font)

    def select_text(self, selected_text):
        idx = self.findData(selected_text)
        if idx != -1:
            self.setCurrentIndex(idx)
        else:
            self.setCurrentIndex(0)

class ReadingStatusGroupBox(QGroupBox):

    def __init__(self, parent):
        QGroupBox.__init__(self, parent)

        self.setTitle(_("Reading status"))
        options_layout = QGridLayout()
        self.setLayout(options_layout)

        self.reading_status_checkbox = QCheckBox(_("Change reading status"), self)
        options_layout.addWidget(self.reading_status_checkbox, 0, 0, 1, 2)
        self.reading_status_checkbox.clicked.connect(self.reading_status_checkbox_clicked)

        self.unread_radiobutton = QRadioButton(_("Unread"), self)
        options_layout.addWidget(self.unread_radiobutton, 1, 0, 1, 1)
        self.unread_radiobutton.setEnabled(False)

        self.reading_radiobutton = QRadioButton(_("Reading"), self)
        options_layout.addWidget(self.reading_radiobutton, 1, 1, 1, 1)
        self.reading_radiobutton.setEnabled(False)

        self.finished_radiobutton = QRadioButton(_("Finished"), self)
        options_layout.addWidget(self.finished_radiobutton, 1, 2, 1, 1)
        self.finished_radiobutton.setEnabled(False)

        self.reset_position_checkbox = QCheckBox(_("Reset reading position"), self)
        options_layout.addWidget(self.reset_position_checkbox, 2, 0, 1, 3)
        self.reset_position_checkbox.setToolTip(_("If this option is checked, the current position and last reading date will be reset."))

    def reading_status_checkbox_clicked(self, checked):
        self.unread_radiobutton.setEnabled(checked)
        self.reading_radiobutton.setEnabled(checked)
        self.finished_radiobutton.setEnabled(checked)
        self.reset_position_checkbox.setEnabled(checked)

    def readingStatusIsChecked(self):
        return self.reading_status_checkbox.checkState() == Qt.Checked

    def readingStatus(self):
        readingStatus = -1
        if self.unread_radiobutton.isChecked():
            readingStatus = 0
        elif self.reading_radiobutton.isChecked():
            readingStatus = 1
        elif self.finished_radiobutton.isChecked():
            readingStatus = 2
        
        return readingStatus


class TemplateConfig(QWidget): # {{{

    def __init__(self, val=None, mi=None):
        QWidget.__init__(self)
        self.mi = mi
        debug_print("TemplateConfig: mi=", self.mi)
        self.t = t = QLineEdit(self)
        t.setText(val or '')
        t.setCursorPosition(0)
        self.setMinimumWidth(300)
        self.l = l = QGridLayout(self)
        self.setLayout(l)
        l.addWidget(t, 1, 0, 1, 1)
        b = self.b = QPushButton(_('&Template editor'))
        l.addWidget(b, 1, 1, 1, 1)
        b.clicked.connect(self.edit_template)

#     def setEnabled(self, enabled):
#         self.l.setEnabled(enabled)
        
    @property
    def template(self):
        return unicode(self.t.text()).strip()

    @template.setter
    def template(self, template):
        self.t.setText(template)

    def edit_template(self):
        t = TemplateDialog(self, self.template, mi=self.mi)
        t.setWindowTitle(_('Edit template'))
        if t.exec_():
            self.t.setText(t.rule[1])

    def validate(self):
        from calibre.utils.formatter import validation_formatter
        tmpl = self.template
        try:
            validation_formatter.validate(tmpl)
            return True
        except Exception as err:
            error_dialog(self, _('Invalid template'),
                    '<p>'+_('The template %s is invalid:')%tmpl + \
                    '<br>'+unicode(err), show=True)

            return False
# }}}



class UpdateBooksToCDialog(SizePersistedDialog):
    def __init__(self, parent, plugin_action, icon, books):
        super(UpdateBooksToCDialog, self).__init__(parent, 'kobo utilities plugin:update book toc dialog', plugin_action=plugin_action)
        self.plugin_action = plugin_action
        self.parent = parent
        
        self.setWindowTitle(DIALOG_NAME)
        
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, 'toc.png', _('Update ToCs in Device Database'))
        layout.addLayout(title_layout)

        self.books_table = ToCBookListTableWidget(self)
        layout.addWidget(self.books_table)

        options_layout = QHBoxLayout()

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.update_button_clicked)
        button_box.rejected.connect(self.reject)
        update_button = button_box.button(QDialogButtonBox.Ok)
        update_button.setText(_("Update ToC"))
        update_button.setToolTip(_("Update ToC in device database for selected books."))

        self.remove_button = button_box.addButton(_('Remove'), QDialogButtonBox.ActionRole)
        self.remove_button.setToolTip(_('Remove selected books from the list'))
        self.remove_button.setIcon(get_icon('list_remove.png'))
        self.remove_button.clicked.connect(self.remove_from_list)

        self.send_books_button = button_box.addButton(_("Send Books"), QDialogButtonBox.ActionRole)
        self.send_books_button.setToolTip(_("Send books to device that have been updated in the library."))
        self.send_books_button.clicked.connect(self.send_books_clicked)

        self.select_all_button = button_box.addButton(_('Select all'), QDialogButtonBox.ResetRole)
        self.select_all_button.clicked.connect(self._select_all_clicked)
        self.select_all_button.setToolTip(_("Select all books in the list."))

        self.select_books_to_send_button = button_box.addButton(_('Select Books to send'), QDialogButtonBox.ResetRole)
        self.select_books_to_send_button.clicked.connect(self._select_books_to_send_clicked)
        self.select_books_to_send_button.setToolTip(_("Select all books that need to be sent to the device."))

        self.select_books_to_update_button = button_box.addButton(_('Select Books to update'), QDialogButtonBox.ResetRole)
        self.select_books_to_update_button.clicked.connect(self._select_books_to_update_clicked)
        self.select_books_to_update_button.setToolTip(_("Select all books in the list."))

        self.clear_all_button = button_box.addButton(_('Clear all'), QDialogButtonBox.ResetRole)
        self.clear_all_button.clicked.connect(self._clear_all_clicked)
        self.clear_all_button.setToolTip(_("Unselect all books in the list."))

        options_layout.addWidget(button_box)
        
        layout.addLayout(options_layout)
        
        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()
        self.books_table.populate_table(books)

    def remove_from_list(self):
        self.books_table.remove_selected_rows()

    def send_books_clicked(self):
        books_to_send = self.books_table.books_to_send
        ids_to_sync = [book['calibre_id'] for book in books_to_send]
        debug_print("send_books_clicked - ids_to_sync=", ids_to_sync)
        if not question_dialog(self.parent, _('Update Books'), '<p>'+
            _("There are {0} books that need to be updated on the device. "
              "After the book has been sent to the device, you can run the check and update the ToC."
              "<br/>"
              "Do you want to send the books to the device?").format(len(ids_to_sync)),
            show_copy_button=False):
            return
        self.parent.sync_to_device(on_card=None, delete_from_library=False, send_ids=ids_to_sync)
        self.reject()

    def update_button_clicked(self):
        books_to_send = self.books_to_update_toc
        ids_to_sync = [book['calibre_id'] for book in books_to_send]
        debug_print("update_button_clicked - ids_to_sync=", ids_to_sync)
        if not question_dialog(self.parent, _('Update Books'), '<p>'+
            _("There are {0} books that need to have their ToC updated on the device. "
              "Any selected books that have not been imported into the database on the device are ignored."
              "<br/>"
              "Do you want to update the ToC in the database on the device?").format(len(ids_to_sync)),
            show_copy_button=False):
            return
        self.accept()

    def _select_books_to_send_clicked(self):
        # self.books_table.toggle_checkmarks(Qt.Unchecked)
        self.books_table.select_checkmarks_send()

    def _select_books_to_update_clicked(self):
        # self.books_table.toggle_checkmarks(Qt.Unchecked)
        self.books_table.select_checkmarks_update_toc()

    def _select_all_clicked(self):
        self.books_table.toggle_checkmarks(Qt.Checked)

    def _clear_all_clicked(self):
        self.books_table.toggle_checkmarks(Qt.Unchecked)

    @property
    def books_to_update_toc(self):
        return self.books_table.books_to_update_toc


class ToCBookListTableWidget(QTableWidget):

    STATUS_COLUMN_NO = 0
    TITLE_COLUMN_NO = 1
    AUTHOR_COLUMN_NO = 2
    LIBRARY_CHAPTERS_COUNT_COLUMN_NO = 3
    LIBRARY_FORMAT_COLUMN_NO = 4
    KOBO_DISC_CHAPTERS_COUNT_COLUMN_NO = 5
    KOBO_DISC_FORMAT_COLUMN_NO = 6
    KOBO_DISC_STATUS_COLUMN_NO = 7 
    SEND_TO_DEVICE_COLUMN_NO = 8
    KOBO_DATABASE_CHAPTERS_COUNT_COLUMN_NO = 9 
    KOBO_DATABASE_STATUS_COLUMN_NO = 10
    UPDATE_TOC_COLUMN_NO = 11
    READING_POSITION_COLUMN_NO = 12
    STATUS_COMMENT_COLUMN_NO = 13 
    
    HEADER_LABELS_DICT = {
        STATUS_COLUMN_NO: '',
        TITLE_COLUMN_NO: _('Title'),
        AUTHOR_COLUMN_NO: _('Author'),
        LIBRARY_CHAPTERS_COUNT_COLUMN_NO: _('Library ToC'),
        LIBRARY_FORMAT_COLUMN_NO: _('Library Format'),
        KOBO_DISC_CHAPTERS_COUNT_COLUMN_NO: _('Kobo ToC'),
        KOBO_DISC_FORMAT_COLUMN_NO: _('Kobo Format'),
        KOBO_DISC_STATUS_COLUMN_NO: _('Status'),
        SEND_TO_DEVICE_COLUMN_NO: _('Send'),
        KOBO_DATABASE_CHAPTERS_COUNT_COLUMN_NO: _('Kobo Database ToC'),
        KOBO_DATABASE_STATUS_COLUMN_NO: _('Status'),
        UPDATE_TOC_COLUMN_NO: _('ToC'),
        READING_POSITION_COLUMN_NO: _('Reading Position'),
        STATUS_COMMENT_COLUMN_NO: _('Comment'),
        }


    def __init__(self, parent):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

    def populate_table(self, books):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(books))
        header_labels = [self.HEADER_LABELS_DICT[header_index] for header_index in sorted(self.HEADER_LABELS_DICT.keys())]
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.horizontalHeader().setStretchLastSection(True)
        #self.verticalHeader().setDefaultSectionSize(24)
        self.verticalHeader().hide()

        self.books={}
        for row, book in enumerate(books):
            self.populate_table_row(row, book)
            self.books[row] = book

        # turning True breaks up/down.  Do we need either sorting or up/down?
        self.setSortingEnabled(True)
        self.resizeColumnsToContents()
        self.setMinimumColumnWidth(1, 100)
        self.setMinimumColumnWidth(2, 100)
        self.setMinimumColumnWidth(3, 100)
        self.setMinimumSize(300, 0)
        # if len(books) > 0:
        #     self.selectRow(0)
        self.sortItems(1)
        self.sortItems(0)

    def setMinimumColumnWidth(self, col, minimum):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row, book):
#         debug_print("populate_table_row - book:", book)
        book_status = 0
        if book['good']:
            icon = get_icon('ok.png')
            book_status = 0
        else:
            icon = get_icon('minus.png')
            book_status = 1
        if 'icon' in book:
            icon = get_icon(book['icon'])

        # status_cell = CheckableTableWidgetItem(checked=not book['good'], icon=icon)
        status_cell = IconWidgetItem(None, icon, book_status)
        status_cell.setData(Qt.UserRole, book_status)
        self.setItem(row, 0, status_cell)
        
        title_cell = ReadOnlyTableWidgetItem(book['title'])
        title_cell.setData(Qt.UserRole, row)
        self.setItem(row, self.TITLE_COLUMN_NO, title_cell)
        
        self.setItem(row, self.AUTHOR_COLUMN_NO, AuthorTableWidgetItem(book['author'], book['author_sort']))
                
        if 'library_chapters' in book and len(book['library_chapters']) > 0:
            library_chapters_count = ReadOnlyTableWidgetItem(unicode(len(book['library_chapters'])))
            library_chapters_count.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.setItem(row, self.LIBRARY_CHAPTERS_COUNT_COLUMN_NO, library_chapters_count)
        
        if 'library_format' in book:
            library_format = ReadOnlyTableWidgetItem(unicode(book['library_format']))
            library_format.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.setItem(row, self.LIBRARY_FORMAT_COLUMN_NO, library_format)
        
        if 'kobo_chapters' in book and len(book['kobo_chapters']) > 0:
            kobo_chapters_count = ReadOnlyTableWidgetItem(unicode(len(book['kobo_chapters'])))
            kobo_chapters_count.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            #url_cell.setData(Qt.UserRole, book['url'])
            self.setItem(row, self.KOBO_DISC_CHAPTERS_COUNT_COLUMN_NO, kobo_chapters_count)

        if 'kobo_format' in book:
            kobo_format = ReadOnlyTableWidgetItem(unicode(book['kobo_format']))
            kobo_format.setTextAlignment(Qt.AlignCenter | Qt.AlignVCenter)
            self.setItem(row, self.KOBO_DISC_FORMAT_COLUMN_NO, kobo_format)

        kobo_format_status = 0
        if 'kobo_format_status' in book:
            if book['kobo_format_status']:
                icon = get_icon('ok.png')
                kobo_format_status = 0
            else:
                icon = get_icon('sync.png')
                kobo_format_status = 1
            kobo_format_status_cell = IconWidgetItem(None, icon, kobo_format_status)
            kobo_format_status_cell.setData(Qt.UserRole, kobo_format_status)
            self.setItem(row, self.KOBO_DISC_STATUS_COLUMN_NO, kobo_format_status_cell)

        kobo_disc_status = kobo_format_status == 1 and not book['good']
        kobo_disc_status_cell = CheckableTableWidgetItem(checked=kobo_disc_status)
        kobo_disc_status_cell.setData(Qt.UserRole, kobo_disc_status)
        self.setItem(row, self.SEND_TO_DEVICE_COLUMN_NO, kobo_disc_status_cell)

        if 'kobo_database_chapters' in book and len(book['kobo_database_chapters']) > 0:
            kobo_database_chapters_count = ReadOnlyTableWidgetItem(unicode(len(book['kobo_database_chapters'])))
            kobo_database_chapters_count.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.setItem(row, self.KOBO_DATABASE_CHAPTERS_COUNT_COLUMN_NO, kobo_database_chapters_count)

        kobo_database_status = 0
        icon_name = 'window-close.png'
        if 'kobo_database_status' in book:
            if not book['can_update_toc']:
                kobo_database_status = 0
                icon_name = 'window-close.png'
            elif book['kobo_database_status']:
                kobo_database_status = 0
                icon_name = 'ok.png'
            else:
                kobo_database_status = 1
                icon_name = 'toc.png'
        icon = get_icon(icon_name)
        kobo_database_status_cell = IconWidgetItem(None, icon, kobo_database_status)
        kobo_database_status_cell.setData(Qt.UserRole, kobo_database_status)
        self.setItem(row, self.KOBO_DATABASE_STATUS_COLUMN_NO, kobo_database_status_cell)
        
        update_toc = kobo_database_status == 1 and book['can_update_toc']
        update_toc_cell = CheckableTableWidgetItem(checked=update_toc)
        update_toc_cell.setData(Qt.UserRole, update_toc)
        self.setItem(row, self.UPDATE_TOC_COLUMN_NO, update_toc_cell)

        if 'koboDatabaseReadingLocation' in book and len(book['koboDatabaseReadingLocation']) > 0:
            koboDatabaseReadingLocation = ReadOnlyTableWidgetItem(book['koboDatabaseReadingLocation'])
            #url_cell.setData(Qt.UserRole, book['url'])
            self.setItem(row, self.READING_POSITION_COLUMN_NO, koboDatabaseReadingLocation)
        
        comment_cell = ReadOnlyTableWidgetItem(book['comment'])
        #comment_cell.setData(Qt.UserRole, book)
        self.setItem(row, self.STATUS_COMMENT_COLUMN_NO, comment_cell)

    @property
    def books_to_update_toc(self):
        books = []
        for row in range(self.rowCount()):
            if self.item(row, self.UPDATE_TOC_COLUMN_NO).get_boolean_value():
                rnum = convert_qvariant(self.item(row, self.TITLE_COLUMN_NO).data(Qt.UserRole))
                book = self.books[rnum]
                if book['can_update_toc']:
                    books.append(book)
        return books

    @property
    def books_to_send(self):
        books = []
        for row in range(self.rowCount()):
            if self.item(row, self.SEND_TO_DEVICE_COLUMN_NO).get_boolean_value():
                rnum = convert_qvariant(self.item(row, self.TITLE_COLUMN_NO).data(Qt.UserRole))
                book = self.books[rnum]
                books.append(book)
        return books

    def remove_selected_rows(self):
        self.setFocus()
        rows = self.selectionModel().selectedRows()
        if len(rows) == 0:
            return
        message = '<p>Are you sure you want to remove this book from the list?'
        if len(rows) > 1:
            message = '<p>Are you sure you want to remove the selected %d books from the list?'%len(rows)
        if not confirm(message,'kobo_utilities_plugin_tocupdate_delete_item', self):
            return
        first_sel_row = self.currentRow()
        for selrow in reversed(rows):
            self.removeRow(selrow.row())
        if first_sel_row < self.rowCount():
            self.select_and_scroll_to_row(first_sel_row)
        elif self.rowCount() > 0:
            self.select_and_scroll_to_row(first_sel_row - 1)

    def select_and_scroll_to_row(self, row):
        self.selectRow(row)
        self.scrollToItem(self.currentItem())

    def toggle_checkmarks(self, select):
        for i in range(self.rowCount()):
            self.item(i, self.UPDATE_TOC_COLUMN_NO).setCheckState(select)
        for i in range(self.rowCount()):
            self.item(i, self.SEND_TO_DEVICE_COLUMN_NO).setCheckState(select)

    def select_checkmarks_send(self):
        for i in range(self.rowCount()):
            rnum = convert_qvariant(self.item(i, 1).data(Qt.UserRole))
            debug_print("select_checkmarks_send - rnum=%s, book=%s" % (rnum, self.books[rnum]))
            self.item(i, self.SEND_TO_DEVICE_COLUMN_NO).setCheckState(Qt.Unchecked if self.books[rnum]['kobo_format_status'] else Qt.Checked)

    def select_checkmarks_update_toc(self):
        for i in range(self.rowCount()):
            book_no = convert_qvariant(self.item(i, 1).data(Qt.UserRole))
            debug_print("select_checkmarks_update_toc - book_no=%s, book=%s" 
                        % (book_no, self.books[book_no])
                        )
            check_for_toc = not self.books[book_no]['kobo_database_status'] and self.books[book_no]['can_update_toc']
            self.item(i, self.UPDATE_TOC_COLUMN_NO).setCheckState(Qt.Checked if check_for_toc else Qt.Unchecked)



class IconWidgetItem(ReadOnlyTextIconWidgetItem):
    def __init__(self, text, icon, sort_key):
        super(IconWidgetItem, self).__init__(text, icon)
        self.sort_key = sort_key

    #Qt uses a simple < check for sorting items, override this to use the sortKey
    def __lt__(self, other):
        return self.sort_key < other.sort_key

class SortableReadOnlyTableWidgetItem(ReadOnlyTableWidgetItem):
    def __init__(self, text, sort_key=None):
        super(SortableReadOnlyTableWidgetItem, self).__init__(text)
        self.sort_key = text if not sort_key or sort_key == '' else sort_key

    #Qt uses a simple < check for sorting items, override this to use the sortKey
    def __lt__(self, other):
        return self.sort_key < other.sort_key



class AboutDialog(QDialog):

    def __init__(self, parent, icon, text):
        QDialog.__init__(self, parent)
        self.resize(400, 250)
        self.l = QGridLayout()
        self.setLayout(self.l)
        self.logo = QLabel()
        self.logo.setMaximumWidth(110)
        self.logo.setPixmap(QPixmap(icon.pixmap(100,100)))
        self.label = QLabel(text)
        self.label.setOpenExternalLinks(True)
        self.label.setWordWrap(True)
        self.setWindowTitle(_('About ' + DIALOG_NAME))
        self.setWindowIcon(icon)
        self.l.addWidget(self.logo, 0, 0)
        self.l.addWidget(self.label, 0, 1)
        self.bb = QDialogButtonBox(self)
        b = self.bb.addButton(_(_("OK")), self.bb.AcceptRole)
        b.setDefault(True)
        self.l.addWidget(self.bb, 2, 0, 1, -1)
        self.bb.accepted.connect(self.accept)

