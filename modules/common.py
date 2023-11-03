"""Common module to provide functionalities for other modules.

"""

import logging
from settings import settings

import time
import requests
import regex

# Create a logger object for this module
logger = logging.getLogger(__name__)


class session(requests.Session):
    """Custom session class inheriting from requests.Session.

    This class provides per-instance rate limiting, automatic retry for
    certain error codes, and a default timeout.

    Attributes:
        DEFAULT_TIMEOUT (int): Default timeout for requests.
        RETRY_CODES (list): List of HTTP status codes to be retried.
        MAX_RETRIES (int): Maximum number of retries.
        GET_RATE_LIMIT (float): Time (in seconds) to wait between GET requests.
        POST_RATE_LIMIT (float): Time (in seconds) to wait between POST requests.
        last_request_time (float): Timestamp of the last request made.
    """

    def __init__(self,
                 timeout=60,
                 retry_codes=[429, 503],
                 max_retries=3,
                 get_rate_limit=0.01,
                 post_rate_limit=0.01):
        """Initialize a new CustomSession instance.

        Args:
            timeout (int): Default timeout for requests.
            retry_codes (list): List of HTTP status codes to be retried.
            max_retries (int): Maximum number of retries.
            get_rate_limit (float): Time (in seconds) to wait between GET requests.
            post_rate_limit (float): Time (in seconds) to wait between POST requests.
        """
        super(session, self).__init__()

        self.DEFAULT_TIMEOUT = timeout
        self.RETRY_CODES = retry_codes
        self.MAX_RETRIES = max_retries
        self.GET_RATE_LIMIT = get_rate_limit
        self.POST_RATE_LIMIT = post_rate_limit
        self.last_request_time = 0

    def request(self, method, url, **kwargs):
        """Override the request method to include rate limiting, retries, and default timeout.

        Args:
            method (str): HTTP method (e.g., 'GET', 'POST').
            url (str): URL to send the request to.
            **kwargs: Additional keyword arguments to pass to the request.

        Returns:
            response: Response object returned from the request.
        """
        # Set default timeout if not provided
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.DEFAULT_TIMEOUT

        # Ensure rate limiting
        elapsed_time = time.time() - self.last_request_time
        if method == 'GET' and elapsed_time < self.GET_RATE_LIMIT:
            time.sleep(self.GET_RATE_LIMIT - elapsed_time)
        elif method == 'POST' and elapsed_time < self.POST_RATE_LIMIT:
            time.sleep(self.POST_RATE_LIMIT - elapsed_time)

        retries = 0
        while retries < self.MAX_RETRIES:
            try:
                response = super(session, self).request(method, url, **kwargs)

                self.last_request_time = time.time()

                if response.status_code in self.RETRY_CODES:
                    logger.error(f"request error: {response.status_code} - retrying...")
                    retries += 1
                    if method == 'GET':
                        time.sleep(self.GET_RATE_LIMIT)
                    elif method == 'POST':
                        time.sleep(self.POST_RATE_LIMIT)
                    continue

                return response

            except requests.RequestException as e:
                logger.error(f"request error: {e}")
                retries += 1
                if method == 'GET':
                    time.sleep(self.GET_RATE_LIMIT)
                elif method == 'POST':
                    time.sleep(self.POST_RATE_LIMIT)

        logger.error(f"failed to fetch URL {url} after {self.MAX_RETRIES} attempts")
        return None

    def get(self, url, **kwargs):
        """Override the GET method to use the custom request method.

        Args:
            url (str): URL to send the GET request to.
            **kwargs: Additional keyword arguments to pass to the request.

        Returns:
            response: Response object returned from the GET request.
        """
        return self.request('GET', url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        """Override the POST method to use the custom request method.

        Args:
            url (str): URL to send the POST request to.
            data (dict, optional): Data to send in the POST request.
            json (dict, optional): JSON data to send in the POST request.
            **kwargs: Additional keyword arguments to pass to the request.

        Returns:
            response: Response object returned from the POST request.
        """
        return self.request('POST', url, data=data, json=json, **kwargs)


class match:
    """
    A utility class for matching and extracting media information such as video format, subtitle format,
    season and episode numbers, and language flags from file names.
    """

    # Compiles a regex pattern to identify various video file extensions.
    video_formats = regex.compile(
        r'(\.)(YUV|WMV|WEBM|VOB|VIV|SVI|ROQ|RMVB|RM|OGV|OGG|NSV|MXF|MTS|M2TS|TS|MPG|MPEG|M2V|MP2|MPE|MPV|MP4|M4P|M4V|MOV|QT|MNG|MKV|FLV|DRC|AVI|ASF|AMV)$', regex.I)

    # Compiles a regex pattern to identify various subtitle file extensions.
    subtitle_formats = regex.compile(
        r'(\.)(SRT|ASS|VTT|SUB|IDX|PGS)$', regex.I)

    # Compiles a regex pattern to extract season numbers from file names.
    season_formats = regex.compile(r'(?:season|s)[\.\-\_\s]?(\d+)', regex.I)

    # Compiles a regex pattern to extract episode numbers from file names.
    episode_formats = regex.compile(r'(?:episode|e)[\.\-\_\s]?(\d+)', regex.I)

    # Compiles a regex pattern to identify files labeled as samples (usually not the main content).
    sample_formats = regex.compile(r'(sample)', regex.I)

    # A dictionary mapping Unicode flags to primary language codes.
    flag_to_primary_language = {
        "🇦🇫": "PS", "🇦🇱": "SQ", "🇩🇿": "AR", "🇦🇸": "EN", "🇦🇩": "CA",
        "🇦🇴": "PT", "🇦🇮": "EN", "🇦🇶": "EN", "🇦🇬": "EN", "🇦🇷": "ES",
        "🇦🇲": "HY", "🇦🇼": "NL", "🇦🇺": "EN", "🇦🇹": "DE", "🇦🇿": "AZ",
        "🇧🇸": "EN", "🇧🇭": "AR", "🇧🇩": "BN", "🇧🇧": "EN", "🇧🇾": "BE",
        "🇧🇪": "NL", "🇧🇿": "EN", "🇧🇯": "FR", "🇧🇲": "EN", "🇧🇹": "DZ",
        "🇧🇴": "ES", "🇧🇦": "BS", "🇧🇼": "EN", "🇧🇷": "PT", "🇮🇴": "EN",
        "🇻🇬": "EN", "🇧🇳": "MS", "🇧🇬": "BG", "🇧🇫": "FR", "🇧🇮": "RN",
        "🇰🇭": "KM", "🇨🇲": "FR", "🇨🇦": "EN", "🇮🇨": "ES", "🇨🇻": "PT",
        "🇧🇶": "NL", "🇰🇾": "EN", "🇨🇫": "FR", "🇹🇩": "AR", "🇨🇱": "ES",
        "🇨🇳": "ZH", "🇨🇽": "EN", "🇨🇨": "EN", "🇨🇴": "ES", "🇰🇲": "AR",
        "🇨🇬": "FR", "🇨🇩": "FR", "🇨🇰": "EN", "🇨🇷": "ES", "🇭🇷": "HR",
        "🇨🇺": "ES", "🇨🇼": "NL", "🇨🇾": "EL", "🇨🇿": "CS", "🇩🇰": "DA",
        "🇩🇯": "FR", "🇩🇲": "EN", "🇩🇴": "ES", "🇪🇨": "ES", "🇪🇬": "AR",
        "🇸🇻": "ES", "🇬🇶": "ES", "🇪🇷": "TI", "🇪🇪": "ET", "🇸🇿": "EN",
        "🇪🇹": "AM", "🇫🇰": "EN", "🇫🇴": "FO", "🇫🇯": "EN", "🇫🇮": "FI",
        "🇫🇷": "FR", "🇬🇫": "FR", "🇵🇫": "FR", "🇹🇫": "FR", "🇬🇦": "FR",
        "🇬🇲": "EN", "🇬🇪": "KA", "🇩🇪": "DE", "🇬🇭": "EN", "🇬🇮": "EN",
        "🇬🇷": "EL", "🇬🇱": "KL", "🇬🇩": "EN", "🇬🇵": "FR", "🇬🇺": "EN",
        "🇬🇹": "ES", "🇬🇬": "EN", "🇬🇳": "FR", "🇬🇼": "PT", "🇬🇾": "EN",
        "🇭🇹": "FR", "🇭🇲": "EN", "🇭🇳": "ES", "🇭🇰": "ZH", "🇭🇺": "HU",
        "🇮🇸": "IS", "🇮🇳": "HI", "🇮🇩": "ID", "🇮🇷": "FA", "🇮🇶": "AR",
        "🇮🇪": "EN", "🇮🇲": "EN", "🇮🇱": "HE", "🇮🇹": "IT", "🇯🇲": "EN",
        "🇯🇵": "JA", "🇯🇪": "EN", "🇯🇴": "AR", "🇰🇿": "KK", "🇰🇪": "SW",
        "🇰🇮": "EN", "🇽🇰": "SQ", "🇰🇼": "AR", "🇰🇬": "KY", "🇱🇦": "LO",
        "🇱🇻": "LV", "🇱🇧": "AR", "🇱🇸": "EN", "🇱🇷": "EN", "🇱🇾": "AR",
        "🇱🇮": "DE", "🇱🇹": "LT", "🇱🇺": "FR", "🇲🇴": "ZH", "🇲🇬": "FR",
        "🇲🇼": "EN", "🇲🇾": "MS", "🇲🇻": "DV", "🇬🇧": "EN", "🇩🇪": "DE",
        "🇫🇷": "FR", "🇪🇸": "ES", "🇮🇹": "IT", "🇳🇿": "EN", "🇨🇺": "ES",
        "🇷🇺": "RU", "🇨🇳": "ZH", "🇯🇵": "JA", "🇰🇷": "KO", "🇸🇦": "AR",
        "🇹🇷": "TR", "🇮🇳": "HI", "🇮🇩": "ID", "🇧🇷": "PT", "🇵🇰": "UR",
        "🇳🇬": "EN", "🇧🇩": "BN", "🇲🇽": "ES", "🇵🇭": "TL", "🇻🇳": "VI",
        "🇪🇹": "AM", "🇪🇬": "AR", "🇩🇪": "DE", "🇮🇷": "FA", "🇹🇭": "TH",
        "🇬🇧": "EN", "🇫🇷": "FR", "🇮🇹": "IT", "🇲🇦": "AR", "🇦🇺": "EN",
        "🇲🇾": "MS", "🇺🇦": "UK", "🇿🇦": "ZU", "🇵🇱": "PL", "🇨🇴": "ES",
        "🇦🇷": "ES", "🇨🇦": "EN", "🇲🇲": "MY", "🇻🇪": "ES", "🇵🇪": "ES",
        "🇳🇵": "NE", "🇸🇬": "EN", "🇴🇲": "AR", "🇸🇪": "SE", "🇵🇹": "PT"
    }

    @staticmethod
    def video(filename):
        """
        Determines if a given filename is a video file based on its extension.

        Parameters:
            filename (str): The filename to check.

        Returns:
            bool: True if the filename matches a video format and is not a sample; False otherwise.
        """
        return bool(regex.search(match.video_formats, filename) and not regex.search(match.sample_formats, filename))

    @staticmethod
    def subtitle(filename):
        """
        Determines if a given filename is a subtitle file based on its extension.

        Parameters:
            filename (str): The filename to check.

        Returns:
            bool: True if the filename matches a subtitle format; False otherwise.
        """
        return bool(regex.search(match.subtitle_formats, filename))

    @staticmethod
    def season(filename):
        """
        Extracts the season number from a given filename.

        Parameters:
            filename (str): The filename from which to extract the season number.

        Returns:
            int or None: The season number if found; otherwise, None.
        """
        season_match = regex.search(match.season_formats, filename)
        return int(season_match.group(1)) if season_match else None

    @staticmethod
    def episode(filename):
        """
        Extracts the episode number from a given filename.

        Parameters:
            filename (str): The filename from which to extract the episode number.

        Returns:
            int or None: The episode number if found; otherwise, None.
        """
        episode_match = regex.search(match.episode_formats, filename)
        return int(episode_match.group(1)) if episode_match else None


class releases:
    """
    The `releases` class provides methods to manipulate and format a collection of release information.

    It offers functionalities to format release details for logging, filter the releases based on the type of media
    (movie or show) and specific season and episode information, and to sort the releases according to predefined
    server rules and filters.

    The class methods are designed to be used statically, operating on lists of dictionaries where each dictionary
    represents a release with various attributes such as resolution, size, language, etc.
    """

    @staticmethod
    def print(list):
        """
        Formats a list of release dictionaries for printing, with each attribute
        aligned for easy reading.

        Parameters:
            list (list of dict): A list of release dictionaries to format.

        Returns:
            list of str: A list of formatted strings ready for printing.
        """
        # Initialize variables to hold the maximum length of each attribute.
        longest_res, longest_cached, longest_title = 0, 0, 0
        longest_size, longest_langs, longest_index, longest_seeders = 0, 0, 0, 0

        # Calculate the longest attribute length for formatting purposes.
        for index, release in enumerate(list):
            # Round the size to two decimal places for display.
            release['printsize'] = str(round(release['size'], 2))

            # Update the maximum length for each attribute if the current one is longer.
            longest_cached = max(longest_cached, len('/'.join(release['cached'])))
            longest_title = max(longest_title, len(release['title']))
            longest_res = max(longest_res, len(str(release['resolution'])))
            longest_size = max(longest_size, len(release['printsize']))
            longest_langs = max(longest_langs, len('/'.join(release['languages'])))
            longest_seeders = max(longest_seeders, len(str(release['seeders'])))
            longest_index = max(longest_index, len(str(index + 1)))

        # Construct formatted string for each release.
        strings = []
        for index, release in enumerate(list):
            # Format each attribute with appropriate spacing.
            i = f"{index + 1}) {' ' * (longest_index - len(str(index + 1)))}"
            resolution = f"resolution: {release['resolution']}{' ' * (longest_res - len(str(release['resolution'])))}"
            langs = f" | languages: {'/'.join(release['languages'])}{' ' * (longest_langs - len('/'.join(release['languages'])))}"
            title = f" | title: {release['title']}{' ' * (longest_title - len(release['title']))}"
            size = f" | size: {release['printsize']}{' ' * (longest_size - len(release['printsize']))}"
            cached = f" | cached: {'/'.join(release['cached'])}{' ' * (longest_cached - len('/'.join(release['cached'])))}"
            seeders = f" | seeders: {release['seeders']}{' ' * (longest_seeders - len(str(release['seeders'])))}"
            source = f" | source: {release['source']}"

            # Append the formatted string to the list.
            strings.append(i + resolution + langs + title + size + cached + seeders + source)

        # Return the list of formatted strings.
        return strings

    @staticmethod
    def type_filter(list, type, s, e):
        """
        Filters a list of releases based on the media type and provided season and episode numbers.

        Parameters:
            list (list of dict): The list of release dictionaries to filter.
            type (str): The type of media ('movie' or 'show').
            s (list): A list of season numbers.
            e (int): An episode number.

        Returns:
            list of dict: The filtered list of release dictionaries.
        """
        # Filter logic for movies.
        if type == 'movie':
            # Remove releases without videos and versions without videos.
            # Set type to 'movie' for remaining releases.
            for release in list[:]:
                if release['videos'] == 0:
                    list.remove(release)
                    continue
                for version in release['versions'][:]:
                    if version['videos'] == 0:
                        release['versions'].remove(version)
            for release in list:
                release['type'] = "movie"
            return list

        seasons = set(s)

        # Filter logic for shows with multiple seasons.
        if len(s) > 1:
            # Remove releases that do not match the required seasons or have too few episodes.
            # Set type to 'show' for remaining releases.
            for release in list[:]:
                if len(seasons - set(release['seasons'])) > len(s) / 2 or release['episodes'] <= 1:
                    list.remove(release)
                    continue
                for version in release['versions'][:]:
                    if len(seasons - set(version['seasons'])) > len(s) / 2 or version['episodes'] <= 1:
                        release['versions'].remove(version)
            for release in list:
                release['type'] = "show"
            return list

        # Filter logic for a single season without specifying episodes.
        if not e:
            # Remove releases that do not match the required season or have too few episodes.
            # Set type to 'show' for remaining releases.
            for release in list[:]:
                if seasons - set(release['seasons']) or release['episodes'] <= 1:
                    list.remove(release)
                    continue
                for version in release['versions'][:]:
                    if seasons - set(version['seasons']) or version['episodes'] <= 1:
                        release['versions'].remove(version)
            for release in list:
                release['type'] = "show"
            return list

        # Filter logic for a single season with a specific episode.
        for release in list[:]:
            # Remove releases that do not match the required season or episode.
            # Set type to 'show' for remaining releases.
            if seasons - set(release['seasons']) or not release['episodes'] == 1:
                list.remove(release)
                continue
            for version in release['versions'][:]:
                if seasons - set(version['seasons']) or not version['episodes'] == 1:
                    release['versions'].remove(version)
            for release in list:
                release['type'] = "show"

        # Return the filtered list after applying all conditions.
        return list

    def sort(server, list):
        """
        Sorts a list of releases based on server-defined rules and filters.

        Parameters:
            server: The server object with defined FILTERS and RULES.
            list (list of dict): The list of release dictionaries to sort.

        Returns:
            list of dict: The sorted list of release dictionaries.
        """
        # Apply server filters to the list.
        for filter in server.FILTERS:
            list = [release for release in list if eval(filter)]

        # Sort the list based on the number of episodes, descending.
        list.sort(key=lambda x: x['episodes'], reverse=True)

        # Apply server rules for further sorting.
        for rule in server.RULES:
            list.sort(key=lambda release: eval(rule), reverse=True)

        # Return the sorted list.
        return list
