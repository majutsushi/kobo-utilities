#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2011, Grant Drake <grant.drake@gmail.com>, 2012-2022 updates by David Forrester <davidfor@internode.on.net>'
__docformat__ = 'restructuredtext en'

import os, time

# calibre Python 3 compatibility.
import six
from six import text_type as unicode

try:
    from PyQt5.Qt import (Qt, QIcon, QPixmap, QLabel, QDialog, QHBoxLayout, QProgressBar,
                          QTableWidgetItem, QFont, QLineEdit, QComboBox, QListWidget,
                          QVBoxLayout, QDialogButtonBox, QStyledItemDelegate, QDateTime,
                          QTextEdit, QAbstractItemView
                          )
except ImportError:
    from PyQt4.Qt import (Qt, QIcon, QPixmap, QLabel, QDialog, QHBoxLayout, QProgressBar,
                          QTableWidgetItem, QFont, QLineEdit, QComboBox, QListWidget,
                          QVBoxLayout, QDialogButtonBox, QStyledItemDelegate, QDateTime,
                          QTextEdit, QAbstractItemView
                          )

from calibre.constants import iswindows, DEBUG
from calibre.gui2 import gprefs, error_dialog, info_dialog, UNDEFINED_QDATETIME, Application
from calibre.gui2.actions import menu_action_unique_name
from calibre.gui2.keyboard import ShortcutConfig
from calibre.utils.config import config_dir
from calibre.utils.date import now, format_date, UNDEFINED_DATE
from calibre import prints

try:
    from calibre.gui2 import QVariant
    del QVariant
except ImportError:
    is_qt4 = False
    convert_qvariant = lambda x: x
else:
    is_qt4 = True

    def convert_qvariant(x):
        vt = x.type()
        if vt == x.String:
            return unicode(x.toString())
        if vt == x.List:
            return [convert_qvariant(i) for i in x.toList()]
        return x.toPyObject()

# Global definition of our plugin name. Used for common functions that require this.
plugin_name = None
# Global definition of our plugin resources. Used to share between the xxxAction and xxxBase
# classes if you need any zip images to be displayed on the configuration dialog.
plugin_icon_resources = {}

BASE_TIME = None
def debug_print(*args):
    global BASE_TIME
    if BASE_TIME is None:
        BASE_TIME = time.time()
    if DEBUG:
        prints('DEBUG: %6.1f'%(time.time()-BASE_TIME), *args)


def set_plugin_icon_resources(name, resources):
    '''
    Set our global store of plugin name and icon resources for sharing between
    the InterfaceAction class which reads them and the ConfigWidget
    if needed for use on the customization dialog for this plugin.
    '''
    global plugin_icon_resources, plugin_name
    plugin_name = name
    plugin_icon_resources = resources


def get_icon(icon_name):
    '''
    Retrieve a QIcon for the named image from the zip file if it exists,
    or if not then from Calibre's image cache.
    '''
    if icon_name:
        pixmap = get_pixmap(icon_name)
        if pixmap is None:
            # Look in Calibre's cache for the icon
            return QIcon(I(icon_name))
        else:
            return QIcon(pixmap)
    return QIcon()


def get_pixmap(icon_name):
    '''
    Retrieve a QPixmap for the named image
    Any icons belonging to the plugin must be prefixed with 'images/'
    '''
    global plugin_icon_resources, plugin_name

    if not icon_name.startswith('images/'):
        # We know this is definitely not an icon belonging to this plugin
        pixmap = QPixmap()
        pixmap.load(I(icon_name))
        return pixmap

    # Check to see whether the icon exists as a Calibre resource
    # This will enable skinning if the user stores icons within a folder like:
    # ...\AppData\Roaming\calibre\resources\images\Plugin Name\
    if plugin_name:
        local_images_dir = get_local_images_dir(plugin_name)
        local_image_path = os.path.join(local_images_dir, icon_name.replace('images/', ''))
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


def get_local_images_dir(subfolder=None):
    '''
    Returns a path to the user's local resources/images folder
    If a subfolder name parameter is specified, appends this to the path
    '''
    images_dir = os.path.join(config_dir, 'resources/images')
    if subfolder:
        images_dir = os.path.join(images_dir, subfolder)
    if iswindows:
        images_dir = os.path.normpath(images_dir)
    return images_dir


