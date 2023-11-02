"""Module to provide scraping functionalities for torrentio.

"""

import logging
from settings import settings
from modules import common
import json
import time
import datetime
import regex

# Create a logger object for this module
logger = logging.getLogger(__name__)

session = common.session(get_rate_limit=1)

MANIFEST = settings.get("torrentio manifest",
                        "https://torrentio.strem.fun/sort=qualitysize|qualityfilter=480p,scr,cam/manifest.json")
OPTIONS = MANIFEST.split('/')[-2]


def scrape(type, imdb, s, e):
    scraped_releases = []
    s = 1 if not s else s[0] if isinstance(s, list) else 1
    e = 1 if not e else e
    type = "series" if type == "show" else "movie"
    response = session.get(
        f'https://torrentio.strem.fun/{OPTIONS}/stream/{type}/{imdb}{f":{s}:{e}" if type == "series" else ""}.json')
    response = json.loads(response.content)
    if 'streams' not in response:
        return scraped_releases
    for result in response['streams']:
        try:
            title = result['title'].split('\n')[0].replace(' ', '.')
            languages = ['EN']
            matches = regex.findall(
                r'[\U0001F1E6-\U0001F1FF][\U0001F1E6-\U0001F1FF]', result['title'])
            if matches:
                languages = matches
            for i, language in enumerate(languages):
                if language in common.match.flag_to_primary_language:
                    languages[i] = common.match.flag_to_primary_language[language]
            resolution = 0
            if regex.search(r'(2160|1080|720|480)(?=p|i)', str(result['title']), regex.I):
                resolution = int(regex.findall(r'(2160|1080|720|480)(?=p|i)', str(result['title']), regex.I)[0])
            size = (float(regex.search(r'(?<=💾 )([0-9]+.?[0-9]+)(?= GB)', result['title']).group()) if regex.search(r'(?<=💾 )([0-9]+.?[0-9]+)(?= GB)', result['title']) else float(
                regex.search(r'(?<=💾 )([0-9]+.?[0-9]+)(?= MB)', result['title']).group()) / 1000 if regex.search(r'(?<=💾 )([0-9]+.?[0-9]+)(?= MB)', result['title']) else 0)
            link = 'magnet:?xt=urn:btih:' + result['infoHash'] + '&dn=&tr='
            hash = result['infoHash']
            seeds = (int(regex.search(r'(?<=👤 )([0-9]+)', result['title']).group())
                     if regex.search(r'(?<=👤 )([1-9]+)', result['title']) else 0)
            source = ((regex.search(r'(?<=⚙️ )(.*)(?=\n|$)', result['title']).group())
                      if regex.search(r'(?<=⚙️ )(.*)(?=\n|$)', result['title']) else "unknown")
            release = {
                'title': title,
                'languages': languages,
                'resolution': resolution,
                'size': size,
                'seeders': seeds,
                'source': source,
                'magnet': link,
                'hash': hash
            }
            scraped_releases += [release]
        except:
            continue

    return scraped_releases


def search(query):
    type = ""
    imdb = ""
    s = [common.match.season(query)]
    e = common.match.episode(query)
    if not s == [None]:
        type = "show"
    if regex.search(r'(tt[0-9]+)', query, regex.I):
        imdb = regex.search(r'(tt[0-9]+)', query, regex.I).group()
    else:
        if type == "show":
            query = regex.sub(common.match.season_formats, '', query)
            query = regex.sub(common.match.episode_formats, '', query)
            response = session.get(
                url=f"https://v3-cinemeta.strem.io/catalog/series/top/search={query}.json"
            )
            meta = json.loads(response.content)
        else:
            response = session.get(
                url=f"https://v3-cinemeta.strem.io/catalog/movie/top/search={query}.json"
            )
            meta = json.loads(response.content)
            type = "movie"
            if "metas" not in meta or len(meta['metas']) == 0:
                response = session.get(
                    url=f"https://v3-cinemeta.strem.io/catalog/series/top/search={query}.json"
                )
                meta = json.loads(response.content)
                type = "show"
        imdb = meta['metas'][0]['imdb_id']
    return type, imdb, s, e
