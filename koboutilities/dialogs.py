# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

from __future__ import annotations

__license__ = "GPL v3"
__copyright__ = "2012-2020, David Forrester <davidfor@internode.on.net>"
__docformat__ = "restructuredtext en"

import datetime as dt
import re
from functools import partial
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    cast,
)
from urllib.parse import quote_plus

from calibre.ebooks.metadata import authors_to_string
from calibre.gui2 import choose_dir, error_dialog, open_url, question_dialog, ui
from calibre.gui2.complete2 import EditWithComplete
from calibre.gui2.dialogs.confirm_delete import confirm
from calibre.gui2.library.delegates import DateDelegate
from calibre.gui2.widgets2 import ColorButton
from calibre.utils.config import tweaks
from calibre.utils.date import qt_to_dt, utc_tz
from calibre.utils.icu import sort_key
from qt.core import (
    QAbstractItemView,
    QAction,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QDropEvent,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QMouseEvent,
    QPixmap,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QTimer,
    QToolButton,
    QUrl,
    QVBoxLayout,
    QWidget,
)

from . import config as cfg
from .book import SeriesBook
from .constants import BOOK_CONTENTTYPE, GUI_NAME
from .utils import (
    CheckableTableWidgetItem,
    CustomColumnComboBox,
    DateTableWidgetItem,
    ImageTitleLayout,
    ProfileComboBox,
    RatingTableWidgetItem,
    ReadOnlyTableWidgetItem,
    ReadOnlyTextIconWidgetItem,
    SizePersistedDialog,
    contentid_from_path,
    convert_calibre_ids_to_books,
    convert_kobo_date,
    debug,
    get_device_paths_from_id,
    get_icon,
    is_device_view,
)

if TYPE_CHECKING:
    from calibre.db.legacy import LibraryDatabase
    from calibre.devices.kobo.books import Book

    from .action import KoboUtilitiesAction

# Checked with FW2.5.2


KEY_REMOVE_ANNOT_ALL = 0
KEY_REMOVE_ANNOT_NOBOOK = 1
KEY_REMOVE_ANNOT_EMPTY = 2
KEY_REMOVE_ANNOT_NONEMPTY = 3
KEY_REMOVE_ANNOT_SELECTED = 4

# pulls in translation files for _() strings
load_translations()


class AuthorTableWidgetItem(ReadOnlyTableWidgetItem):
    def __init__(self, text: str, sort_key: str):
        ReadOnlyTableWidgetItem.__init__(self, text)
        self.sort_key = sort_key

    # Qt uses a simple < check for sorting items, override this to use the sortKey
    def __lt__(self, other: Any):
        if isinstance(other, AuthorTableWidgetItem):
            return self.sort_key < other.sort_key
        return super().__lt__(other)