def create_menu_item(ia, parent_menu, menu_text, image=None, tooltip=None,
                     shortcut=(), triggered=None, is_checked=None):
    '''
    Create a menu action with the specified criteria and action
    Note that if no shortcut is specified, will not appear in Preferences->Keyboard
    This method should only be used for actions which either have no shortcuts,
    or register their menus only once. Use create_menu_action_unique for all else.
    '''
    if shortcut is not None:
        if len(shortcut) == 0:
            shortcut = ()
        else:
            shortcut = _(shortcut)
    ac = ia.create_action(spec=(menu_text, None, tooltip, shortcut),
        attr=menu_text)
    if image:
        ac.setIcon(get_icon(image))
    if triggered is not None:
        ac.triggered.connect(triggered)
    if is_checked is not None:
        ac.setCheckable(True)
        if is_checked:
            ac.setChecked(True)

    parent_menu.addAction(ac)
    return ac


def create_menu_action_unique(ia, parent_menu, menu_text, image=None, tooltip=None,
                       shortcut=None, triggered=None, is_checked=None, shortcut_name=None,
                       unique_name=None, favourites_menu_unique_name=None):
    '''
    Create a menu action with the specified criteria and action, using the new
    InterfaceAction.create_menu_action() function which ensures that regardless of
    whether a shortcut is specified it will appear in Preferences->Keyboard
    '''
    orig_shortcut = shortcut
    kb = ia.gui.keyboard
    if unique_name is None:
        unique_name = menu_text
    if not shortcut == False:
        full_unique_name = menu_action_unique_name(ia, unique_name)
        if full_unique_name in kb.shortcuts:
            shortcut = False
        else:
            if shortcut is not None and not shortcut == False:
                if len(shortcut) == 0:
                    shortcut = None
                else:
                    shortcut = _(shortcut)

    if shortcut_name is None:
        shortcut_name = menu_text.replace('&','')

    ac = ia.create_menu_action(parent_menu, unique_name, menu_text, icon=None, shortcut=shortcut,
        description=tooltip, triggered=triggered, shortcut_name=shortcut_name)
    if shortcut == False and not orig_shortcut == False:
        if ac.calibre_shortcut_unique_name in ia.gui.keyboard.shortcuts:
            kb.replace_action(ac.calibre_shortcut_unique_name, ac)
    if image:
        ac.setIcon(get_icon(image))
    if is_checked is not None:
        ac.setCheckable(True)
        if is_checked:
            ac.setChecked(True)
    # For use by the Favourites Menu plugin. If this menu action has text
    # that is not constant through the life of this plugin, then we need
    # to attribute it with something that will be constant that the
    # Favourites Menu plugin can use to identify it.
    if favourites_menu_unique_name:
        ac.favourites_menu_unique_name = favourites_menu_unique_name
    return ac


def get_library_uuid(db):
    try:
        library_uuid = db.library_id
    except:
        library_uuid = ''
    return library_uuid


def call_plugin_callback(plugin_callback, parent, plugin_results=None):
    '''
    This function executes a callback to a calling plugin. Because this 
    can be called after a job has been run, the plugin and callback function 
    are passed as strings.
    
    The parameters are:

      plugin_callback - This is a dictionary definging the callbak function.
          The elements are:
              plugin_name - name of the plugin to be called
              func_name - name of the functio to be called
              args - Arguments to be passedd to the callback function. Will be
                  passed as "*args" so must be a collection if it is supplied.
              kwargs - Keyword arguments to be passedd to the callback function.
                  Will be passed as "**kargs" so must be a dictionary if it 
                  is supplied.

      parent - parent gui needed to find the plugin.

      plugin_results - Results to be passed to the plugin.
      
    If the kwargs dictionary contains an entry for "plugin_results", the value
    will be replaced by the parameter "plugin_results". This allows the results
    of the called plugin to be passed to the callback. 
    '''
    print("call_plugin_callback: have callback:", plugin_callback)
    from calibre.customize.ui import find_plugin
    plugin = find_plugin (plugin_callback['plugin_name'])
    if plugin is not None:
        print("call_plugin_callback: have plugin for callback:", plugin)
        callback_func = getattr(plugin.load_actual_plugin(parent), plugin_callback['func_name'])
        args = plugin_callback['args'] if 'args'  in plugin_callback else []
        kwargs = plugin_callback['kwargs'] if 'kwargs' in plugin_callback else {}
        if 'plugin_results' in kwargs and plugin_results:
            kwargs['plugin_results'] = plugin_results
        print("call_plugin_callback: about to call callback - kwargs=", kwargs)
        callback_func(*args, **kwargs)


