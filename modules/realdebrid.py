"""Module to provide debrid functionalities for realdebrid.

"""

import logging
from settings import settings
from modules import common
import json
import time

# Create a logger object for this module
logger = logging.getLogger(__name__)

session = common.session(get_rate_limit=1, retry_codes=[429, 503, 404, 400, 500])

TOKEN = settings.get('realdebrid api key')


def check(releases):
    hashes = []
    for release in releases:
        hashes += [release['hash']]
        release['cached'] = []
        release['versions'] = []
    if len(hashes) == 0:
        return releases
    response = session.get(
        url=f'https://api.real-debrid.com/rest/1.0/torrents/instantAvailability/{"/".join(hashes)}',
        headers={'authorization': f'Bearer {TOKEN}'}
    )
    response = json.loads(response.content)
    for release in releases[:]:
        if not release['hash'] in response or 'rd' not in response[release['hash']] or len(response[release['hash']]['rd']) == 0:
            releases.remove(release)
    for release in releases:
        release['versions'] = []
        for files in response[release['hash']]['rd']:
            version = {'size': 0, 'files': [], 'videos': 0, 'episodes': 0, 'subtitles': 0, 'seasons': []}
            for id in files:
                file = {
                    'name': files[id]['filename'],
                    'size': files[id]['filesize'] / (8 * 1024 * 1024 * 1024),
                    'id': id,
                    'video': common.match.video(files[id]['filename']),
                    'subtitle': common.match.subtitle(files[id]['filename']),
                    'season': common.match.season(files[id]['filename']),
                    'episode': common.match.episode(files[id]['filename'])
                }
                version['files'] += [file]
                version['size'] += file['size']
                version['videos'] += int(file['video'])
                version['subtitles'] += int(file['subtitle'])
                if file['season'] and file['video'] and not file['season'] in version['seasons']:
                    version['seasons'] += [file['season']]
                version['episodes'] += int(bool(file['episode']) and file['video'])
            release['versions'] += [version]
        release['versions'].sort(key=lambda x: x['videos'] / len(x['files']), reverse=True)
        release['versions'].sort(key=lambda x: x['videos'], reverse=True)
        release['size'] = release['versions'][0]['size']
        release['videos'] = release['versions'][0]['videos']
        release['seasons'] = release['versions'][0]['seasons']
        release['episodes'] = release['versions'][0]['episodes']
        release['cached'] += ['RD']

    for line in common.releases.print(releases):
        logger.info(line)


def download(release):
    response = session.post(
        url='https://api.real-debrid.com/rest/1.0/torrents/addMagnet',
        data={'magnet': str(release['magnet'])},
        headers={'authorization': f'Bearer {TOKEN}'}
    )
    response = json.loads(response.content)
    torrent_id = str(response['id'])
    for version in release['versions']:
        ids = [file['id'] for file in version['files']]
        response = session.post(
            url=f'https://api.real-debrid.com/rest/1.0/torrents/selectFiles/{torrent_id}',
            data={'files': str(','.join(ids))},
            headers={'authorization': f'Bearer {TOKEN}'}
        )
        response = session.get(
            url=f'https://api.real-debrid.com/rest/1.0/torrents/info/{torrent_id}',
            headers={'authorization': f'Bearer {TOKEN}'}
        )
        time.sleep(0.05)
        response = json.loads(response.content)
        if len(response['links']) == len(ids):
            release['title'] = response['filename']
            release['download'] = response['links']
            break
        else:
            logger.error(f"this file combination of release {release['title']} is a .rar archive - trying again")
            session.request(
                method='DELETE',
                url=f'https://api.real-debrid.com/rest/1.0/torrents/delete/{torrent_id}',
                headers={'authorization': f'Bearer {TOKEN}'}
            )
            continue
    if len(release['download']) > 0:
        logger.info(f"added {release['title']} to realdebrid")
        for link in release['download']:
            response = session.post(
                url='https://api.real-debrid.com/rest/1.0/unrestrict/link',
                data={'link': link},
                headers={'authorization': f'Bearer {TOKEN}'}
            )
        release['files'] = version['files']
        return True
    return False