class ReadLocationsProgressDialog(QProgressDialog):
    def __init__(
        self,
        gui: ui.Main,
        options: cfg.ReadLocationsJobOptions,
        queue: Callable[
            [cfg.ReadLocationsJobOptions, list[tuple[Any]]],
            None,
        ],
        db: LibraryDatabase | None,
        plugin_action: KoboUtilitiesAction,
    ):
        QProgressDialog.__init__(self, "", "", 0, 0, gui)
        debug("init")
        self.setMinimumWidth(500)
        self.books = []
        self.options, self.queue, self.db = (options, queue, db)
        self.plugin_action = plugin_action
        self.gui = gui
        self.i = 0
        self.books_to_scan = []
        self.profileName = self.options.profile_name
        self.setWindowTitle(_("Queueing books for storing reading position"))
        QTimer.singleShot(0, self.do_books)
        self.exec()

    def do_books(self):
        debug("Start")

        library_db = self.db
        assert library_db is not None

        custom_columns = cfg.get_column_names(self.gui, self.plugin_action.device)
        self.options.custom_columns = custom_columns
        kobo_chapteridbookmarked_column = custom_columns.current_location
        kobo_percentRead_column = custom_columns.percent_read
        rating_column = custom_columns.rating
        last_read_column = custom_columns.last_read
        time_spent_reading_column = custom_columns.time_spent_reading
        rest_of_book_estimate_column = custom_columns.rest_of_book_estimate

        debug("kobo_percentRead_column='%s'" % kobo_percentRead_column)
        self.setLabelText(_("Preparing the list of books ..."))
        self.setValue(1)
        search_condition = ""
        if self.options.bookmark_options.doNotStoreIfReopened:
            search_condition = f"and ({kobo_percentRead_column}:false or {kobo_percentRead_column}:<100)"
        if self.options.allOnDevice:
            search_condition = f"ondevice:True {search_condition}"
            debug("search_condition=", search_condition)
            onDeviceIds = set(
                library_db.search_getting_ids(  # pyright: ignore[reportAttributeAccessIssue]
                    search_condition,
                    None,
                    sort_results=False,
                    use_virtual_library=False,
                )
            )
        else:
            onDeviceIds = self.plugin_action._get_selected_ids()

        self.books = convert_calibre_ids_to_books(library_db, onDeviceIds)
        self.setRange(0, len(self.books))
        device = self.plugin_action.device
        assert device is not None
        for book in self.books:
            self.i += 1
            device_book_paths = get_device_paths_from_id(
                cast("int", book.calibre_id), self.gui
            )
            book.contentIDs = [
                contentid_from_path(device, path, BOOK_CONTENTTYPE)
                for path in device_book_paths
            ]
            if len(book.contentIDs):
                title = book.title
                self.setLabelText(_("Queueing {}").format(title))
                authors = authors_to_string(book.authors)
                current_chapterid = None
                current_percentRead = None
                current_rating = None
                current_last_read = None
                current_time_spent_reading = None
                current_rest_of_book_estimate = None
                if kobo_chapteridbookmarked_column:
                    metadata = book.get_user_metadata(
                        kobo_chapteridbookmarked_column, True
                    )
                    assert metadata is not None
                    current_chapterid = metadata["#value#"]
                if kobo_percentRead_column:
                    metadata = book.get_user_metadata(kobo_percentRead_column, True)
                    assert metadata is not None
                    current_percentRead = metadata["#value#"]
                if rating_column:
                    if rating_column == "rating":
                        current_rating = book.rating
                    else:
                        metadata = book.get_user_metadata(rating_column, True)
                        assert metadata is not None
                        current_rating = metadata["#value#"]
                if last_read_column:
                    metadata = book.get_user_metadata(last_read_column, True)
                    assert metadata is not None
                    current_last_read = metadata["#value#"]
                if time_spent_reading_column:
                    metadata = book.get_user_metadata(time_spent_reading_column, True)
                    assert metadata is not None
                    current_time_spent_reading = metadata["#value#"]
                if rest_of_book_estimate_column:
                    metadata = book.get_user_metadata(
                        rest_of_book_estimate_column, True
                    )
                    assert metadata is not None
                    current_rest_of_book_estimate = metadata["#value#"]

                self.books_to_scan.append(
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
            self.setValue(self.i)

        debug("Finish")
        self.hide()

        # Queue a job to process these ePub books
        self.queue(self.options, self.books_to_scan)


class CleanImagesDirProgressDialog(QProgressDialog):
    def __init__(
        self,
        gui: ui.Main | None,  # TODO Can this actually be None?
        options: cfg.CleanImagesDirJobOptions,
        queue: Callable[[cfg.CleanImagesDirJobOptions], None],
    ):
        QProgressDialog.__init__(self, "", "", 0, 0, gui)
        debug("init")
        self.setMinimumWidth(500)
        self.options = options
        self.queue = queue
        self.gui = gui
        self.setWindowTitle(_("Creating queue for checking images directory"))
        QTimer.singleShot(0, self.do_clean_images_dir_queue)
        self.exec()

    def do_clean_images_dir_queue(self):
        debug("start")
        if self.gui is None:
            # There is a nasty QT bug with the timers/logic above which can
            # result in the do_queue method being called twice
            return
        self.hide()

        # Queue a job to process these ePub books
        self.queue(self.options)


class RemoveAnnotationsProgressDialog(QProgressDialog):
    def __init__(
        self,
        gui: ui.Main | None,  # TODO Can this actually be None?
        options: cfg.RemoveAnnotationsJobOptions,
        queue: Callable[[cfg.RemoveAnnotationsJobOptions, list[tuple[Any]]], None],
        db: LibraryDatabase | None,
        plugin_action: KoboUtilitiesAction,
    ):
        QProgressDialog.__init__(self, "", "", 0, 0, gui)
        debug("init")
        self.setMinimumWidth(500)
        self.books = []
        self.options = options
        self.queue = queue
        self.db = db
        self.plugin_action = plugin_action
        self.gui = gui
        self.books_to_scan = []

        self.setWindowTitle(_("Creating queue for removing annotations files"))
        QTimer.singleShot(0, self.do_remove_annotations_queue)
        self.exec()

    def do_remove_annotations_queue(self):
        debug("start")
        if self.gui is None:
            # There is a nasty QT bug with the timers/logic above which can
            # result in the do_queue method being called twice
            return
        if self.options.remove_annot_action == cfg.RemoveAnnotationsAction.Selected:
            library_db = self.db  # self.gui.current_db
            assert library_db is not None

            self.setLabelText(_("Preparing the list of books ..."))
            self.setValue(1)

            if is_device_view(self.gui):
                self.books = self.plugin_action._get_books_for_selected()
            else:
                onDeviceIds = self.plugin_action._get_selected_ids()
                self.books = convert_calibre_ids_to_books(library_db, onDeviceIds)
            self.setRange(0, len(self.books))

            device = self.plugin_action.device
            assert device is not None
            for i, book in enumerate(self.books, start=1):
                if is_device_view(self.gui):
                    device_book_paths = [book.path]
                    contentIDs = [book.contentID]
                else:
                    device_book_paths = get_device_paths_from_id(
                        cast("int", book.calibre_id), self.gui
                    )
                    contentIDs = [
                        contentid_from_path(device, path, BOOK_CONTENTTYPE)
                        for path in device_book_paths
                    ]
                debug("device_book_paths:", device_book_paths)
                book.paths = device_book_paths
                book.contentIDs = contentIDs
                if len(book.contentIDs):
                    title = book.title
                    self.setLabelText(_("Queueing {}").format(title))
                    authors = authors_to_string(book.authors)

                    self.books_to_scan.append(
                        (book.calibre_id, book.contentIDs, book.paths, title, authors)
                    )
                self.setValue(i)
        self.hide()

        # Queue a job to process these ePub books
        self.queue(self.options, self.books_to_scan)


class GetShelvesFromDeviceDialog(SizePersistedDialog):
    def __init__(self, parent: ui.Main, plugin_action: KoboUtilitiesAction):
        SizePersistedDialog.__init__(
            self,
            parent,
            "kobo utilities plugin:get shelves from device settings dialog",
        )
        self.plugin_action = plugin_action
        self.help_anchor = "GetShelvesFromDevice"

        self.initialize_controls()

        all_books = cfg.plugin_prefs.getShelvesOptionStore.allBooks
        self.all_books_checkbox.setChecked(all_books)

        replace_shelves = cfg.plugin_prefs.getShelvesOptionStore.replaceShelves
        self.replace_shelves_checkbox.setChecked(replace_shelves)

        self.library_config = cfg.get_library_config(self.plugin_action.gui.current_db)
        shelf_column = self.library_config.shelvesColumn
        self.tag_type_custom_columns = self.get_tag_type_custom_columns()
        self.shelf_column_combo.populate_combo(
            self.tag_type_custom_columns, shelf_column
        )
        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(GUI_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(
            self, "images/icon.png", _("Get collections from device")
        )
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("Options"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        shelf_column_label = QLabel(_("Collection column:"), self)
        shelf_column_tooltip = _(
            "Select a custom column to store the retrieved collection names. The column type must\nbe of type 'text'."
        )
        shelf_column_label.setToolTip(shelf_column_tooltip)
        self.shelf_column_combo = CustomColumnComboBox(self)
        self.shelf_column_combo.setToolTip(shelf_column_tooltip)
        shelf_column_label.setBuddy(self.shelf_column_combo)
        options_layout.addWidget(shelf_column_label, 0, 0, 1, 1)
        options_layout.addWidget(self.shelf_column_combo, 0, 1, 1, 1)

        self.all_books_checkbox = QCheckBox(_("All books on device"), self)
        self.all_books_checkbox.setToolTip(
            _(
                "Get the collections for all the books on the device that are in the library. If not checked, will only get them for the selected books."
            )
        )
        options_layout.addWidget(self.all_books_checkbox, 1, 0, 1, 2)

        self.replace_shelves_checkbox = QCheckBox(
            _("Replace column with collections"), self
        )
        self.replace_shelves_checkbox.setToolTip(
            _(
                "If this is selected, the current value in the library, will be replaced by\nthe retrieved collections. Otherwise, the retrieved collections will be added to the value"
            )
        )
        options_layout.addWidget(self.replace_shelves_checkbox, 2, 0, 1, 2)

        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_tag_type_custom_columns(self):
        column_types = ["text"]
        return self.get_custom_columns(column_types)

    def get_custom_columns(self, column_types: list[str]) -> dict[str, str]:
        custom_columns = self.plugin_action.gui.library_view.model().custom_columns
        available_columns: dict[str, str] = {}
        for key, column in custom_columns.items():
            typ = column["datatype"]
            if typ in column_types:
                available_columns[key] = column["name"]
        return available_columns

    def ok_clicked(self) -> None:
        with cfg.plugin_prefs.getShelvesOptionStore as options:
            options.allBooks = self.all_books_checkbox.isChecked()
            options.replaceShelves = self.replace_shelves_checkbox.isChecked()

        shelves_column = self.shelf_column_combo.get_selected_column()
        if not shelves_column:
            error_dialog(
                self,
                _("No collection column selected"),
                _(
                    "You must select a column to populate from the collections on the device"
                ),
                show=True,
                show_copy_button=False,
            )
            return

        self.library_config.shelvesColumn = shelves_column
        cfg.set_library_config(self.plugin_action.gui.current_db, self.library_config)

        self.accept()


class BookmarkOptionsDialog(SizePersistedDialog):
    def __init__(self, parent: QWidget, plugin_action: KoboUtilitiesAction):
        SizePersistedDialog.__init__(
            self, parent, "kobo utilities plugin:bookmark options dialog"
        )
        self.plugin_action = plugin_action
        self.help_anchor = "StoreCurrentBookmark"

        library_config = cfg.get_library_config(self.plugin_action.gui.current_db)
        self.profiles = library_config.profiles
        self.profile_name = (
            self.plugin_action.device.profile.profileName
            if self.plugin_action.device and self.plugin_action.device.profile
            else None
        )
        self.initialize_controls()

        options = cfg.plugin_prefs.BookmarkOptions
        if options.storeBookmarks:
            self.store_radiobutton.click()
        else:
            self.restore_radiobutton.click()
        self.status_to_reading_checkbox.setChecked(options.readingStatus)
        self.date_to_now_checkbox.setChecked(options.setDateToNow)
        self.set_rating_checkbox.setChecked(
            options.rating
            and self.plugin_action.device is not None
            and self.plugin_action.device.supports_ratings
        )

        self.clear_if_unread_checkbox.setChecked(options.clearIfUnread)
        self.store_if_more_recent_checkbox.setChecked(options.storeIfMoreRecent)
        self.do_not_store_if_reopened_checkbox.setChecked(options.doNotStoreIfReopened)
        self.do_not_store_if_reopened_checkbox_clicked(options.doNotStoreIfReopened)
        self.background_checkbox.setChecked(options.backgroundJob)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(GUI_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(
            self, "images/icon.png", _("Store or restore reading positions")
        )
        layout.addLayout(title_layout)

        options_column_group = QGroupBox(_("Options"), self)
        layout.addWidget(options_column_group)
        options_layout = QGridLayout()
        options_column_group.setLayout(options_layout)

        self.store_radiobutton = QRadioButton(_("Store"), self)
        self.store_radiobutton.setToolTip(
            _("Store the current reading position in the calibre library.")
        )
        options_layout.addWidget(self.store_radiobutton, 1, 0, 1, 1)
        self.store_radiobutton.clicked.connect(self.store_radiobutton_clicked)

        self.store_if_more_recent_checkbox = QCheckBox(_("Only if more recent"), self)
        self.store_if_more_recent_checkbox.setToolTip(
            _(
                "Only store the reading position if the last read timestamp on the device is more recent than in the library."
            )
        )
        options_layout.addWidget(self.store_if_more_recent_checkbox, 2, 0, 1, 1)

        self.do_not_store_if_reopened_checkbox = QCheckBox(
            _("Not if finished in library"), self
        )
        self.do_not_store_if_reopened_checkbox.setToolTip(
            _(
                "Do not store the reading position if the library has the book as finished. This is if the percent read is 100%."
            )
        )
        options_layout.addWidget(self.do_not_store_if_reopened_checkbox, 3, 0, 1, 1)
        self.do_not_store_if_reopened_checkbox.clicked.connect(
            self.do_not_store_if_reopened_checkbox_clicked
        )

        self.clear_if_unread_checkbox = QCheckBox(_("Clear if unread"), self)
        self.clear_if_unread_checkbox.setToolTip(
            _(
                "If the book on the device is shown as unread, clear the reading position stored in the library."
            )
        )
        options_layout.addWidget(self.clear_if_unread_checkbox, 4, 0, 1, 1)

        self.background_checkbox = QCheckBox(_("Run in background"), self)
        self.background_checkbox.setToolTip(_("Do store or restore as background job."))
        options_layout.addWidget(self.background_checkbox, 5, 0, 1, 2)

        self.restore_radiobutton = QRadioButton(_("Restore"), self)
        self.restore_radiobutton.setToolTip(
            _("Copy the current reading position back to the device.")
        )
        options_layout.addWidget(self.restore_radiobutton, 1, 1, 1, 1)
        self.restore_radiobutton.clicked.connect(self.restore_radiobutton_clicked)

        self.status_to_reading_checkbox = QCheckBox(_("Set reading status"), self)
        self.status_to_reading_checkbox.setToolTip(
            _(
                "If this is not set, when the current reading position is on the device, the reading status will not be changes. If the percent read is 100%, the book will be marked as finished. Otherwise, it will be in progress."
            )
        )
        options_layout.addWidget(self.status_to_reading_checkbox, 2, 1, 1, 1)

        self.date_to_now_checkbox = QCheckBox(_("Set date to now"), self)
        self.date_to_now_checkbox.setToolTip(
            _(
                'Setting the date to now will put the book at the top of the "Recent reads" list.'
            )
        )
        options_layout.addWidget(self.date_to_now_checkbox, 3, 1, 1, 1)

        self.set_rating_checkbox = QCheckBox(_("Update rating"), self)
        self.set_rating_checkbox.setToolTip(
            _(
                "Set the book rating on the device. If the current rating in the library is zero, the rating on the device will be reset."
            )
        )
        options_layout.addWidget(self.set_rating_checkbox, 4, 1, 1, 1)

        profiles_label = QLabel(_("Profile"), self)
        options_layout.addWidget(profiles_label, 6, 0, 1, 1)
        self.select_profile_combo = ProfileComboBox(
            self, self.profiles, self.profile_name
        )
        self.select_profile_combo.setMinimumSize(150, 20)
        options_layout.addWidget(self.select_profile_combo, 6, 1, 1, 1)

        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):
        profile_name = str(self.select_profile_combo.currentText()).strip()
        msg = self.plugin_action.validate_profile(profile_name)
        if msg is not None:
            error_dialog(
                self, "Invalid profile", msg, show=True, show_copy_button=False
            )
            return
        self.profile_name = profile_name
        with cfg.plugin_prefs.BookmarkOptions as options:
            options.storeBookmarks = self.store_radiobutton.isChecked()
            options.readingStatus = self.status_to_reading_checkbox.isChecked()
            options.setDateToNow = self.date_to_now_checkbox.isChecked()
            options.rating = self.set_rating_checkbox.isChecked()
            options.clearIfUnread = self.clear_if_unread_checkbox.isChecked()
            options.storeIfMoreRecent = self.store_if_more_recent_checkbox.isChecked()
            options.doNotStoreIfReopened = (
                self.do_not_store_if_reopened_checkbox.isChecked()
            )
            options.backgroundJob = self.background_checkbox.isChecked()
            if options.doNotStoreIfReopened:
                options.clearIfUnread = False
        self.accept()

    def do_not_store_if_reopened_checkbox_clicked(self, checked: bool):
        self.clear_if_unread_checkbox.setEnabled(not checked)

    def restore_radiobutton_clicked(self, checked: bool):
        self.status_to_reading_checkbox.setEnabled(checked)
        self.date_to_now_checkbox.setEnabled(checked)
        device = self.plugin_action.device
        has_rating_column = (
            cfg.get_column_names(self.plugin_action.gui, device).rating != ""
        )
        self.set_rating_checkbox.setEnabled(
            checked
            and has_rating_column
            and device is not None
            and device.supports_ratings
        )
        self.clear_if_unread_checkbox.setEnabled(not checked)
        self.store_if_more_recent_checkbox.setEnabled(not checked)
        self.do_not_store_if_reopened_checkbox.setEnabled(not checked)
        self.background_checkbox.setEnabled(not checked)

    def store_radiobutton_clicked(self, checked: bool):
        self.status_to_reading_checkbox.setEnabled(not checked)
        self.date_to_now_checkbox.setEnabled(not checked)
        self.set_rating_checkbox.setEnabled(not checked)
        self.clear_if_unread_checkbox.setEnabled(checked)
        self.store_if_more_recent_checkbox.setEnabled(checked)
        self.do_not_store_if_reopened_checkbox.setEnabled(checked)
        self.background_checkbox.setEnabled(checked)


class ChangeReadingStatusOptionsDialog(SizePersistedDialog):
    def __init__(self, parent: ui.Main, plugin_action: KoboUtilitiesAction):
        SizePersistedDialog.__init__(
            self, parent, "kobo utilities plugin:change reading status settings dialog"
        )
        self.plugin_action = plugin_action
        self.help_anchor = "ChangeReadingStatus"
        self.options = cfg.MetadataOptionsConfig()

        self.initialize_controls()

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(GUI_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(
            self, "images/icon.png", _("Change reading status in device library")
        )
        layout.addLayout(title_layout)

        self.readingStatusGroupBox = ReadingStatusGroupBox(
            cast("ui.Main", self.parent())
        )
        layout.addWidget(self.readingStatusGroupBox)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self) -> None:
        self.options.setRreadingStatus = (
            self.readingStatusGroupBox.readingStatusIsChecked()
        )
        if self.options.setRreadingStatus:
            self.options.readingStatus = self.readingStatusGroupBox.readingStatus()
            if self.options.readingStatus < 0:
                error_dialog(
                    self,
                    "No reading status option selected",
                    "If you are changing the reading status, you must select an option to continue",
                    show=True,
                    show_copy_button=False,
                )
                return
            self.options.resetPosition = (
                self.readingStatusGroupBox.reset_position_checkbox.isChecked()
            )

        # Only if the user has checked at least one option will we continue
        for _key, val in self.options:
            if val:
                self.accept()
                return
        error_dialog(
            self,
            _("No options selected"),
            _("You must select at least one option to continue."),
            show=True,
            show_copy_button=False,
        )


class BackupAnnotationsOptionsDialog(SizePersistedDialog):
    def __init__(self, parent: QWidget, plugin_action: KoboUtilitiesAction):
        SizePersistedDialog.__init__(
            self,
            parent,
            "kobo utilities plugin:backup annotation files settings dialog",
        )
        self.plugin_action = plugin_action
        self.help_anchor = "BackupAnnotations"

        self.initialize_controls()

        self.dest_directory_edit.setText(
            cfg.plugin_prefs.backupAnnotations.dest_directory
        )
        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(GUI_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(
            self, "images/icon.png", _("Back up annotations files")
        )
        layout.addLayout(title_layout)
        options_layout = QGridLayout()
        layout.addLayout(options_layout)

        dest_directory_label = QLabel(_("Destination:"), self)
        dest_directory_label.setToolTip(
            _("Select the destination the annotations files are to be backed up in.")
        )
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
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self) -> None:
        if len(self.dest_directory_edit.text()) == 0:
            error_dialog(
                self,
                "No destination",
                "You must enter a destination directory to save the annotation files in",
                show=True,
                show_copy_button=False,
            )

        cfg.plugin_prefs.backupAnnotations.dest_directory = (
            self.dest_directory_edit.text()
        )
        self.accept()

    def dest_path(self):
        return self.dest_directory_edit.text()

    def _get_dest_directory_name(self):
        path = choose_dir(
            self,
            "back up annotations destination dialog",
            _("Choose destination directory"),
        )
        self.dest_directory_edit.setText(path)


class RemoveAnnotationsOptionsDialog(SizePersistedDialog):
    def __init__(self, parent: QWidget, plugin_action: KoboUtilitiesAction):
        SizePersistedDialog.__init__(
            self,
            parent,
            "kobo utilities plugin:remove annotation files settings dialog",
        )
        self.plugin_action = plugin_action
        self.help_anchor = "RemoveAnnotations"

        self.initialize_controls()
        self.annotation_clean_option_idx = (
            cfg.plugin_prefs.removeAnnotations.removeAnnotAction.value
        )
        button = self.annotation_clean_option_button_group.button(
            self.annotation_clean_option_idx
        )
        assert button is not None
        button.setChecked(True)
        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(GUI_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(
            self, "images/icon.png", _("Remove annotations files")
        )
        layout.addLayout(title_layout)
        options_layout = QGridLayout()
        layout.addLayout(options_layout)

        annotation_clean_option_group_box = QGroupBox(_("Remove..."), self)
        options_layout.addWidget(annotation_clean_option_group_box, 0, 0, 1, 1)

        annotation_clean_options = {
            cfg.RemoveAnnotationsAction.All.value: (
                _("All"),
                _("Remove the annotations directory and all files within it"),
                True,
            ),
            cfg.RemoveAnnotationsAction.Selected.value: (
                _("For selected books"),
                _("Only remove annotations files for the selected books"),
                False,
            ),
            cfg.RemoveAnnotationsAction.NotOnDevice.value: (
                _("Where book is not on device"),
                _("Remove annotations files where there is no book on the device"),
                True,
            ),
            cfg.RemoveAnnotationsAction.Empty.value: (
                _("Empty"),
                _("Remove all empty annotations files"),
                True,
            ),
            cfg.RemoveAnnotationsAction.NotEmpty.value: (
                _("Not empty"),
                _("Only remove annotations files if they contain annotations"),
                True,
            ),
        }

        annotation_clean_option_group_box_layout = QVBoxLayout()
        annotation_clean_option_group_box.setLayout(
            annotation_clean_option_group_box_layout
        )
        self.annotation_clean_option_button_group = QButtonGroup(self)
        self.annotation_clean_option_button_group.buttonClicked.connect(
            self._annotation_clean_option_radio_clicked
        )
        self.annotation_clean_option_buttons = {}
        for row, clean_option in enumerate(annotation_clean_options):
            clean_options = annotation_clean_options[clean_option]
            rdo = QRadioButton(clean_options[0], self)
            rdo.setToolTip(clean_options[1])
            self.annotation_clean_option_button_group.addButton(rdo)
            self.annotation_clean_option_button_group.setId(rdo, clean_option)
            annotation_clean_option_group_box_layout.addWidget(rdo)
            self.annotation_clean_option_buttons[rdo] = row

        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):
        cfg.plugin_prefs.removeAnnotations.removeAnnotAction = (
            cfg.RemoveAnnotationsAction(self.annotation_clean_option_idx)
        )
        self.accept()

    def _annotation_clean_option_radio_clicked(self, radioButton: QRadioButton):
        self.annotation_clean_option_idx = self.annotation_clean_option_buttons[
            radioButton
        ]


class CoverUploadOptionsDialog(SizePersistedDialog):
    def __init__(self, parent: QWidget, plugin_action: KoboUtilitiesAction):
        SizePersistedDialog.__init__(
            self, parent, "kobo utilities plugin:cover upload settings dialog"
        )
        self.plugin_action = plugin_action
        self.help_anchor = "UploadCovers"

        self.initialize_controls()

        options = cfg.plugin_prefs.coverUpload

        # Set some default values from last time dialog was used.
        blackandwhite = options.blackandwhite
        self.blackandwhite_checkbox.setChecked(blackandwhite)
        self.blackandwhite_checkbox_clicked(blackandwhite)
        self.ditheredcovers_checkbox.setChecked(options.dithered_covers)

        assert self.plugin_action.device is not None
        # Hide options if the driver doesn't have the extended options.
        self.driver_supports_extended_cover_options = hasattr(
            self.plugin_action.device.driver, "dithered_covers"
        )
        self.driver_supports_cover_letterbox_colors = hasattr(
            self.plugin_action.device.driver, "letterbox_fs_covers_color"
        )
        self.ditheredcovers_checkbox.setVisible(
            self.driver_supports_extended_cover_options
        )
        self.letterbox_checkbox.setVisible(self.driver_supports_extended_cover_options)
        self.pngcovers_checkbox.setVisible(self.driver_supports_extended_cover_options)
        self.letterbox_colorbutton.setVisible(
            self.driver_supports_cover_letterbox_colors
        )

        letterbox = options.letterbox
        self.letterbox_checkbox.setChecked(letterbox)
        self.letterbox_checkbox_clicked(letterbox)
        keep_cover_aspect = options.keep_cover_aspect
        self.keep_cover_aspect_checkbox.setChecked(keep_cover_aspect)
        self.keep_cover_aspect_checkbox_clicked(keep_cover_aspect)
        letterbox_color = options.letterbox_color
        self.letterbox_colorbutton.color = letterbox_color
        self.pngcovers_checkbox.setChecked(options.png_covers)
        self.kepub_covers_checkbox.setChecked(options.kepub_covers)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(GUI_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, "default_cover.png", _("Upload covers"))
        layout.addLayout(title_layout, stretch=0)

        options_group = QGroupBox(_("Upload covers"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        self.blackandwhite_checkbox = QCheckBox(_("Black and white covers"), self)
        options_layout.addWidget(self.blackandwhite_checkbox, 0, 0, 1, 1)
        self.blackandwhite_checkbox.clicked.connect(self.blackandwhite_checkbox_clicked)
        self.ditheredcovers_checkbox = QCheckBox(_("Dithered covers"), self)
        options_layout.addWidget(self.ditheredcovers_checkbox, 0, 1, 1, 1)
        self.pngcovers_checkbox = QCheckBox(_("PNG covers"), self)
        options_layout.addWidget(self.pngcovers_checkbox, 0, 2, 1, 2)

        self.keep_cover_aspect_checkbox = QCheckBox(_("Keep cover aspect ratio"), self)
        options_layout.addWidget(self.keep_cover_aspect_checkbox, 1, 0, 1, 1)
        self.keep_cover_aspect_checkbox.clicked.connect(
            self.keep_cover_aspect_checkbox_clicked
        )
        self.letterbox_checkbox = QCheckBox(_("Letterbox covers"), self)
        options_layout.addWidget(self.letterbox_checkbox, 1, 1, 1, 1)
        self.letterbox_checkbox.clicked.connect(self.letterbox_checkbox_clicked)

        self.letterbox_colorbutton = ColorButton(options_layout)
        self.letterbox_colorbutton.setToolTip(
            _(
                "Choose the color to use when letterboxing the cover."
                " The default color is black (#000000)"
            )
        )
        options_layout.addWidget(self.letterbox_colorbutton, 1, 2, 1, 1)

        self.kepub_covers_checkbox = QCheckBox(_("Upload covers for Kobo ePubs"), self)
        options_layout.addWidget(self.kepub_covers_checkbox, 2, 0, 1, 3)
        options_layout.setColumnStretch(0, 0)
        options_layout.setColumnStretch(1, 0)
        options_layout.setColumnStretch(2, 0)

        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):
        with cfg.plugin_prefs.coverUpload as options:
            options.blackandwhite = self.blackandwhite_checkbox.isChecked()
            options.dithered_covers = self.ditheredcovers_checkbox.isChecked()
            options.png_covers = self.pngcovers_checkbox.isChecked()
            options.keep_cover_aspect = self.keep_cover_aspect_checkbox.isChecked()
            options.letterbox = self.letterbox_checkbox.isChecked()
            if self.driver_supports_cover_letterbox_colors:
                options.letterbox_color = cast("str", self.letterbox_colorbutton.color)
            options.kepub_covers = self.kepub_covers_checkbox.isChecked()

        self.accept()

    def blackandwhite_checkbox_clicked(self, checked: bool):
        self.ditheredcovers_checkbox.setEnabled(
            checked and self.blackandwhite_checkbox.isChecked()
        )
        self.pngcovers_checkbox.setEnabled(
            checked and self.blackandwhite_checkbox.isChecked()
        )

    def keep_cover_aspect_checkbox_clicked(self, checked: bool):
        self.letterbox_checkbox.setEnabled(
            checked and self.keep_cover_aspect_checkbox.isChecked()
        )
        self.letterbox_colorbutton.setEnabled(
            checked and self.letterbox_checkbox.isChecked()
        )

    def letterbox_checkbox_clicked(self, checked: bool):
        self.letterbox_colorbutton.setEnabled(
            checked and self.letterbox_checkbox.isChecked()
        )


class RemoveCoverOptionsDialog(SizePersistedDialog):
    def __init__(self, parent: QWidget, plugin_action: KoboUtilitiesAction):
        SizePersistedDialog.__init__(
            self, parent, "kobo utilities plugin:remove cover settings dialog"
        )
        self.plugin_action = plugin_action
        self.help_anchor = "RemoveCovers"

        self.initialize_controls()

        options = cfg.plugin_prefs.removeCovers
        self.remove_fullsize_covers_checkbox.setChecked(options.remove_fullsize_covers)
        self.kepub_covers_checkbox.setChecked(options.kepub_covers)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(GUI_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(self, "default_cover.png", _("Remove covers"))
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("Remove covers"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)

        self.remove_fullsize_covers_checkbox = QCheckBox(
            _("Remove full size covers"), self
        )
        self.remove_fullsize_covers_checkbox.setToolTip(
            _(
                "Check this if you want to remove just the full size cover from the device. This will save space, but, if covers are used for the sleep screen, they will not look very good."
            )
        )
        options_layout.addWidget(self.remove_fullsize_covers_checkbox, 0, 0, 1, 1)

        self.kepub_covers_checkbox = QCheckBox(_("Remove covers for Kobo epubs"), self)
        self.kepub_covers_checkbox.setToolTip(
            _(
                "Check this if you want to remove covers for any Kobo epubs synced from the Kobo server."
            )
        )
        options_layout.addWidget(self.kepub_covers_checkbox, 2, 0, 1, 1)

        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):
        with cfg.plugin_prefs.removeCovers as options:
            options.remove_fullsize_covers = (
                self.remove_fullsize_covers_checkbox.isChecked()
            )
            options.kepub_covers = self.kepub_covers_checkbox.isChecked()
        self.accept()


class CleanImagesDirOptionsDialog(SizePersistedDialog):
    def __init__(self, parent: QWidget, plugin_action: KoboUtilitiesAction):
        SizePersistedDialog.__init__(
            self, parent, "kobo utilities plugin:clean images dir settings dialog"
        )
        self.plugin_action = plugin_action
        self.help_anchor = "CleanImagesDir"

        self.initialize_controls()

        self.delete_extra_covers_checkbox.setChecked(
            cfg.plugin_prefs.cleanImagesDir.delete_extra_covers
        )

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(GUI_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(
            self, "images/icon.png", _("Clean images directory")
        )
        layout.addLayout(title_layout)

        options_group = QGroupBox(_("Clean images"), self)
        layout.addWidget(options_group)
        options_layout = QGridLayout()
        options_group.setLayout(options_layout)
        self.delete_extra_covers_checkbox = QCheckBox(
            _("Delete extra cover image files"), self
        )
        self.delete_extra_covers_checkbox.setToolTip(
            _(
                "Check this if you want to delete the extra cover image files from the images directory on the device."
            )
        )
        options_layout.addWidget(self.delete_extra_covers_checkbox, 0, 0, 1, 1)

        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.ok_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def ok_clicked(self):
        cfg.plugin_prefs.cleanImagesDir.delete_extra_covers = (
            self.delete_extra_covers_checkbox.isChecked()
        )
        self.accept()


class LockSeriesDialog(SizePersistedDialog):
    def __init__(self, parent: QWidget, title: str, initial_value: float):
        SizePersistedDialog.__init__(
            self, parent, "Manage Series plugin:lock series dialog"
        )
        self.initialize_controls(title, initial_value)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self, title: str, initial_value: float):
        self.setWindowTitle(_("Lock series index"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(
            self, "images/lock32.png", _("Lock series index")
        )
        layout.addLayout(title_layout)

        layout.addSpacing(10)
        self.title_label = QLabel("Series index for book: '%s'" % title, self)
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

        self.assign_same_checkbox = QCheckBox(
            _("&Assign this index value to all remaining books"), self
        )
        layout.addWidget(self.assign_same_checkbox)
        layout.addStretch(1)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_value(self):
        return float(str(self.value_spinbox.value()))

    def assign_same_value(self):
        return self.assign_same_checkbox.isChecked()


class TitleWidgetItem(QTableWidgetItem):
    def __init__(self, book: Book | SeriesBook):
        if isinstance(book, SeriesBook):
            super().__init__(book.title())
            self.title_sort = book.title()
            if not book.is_valid():
                self.setIcon(get_icon("dialog_warning.png"))
                self.setToolTip(
                    _("You have conflicting or out of sequence series indexes")
                )
            elif book.id() is None:
                self.setIcon(get_icon("add_book.png"))
                self.setToolTip(_("Empty book added to series"))
            elif (
                book.is_title_changed()
                or book.is_pubdate_changed()
                or book.is_series_changed()
            ):
                self.setIcon(get_icon("format-list-ordered.png"))
                self.setToolTip(_("The book data has been changed"))
            else:
                self.setIcon(get_icon("ok.png"))
                self.setToolTip(_("The series data is unchanged"))
        else:
            super().__init__(book.title)
            self.title_sort = book.title_sort

    def __lt__(self, other: Any) -> bool:
        if isinstance(other, TitleWidgetItem):
            return self.title_sort < other.title_sort
        return super().__lt__(other)


class AuthorsTableWidgetItem(ReadOnlyTableWidgetItem):
    def __init__(self, authors: list[str], author_sort: str | None = None):
        text = " & ".join(authors)
        ReadOnlyTableWidgetItem.__init__(self, text)
        self.setForeground(Qt.GlobalColor.darkGray)
        self.author_sort = author_sort

    def __lt__(self, other: Any):
        if (
            self.author_sort is not None
            and isinstance(other, AuthorsTableWidgetItem)
            and other.author_sort is not None
        ):
            return self.author_sort < other.author_sort
        return super().__lt__(other)


class SeriesTableWidgetItem(ReadOnlyTableWidgetItem):
    def __init__(
        self,
        series_name: str | None,
        series_index: str,
        is_original: bool = False,
        assigned_index: float | None = None,
    ):
        if series_name:
            text = "%s [%s]" % (series_name, series_index)
            text = "%s - %s" % (series_name, series_index)
        else:
            text = ""
        ReadOnlyTableWidgetItem.__init__(self, text)
        if assigned_index is not None:
            self.setIcon(get_icon("images/lock.png"))
            self.setToolTip(_("Value assigned by user"))
        if is_original:
            self.setForeground(Qt.GlobalColor.darkGray)


class SeriesColumnComboBox(QComboBox):
    def __init__(self, parent: QWidget, series_columns: dict[str, Any]):
        QComboBox.__init__(self, parent)
        self.series_columns = series_columns
        for key, column in series_columns.items():
            self.addItem("%s (%s)" % (key, column))
        self.insertItem(0, "Series")

    def select_text(self, selected_key: str):
        if selected_key == "Series":
            self.setCurrentIndex(0)
        else:
            for idx, key in enumerate(self.seriesColumns.keys()):  # type: ignore[reportAttributeAccessIssue]
                if key == selected_key:
                    self.setCurrentIndex(idx)
                    return

    def selected_value(self) -> str:
        if self.currentIndex() == 0:
            return "Series"
        return list(self.series_columns.keys())[self.currentIndex() - 1]


class SeriesTableWidget(QTableWidget):
    def __init__(self, parent: QWidget):
        QTableWidget.__init__(self, parent)
        self.create_context_menu()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDropIndicatorShown(True)
        self.fmt = tweaks["gui_pubdate_display_format"]
        if self.fmt is None:
            self.fmt = "MMM yyyy"

    def create_context_menu(self):
        parent = self.parent()
        assert isinstance(parent, ManageSeriesDeviceDialog)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.assign_original_index_action = QAction(
            _("Lock original series index"), self
        )
        self.assign_original_index_action.setIcon(get_icon("images/lock.png"))
        self.assign_original_index_action.triggered.connect(
            parent.assign_original_index
        )
        self.addAction(self.assign_original_index_action)
        self.assign_index_action = QAction(_("Lock series index..."), self)
        self.assign_index_action.setIcon(get_icon("images/lock.png"))
        self.assign_index_action.triggered.connect(parent.assign_index)
        self.addAction(self.assign_index_action)
        self.clear_index_action = QAction(_("Unlock series index"), self)
        self.clear_index_action.setIcon(get_icon("images/lock_delete.png"))
        self.clear_index_action.triggered.connect(
            partial(parent.clear_index, all_rows=False)
        )
        self.addAction(self.clear_index_action)
        self.clear_all_index_action = QAction(_("Unlock all series index"), self)
        self.clear_all_index_action.setIcon(get_icon("images/lock_open.png"))
        self.clear_all_index_action.triggered.connect(
            partial(parent.clear_index, all_rows=True)
        )
        self.addAction(self.clear_all_index_action)
        sep2 = QAction(self)
        sep2.setSeparator(True)
        self.addAction(sep2)
        for name in ["PubDate", "Original Series Index", "Original Series Name"]:
            sort_action = QAction("Sort by " + name, self)
            sort_action.setIcon(get_icon("images/sort.png"))
            sort_action.triggered.connect(partial(parent.sort_by, name))
            self.addAction(sort_action)
        sep3 = QAction(self)
        sep3.setSeparator(True)
        self.addAction(sep3)
        for name, icon in [
            ("FantasticFiction", "images/ms_ff.png"),
            ("Goodreads", "images/ms_goodreads.png"),
            ("Google", "images/ms_google.png"),
            ("Wikipedia", "images/ms_wikipedia.png"),
        ]:
            menu_action = QAction("Search %s" % name, self)
            menu_action.setIcon(get_icon(icon))
            menu_action.triggered.connect(partial(parent.search_web, name))
            self.addAction(menu_action)

    def populate_table(self, books: list[SeriesBook]):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(books))
        header_labels = ["Title", "Author(s)", "PubDate", "Series", "New Series"]
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        self.verticalHeader().setDefaultSectionSize(24)  # type: ignore[reportOptionalMemberAccess]
        self.horizontalHeader().setStretchLastSection(True)  # type: ignore[reportOptionalMemberAccess]

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
        delegate = DateDelegate(self, tweak_name="gui_pubdate_display_format")
        self.setItemDelegateForColumn(2, delegate)

    def setMinimumColumnWidth(self, col: int, minimum: int):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row: int, book: SeriesBook):
        self.blockSignals(True)
        self.setItem(row, 0, TitleWidgetItem(book))
        self.setItem(row, 1, AuthorsTableWidgetItem(book.authors()))
        self.setItem(
            row,
            2,
            DateTableWidgetItem(
                book.pubdate(), is_read_only=False, default_to_today=False, fmt=self.fmt
            ),
        )
        self.setItem(
            row,
            3,
            SeriesTableWidgetItem(
                book.orig_series_name(),
                book.orig_series_index_string(),
                is_original=True,
            ),
        )
        self.setItem(
            row,
            4,
            SeriesTableWidgetItem(
                book.series_name(),
                book.series_index_string(),
                assigned_index=book.assigned_index(),
            ),
        )
        self.blockSignals(False)

    def swap_row_widgets(self, src_row: int, dest_row: int):
        self.blockSignals(True)
        self.insertRow(dest_row)
        for col in range(self.columnCount()):
            self.setItem(dest_row, col, self.takeItem(src_row, col))
        self.removeRow(src_row)
        self.blockSignals(False)

    def select_and_scroll_to_row(self, row: int):
        self.selectRow(row)
        self.scrollToItem(self.currentItem())

    def event_has_mods(self, event: QMouseEvent | None = None):
        mods = (
            event.modifiers() if event is not None else QApplication.keyboardModifiers()
        )
        return (
            mods & Qt.KeyboardModifier.ControlModifier
            or mods & Qt.KeyboardModifier.ShiftModifier
        )

    def mousePressEvent(self, e: QMouseEvent | None):
        assert e is not None
        ep = e.pos()
        selection_model = self.selectionModel()
        assert selection_model is not None
        if (
            self.indexAt(ep) not in selection_model.selectedIndexes()
            and e.button() == Qt.MouseButton.LeftButton
            and not self.event_has_mods()
        ):
            self.setDragEnabled(False)
        else:
            self.setDragEnabled(True)
        return QTableWidget.mousePressEvent(self, e)

    def dropEvent(self, event: QDropEvent | None):
        assert event is not None
        selection_model = self.selectionModel()
        assert selection_model is not None
        rows = selection_model.selectedRows()
        selrows = sorted(row.row() for row in rows)
        drop_row = self.rowAt(event.pos().y())  # type: ignore[reportAttributeAccessIssue]
        if drop_row == -1:
            drop_row = self.rowCount() - 1
        rows_before_drop = [idx for idx in selrows if idx < drop_row]
        rows_after_drop = [idx for idx in selrows if idx >= drop_row]

        parent = self.parent()
        assert isinstance(parent, ManageSeriesDeviceDialog)
        dest_row = drop_row
        for selrow in rows_after_drop:
            dest_row += 1
            self.swap_row_widgets(selrow + 1, dest_row)
            book = parent.books.pop(selrow)
            parent.books.insert(dest_row, book)

        dest_row = drop_row + 1
        for selrow in reversed(rows_before_drop):
            self.swap_row_widgets(selrow, dest_row)
            book = parent.books.pop(selrow)
            parent.books.insert(dest_row - 1, book)
            dest_row = dest_row - 1

        event.setDropAction(Qt.DropAction.CopyAction)
        # Determine the new row selection
        self.selectRow(drop_row)
        parent.renumber_series()

    def set_series_column_headers(self, text: str):
        item = self.horizontalHeaderItem(3)
        if item is not None:
            item.setText("Original " + text)
        item = self.horizontalHeaderItem(4)
        if item is not None:
            item.setText("New " + text)


class ManageSeriesDeviceDialog(SizePersistedDialog):
    def __init__(
        self,
        parent: ui.Main,
        plugin_action: KoboUtilitiesAction,
        books: list[SeriesBook],
        all_series: list[tuple[int, str]],
        series_columns: dict[str, str],
    ):
        SizePersistedDialog.__init__(
            self, parent, "kobo utilities plugin:series dialog"
        )
        self.plugin_action = plugin_action
        self.db = parent.library_view.model().db
        self.books = books
        self.all_series = all_series
        self.series_columns = series_columns
        self.blockSignals(True)

        self.initialize_controls()

        # Books will have been sorted by the Calibre series column
        # Choose the appropriate series column to be editing
        initial_series_column = "Series"
        self.series_column_combo.select_text(initial_series_column)
        if len(series_columns) == 0:
            # Will not have fired the series_column_changed event
            self.series_column_changed()
        # Renumber the books using the assigned series name/index in combos/spinbox
        self.renumber_series(display_in_table=False)

        # Display the books in the table
        self.blockSignals(False)
        self.series_table.populate_table(books)
        if len(str(self.series_combo.text()).strip()) > 0:
            self.series_table.setFocus()
        else:
            self.series_combo.setFocus()
        self.update_series_headers(initial_series_column)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(_("Manage series"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(
            self, "images/manage_series.png", _("Manage series on device")
        )
        layout.addLayout(title_layout)

        # Series name and start index layout
        series_name_layout = QHBoxLayout()
        layout.addLayout(series_name_layout)

        series_column_label = QLabel(_("Series &Column:"), self)
        series_name_layout.addWidget(series_column_label)
        self.series_column_combo = SeriesColumnComboBox(self, self.series_columns)
        self.series_column_combo.currentIndexChanged[int].connect(
            self.series_column_changed
        )
        series_name_layout.addWidget(self.series_column_combo)
        series_column_label.setBuddy(self.series_column_combo)
        series_name_layout.addSpacing(20)

        series_label = QLabel(_("Series &Name:"), self)
        series_name_layout.addWidget(series_label)
        self.series_combo = EditWithComplete(self)
        self.series_combo.setEditable(True)
        self.series_combo.setInsertPolicy(QComboBox.InsertPolicy.InsertAlphabetically)
        self.series_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.series_combo.setMinimumContentsLength(25)
        self.series_combo.currentIndexChanged[int].connect(self.series_changed)
        self.series_combo.editTextChanged.connect(self.series_changed)
        self.series_combo.set_separator(None)
        series_label.setBuddy(self.series_combo)
        series_name_layout.addWidget(self.series_combo)
        series_name_layout.addSpacing(20)
        series_start_label = QLabel(_("&Start at:"), self)
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
        self.clean_title_checkbox.setToolTip(
            _(
                "Removes series information from the titles. For Kobo books, this is '(Series Name - #1)'"
            )
        )
        self.clean_title_checkbox.clicked.connect(self.clean_title_checkbox_clicked)

        # Main series table layout
        table_layout = QHBoxLayout()
        layout.addLayout(table_layout)

        self.series_table = SeriesTableWidget(self)
        self.series_table.itemSelectionChanged.connect(self.item_selection_changed)
        self.series_table.cellChanged[int, int].connect(self.cell_changed)

        table_layout.addWidget(self.series_table)
        table_button_layout = QVBoxLayout()
        table_layout.addLayout(table_button_layout)
        move_up_button = QToolButton(self)
        move_up_button.setToolTip(_("Move book up in series (Alt+Up)"))
        move_up_button.setIcon(get_icon("arrow-up.png"))
        move_up_button.setShortcut(_("Alt+Up"))
        move_up_button.clicked.connect(self.move_rows_up)
        table_button_layout.addWidget(move_up_button)
        move_down_button = QToolButton(self)
        move_down_button.setToolTip(_("Move book down in series (Alt+Down)"))
        move_down_button.setIcon(get_icon("arrow-down.png"))
        move_down_button.setShortcut(_("Alt+Down"))
        move_down_button.clicked.connect(self.move_rows_down)
        table_button_layout.addWidget(move_down_button)
        spacerItem1 = QSpacerItem(
            20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )
        table_button_layout.addItem(spacerItem1)
        assign_index_button = QToolButton(self)
        assign_index_button.setToolTip(_("Lock to index value..."))
        assign_index_button.setIcon(get_icon("images/lock.png"))
        assign_index_button.clicked.connect(self.assign_index)
        table_button_layout.addWidget(assign_index_button)
        clear_index_button = QToolButton(self)
        clear_index_button.setToolTip(_("Unlock series index"))
        clear_index_button.setIcon(get_icon("images/lock_delete.png"))
        clear_index_button.clicked.connect(self.clear_index)
        table_button_layout.addWidget(clear_index_button)
        spacerItem2 = QSpacerItem(
            20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )
        table_button_layout.addItem(spacerItem2)
        delete_button = QToolButton(self)
        delete_button.setToolTip(_("Remove book from the series list"))
        delete_button.setIcon(get_icon("trash.png"))
        delete_button.clicked.connect(self.remove_book)
        table_button_layout.addWidget(delete_button)
        spacerItem3 = QSpacerItem(
            20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )
        table_button_layout.addItem(spacerItem3)
        move_left_button = QToolButton(self)
        move_left_button.setToolTip(
            _("Move series index to left of decimal point (Alt+Left)")
        )
        move_left_button.setIcon(get_icon("back.png"))
        move_left_button.setShortcut(_("Alt+Left"))
        move_left_button.clicked.connect(partial(self.series_indent_change, -1))
        table_button_layout.addWidget(move_left_button)
        move_right_button = QToolButton(self)
        move_right_button.setToolTip(
            _("Move series index to right of decimal point (Alt+Right)")
        )
        move_right_button.setIcon(get_icon("forward.png"))
        move_right_button.setShortcut(_("Alt+Right"))
        move_right_button.clicked.connect(partial(self.series_indent_change, 1))
        table_button_layout.addWidget(move_right_button)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        keep_button = button_box.addButton(
            _(" &Restore original series "), QDialogButtonBox.ButtonRole.ResetRole
        )
        assert keep_button is not None
        keep_button.clicked.connect(self.restore_original_series)

    def reject(self):
        debug("start")
        for book in self.books:
            book.revert_changes()
        super().reject()

    def series_column_changed(self):
        debug("start")
        series_column = self.series_column_combo.selected_value()
        SeriesBook.series_column = series_column
        # Choose a series name and series index from the first book in the list
        initial_series_name = ""
        initial_series_index = 1
        if len(self.books) > 0:
            first_book = self.books[0]
            initial_series_name = first_book.series_name()
            debug("initial_series_name='%s'" % initial_series_name)
            if initial_series_name is not None:
                debug("first_book.series_index()='%s'" % first_book.series_index())
                try:
                    initial_series_index = int(first_book.series_index())
                except Exception:
                    initial_series_index = 1
        # Populate the series name combo as appropriate for that column
        self.initialize_series_name_combo(series_column, initial_series_name)
        # Populate the series index spinbox with the initial value
        self.series_start_number.setProperty("value", initial_series_index)
        self.update_series_headers(series_column)
        if self.signalsBlocked():
            return
        self.renumber_series()

    def update_series_headers(self, series_column: str) -> None:
        if series_column == "Series":
            self.series_table.set_series_column_headers(series_column)
        else:
            header_text = self.series_columns[series_column]
            self.series_table.set_series_column_headers(header_text)

    def initialize_series_name_combo(
        self, series_column: str, series_name: str | None
    ) -> None:
        self.series_combo.clear()
        if series_name is None:
            series_name = ""
        values = self.all_series
        if series_column == "Series":
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
        if self.signalsBlocked():
            return
        self.renumber_series()

    def series_start_changed(self):
        if self.signalsBlocked():
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

    def clean_title(self, remove_series: bool):
        # Go through the books and clean the Kobo series from the title
        for book in self.books:
            if remove_series:
                series_in_title = re.findall(r"\(.*\)", book._orig_title)
                if len(series_in_title) > 0:
                    book._mi.title = book._orig_title.replace(
                        series_in_title[len(series_in_title) - 1], ""
                    )
            else:
                book._mi.title = book._orig_title
        # Now renumber the whole series so that anything in between gets changed
        self.renumber_series()

    def clean_title_checkbox_clicked(self, checked: bool):
        self.clean_title(checked)

    def renumber_series(self, display_in_table: bool = True):
        if len(self.books) == 0:
            return
        series_name = str(self.series_combo.currentText()).strip()
        series_index = float(str(self.series_start_number.value()))
        last_series_indent = 0
        for row, book in enumerate(self.books):
            book.set_series_name(series_name)
            series_indent = book.series_indent()
            assigned_index = book.assigned_index()
            if assigned_index is not None:
                series_index = assigned_index
            else:
                if series_indent >= last_series_indent:
                    if series_indent == 0:
                        if row > 0:
                            series_index += 1.0
                    elif series_indent == 1:
                        series_index += 0.1
                    else:
                        series_index += 0.01
                else:
                    # When series indent decreases, need to round to next
                    if series_indent == 1:
                        series_index = round(series_index + 0.05, 1)
                    else:  # series_indent == 0:
                        series_index = round(series_index + 0.5, 0)
            book.set_series_index(series_index)
            last_series_indent = series_indent
        # Now determine whether books have a valid index or not
        self.books[0].set_is_valid(True)
        for row in range(len(self.books) - 1, 0, -1):
            book = self.books[row]
            previous_book = self.books[row - 1]
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
        selection_model = self.series_table.selectionModel()
        assert selection_model is not None
        for row in selection_model.selectedRows():
            book = self.books[row.row()]
            book.set_assigned_index(book.orig_series_index())
        self.renumber_series()
        self.item_selection_changed()

    def assign_index(self):
        if len(self.books) == 0:
            return
        auto_assign_value = None
        selection_model = self.series_table.selectionModel()
        assert selection_model is not None
        for row in selection_model.selectedRows():
            book = self.books[row.row()]
            if auto_assign_value is not None:
                book.set_assigned_index(auto_assign_value)
                continue

            d = LockSeriesDialog(self, book.title(), book.series_index())
            d.exec()
            if d.result() != d.DialogCode.Accepted:
                break
            if d.assign_same_value():
                auto_assign_value = d.get_value()
                book.set_assigned_index(auto_assign_value)
            else:
                book.set_assigned_index(d.get_value())

        self.renumber_series()
        self.item_selection_changed()

    def clear_index(self, all_rows: bool = False):
        if len(self.books) == 0:
            return
        if all_rows:
            for book in self.books:
                book.set_assigned_index(None)
        else:
            selection_model = self.series_table.selectionModel()
            assert selection_model is not None
            for row in selection_model.selectedRows():
                book = self.books[row.row()]
                book.set_assigned_index(None)
        self.renumber_series()

    def remove_book(self):
        if not question_dialog(
            self,
            _("Are you sure?"),
            "<p>" + _("Remove the selected book(s) from the series list?"),
            show_copy_button=False,
        ):
            return
        selection_model = self.series_table.selectionModel()
        assert selection_model is not None
        rows = selection_model.selectedRows()
        if len(rows) == 0:
            return
        selrows = sorted(row.row() for row in rows)
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
        selection_model = self.series_table.selectionModel()
        assert selection_model is not None
        rows = selection_model.selectedRows()
        if len(rows) == 0:
            return
        first_sel_row = rows[0].row()
        if first_sel_row <= 0:
            return
        # Workaround for strange selection bug in Qt which "alters" the selection
        # in certain circumstances which meant move down only worked properly "once"
        selrows = sorted(row.row() for row in rows)
        for selrow in selrows:
            self.series_table.swap_row_widgets(selrow - 1, selrow + 1)
            self.books[selrow - 1], self.books[selrow] = (
                self.books[selrow],
                self.books[selrow - 1],
            )

        scroll_to_row = first_sel_row - 1
        if scroll_to_row > 0:
            scroll_to_row = scroll_to_row - 1
        self.series_table.scrollToItem(self.series_table.item(scroll_to_row, 0))
        self.renumber_series()

    def move_rows_down(self):
        self.series_table.setFocus()
        selection_model = self.series_table.selectionModel()
        assert selection_model is not None
        rows = selection_model.selectedRows()
        if len(rows) == 0:
            return
        last_sel_row = rows[-1].row()
        if last_sel_row == self.series_table.rowCount() - 1:
            return
        # Workaround for strange selection bug in Qt which "alters" the selection
        # in certain circumstances which meant move down only worked properly "once"
        selrows = sorted(row.row() for row in rows)
        for selrow in reversed(selrows):
            self.series_table.swap_row_widgets(selrow + 2, selrow)
            self.books[selrow + 1], self.books[selrow] = (
                self.books[selrow],
                self.books[selrow + 1],
            )

        scroll_to_row = last_sel_row + 1
        if scroll_to_row < self.series_table.rowCount() - 1:
            scroll_to_row = scroll_to_row + 1
        self.series_table.scrollToItem(self.series_table.item(scroll_to_row, 0))
        self.renumber_series()

    def series_indent_change(self, delta: int):
        selection_model = self.series_table.selectionModel()
        assert selection_model is not None
        for row in selection_model.selectedRows():
            book = self.books[row.row()]
            series_indent = book.series_indent()
            if delta > 0:
                if series_indent < 2:
                    book.set_series_indent(series_indent + 1)
            else:
                if series_indent > 0:
                    book.set_series_indent(series_indent - 1)
            book.set_assigned_index(None)
        self.renumber_series()

    def sort_by(self, name: str):
        if name == "PubDate":
            self.books = sorted(
                self.books, key=lambda k: k.sort_key(sort_by_pubdate=True)
            )
        elif name == "Original Series Name":
            self.books = sorted(self.books, key=lambda k: k.sort_key(sort_by_name=True))
        else:
            self.books = sorted(self.books, key=lambda k: k.sort_key())
        self.renumber_series()

    def search_web(self, name: str):
        URLS = {
            "FantasticFiction": "http://www.fantasticfiction.co.uk/search/?searchfor=author&keywords={author}",
            "Goodreads": "http://www.goodreads.com/search/search?q={author}&search_type=books",
            "Google": "http://www.google.com/#sclient=psy&q=%22{author}%22+%22{title}%22",
            "Wikipedia": "http://en.wikipedia.org/w/index.php?title=Special%3ASearch&search={author}",
        }
        selection_model = self.series_table.selectionModel()
        assert selection_model is not None
        for row in selection_model.selectedRows():
            book = self.books[row.row()]
            safe_title = self.convert_to_search_text(book.title())
            safe_author = self.convert_author_to_search_text(book.authors()[0])
            url = (
                URLS[name]
                .replace("{title}", safe_title)
                .replace("{author}", safe_author)
            )
            open_url(QUrl(url))

    def convert_to_search_text(self, text: str, encoding: str = "utf-8"):
        # First we strip characters we will definitely not want to pass through.
        # Periods from author initials etc do not need to be supplied
        text = text.replace(".", "")
        # Now encode the text using Python function with chosen encoding
        text = quote_plus(text.encode(encoding, "ignore"))
        # If we ended up with double spaces as plus signs (++) replace them
        return text.replace("++", "+")

    def convert_author_to_search_text(self, author: str, encoding: str = "utf-8"):
        # We want to convert the author name to FN LN format if it is stored LN, FN
        # We do this because some websites (Kobo) have crappy search engines that
        # will not match Adams+Douglas but will match Douglas+Adams
        # Not really sure of the best way of determining if the user is using LN, FN
        # Approach will be to check the tweak and see if a comma is in the name

        # Comma separated author will be pipe delimited in Calibre database
        fn_ln_author = author
        if author.find(",") > -1:
            # This might be because of a FN LN,Jr - check the tweak
            sort_copy_method = tweaks["author_sort_copy_method"]
            if sort_copy_method == "invert":
                # Calibre default. Hence "probably" using FN LN format.
                fn_ln_author = author
            else:
                # We will assume that we need to switch the names from LN,FN to FN LN
                parts = author.split(",")
                surname = parts.pop(0)
                parts.append(surname)
                fn_ln_author = " ".join(parts).strip()
        return self.convert_to_search_text(fn_ln_author, encoding)

    def cell_changed(self, row: int, column: int):
        book = self.books[row]
        item = self.series_table.item(row, column)
        assert item is not None
        if column == 0:
            book.set_title(str(item.text()).strip())
        elif column == 2:
            qtdate = item.data(Qt.ItemDataRole.DisplayRole)
            book.set_pubdate(qt_to_dt(qtdate, as_utc=False))

    def item_selection_changed(self):
        row = self.series_table.currentRow()
        if row == -1:
            return
        has_assigned_index = False
        selection_model = self.series_table.selectionModel()
        assert selection_model is not None
        for row in selection_model.selectedRows():
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
    def __init__(self, parent: QWidget):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.fmt = tweaks["gui_pubdate_display_format"]
        if self.fmt is None:
            self.fmt = "MMM yyyy"

    def populate_table(self, books: list[Book]):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(books))
        header_labels = [
            _("Title"),
            _("Author(s)"),
            _("File path"),
            _("PubDate"),
            _("File timestamp"),
        ]
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        vert_header = self.verticalHeader()
        assert vert_header is not None
        vert_header.setDefaultSectionSize(24)
        horiz_header = self.horizontalHeader()
        assert horiz_header is not None
        horiz_header.setStretchLastSection(True)

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
        delegate = DateDelegate(self, tweak_name="gui_pubdate_display_format")
        self.setItemDelegateForColumn(3, delegate)

    def setMinimumColumnWidth(self, col: int, minimum: int):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row: int, book: Book):
        self.blockSignals(True)
        titleColumn = TitleWidgetItem(book)
        titleColumn.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        self.setItem(row, 0, titleColumn)
        authorColumn = AuthorsTableWidgetItem(book.authors, book.author_sort)
        self.setItem(row, 1, authorColumn)
        pathColumn = QTableWidgetItem(book.path)
        pathColumn.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        self.setItem(row, 2, pathColumn)
        self.setItem(
            row,
            3,
            DateTableWidgetItem(
                cast("dt.datetime", book.pubdate),
                is_read_only=True,
                default_to_today=False,
                fmt=self.fmt,
            ),
        )
        self.setItem(
            row,
            4,
            DateTableWidgetItem(
                dt.datetime(
                    book.datetime[0],
                    book.datetime[1],
                    book.datetime[2],
                    book.datetime[3],
                    book.datetime[4],
                    book.datetime[5],
                    book.datetime[6],
                    utc_tz,
                ),
                is_read_only=True,
                default_to_today=False,
            ),
        )
        self.blockSignals(False)


class ShowBooksNotInDeviceDatabaseDialog(SizePersistedDialog):
    def __init__(self, parent: ui.Main, books: list[Book]):
        SizePersistedDialog.__init__(
            self, parent, "kobo utilities plugin:not in device database dialog"
        )
        self.db = parent.library_view.model().db
        self.books = books
        self.blockSignals(True)

        self.initialize_controls()

        # Display the books in the table
        self.blockSignals(False)
        self.books_table.populate_table(books)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(_("Books not in device database"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(
            self, "images/manage_series.png", _("Books not in device database")
        )
        layout.addLayout(title_layout)

        # Main series table layout
        table_layout = QHBoxLayout()
        layout.addLayout(table_layout)

        self.books_table = BooksNotInDeviceDatabaseTableWidget(self)
        table_layout.addWidget(self.books_table)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)


class ShowReadingPositionChangesDialog(SizePersistedDialog):
    def __init__(
        self,
        parent: QWidget,
        plugin_action: KoboUtilitiesAction,
        reading_locations: dict[int, dict[str, Any]],
        db: LibraryDatabase,
        profileName: str | None,
        goodreads_sync_installed: bool = False,
    ):
        SizePersistedDialog.__init__(
            self, parent, "kobo utilities plugin:show reading position changes dialog"
        )
        self.plugin_action = plugin_action
        self.reading_locations = reading_locations
        self.blockSignals(True)
        self.help_anchor = "ShowReadingPositionChanges"
        self.db = db

        assert self.plugin_action.device is not None

        self.profileName = (
            self.plugin_action.device.profile.profileName
            if not profileName and self.plugin_action.device.profile is not None
            else profileName
        )
        self.deviceName = cfg.get_device_name(self.plugin_action.device.uuid)
        options = cfg.get_library_config(
            self.plugin_action.gui.current_db
        ).readingPositionChangesStore

        self.initialize_controls()

        # Display the books in the table
        self.blockSignals(False)
        self.reading_locations_table.populate_table(self.reading_locations)

        self.select_books_checkbox.setChecked(options.selectBooksInLibrary)
        update_goodreads_progress = options.updeateGoodreadsProgress
        self.update_goodreads_progress_checkbox.setChecked(update_goodreads_progress)
        if goodreads_sync_installed:
            self.update_goodreads_progress_checkbox_clicked(update_goodreads_progress)
        else:
            self.update_goodreads_progress_checkbox.setEnabled(False)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(_("Show reading position changes"))
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(
            self, "images/manage_series.png", _("Show reading position changes")
        )
        layout.addLayout(title_layout)

        # Main series table layout
        table_layout = QGridLayout()
        layout.addLayout(table_layout)

        table_layout.addWidget(
            QLabel(_("Profile: {0}").format(self.profileName)), 0, 0, 1, 1
        )
        table_layout.addWidget(
            QLabel(_("Device: {0}").format(self.deviceName)), 0, 2, 1, 1
        )

        self.reading_locations_table = ShowReadingPositionChangesTableWidget(
            self, self.db
        )
        table_layout.addWidget(self.reading_locations_table, 1, 0, 1, 4)

        self.select_books_checkbox = QCheckBox(_("Select updated books in library"))
        table_layout.addWidget(self.select_books_checkbox, 2, 0, 1, 2)

        self.update_goodreads_progress_checkbox = QCheckBox(
            _("Update Goodread reading progress")
        )
        self.update_goodreads_progress_checkbox.clicked.connect(
            self.update_goodreads_progress_checkbox_clicked
        )
        table_layout.addWidget(self.update_goodreads_progress_checkbox, 2, 1, 1, 2)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._ok_clicked)
        button_box.rejected.connect(self.reject)
        select_all_button = button_box.addButton(
            _("Select all"), QDialogButtonBox.ButtonRole.ResetRole
        )
        assert select_all_button is not None
        select_all_button.clicked.connect(self._select_all_clicked)
        clear_all_button = button_box.addButton(
            _("Clear all"), QDialogButtonBox.ButtonRole.ResetRole
        )
        assert clear_all_button is not None
        clear_all_button.clicked.connect(self._clear_all_clicked)

        layout.addWidget(button_box)

    def _ok_clicked(self):
        library_config = cfg.get_library_config(self.plugin_action.gui.current_db)
        library_config.readingPositionChangesStore.selectBooksInLibrary = (
            self.select_books_checkbox.isChecked()
        )
        library_config.readingPositionChangesStore.updeateGoodreadsProgress = (
            self.update_goodreads_progress_checkbox.isChecked()
        )
        cfg.set_library_config(self.plugin_action.gui.current_db, library_config)

        for i in range(len(self.reading_locations)):
            self.reading_locations_table.selectRow(i)
            item = self.reading_locations_table.item(i, 0)
            assert item is not None
            enabled = item.checkState() == Qt.CheckState.Checked
            debug("row=%d, enabled=%s" % (i, enabled))
            if not enabled:
                item = self.reading_locations_table.item(i, 7)
                assert item is not None
                book_id = item.data(Qt.ItemDataRole.DisplayRole)
                debug("row=%d, book_id=%s" % (i, book_id))
                del self.reading_locations[book_id]
        self.accept()
        return

    def _select_all_clicked(self):
        self.reading_locations_table.toggle_checkmarks(Qt.CheckState.Checked)

    def _clear_all_clicked(self):
        self.reading_locations_table.toggle_checkmarks(Qt.CheckState.Unchecked)

    def update_goodreads_progress_checkbox_clicked(self, checked: bool):
        self.select_books_checkbox.setEnabled(not checked)


class ShowReadingPositionChangesTableWidget(QTableWidget):
    def __init__(self, parent: ShowReadingPositionChangesDialog, db: LibraryDatabase):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.db = db

        custom_columns = cfg.get_column_names(
            parent.plugin_action.gui, parent.plugin_action.device
        )
        self.kobo_percentRead_column = custom_columns.percent_read
        self.last_read_column = custom_columns.last_read

    def populate_table(self, reading_positions: dict[int, dict[str, Any]]):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(reading_positions))
        header_labels = [
            "",
            _("Title"),
            _("Authors(s)"),
            _("Current %"),
            _("New %"),
            _("Current date"),
            _("New date"),
            _("Book ID"),
        ]
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        vert_header = self.verticalHeader()
        assert vert_header is not None
        vert_header.setDefaultSectionSize(24)
        horiz_header = self.horizontalHeader()
        assert horiz_header is not None
        horiz_header.setStretchLastSection(True)

        debug("reading_positions=", reading_positions)
        for row, (book_id, reading_position) in enumerate(reading_positions.items()):
            self.populate_table_row(row, book_id, reading_position)

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
        self.selectRow(0)
        delegate = DateDelegate(self)
        self.setItemDelegateForColumn(5, delegate)
        self.setItemDelegateForColumn(6, delegate)

    def setMinimumColumnWidth(self, col: int, minimum: int):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(
        self, row: int, book_id: int, reading_position: dict[str, Any]
    ):
        self.blockSignals(True)

        book = self.db.get_metadata(book_id, index_is_id=True, get_cover=False)

        self.setItem(row, 0, CheckableTableWidgetItem(True))

        titleColumn = QTableWidgetItem(reading_position["Title"])
        titleColumn.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        self.setItem(row, 1, titleColumn)

        authorColumn = AuthorsTableWidgetItem(book.authors, book.author_sort)
        self.setItem(row, 2, authorColumn)

        current_percentRead = None
        if self.kobo_percentRead_column:
            metadata = book.get_user_metadata(self.kobo_percentRead_column, True)
            assert metadata is not None
            current_percentRead = metadata["#value#"]
        current_percent = RatingTableWidgetItem(current_percentRead, is_read_only=True)
        current_percent.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.setItem(row, 3, current_percent)

        new_percentRead = 0
        if reading_position["ReadStatus"] == 1:
            new_percentRead = reading_position["___PercentRead"]
        elif reading_position["ReadStatus"] == 2:
            new_percentRead = 100
        new_percent = RatingTableWidgetItem(new_percentRead, is_read_only=True)
        new_percent.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.setItem(row, 4, new_percent)

        current_last_read = None
        if self.last_read_column:
            metadata = book.get_user_metadata(self.last_read_column, True)
            assert metadata is not None
            current_last_read = metadata["#value#"]
        if current_last_read:
            self.setItem(
                row,
                5,
                DateTableWidgetItem(
                    current_last_read, is_read_only=True, default_to_today=False
                ),
            )
        if reading_position["DateLastRead"] is not None:
            self.setItem(
                row,
                6,
                DateTableWidgetItem(
                    convert_kobo_date(reading_position["DateLastRead"]),
                    is_read_only=True,
                    default_to_today=False,
                ),
            )
        book_idColumn = RatingTableWidgetItem(book_id)
        self.setItem(row, 7, book_idColumn)
        self.blockSignals(False)

    def toggle_checkmarks(self, select: Qt.CheckState):
        for i in range(self.rowCount()):
            item = self.item(i, 0)
            assert item is not None
            item.setCheckState(select)


class OrderSeriesShelvesTableWidget(QTableWidget):
    def __init__(self, parent: QWidget):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.header_labels = [_("Collection/series name"), _("Books in collection")]
        self.shelves = {}

    def populate_table(self, shelves: list[dict[str, Any]]):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(shelves))
        self.setColumnCount(len(self.header_labels))
        self.setHorizontalHeaderLabels(self.header_labels)
        vert_header = self.verticalHeader()
        assert vert_header is not None
        vert_header.setDefaultSectionSize(24)
        horiz_header = self.horizontalHeader()
        assert horiz_header is not None
        horiz_header.setStretchLastSection(True)

        self.shelves = {}
        for row, shelf in enumerate(shelves):
            self.populate_table_row(row, shelf)
            self.shelves[row] = shelf

        self.resizeColumnToContents(0)
        self.setMinimumColumnWidth(0, 150)
        self.setColumnWidth(1, 150)
        self.setSortingEnabled(True)
        self.selectRow(0)

    def setMinimumColumnWidth(self, col: int, minimum: int):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row: int, shelf: dict[str, Any]):
        self.blockSignals(True)
        nameColumn = QTableWidgetItem(shelf["name"])
        nameColumn.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        nameColumn.setData(Qt.ItemDataRole.UserRole, row)
        self.setItem(row, 0, nameColumn)
        shelf_count = RatingTableWidgetItem(shelf["count"], is_read_only=True)
        shelf_count.setTextAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.setItem(row, 1, shelf_count)
        self.blockSignals(False)

    def get_shelves(self) -> list[dict[str, Any]]:
        shelves = []
        for row in range(self.rowCount()):
            rnum = self.item(row, 0).data(Qt.ItemDataRole.UserRole)  # type: ignore[reportOptionalMemberAccess]
            shelf = self.shelves[rnum]
            shelves.append(shelf)
        return shelves

    def remove_selected_rows(self):
        self.setFocus()
        rows = self.selectionModel().selectedRows()  # type: ignore[reportOptionalMemberAccess]
        if len(rows) == 0:
            return
        first_sel_row = self.currentRow()
        for selrow in reversed(rows):
            self.removeRow(selrow.row())
        if first_sel_row < self.rowCount():
            self.select_and_scroll_to_row(first_sel_row)
        elif self.rowCount() > 0:
            self.select_and_scroll_to_row(first_sel_row - 1)

    def select_and_scroll_to_row(self, row: int):
        self.selectRow(row)
        self.scrollToItem(self.currentItem())


class SetRelatedBooksDialog(SizePersistedDialog):
    def __init__(
        self,
        parent: ui.Main,
        plugin_action: KoboUtilitiesAction,
        related_types: list[dict[str, Any]],
    ):
        SizePersistedDialog.__init__(
            self, parent, "kobo utilities plugin:set related books dialog"
        )
        self.plugin_action = plugin_action
        self.related_types = related_types
        self.blockSignals(True)
        self.help_anchor = "SetRelatedBooks"
        self.dialog_title = _("Set related books")

        self.initialize_controls()

        self.related_category = (
            cfg.plugin_prefs.setRelatedBooksOptionsStore.relatedBooksType
        )
        self.deleteAllRelatedBooks = False
        button = self.related_categories_option_button_group.button(
            self.related_category
        )
        assert button is not None
        button.setChecked(True)

        # Display the books in the table
        self.blockSignals(False)
        self.related_types_table.populate_table(self.related_types)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()

    def initialize_controls(self):
        self.setWindowTitle(GUI_NAME)
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(
            self, "images/manage_series.png", self.dialog_title
        )
        layout.addLayout(title_layout)

        related_categories_option_group_box = QGroupBox(_("Related books type"), self)
        layout.addWidget(related_categories_option_group_box)

        related_categories_options = {
            cfg.RelatedBooksType.Series.value: (
                _("Series"),
                _("The related books will be all books in a series."),
                True,
            ),
            cfg.RelatedBooksType.Authors.value: (
                _("Authors"),
                _("The related books will be all books by the same author."),
                False,
            ),
        }

        related_categories_option_group_box_layout = QHBoxLayout()
        related_categories_option_group_box.setLayout(
            related_categories_option_group_box_layout
        )
        self.related_categories_option_button_group = QButtonGroup(self)
        self.related_categories_option_button_group.buttonClicked[int].connect(
            self._related_categories_option_radio_clicked
        )
        for clean_option in related_categories_options:
            clean_options = related_categories_options[clean_option]
            rdo = QRadioButton(clean_options[0], self)
            rdo.setToolTip(clean_options[1])
            self.related_categories_option_button_group.addButton(rdo)
            self.related_categories_option_button_group.setId(rdo, clean_option)
            related_categories_option_group_box_layout.addWidget(rdo)

        self.fetch_button = QPushButton(_("Get list"), self)
        self.fetch_button.setToolTip(
            _("Get the list of categories to use for the related books")
        )
        self.fetch_button.clicked.connect(self.fetch_button_clicked)
        related_categories_option_group_box_layout.addWidget(self.fetch_button)

        # Main series table layout
        table_layout = QHBoxLayout()
        layout.addLayout(table_layout)

        self.related_types_table = OrderSeriesShelvesTableWidget(self)
        self.related_types_table.header_labels = [
            _("Series/author name"),
            _("Number of books"),
        ]
        table_layout.addWidget(self.related_types_table)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._ok_clicked)
        button_box.rejected.connect(self.reject)
        remove_selected_button = button_box.addButton(
            _("Remove"), QDialogButtonBox.ButtonRole.ResetRole
        )
        assert remove_selected_button is not None
        remove_selected_button.setToolTip(
            _(
                "Remove the selected category from the list. This will mean related books will not be changed for that category."
            )
        )
        remove_selected_button.clicked.connect(self._remove_selected_clicked)
        delete_related_button = button_box.addButton(
            _("Delete all"), QDialogButtonBox.ButtonRole.ActionRole
        )
        assert delete_related_button is not None
        delete_related_button.setToolTip(
            _("Delete all related books for sideloaded books.")
        )
        delete_related_button.clicked.connect(self._delete_related_clicked)
        layout.addWidget(button_box)

    def _ok_clicked(self):
        cfg.plugin_prefs.setRelatedBooksOptionsStore.relatedBooksType = (
            cfg.RelatedBooksType(self.related_category)
        )
        self.accept()
        return

    def _related_categories_option_radio_clicked(self, idx: int):
        self.related_category = idx

    def fetch_button_clicked(self):
        self.related_types = self.plugin_action._get_related_books_count(
            self.related_category
        )
        self.related_types_table.populate_table(self.related_types)
        return

    def _remove_selected_clicked(self):
        self.related_types_table.remove_selected_rows()

    def _delete_related_clicked(self):
        mb = question_dialog(
            self,
            self.dialog_title,
            _("Do you want to remove related books for all sideloaded books?"),
            show_copy_button=False,
        )
        if not mb:
            return

        self.deleteAllRelatedBooks = True
        self.accept()
        return

    def get_related_types(self):
        return self.related_types_table.get_shelves()