class ImageLabel(QLabel):

    def __init__(self, parent, icon_name, size=16):
        super(ImageLabel,self).__init__(parent)
        pixmap = get_pixmap(icon_name)
        self.setPixmap(pixmap)
        self.setMaximumSize(size, size)
        self.setScaledContents(True)


class ImageTitleLayout(QHBoxLayout):
    '''
    A reusable layout widget displaying an image followed by a title
    '''
    def __init__(self, parent, icon_name, title):
        super(ImageTitleLayout, self).__init__()
        self.title_image_label = QLabel(parent)
        self.update_title_icon(icon_name)
        self.addWidget(self.title_image_label)

        title_font = QFont()
        title_font.setPointSize(16)
        shelf_label = QLabel(title, parent)
        shelf_label.setFont(title_font)
        self.addWidget(shelf_label)
        
        # Add hyperlink to a help file at the right. We will replace the correct name when it is clicked.
        help_label = QLabel(('<a href="http://www.foo.com/">{0}</a>').format(_("Help")), parent)
        help_label.setTextInteractionFlags(Qt.LinksAccessibleByMouse | Qt.LinksAccessibleByKeyboard)
        help_label.setAlignment(Qt.AlignRight)
        help_label.linkActivated.connect(parent.help_link_activated)
        self.addWidget(help_label)

    def update_title_icon(self, icon_name):
        pixmap = get_pixmap(icon_name)
        if pixmap is None:
            error_dialog(self.parent(),  _("Restart required"),
                          _("Title image not found - you must restart Calibre before using this plugin!"), show=True)
        else:
            self.title_image_label.setPixmap(pixmap)
        self.title_image_label.setMaximumSize(32, 32)
        self.title_image_label.setScaledContents(True)


class SizePersistedDialog(QDialog):
    '''
    This dialog is a base class for any dialogs that want their size/position
    restored when they are next opened.
    '''
    def __init__(self, parent, unique_pref_name, plugin_action=None):
        super(SizePersistedDialog, self).__init__(parent)
        self.unique_pref_name = unique_pref_name
        self.geom = gprefs.get(unique_pref_name, None)
        self.finished.connect(self.dialog_closing)
        self.help_anchor = None
        self.setWindowIcon(get_icon('images/icon.png'))
        self.plugin_action = plugin_action

    def resize_dialog(self):
        if self.geom is None:
            self.resize(self.sizeHint())
        else:
            self.restoreGeometry(self.geom)

    def dialog_closing(self, result):
        geom = bytearray(self.saveGeometry())
        gprefs[self.unique_pref_name] = geom
        self.persist_custom_prefs()

    def persist_custom_prefs(self):
        '''
        Invoked when the dialog is closing. Override this function to call
        save_custom_pref() if you have a setting you want persisted that you can
        retrieve in your __init__() using load_custom_pref() when next opened
        '''
        pass

    def load_custom_pref(self, name, default=None):
        return gprefs.get(self.unique_pref_name+':'+name, default)

    def save_custom_pref(self, name, value):
        gprefs[self.unique_pref_name+':'+name] = value

    def help_link_activated(self, url):
        if self.plugin_action is not None:
            self.plugin_action.show_help(anchor=self.help_anchor)


class ReadOnlyTableWidgetItem(QTableWidgetItem):

    def __init__(self, text):
        if text is None:
            text = ''
        super(ReadOnlyTableWidgetItem, self).__init__(text)
        self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)

class NumericTableWidgetItem(QTableWidgetItem):

    def __init__(self, number, is_read_only=False):
        super(NumericTableWidgetItem, self).__init__('')
        self.setData(Qt.DisplayRole, number)
        if is_read_only:
            self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)

    def value(self):
        return self.data(Qt.DisplayRole)

class RatingTableWidgetItem(QTableWidgetItem):

    def __init__(self, rating, is_read_only=False):
        super(RatingTableWidgetItem, self).__init__('')
        self.setData(Qt.DisplayRole, rating)
        if is_read_only:
            self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)


class DateTableWidgetItem(QTableWidgetItem):

    def __init__(self, date_read, is_read_only=False, default_to_today=False, fmt=None):
