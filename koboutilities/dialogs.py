# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

from __future__ import annotations

__license__ = "GPL v3"
__copyright__ = "2012-2020, David Forrester <davidfor@internode.on.net>"
__docformat__ = "restructuredtext en"

from typing import (
    TYPE_CHECKING,
    Any,
)

from qt.core import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QIcon,
    QLabel,
    QPixmap,
    QRadioButton,
    Qt,
    QTableWidgetItem,
    QWidget,
)

from .constants import GUI_NAME
from .utils import (
    ReadOnlyTableWidgetItem,
)

if TYPE_CHECKING:
    from calibre.devices.kobo.books import Book
    from calibre.gui2 import ui


# pulls in translation files for _() strings
load_translations()


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