class ReadingStatusGroupBox(QGroupBox):
    def __init__(self, parent: QWidget):
        QGroupBox.__init__(self, parent)

        self.setTitle(_("Reading status"))
        options_layout = QGridLayout()
        self.setLayout(options_layout)

        self.reading_status_checkbox = QCheckBox(_("Change reading status"), self)
        options_layout.addWidget(self.reading_status_checkbox, 0, 0, 1, 2)
        self.reading_status_checkbox.clicked.connect(
            self.reading_status_checkbox_clicked
        )

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
        self.reset_position_checkbox.setToolTip(
            _(
                "If this option is checked, the current position and last reading date will be reset."
            )
        )

    def reading_status_checkbox_clicked(self, checked: bool):
        self.unread_radiobutton.setEnabled(checked)
        self.reading_radiobutton.setEnabled(checked)
        self.finished_radiobutton.setEnabled(checked)
        self.reset_position_checkbox.setEnabled(checked)

    def readingStatusIsChecked(self):
        return self.reading_status_checkbox.isChecked()

    def readingStatus(self):
        readingStatus = -1
        if self.unread_radiobutton.isChecked():
            readingStatus = 0
        elif self.reading_radiobutton.isChecked():
            readingStatus = 1
        elif self.finished_radiobutton.isChecked():
            readingStatus = 2

        return readingStatus