#        debug_print("DateTableWidgetItem:__init__ - date_read=", date_read)
        if date_read is None or date_read == UNDEFINED_DATE and default_to_today:
            date_read = now()
        if is_read_only:
            super(DateTableWidgetItem, self).__init__(format_date(date_read, fmt))
            self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)
            self.setData(Qt.DisplayRole, QDateTime(date_read))
        else:
            super(DateTableWidgetItem, self).__init__('')
            self.setData(Qt.DisplayRole, QDateTime(date_read))

from calibre.gui2.library.delegates import DateDelegate as _DateDelegate
class DateDelegate(_DateDelegate):
    '''
    Delegate for dates. Because this delegate stores the
    format as an instance variable, a new instance must be created for each
    column. This differs from all the other delegates.
    '''
    def __init__(self, parent, fmt='dd MMM yyyy', default_to_today=True):
        super(DateDelegate, self).__init__(parent)
        self.format = fmt
        self.default_to_today = default_to_today

    def createEditor(self, parent, option, index):
        qde = QStyledItemDelegate.createEditor(self, parent, option, index)
        qde.setDisplayFormat(self.format)
        qde.setMinimumDateTime(UNDEFINED_QDATETIME)
        qde.setSpecialValueText(_('Undefined'))
        qde.setCalendarPopup(True)
        return qde

    def setEditorData(self, editor, index):
        val = index.model().data(index, Qt.DisplayRole)
        if val is None or val == UNDEFINED_QDATETIME:
            if self.default_to_today:
                val = self.default_date
            else:
                val = UNDEFINED_QDATETIME
        editor.setDateTime(val)

    def setModelData(self, editor, model, index):
        val = editor.dateTime()
        if val <= UNDEFINED_QDATETIME:
            model.setData(index, UNDEFINED_QDATETIME, Qt.EditRole)
        else:
            model.setData(index, QDateTime(val), Qt.EditRole)


class NoWheelComboBox(QComboBox):

    def wheelEvent (self, event):
        # Disable the mouse wheel on top of the combo box changing selection as plays havoc in a grid
        event.ignore()


class CheckableTableWidgetItem(QTableWidgetItem):

    def __init__(self, checked=False, is_tristate=False):
        super(CheckableTableWidgetItem, self).__init__('')
        try: # TODO: For Qt Backwards compatibilyt.
            self.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled )
        except:
            self.setFlags(Qt.ItemFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled ))
        if is_tristate:
            self.setFlags(self.flags() | Qt.ItemIsTristate)
        if checked:
            self.setCheckState(Qt.Checked)
        else:
            if is_tristate and checked is None:
                self.setCheckState(Qt.PartiallyChecked)
            else:
                self.setCheckState(Qt.Unchecked)

    def get_boolean_value(self):
        '''
        Return a boolean value indicating whether checkbox is checked
        If this is a tristate checkbox, a partially checked value is returned as None
        '''
        if self.checkState() == Qt.PartiallyChecked:
            return None
        else:
            return self.checkState() == Qt.Checked


class ReadOnlyCheckableTableWidgetItem(ReadOnlyTableWidgetItem):

    def __init__(self, text, checked=False, is_tristate=False):
        super(ReadOnlyCheckableTableWidgetItem, self).__init__(text)
        try: # TODO: For Qt Backwards compatibilyt.
            self.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled )
        except:
            self.setFlags(Qt.ItemFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled ))
        if is_tristate:
            self.setFlags(self.flags() | Qt.ItemIsTristate)
        if checked:
            self.setCheckState(Qt.Checked)
        else:
            if is_tristate and checked is None:
                self.setCheckState(Qt.PartiallyChecked)
            else:
                self.setCheckState(Qt.Unchecked)

    def get_boolean_value(self):
        '''
        Return a boolean value indicating whether checkbox is checked
        If this is a tristate checkbox, a partially checked value is returned as None
        '''
        if self.checkState() == Qt.PartiallyChecked:
            return None
        else:
            return self.checkState() == Qt.Checked


class TextIconWidgetItem(QTableWidgetItem):

    def __init__(self, text, icon, tooltip=None, is_read_only=False):
        super(TextIconWidgetItem, self).__init__(self, text)
        if icon:
            self.setIcon(icon)
        if tooltip:
            self.setToolTip(tooltip)
        if is_read_only:
            self.setFlags(Qt.ItemIsSelectable|Qt.ItemIsEnabled)


