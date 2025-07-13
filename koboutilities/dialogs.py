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
from calibre.gui2 import choose_dir, error_dialog, ui
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
    DateTableWidgetItem,
    ImageTitleLayout,
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