class UpdateBooksToCDialog(SizePersistedDialog):
    def __init__(
        self,
        parent: ui.Main,
        plugin_action: KoboUtilitiesAction,
        icon: QIcon,
        books: list[dict[str, Any]],
    ):
        del icon
        super().__init__(
            parent,
            "kobo utilities plugin:update book toc dialog",
            plugin_action=plugin_action,
        )
        self.plugin_action = plugin_action

        self.setWindowTitle(GUI_NAME)

        layout = QVBoxLayout(self)
        self.setLayout(layout)
        title_layout = ImageTitleLayout(
            self, "toc.png", _("Update ToCs in device database")
        )
        layout.addLayout(title_layout)

        self.books_table = ToCBookListTableWidget(self)
        layout.addWidget(self.books_table)

        options_layout = QHBoxLayout()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.update_button_clicked)
        button_box.rejected.connect(self.reject)
        update_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        assert update_button is not None
        update_button.setText(_("Update ToC"))
        update_button.setToolTip(_("Update ToC in device database for selected books."))

        remove_button = button_box.addButton(
            _("Remove"), QDialogButtonBox.ButtonRole.ActionRole
        )
        assert remove_button is not None
        remove_button.setToolTip(_("Remove selected books from the list"))
        remove_button.setIcon(get_icon("list_remove.png"))
        remove_button.clicked.connect(self.remove_from_list)

        send_books_button = button_box.addButton(
            _("Send books"), QDialogButtonBox.ButtonRole.ActionRole
        )
        assert send_books_button is not None
        send_books_button.setToolTip(
            _("Send books to device that have been updated in the library.")
        )
        send_books_button.clicked.connect(self.send_books_clicked)

        select_all_button = button_box.addButton(
            _("Select all"), QDialogButtonBox.ButtonRole.ResetRole
        )
        assert select_all_button is not None
        select_all_button.clicked.connect(self._select_all_clicked)
        select_all_button.setToolTip(_("Select all books in the list."))

        select_books_to_send_button = button_box.addButton(
            _("Select books to send"), QDialogButtonBox.ButtonRole.ResetRole
        )
        assert select_books_to_send_button is not None
        select_books_to_send_button.clicked.connect(self._select_books_to_send_clicked)
        select_books_to_send_button.setToolTip(
            _("Select all books that need to be sent to the device.")
        )

        select_books_to_update_button = button_box.addButton(
            _("Select books to update"), QDialogButtonBox.ButtonRole.ResetRole
        )
        assert select_books_to_update_button is not None
        select_books_to_update_button.clicked.connect(
            self._select_books_to_update_clicked
        )
        select_books_to_update_button.setToolTip(_("Select all books in the list."))

        clear_all_button = button_box.addButton(
            _("Clear all"), QDialogButtonBox.ButtonRole.ResetRole
        )
        assert clear_all_button is not None
        clear_all_button.clicked.connect(self._clear_all_clicked)
        clear_all_button.setToolTip(_("Unselect all books in the list."))

        options_layout.addWidget(button_box)

        layout.addLayout(options_layout)

        # Cause our dialog size to be restored from prefs or created on first usage
        self.resize_dialog()
        self.books_table.populate_table(books)

    def remove_from_list(self):
        self.books_table.remove_selected_rows()

    def send_books_clicked(self):
        books_to_send = self.books_table.books_to_send
        ids_to_sync = [book["calibre_id"] for book in books_to_send]
        debug("ids_to_sync=", ids_to_sync)
        parent = self.parent()
        assert isinstance(parent, ui.Main)
        if not question_dialog(
            self.parent(),
            _("Update books"),
            "<p>"
            + _(
                "There are {0} books that need to be updated on the device. "
                "After the book has been sent to the device, you can run the check and update the ToC."
                "<br/>"
                "Do you want to send the books to the device?"
            ).format(len(ids_to_sync)),
            show_copy_button=False,
        ):
            return
        parent.sync_to_device(
            on_card=None, delete_from_library=False, send_ids=ids_to_sync
        )
        self.reject()

    def update_button_clicked(self):
        books_to_send = self.books_to_update_toc
        ids_to_sync = [book["calibre_id"] for book in books_to_send]
        debug("ids_to_sync=", ids_to_sync)
        if not question_dialog(
            self.parent(),
            _("Update books"),
            "<p>"
            + _(
                "There are {0} books that need to have their ToC updated on the device. "
                "Any selected books that have not been imported into the database on the device are ignored."
                "<br/>"
                "Do you want to update the ToC in the database on the device?"
            ).format(len(ids_to_sync)),
            show_copy_button=False,
        ):
            return
        self.accept()

    def _select_books_to_send_clicked(self):
        self.books_table.select_checkmarks_send()

    def _select_books_to_update_clicked(self):
        self.books_table.select_checkmarks_update_toc()

    def _select_all_clicked(self):
        self.books_table.toggle_checkmarks(Qt.CheckState.Checked)

    def _clear_all_clicked(self):
        self.books_table.toggle_checkmarks(Qt.CheckState.Unchecked)

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

    HEADER_LABELS_DICT = MappingProxyType(
        {
            STATUS_COLUMN_NO: "",
            TITLE_COLUMN_NO: _("Title"),
            AUTHOR_COLUMN_NO: _("Author"),
            LIBRARY_CHAPTERS_COUNT_COLUMN_NO: _("Library ToC"),
            LIBRARY_FORMAT_COLUMN_NO: _("Library format"),
            KOBO_DISC_CHAPTERS_COUNT_COLUMN_NO: _("Kobo ToC"),
            KOBO_DISC_FORMAT_COLUMN_NO: _("Kobo format"),
            KOBO_DISC_STATUS_COLUMN_NO: _("Status"),
            SEND_TO_DEVICE_COLUMN_NO: _("Send"),
            KOBO_DATABASE_CHAPTERS_COUNT_COLUMN_NO: _("Kobo database ToC"),
            KOBO_DATABASE_STATUS_COLUMN_NO: _("Status"),
            UPDATE_TOC_COLUMN_NO: _("ToC"),
            READING_POSITION_COLUMN_NO: _("Reading position"),
            STATUS_COMMENT_COLUMN_NO: _("Comment"),
        }
    )

    def __init__(self, parent: QWidget):
        QTableWidget.__init__(self, parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.books = {}

    def populate_table(self, books: list[dict[str, Any]]):
        self.clear()
        self.setAlternatingRowColors(True)
        self.setRowCount(len(books))
        header_labels = [
            self.HEADER_LABELS_DICT[header_index]
            for header_index in sorted(self.HEADER_LABELS_DICT.keys())
        ]
        self.setColumnCount(len(header_labels))
        self.setHorizontalHeaderLabels(header_labels)
        horiz_header = self.horizontalHeader()
        assert horiz_header is not None
        horiz_header.setStretchLastSection(True)
        vert_header = self.verticalHeader()
        assert vert_header is not None
        vert_header.hide()

        self.books: dict[int, dict[str, Any]] = {}
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
        self.sortItems(1)
        self.sortItems(0)

    def setMinimumColumnWidth(self, col: int, minimum: int):
        if self.columnWidth(col) < minimum:
            self.setColumnWidth(col, minimum)

    def populate_table_row(self, row: int, book: dict[str, Any]):
        book_status = 0
        if book["good"]:
            icon = get_icon("ok.png")
            book_status = 0
        else:
            icon = get_icon("minus.png")
            book_status = 1
        if "icon" in book:
            icon = get_icon(book["icon"])

        status_cell = IconWidgetItem(None, icon, book_status)
        status_cell.setData(Qt.ItemDataRole.UserRole, book_status)
        self.setItem(row, 0, status_cell)

        title_cell = ReadOnlyTableWidgetItem(book["title"])
        title_cell.setData(Qt.ItemDataRole.UserRole, row)
        self.setItem(row, self.TITLE_COLUMN_NO, title_cell)

        self.setItem(
            row,
            self.AUTHOR_COLUMN_NO,
            AuthorTableWidgetItem(book["author"], book["author_sort"]),
        )

        if "library_chapters" in book and len(book["library_chapters"]) > 0:
            library_chapters_count = ReadOnlyTableWidgetItem(
                str(len(book["library_chapters"]))
            )
            library_chapters_count.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.setItem(
                row, self.LIBRARY_CHAPTERS_COUNT_COLUMN_NO, library_chapters_count
            )

        if "library_format" in book:
            library_format = ReadOnlyTableWidgetItem(str(book["library_format"]))
            library_format.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )
            self.setItem(row, self.LIBRARY_FORMAT_COLUMN_NO, library_format)

        if "kobo_chapters" in book and len(book["kobo_chapters"]) > 0:
            kobo_chapters_count = ReadOnlyTableWidgetItem(
                str(len(book["kobo_chapters"]))
            )
            kobo_chapters_count.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.setItem(
                row, self.KOBO_DISC_CHAPTERS_COUNT_COLUMN_NO, kobo_chapters_count
            )

        if "kobo_format" in book:
            kobo_format = ReadOnlyTableWidgetItem(str(book["kobo_format"]))
            kobo_format.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )
            self.setItem(row, self.KOBO_DISC_FORMAT_COLUMN_NO, kobo_format)

        kobo_format_status = 0
        if "kobo_format_status" in book:
            if book["kobo_format_status"]:
                icon = get_icon("ok.png")
                kobo_format_status = 0
            else:
                icon = get_icon("sync.png")
                kobo_format_status = 1
            kobo_format_status_cell = IconWidgetItem(None, icon, kobo_format_status)
            kobo_format_status_cell.setData(
                Qt.ItemDataRole.UserRole, kobo_format_status
            )
            self.setItem(row, self.KOBO_DISC_STATUS_COLUMN_NO, kobo_format_status_cell)

        kobo_disc_status = kobo_format_status == 1 and not book["good"]
        kobo_disc_status_cell = CheckableTableWidgetItem(checked=kobo_disc_status)
        kobo_disc_status_cell.setData(Qt.ItemDataRole.UserRole, kobo_disc_status)
        self.setItem(row, self.SEND_TO_DEVICE_COLUMN_NO, kobo_disc_status_cell)

        if "kobo_database_chapters" in book and len(book["kobo_database_chapters"]) > 0:
            kobo_database_chapters_count = ReadOnlyTableWidgetItem(
                str(len(book["kobo_database_chapters"]))
            )
            kobo_database_chapters_count.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.setItem(
                row,
                self.KOBO_DATABASE_CHAPTERS_COUNT_COLUMN_NO,
                kobo_database_chapters_count,
            )

        kobo_database_status = 0
        icon_name = "window-close.png"
        if "kobo_database_status" in book:
            if not book["can_update_toc"]:
                kobo_database_status = 0
                icon_name = "window-close.png"
            elif book["kobo_database_status"]:
                kobo_database_status = 0
                icon_name = "ok.png"
            else:
                kobo_database_status = 1
                icon_name = "toc.png"
        icon = get_icon(icon_name)
        kobo_database_status_cell = IconWidgetItem(None, icon, kobo_database_status)
        kobo_database_status_cell.setData(
            Qt.ItemDataRole.UserRole, kobo_database_status
        )
        self.setItem(
            row, self.KOBO_DATABASE_STATUS_COLUMN_NO, kobo_database_status_cell
        )

        update_toc = kobo_database_status == 1 and book["can_update_toc"]
        update_toc_cell = CheckableTableWidgetItem(checked=update_toc)
        update_toc_cell.setData(Qt.ItemDataRole.UserRole, update_toc)
        self.setItem(row, self.UPDATE_TOC_COLUMN_NO, update_toc_cell)

        if (
            "koboDatabaseReadingLocation" in book
            and len(book["koboDatabaseReadingLocation"]) > 0
        ):
            koboDatabaseReadingLocation = ReadOnlyTableWidgetItem(
                book["koboDatabaseReadingLocation"]
            )
            self.setItem(
                row, self.READING_POSITION_COLUMN_NO, koboDatabaseReadingLocation
            )

        comment_cell = ReadOnlyTableWidgetItem(book["comment"])
        self.setItem(row, self.STATUS_COMMENT_COLUMN_NO, comment_cell)

    @property
    def books_to_update_toc(self) -> list[dict[str, Any]]:
        books = []
        for row in range(self.rowCount()):
            if cast(
                "CheckableTableWidgetItem", self.item(row, self.UPDATE_TOC_COLUMN_NO)
            ).get_boolean_value():
                item = self.item(row, self.TITLE_COLUMN_NO)
                assert item is not None
                rnum = item.data(Qt.ItemDataRole.UserRole)
                book = self.books[rnum]
                if book["can_update_toc"]:
                    books.append(book)
        return books

    @property
    def books_to_send(self) -> list[dict[str, Any]]:
        books = []
        for row in range(self.rowCount()):
            if cast(
                "CheckableTableWidgetItem",
                self.item(row, self.SEND_TO_DEVICE_COLUMN_NO),
            ).get_boolean_value():
                item = self.item(row, self.TITLE_COLUMN_NO)
                assert item is not None
                rnum = item.data(Qt.ItemDataRole.UserRole)
                book = self.books[rnum]
                books.append(book)
        return books

    def remove_selected_rows(self):
        self.setFocus()
        selection_model = self.selectionModel()
        assert selection_model is not None
        rows = selection_model.selectedRows()
        if len(rows) == 0:
            return
        message = "<p>Are you sure you want to remove this book from the list?"
        if len(rows) > 1:
            message = (
                "<p>Are you sure you want to remove the selected %d books from the list?"
                % len(rows)
            )
        if not confirm(message, "kobo_utilities_plugin_tocupdate_delete_item", self):
            return
        first_sel_row = self.currentRow()
        for selrow in reversed(rows):
            self.removeRow(selrow.row())
        if first_sel_row < self.rowCount():
            self.select_and_scroll_to_row(first_sel_row)
        elif self.rowCount() > 0:
            self.select_and_scroll_to_row(first_sel_row - 1)

    def select_and_scroll_to_row(self, row: int):
        self.selectRow(row)
        self.scrollToItem(self.currentItem())

    def toggle_checkmarks(self, select: Qt.CheckState):
        for i in range(self.rowCount()):
            item = self.item(i, self.UPDATE_TOC_COLUMN_NO)
            assert item is not None
            item.setCheckState(select)
        for i in range(self.rowCount()):
            item = self.item(i, self.SEND_TO_DEVICE_COLUMN_NO)
            assert item is not None
            item.setCheckState(select)

    def select_checkmarks_send(self):
        for i in range(self.rowCount()):
            item = self.item(i, 1)
            assert item is not None
            rnum = item.data(Qt.ItemDataRole.UserRole)
            debug("rnum=%s, book=%s" % (rnum, self.books[rnum]))
            item = self.item(i, self.SEND_TO_DEVICE_COLUMN_NO)
            assert item is not None
            item.setCheckState(
                Qt.CheckState.Unchecked
                if self.books[rnum]["kobo_format_status"]
                else Qt.CheckState.Checked
            )

    def select_checkmarks_update_toc(self):
        for i in range(self.rowCount()):
            item = self.item(i, 1)
            assert item is not None
            book_no = item.data(Qt.ItemDataRole.UserRole)
            debug("book_no=%s, book=%s" % (book_no, self.books[book_no]))
            check_for_toc = (
                not self.books[book_no]["kobo_database_status"]
                and self.books[book_no]["can_update_toc"]
            )
            item = self.item(i, self.UPDATE_TOC_COLUMN_NO)
            assert item is not None
            item.setCheckState(
                Qt.CheckState.Checked if check_for_toc else Qt.CheckState.Unchecked
            )