class ReadOnlyTextIconWidgetItem(ReadOnlyTableWidgetItem):

    def __init__(self, text, icon):
        super(ReadOnlyTextIconWidgetItem, self).__init__(text)
        if icon:
            self.setIcon(icon)


class ReadOnlyLineEdit(QLineEdit):

    def __init__(self, text, parent):
        if text is None:
            text = ''
        super(ReadOnlyLineEdit, self).__init__(text, parent)
        self.setEnabled(False)


class KeyValueComboBox(QComboBox):

    def __init__(self, parent, values, selected_key):
        super(KeyValueComboBox, self).__init__(parent)
        self.values = values
        self.populate_combo(selected_key)

    def populate_combo(self, selected_key):
        self.clear()
        selected_idx = idx = -1
        for key, value in list(self.values.items()):
            idx = idx + 1
            self.addItem(value)
            if key == selected_key:
                selected_idx = idx
        self.setCurrentIndex(selected_idx)

    def selected_key(self):
        for key, value in list(self.values.items()):
            if value == unicode(self.currentText()).strip():
                return key


class ProfileComboBox(QComboBox):

    def __init__(self, parent, profiles, selected_text=None):
        super(ProfileComboBox, self).__init__(parent)
        self.populate_combo(profiles, selected_text)

    def populate_combo(self, profiles, selected_text=None):
        self.blockSignals(True)
        self.clear()
        for list_name in list(sorted(profiles.keys())):
            self.addItem(list_name)
        self.select_view(selected_text)

    def select_view(self, selected_text):
        self.blockSignals(True)
        if selected_text:
            idx = self.findText(selected_text)
            self.setCurrentIndex(idx)
        elif self.count() > 0:
            self.setCurrentIndex(0)
        self.blockSignals(False)


class KeyComboBox(QComboBox):

    def __init__(self, parent, values, selected_key):
        super(KeyComboBox, self).__init__(parent)
        self.values = values
        self.populate_combo(selected_key)

    def populate_combo(self, selected_key):
        self.clear()
        selected_idx = idx = -1
        for key in sorted(self.values.keys()):
            idx = idx + 1
            self.addItem(key)
            if key == selected_key:
                selected_idx = idx
        self.setCurrentIndex(selected_idx)

    def selected_key(self):
        for key, value in list(self.values.items()):
            if key == unicode(self.currentText()).strip():
                return key


class SimpleComboBox(QComboBox):

    def __init__(self, parent, values, selected_value):
        super(SimpleComboBox, self).__init__(parent)
        self.values = values
        self.populate_combo(selected_value)

    def populate_combo(self, selected_value):
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
            if value == unicode(self.currentText()).strip():
                return value


