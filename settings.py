"""Module to manage settings.

This module provides a centralized way to manage application settings,
stored in a JSON file. It contains a class, SettingsManager, which encapsulates
the methods to load, save, get, and set these settings.

Example:
    from settings import settings

    log_level = settings.get('log_level', 'INFO')
    settings.set('log_level', 'DEBUG')

"""

import json


class SettingsManager:
    """Class to manage application settings.

    The SettingsManager class reads settings from a JSON file and provides methods
    to get and set these settings. Any changes to the settings are immediately
    saved to the file.

    Attributes:
        settings_file (str): The name of the file where settings are stored.
        settings (dict): Dictionary containing the settings.
    """

    def __init__(self, settings_file='config/settings.json'):
        """Initialize the SettingsManager with a given settings file.

        Args:
            settings_file (str): The name of the file to read settings from. Defaults to 'settings.json'.

        """
        self.settings_file = settings_file
        self.load()

    def load(self):
        """Load settings from the JSON file.

        Reads the JSON file specified in `settings_file` and loads it into the `settings` dictionary.

        """
        with open(self.settings_file, 'r') as f:
            self.settings = json.load(f)

    def save(self):
        """Save the current settings to the JSON file.

        Writes the contents of the `settings` dictionary back to the JSON file.

        """
        with open(self.settings_file, 'w') as f:
            json.dump(self.settings, f, indent=4)

    def get(self, key, default=None):
        """Retrieve a setting value by its key.

        Args:
            key (str): The key for the setting.

        Returns:
            The value for the given key, or the default value if the key does not exist.
        """
        return self.settings.get(key, default)

    def set(self, key, value):
        """Set a setting value by its key.

        Args:
            key (str): The key for the setting.
            value: The value to set.

        """
        self.settings[key] = value
        self.save()


# Initialize a global instance to be used throughout the application
settings = SettingsManager()
