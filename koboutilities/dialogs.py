# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

from __future__ import annotations

__license__ = "GPL v3"
__copyright__ = "2012-2020, David Forrester <davidfor@internode.on.net>"
__docformat__ = "restructuredtext en"

import datetime as dt
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    cast,
)

from calibre.ebooks.metadata import authors_to_string
from calibre.gui2 import choose_dir, error_dialog, question_dialog, ui
from calibre.gui2.library.delegates import DateDelegate
from calibre.utils.config import tweaks
from calibre.utils.date import utc_tz
from qt.core import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QIcon,
    QLabel,
    QLineEdit,
    QPixmap,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    Qt,
    QTableWidget,
    QTableWidgetItem,
    QTimer,
    QVBoxLayout,
    QWidget,
)

from . import config as cfg
from .constants import BOOK_CONTENTTYPE, GUI_NAME
from .utils import (
    CustomColumnComboBox,
    DateTableWidgetItem,
    ImageTitleLayout,
    RatingTableWidgetItem,
    ReadOnlyTableWidgetItem,
    SizePersistedDialog,
    contentid_from_path,
    convert_calibre_ids_to_books,
    debug,
    get_books_for_selected,
    get_device_paths_from_id,
    get_selected_ids,
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
                self.books = get_books_for_selected(self.gui)
            else:
                onDeviceIds = get_selected_ids(self.gui)
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
            plugin_action.load_resources,
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


class BackupAnnotationsOptionsDialog(SizePersistedDialog):
    def __init__(self, parent: QWidget, plugin_action: KoboUtilitiesAction):
        SizePersistedDialog.__init__(
            self,
            parent,
            "kobo utilities plugin:backup annotation files settings dialog",
            plugin_action.load_resources,
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
            plugin_action.load_resources,
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


class TitleWidgetItem(QTableWidgetItem):
    def __init__(self, book: Book):
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
    def __init__(
        self, parent: ui.Main, plugin_action: KoboUtilitiesAction, books: list[Book]
    ):
        SizePersistedDialog.__init__(
            self,
            parent,
            "kobo utilities plugin:not in device database dialog",
            plugin_action.load_resources,
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
            self,
            parent,
            "kobo utilities plugin:set related books dialog",
            plugin_action.load_resources,
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