class CustomColumnComboBox(QComboBox):

    CREATE_NEW_COLUMN_ITEM = _("Create new column")

    def __init__(self, parent, custom_columns={}, selected_column='', initial_items=[''], create_column_callback=None):
        super(CustomColumnComboBox, self).__init__(parent)
        debug_print("CustomColumnComboBox::__init__ - create_column_callback=", create_column_callback)
        self.create_column_callback = create_column_callback
        self.current_index = 0
        if create_column_callback is not None:
            self.currentTextChanged.connect(self.current_text_changed)
        self.populate_combo(custom_columns, selected_column, initial_items)

    def populate_combo(self, custom_columns, selected_column, initial_items=[''], show_lookup_name=True):
        self.clear()
        self.column_names = []
        selected_idx = 0

        # debug_print("CustomColumnComboBox::populate_combo - custom_columns=", custom_columns)
        # debug_print("CustomColumnComboBox::populate_combo - selected_column=", selected_column)
        for key in sorted(custom_columns.keys()):
            self.column_names.append(key)
            display_name = '%s (%s)'%(key, custom_columns[key]['name']) if show_lookup_name else custom_columns[key]['name']
            self.addItem(display_name)
            if key == selected_column:
                selected_idx = len(self.column_names) - 1
        
        # debug_print("CustomColumnComboBox::populate_combo - initial_items=", initial_items)
        # debug_print("CustomColumnComboBox::populate_combo - initial_items.__class__=", initial_items.__class__)
        # debug_print("CustomColumnComboBox::populate_combo - initial_items.__class__=", isinstance(initial_items, dict))
        if isinstance(initial_items, dict):
            for key in sorted(initial_items.keys()):
                self.column_names.append(key)
                display_name = initial_items[key]
                self.addItem(display_name)
                if key == selected_column:
                    selected_idx = len(self.column_names) - 1
        else:
            for display_name in initial_items:
                # debug_print("CustomColumnComboBox::populate_combo - initial_items - display_name=", display_name)
                self.column_names.append(display_name)
                self.addItem(display_name)
                if display_name == selected_column:
                    selected_idx = len(self.column_names) - 1

        debug_print("CustomColumnComboBox::create_column_callback=", self.create_column_callback)
        if self.create_column_callback is not None:
            self.addItem(self.CREATE_NEW_COLUMN_ITEM)

        self.setCurrentIndex(selected_idx)

    def get_selected_column(self):
        return self.column_names[self.currentIndex()]
    
    def current_text_changed(self, new_text):
        debug_print("CustomColumnComboBox::current_text_changed - new_text='%s'" % new_text)
        debug_print("CustomColumnComboBox::current_text_changed - new_text == self.CREATE_NEW_COLUMN_ITEM='%s'" % (new_text == self.CREATE_NEW_COLUMN_ITEM))
        if new_text == self.CREATE_NEW_COLUMN_ITEM:
            debug_print("CustomColumnComboBox::current_text_changed - calling callback")
            result = self.create_column_callback()
            if not result:
                debug_print("CustomColumnComboBox::current_text_changed - column not created, setting back to original value - ", self.current_index)
                self.setCurrentIndex(self.current_index)
        else:
            self.current_index = self.currentIndex()


class KeyboardConfigDialog(SizePersistedDialog):
    '''
    This dialog is used to allow editing of keyboard shortcuts.
    '''
    def __init__(self, gui, group_name):
        super(KeyboardConfigDialog, self).__init__(gui, 'Keyboard shortcut dialog')
        self.gui = gui
        self.setWindowTitle('Keyboard shortcuts')
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        self.keyboard_widget = ShortcutConfig(self)
        layout.addWidget(self.keyboard_widget)
        self.group_name = group_name

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
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


from calibre.gui2.library.delegates import TextDelegate
class TextWithLengthDelegate(TextDelegate):
    '''
    Override the calibre TextDelegate to set a maximum length.
    '''
    def __init__(self, parent, text_length=None):
        super(TextWithLengthDelegate, self).__init__(parent)
        self.text_length = text_length

    def createEditor(self, parent, option, index):
        editor = super(TextWithLengthDelegate, self).createEditor(parent, option, index)
        if self.text_length:
            editor.setMaxLength(self.text_length)
        return editor

def get_title_authors_text(db, book_id):

    def authors_to_list(db, book_id):
        authors = db.authors(book_id, index_is_id=True)
        if authors:
            return [a.strip().replace('|',',') for a in authors.split(',')]
        return []

    title = db.title(book_id, index_is_id=True)
    authors = authors_to_list(db, book_id)
    from calibre.ebooks.metadata import authors_to_string
    return '%s / %s'%(title, authors_to_string(authors))


class ProgressBar(QDialog):
    def __init__(self, parent=None, max_items=100, window_title='Progress Bar',
                 label='Label goes here', on_top=False):
        if on_top:
            super(ProgressBar, self).__init__(parent=parent, flags=Qt.WindowStaysOnTopHint)
        else:
            super(ProgressBar, self).__init__(parent=parent)
        self.application = Application
        self.setWindowTitle(window_title)
        self.l = QVBoxLayout(self)
        self.setLayout(self.l)

        self.label = QLabel(label)
#         self.label.setAlignment(Qt.AlignHCenter)
        self.l.addWidget(self.label)

        self.progressBar = QProgressBar(self)
        self.progressBar.setRange(0, max_items)
        self.progressBar.setValue(0)
        self.l.addWidget(self.progressBar)

    def increment(self):
        self.progressBar.setValue(self.progressBar.value() + 1)
        self.refresh()

    def refresh(self):
        self.application.processEvents()

    def set_label(self, value):
        self.label.setText(value)
        self.refresh()

    def left_align_label(self):
        self.label.setAlignment(Qt.AlignLeft )

    def set_maximum(self, value):
        self.progressBar.setMaximum(value)
        self.refresh()

    def set_value(self, value):
        self.progressBar.setValue(value)
        self.refresh()

    def set_progress_format(self, progress_format=None):
        pass
