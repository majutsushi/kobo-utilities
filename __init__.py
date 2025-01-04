# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai

__license__ = "GPL v3"
__copyright__ = "2013-2020, David Forrester <davidfor@internode.on.net>"
__docformat__ = "restructuredtext en"

# The class that all Interface Action plugin wrappers must inherit from
from calibre.customize import InterfaceActionBase


class ActionKoboUtilities(InterfaceActionBase):
    """
    This class is a simple wrapper that provides information about the actual
    plugin class. The actual interface plugin class is called InterfacePlugin
    and is defined in the ui.py file, as specified in the actual_plugin field
    below.

    The reason for having two classes is that it allows the command line
    calibre utilities to run without needing to load the GUI libraries.
    """

    name = "Kobo Utilities"
    description = "Utilities to use with Kobo ereaders"
    supported_platforms = ["windows", "osx", "linux"]  # noqa: RUF012
    author = "David Forrester and others"
    version = (2, 17, 2)
    # Calibre 5.13.0: Python 3.8.5
    # Calibre 6.0.0: Python 3.10.1
    # Maintenance note: if you update the minimum version here,
    # make sure to also update it in scripts/run
    minimum_calibre_version = (5, 13, 0)

    #: This field defines the GUI plugin class that contains all the code
    #: that actually does something. Its format is module_path:class_name
    #: The specified class must be defined in the specified module.
    actual_plugin = "calibre_plugins.koboutilities.action:KoboUtilitiesAction"

    def is_customizable(self):
        """
        This method must return True to enable customization via
        Preferences->Plugins
        """
        return True

    def config_widget(self):
        """
        Implement this method and :meth:`save_settings` in your plugin to
        use a custom configuration dialog.

        This method, if implemented, must return a QWidget. The widget can have
        an optional method validate() that takes no arguments and is called
        immediately after the user clicks OK. Changes are applied if and only
        if the method returns True.

        If for some reason you cannot perform the configuration at this time,
        return a tuple of two strings (message, details), these will be
        displayed as a warning dialog to the user and the process will be
        aborted.

        The base class implementation of this method raises NotImplementedError
        so by default no user configuration is possible.
        """
        if self.actual_plugin_:
            from .config import ConfigWidget

            return ConfigWidget(self.actual_plugin_)

    def save_settings(self, config_widget):
        """
        Save the settings specified by the user with config_widget.

        :param config_widget: The widget returned by :meth:`config_widget`.
        """
        config_widget.save_settings()
