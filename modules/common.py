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

    video_formats = regex.compile(
        r'(\.)(YUV|WMV|WEBM|VOB|VIV|SVI|ROQ|RMVB|RM|OGV|OGG|NSV|MXF|MTS|M2TS|TS|MPG|MPEG|M2V|MP2|MPE|MPV|MP4|M4P|M4V|MOV|QT|MNG|MKV|FLV|DRC|AVI|ASF|AMV)$', regex.I)

    subtitle_formats = regex.compile(
        r'(\.)(SRT|ASS|VTT|SUB|IDX|PGS)$', regex.I)

    season_formats = regex.compile(r'(?:season|s)[\.\-\_\s]?(\d+)', regex.I)

    episode_formats = regex.compile(r'(?:episode|e)[\.\-\_\s]?(\d+)', regex.I)
    sample_formats = regex.compile(r'(sample)', regex.I)

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

    def video(filename):
        return bool(regex.search(match.video_formats, filename) and not regex.search(match.sample_formats, filename))

    def subtitle(filename):
        return bool(regex.search(match.subtitle_formats, filename))

    def season(filename):
        season = regex.search(match.season_formats, filename)
        if season:
            return int(season.group(1))
        else:
            return None

    def episode(filename):
        episode = regex.search(match.episode_formats, filename)
        if episode:
            return int(episode.group(1))
        else:
            return None


class releases:
    def print(list):
        strings = []
        longest_res = 0
        longest_cached = 0
        longest_title = 0
        longest_size = 0
        longest_langs = 0
        longest_index = 0
        longest_seeders = 0
        for index, release in enumerate(list):
            release['printsize'] = str(round(release['size'], 2))
            if len('/'.join(release['cached'])) > longest_cached:
                longest_cached = len('/'.join(release['cached']))
            if len(release['title']) > longest_title:
                longest_title = len(release['title'])
            if len(str(release['resolution'])) > longest_res:
                longest_res = len(str(release['resolution']))
            if len(str(release['printsize'])) > longest_size:
                longest_size = len(str(release['printsize']))
            if len('/'.join(release['languages'])) > longest_langs:
                longest_langs = len('/'.join(release['languages']))
            if len(str(release['seeders'])) > longest_seeders:
                longest_seeders = len(str(release['seeders']))
            if len(str(index + 1)) > longest_index:
                longest_index = len(str(index + 1))
        for index, release in enumerate(list):
            i = str(index + 1) + ") " + ' ' * (longest_index - len(str(index + 1)))
            resolution = "resolution: " + str(release['resolution']) + ' ' * \
                (longest_res - len(str(release['resolution'])))
            langs = " | languages: " + '/'.join(release['languages']) + ' ' * \
                (longest_langs - len('/'.join(release['languages'])))
            title = " | title: " + release['title'] + ' ' * (longest_title - len(release['title']))
            size = " | size: " + str(release['printsize']) + ' ' * (longest_size - len(str(release['printsize'])))
            cached = " | cached: " + '/'.join(release['cached']) + ' ' * \
                (longest_cached - len('/'.join(release['cached'])))
            seeders = " | seeders: " + str(release['seeders']) + ' ' * (longest_seeders - len(str(release['seeders'])))
            source = " | source: " + release['source']
            strings += [i + resolution + langs + title + size + cached + seeders + source]
        return strings

    def type_filter(list, type, s, e):
        if type == 'movie':
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
        if len(s) > 1:
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
        if not e:
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
        for release in list[:]:
            if seasons - set(release['seasons']) or not release['episodes'] == 1:
                list.remove(release)
                continue
            for version in release['versions'][:]:
                if seasons - set(version['seasons']) or not version['episodes'] == 1:
                    release['versions'].remove(version)
            for release in list:
                release['type'] = "show"
        return list

    def sort(server, list):
        for filter in server.FILTERS:
            list = [release for release in list if eval(filter)]
        list.sort(key=lambda x: x['episodes'], reverse=True)
        for rule in server.RULES:
            list.sort(key=lambda release: eval(rule), reverse=True)
        return list
