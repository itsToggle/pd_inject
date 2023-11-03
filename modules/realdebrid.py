"""Module to provide debrid functionalities for real-debrid.com."""

import logging
from settings import settings
from modules import common
import json
import time

# Create a logger object for this module
logger = logging.getLogger(__name__)

# Establish a new session with specified rate limits and retry codes
session = common.session(get_rate_limit=1, retry_codes=[429, 503, 404, 400, 500])

# Retrieve the API key for realdebrid from settings
TOKEN = settings.get('realdebrid api key')


def check(releases):
    """
    Check the cache status of scraped releases on realdebrid and enrich the release data with available versions.

    Parameters:
        releases (list): A list of dictionaries, each containing release data with a 'hash' key.

    Returns:
        list: The enriched list of releases with cache and version information.
    """
    hashes = []
    for release in releases:
        # Compile hashes for the batch check and initialize cache and versions
        hashes.append(release['hash'])
        release['cached'] = []
        release['versions'] = []

    # If no hashes are present, return the original releases list
    if not len(hashes):
        return releases

    try:
        # Perform the cache check with the realdebrid API
        response = session.get(
            url=f'https://api.real-debrid.com/rest/1.0/torrents/instantAvailability/{"/".join(hashes)}',
            headers={'authorization': f'Bearer {TOKEN}'}
        )
        response = json.loads(response.content)

        # Filter out releases not cached on realdebrid
        releases[:] = [release for release in releases if release['hash'] in response and 'rd' in response[release['hash']] and response[release['hash']]['rd']]

        # Enrich each release with version information based on the cache check
        for release in releases:
            for files in response[release['hash']]['rd']:
                version = {'size': 0, 'files': [], 'videos': 0, 'episodes': 0, 'subtitles': 0, 'seasons': []}
                for id in files:
                    file = {
                        'name': files[id]['filename'],
                        'size': files[id]['filesize'] / (8 * 1024 * 1024 * 1024),  # Convert size to GB
                        'id': id,
                        'video': common.match.video(files[id]['filename']),
                        'subtitle': common.match.subtitle(files[id]['filename']),
                        'season': common.match.season(files[id]['filename']),
                        'episode': common.match.episode(files[id]['filename'])
                    }
                    version['files'].append(file)
                    version['size'] += file['size']
                    version['videos'] += int(file['video'])
                    version['subtitles'] += int(file['subtitle'])
                    if file['season'] and file['video'] and file['season'] not in version['seasons']:
                        version['seasons'].append(file['season'])
                    version['episodes'] += int(bool(file['episode']) and file['video'])
                release['versions'].append(version)

            # Sort versions by video count and ratio of videos to total files
            release['versions'].sort(key=lambda x: (x['videos'], x['videos'] / len(x['files'])), reverse=True)

            # Take the first version's size and video details for the release
            if release['versions']:
                first_version = release['versions'][0]
                release.update({
                    'size': first_version['size'],
                    'videos': first_version['videos'],
                    'seasons': first_version['seasons'],
                    'episodes': first_version['episodes'],
                    'cached': ['RD']
                })

        # Log the enriched releases
        for line in common.releases.print(releases):
            logger.info(line)

    except Exception as e:
        logger.exception(f"An error occurred during the cache check: {e}")

    return releases


def download(release):
    """
    Download a release via realdebrid by adding a magnet link and selecting files to download.

    Parameters:
        release (dict): A dictionary containing the release's magnet link and version information.

    Returns:
        bool: True if the download was initiated successfully, False otherwise.
    """
    try:
        # Add the magnet link to realdebrid
        response = session.post(
            url='https://api.real-debrid.com/rest/1.0/torrents/addMagnet',
            data={'magnet': release['magnet']},
            headers={'authorization': f'Bearer {TOKEN}'}
        )
        response = json.loads(response.content)
        torrent_id = response['id']

        for version in release['versions']:
            ids = [file['id'] for file in version['files']]
            try:
                # Select specific files from the torrent to download
                session.post(
                    url=f'https://api.real-debrid.com/rest/1.0/torrents/selectFiles/{torrent_id}',
                    data={'files': ','.join(ids)},
                    headers={'authorization': f'Bearer {TOKEN}'}
                )
                # Fetch the torrent info to check if the files are ready
                response = session.get(
                    url=f'https://api.real-debrid.com/rest/1.0/torrents/info/{torrent_id}',
                    headers={'authorization': f'Bearer {TOKEN}'}
                )
                time.sleep(0.05)  # A short delay to prevent API rate limit issues
                response = json.loads(response.content)

                if len(response['links']) == len(ids):
                    # If all selected files are ready, set the download information
                    release['title'] = response['filename']
                    release['download'] = response['links']
                    break
                else:
                    # If the files are not ready, log the issue and retry
                    logger.error(f"File combination for release {release['title']} is a .rar archive - trying again")
                    # Delete the torrent if the file combination is not correct
                    session.request(
                        method='DELETE',
                        url=f'https://api.real-debrid.com/rest/1.0/torrents/delete/{torrent_id}',
                        headers={'authorization': f'Bearer {TOKEN}'}
                    )
            except Exception as e:
                logger.exception(f"An error occurred during file selection or retrieval: {e}")
                continue

        if release.get('download'):
            # If downloads are available, initiate the unrestricted download process
            logger.info(f"Added {release['title']} to realdebrid")
            for link in release['download']:
                session.post(
                    url='https://api.real-debrid.com/rest/1.0/unrestrict/link',
                    data={'link': link},
                    headers={'authorization': f'Bearer {TOKEN}'}
                )
            release['files'] = version['files']
            return True

    except Exception as e:
        logger.exception(f"An error occurred during the download process: {e}")

    return False