#         if format is not None:
#             self.progressBar.setFormat(progress_format)
#         else:
#                 self.progressBar.resetFormat()

def prompt_for_restart(parent, title, message):
    d = info_dialog(parent, title, message, show_copy_button=False)
    b = d.bb.addButton(_('Restart calibre now'), d.bb.AcceptRole)
    b.setIcon(QIcon(I('lt.png')))
    d.do_restart = False
    def rf():
        d.do_restart = True
    b.clicked.connect(rf)
    d.set_details('')
    d.exec_()
    b.clicked.disconnect()
    return d.do_restart


class PrefsViewerDialog(SizePersistedDialog):

    def __init__(self, gui, namespace):
        super(PrefsViewerDialog, self).__init__(gui, _('Prefs Viewer dialog'))
        self.setWindowTitle(_('Preferences for: ') + namespace)

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
        self.keys_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.keys_list.setFixedWidth(150)
        self.keys_list.setAlternatingRowColors(True)
        ml.addWidget(self.keys_list)
        self.value_text = QTextEdit(self)
        self.value_text.setReadOnly(False)
        ml.addWidget(self.value_text, 1)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._apply_changes)
        button_box.rejected.connect(self.reject)
        self.clear_button = button_box.addButton(_('Clear'), QDialogButtonBox.ResetRole)
        self.clear_button.setIcon(get_icon('trash.png'))
        self.clear_button.setToolTip(_('Clear all settings for this plugin'))
        self.clear_button.clicked.connect(self._clear_settings)
        layout.addWidget(button_box)

    def _populate_settings(self):
        self.keys_list.clear()
        ns_prefix = self._get_ns_prefix()
        keys = sorted([k[len(ns_prefix):] for k in list(self.db.prefs.keys())
                       if k.startswith(ns_prefix)])
        for key in keys:
            self.keys_list.addItem(key)
        self.keys_list.setMinimumWidth(self.keys_list.sizeHintForColumn(0))
        self.keys_list.currentRowChanged[int].connect(self._current_row_changed)

    def _current_row_changed(self, new_row):
        if new_row < 0:
            self.value_text.clear()
            return
        key = unicode(self.keys_list.currentItem().text())
        val = self.db.prefs.get_namespaced(self.namespace, key, '')
        self.value_text.setPlainText(self.db.prefs.to_raw(val))

    def _get_ns_prefix(self):
        return 'namespaced:%s:'% self.namespace

    def _apply_changes(self):
        from calibre.gui2.dialogs.confirm_delete import confirm
        message = '<p>Are you sure you want to change your settings in this library for this plugin?</p>' \
                  '<p>Any settings in other libraries or stored in a JSON file in your calibre plugins ' \
                  'folder will not be touched.</p>' \
                  '<p>You must restart calibre afterwards.</p>'
        if not confirm(message, self.namespace+'_clear_settings', self):
            return

        val = self.db.prefs.raw_to_object(unicode(self.value_text.toPlainText()))
        key = unicode(self.keys_list.currentItem().text())
        self.db.prefs.set_namespaced(self.namespace, key, val)

        restart = prompt_for_restart(self, 'Settings changed',
                           '<p>Settings for this plugin in this library have been changed.</p>'
                           '<p>Please restart calibre now.</p>')
        self.close()
        if restart:
            self.gui.quit(restart=True)

    def _clear_settings(self):
        from calibre.gui2.dialogs.confirm_delete import confirm
        message = '<p>Are you sure you want to clear your settings in this library for this plugin?</p>' \
                  '<p>Any settings in other libraries or stored in a JSON file in your calibre plugins ' \
                  'folder will not be touched.</p>' \
                  '<p>You must restart calibre afterwards.</p>'
        if not confirm(message, self.namespace+'_clear_settings', self):
            return

        ns_prefix = self._get_ns_prefix()
        keys = [k for k in list(self.db.prefs.keys()) if k.startswith(ns_prefix)]
        for k in keys:
            del self.db.prefs[k]
        self._populate_settings()
        restart = prompt_for_restart(self, _('Settings deleted'),
                           _('<p>All settings for this plugin in this library have been cleared.</p>') +
                           _('<p>Please restart calibre now.</p>'))
        self.close()
        if restart:
            self.gui.quit(restart=True)