class IconWidgetItem(ReadOnlyTextIconWidgetItem):
    def __init__(self, text: str | None, icon: QIcon, sort_key: int):
        super().__init__(text, icon)
        self.sort_key = sort_key

    # Qt uses a simple < check for sorting items, override this to use the sortKey
    def __lt__(self, other: Any):
        if isinstance(other, IconWidgetItem):
            return self.sort_key < other.sort_key
        return super().__lt__(other)


class AboutDialog(QDialog):
    def __init__(self, parent: ui.Main, icon: QIcon, text: str):
        QDialog.__init__(self, parent)
        self.resize(500, 300)
        self.l = QGridLayout()
        self.setLayout(self.l)
        self.logo = QLabel()
        self.logo.setMaximumWidth(110)
        self.logo.setPixmap(QPixmap(icon.pixmap(100, 100)))
        self.label = QLabel(text)
        self.label.setOpenExternalLinks(True)
        self.label.setWordWrap(True)
        self.label.setTextFormat(Qt.TextFormat.MarkdownText)
        self.setWindowTitle(_("About {}").format(GUI_NAME))
        self.setWindowIcon(icon)
        self.l.addWidget(self.logo, 0, 0)
        self.l.addWidget(self.label, 0, 1)
        self.bb = QDialogButtonBox(self)
        b = self.bb.addButton(_(_("OK")), self.bb.ButtonRole.AcceptRole)
        assert b is not None
        b.setDefault(True)
        self.l.addWidget(self.bb, 2, 0, 1, -1)
        self.bb.accepted.connect(self.accept)
