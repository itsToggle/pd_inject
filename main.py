"""Main module for running tasks.
This module sets up a mock plex server using Flask, ngrok for public https access, and defines routes for handling different tasks.
"""

from flask import Flask, request
from flask_caching import Cache
from pyngrok import ngrok, conf
import threading
import logging
import json
import zlib
import requests
import regex
from dicttoxml import dicttoxml
from modules import common
from modules import plex
from modules import torrentio
from modules import realdebrid
from settings import settings
import time
import copy
import uuid

session = common.session()

PORT = 8008


def configure_logging():
    """Configure logging settings.

    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s (%(levelname)s) [%(module)s.%(funcName)s] %(message)s'
    )


app = Flask(__name__)
cache = Cache(app, config={'CACHE_TYPE': 'simple', "CACHE_DEFAULT_TIMEOUT": 300})

# Start the ngrok tunnel
conf.get_default().region = 'us'
public_url = ngrok.connect(PORT)

# Start a new thread for the Flask application
threading.Thread(target=app.run, kwargs={
    'use_reloader': False,
    'debug': True,
    'port': PORT
}).start()

mock_servers = [plex.mockserver(server, public_url.public_url) for server in settings.get("versions")]


def zlib_encode(content):
    zlib_compress = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS)
    data = zlib_compress.compress(content) + zlib_compress.flush()
    return data


def deflate_encode(content):
    deflate_compress = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    data = deflate_compress.compress(content) + deflate_compress.flush()
    return data


def gzip_encode(content):
    gzip_compress = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16)
    data = gzip_compress.compress(content) + gzip_compress.flush()
    return data


def format(content, request):

    if request.accept_mimetypes.best == 'application/xml' and isinstance(content, dict):
        content = dicttoxml(content, root=False, attr_type=False)
    elif isinstance(content, dict):
        content = json.dumps(content).encode('utf-8')
    uncompressed = len(content)
    content = gzip_encode(content)
    compressed = len(content)
    headers = {
        'X-Plex-Content-Original-Length': uncompressed,
        'X-Plex-Content-Compressed-Length': compressed,
        'Content-Encoding': 'gzip',
        'Content-Type': request.accept_mimetypes.best,
        'Access-Control-Allow-Origin': '*',
        'X-Plex-Protocol': '1.0',
        'Vary': 'Origin, X-Plex-Token',
        'Connection': 'keep-alive'
    }
    return content, 200, headers


releases = None
processing_lock = threading.Lock()
processing = False
search_lock = threading.Lock()
last_search_time = 0
last_search_term = ""
data_store = {}


@app.route('/media/providers', methods=['GET'])
@app.route('/<path:server>/media/providers', methods=['GET'])
def handle_providers(server=mock_servers[0].IDENTIFIER):
    mock_server = next((s for s in mock_servers if s.IDENTIFIER == server), None)
    path = requests.utils.unquote(request.full_path)
    content = mock_server.provider('includePreferences=1' in path)
    content, code, headers = format(content, request)
    return content, code, headers


@app.route('/<path:server>/library/metadata/<path:guid>', methods=['GET'])
def handle_metadata(server, guid):
    mock_server = next((s for s in mock_servers if s.IDENTIFIER == server), None)
    if 'availabilities' in guid:
        content = {}
        content, code, headers = format(content, request)
        return content, code, headers
    content = mock_server.metadata(requests.utils.unquote(guid), request.args)
    content, code, headers = format(content, request)
    return content, code, headers


@app.route('/library/all', methods=['GET'])
@app.route('/<path:server>/library/all', methods=['GET'])
@cache.cached(timeout=300, query_string=True)
def handle_availability(server=None):
    mock_server = next((s for s in mock_servers if s.IDENTIFIER == server), None)

    path = requests.utils.unquote(request.full_path)
    guid = regex.search(r'(?<=guid=)(.*?)(?=&)', path, regex.I).group()

    global releases, processing, data_store

    if mock_server:
        mock_server = [mock_server]
    else:
        mock_server = mock_servers

    with processing_lock:

        if not processing:

            processing = True

            type, imdb, s, e = mock_server[0].identify(path)

            releases = torrentio.scrape(type, imdb, s, e)

            realdebrid.check(releases)

            common.releases.type_filter(releases, type, s, e)

    local_releases = copy.deepcopy(releases)

    time.sleep(0.05)

    processing = False

    metadata = []

    for server in mock_server:

        if len(mock_server) > 1:
            local_releases = copy.deepcopy(releases)

        local_releases = common.releases.sort(server, local_releases)

        unique_id = str(uuid.uuid4())
        data_store[unique_id] = local_releases

        for i, release in enumerate(local_releases[:server.RESULTS]):
            metadata += [{
                "ratingKey": "2785",
                "key": f"/download/{requests.utils.quote(unique_id)}/{i}",
                "librarySectionID": 2,
                "librarySectionKey": "/library/sections/2",
                "guid": guid,
                "librarySectionTitle": server.SERVERNAME,
                "Media": [
                    {
                        "videoResolution": (release['title'] if len(mock_server) == 1 else release['resolution']),
                    },
                ],
            },]

    content = {
        "MediaContainer": {
            "size": 1,
            "allowSync": False,
            "identifier": "com.plexapp.plugins.library",
            "mediaTagPrefix": "/system/bundle/media/flags/",
            "mediaTagVersion": 1655122614,
            "Metadata": metadata
        }
    }
    content, code, headers = format(content, request)
    return content, code, headers


@app.route('/hubs/search', methods=['GET'])
@app.route('/<path:server>/hubs/search', methods=['GET'])
@cache.cached(timeout=300, query_string=True)
def handle_search(server=None):
    mock_server = next((s for s in mock_servers if s.IDENTIFIER == server), None)
    query = request.args.get('query', '')
    # Debounce the search
    global last_search_time, releases, processing
    with search_lock:
        # Replace the old timer with the new one
        last_search_time = time.time()
        last_search_term = copy.deepcopy(query)
    while True:
        with search_lock:
            # If a new search has been initiated by the same client, break the loop
            if time.time() - last_search_time > 1:
                break
        time.sleep(0.1)
    if not query == last_search_term:
        content = {}
        content, code, headers = format(content, request)
        return content, code, headers
    if mock_server:
        mock_server = [mock_server]
    else:
        mock_server = mock_servers

    with processing_lock:

        if not processing:

            processing = True

            type, imdb, s, e = torrentio.search(query)

            releases = torrentio.scrape(type, imdb, s, e)

            realdebrid.check(releases)

            common.releases.type_filter(releases, type, s, e)

    local_releases = copy.deepcopy(releases)

    time.sleep(0.05)

    processing = False

    metadata = []

    for server in mock_server:

        if len(mock_server) > 1:
            local_releases = copy.deepcopy(releases)

        local_releases = common.releases.sort(server, local_releases)

        unique_id = str(uuid.uuid4())
        data_store[unique_id] = local_releases

        for i, release in enumerate(local_releases[:server.RESULTS]):
            metadata += [
                {
                    "librarySectionTitle": "Torrentio",
                    "score": "0.33078",
                    "ratingKey": "",
                    "key": f"/download/{requests.utils.quote(unique_id)}/{i}",
                    "guid": release['title'],
                    "studio": "Hyperobject Industries",
                    "type": "movie",
                    "title": release['title'],
                    "librarySectionID": 1,
                    "librarySectionKey": "/library/sections/1",
                    "contentRating": "R",
                    "summary": "",
                    "rating": 5.5,
                    "audienceRating": 7.8,
                    "year": 2022,
                    "tagline": "Based on truly possible events.",
                    "thumb": "https://static.thenounproject.com/png/1390707-200.png",
                    "art": "https://static.thenounproject.com/png/1390707-200.png",
                    "duration": 8591530,
                    "originallyAvailableAt": "2021-12-24",
                    "addedAt": 1655228225,
                    "updatedAt": 1655228225,
                    "audienceRatingImage": "rottentomatoes://image.rating.upright",
                    "primaryExtraKey": "/library/metadata/89",
                    "ratingImage": "rottentomatoes://image.rating.rotten",
                }
            ]
    content = {
        "MediaContainer": {
            "size": 18,
            "Hub": [
                {
                    "title": "Movies",
                    "type": "movie",
                    "hubIdentifier": "movie",
                    "context": "",
                    "size": 1,
                    "more": False,
                    "style": "shelf",
                    "Metadata": metadata
                }
            ]
        }
    }

    content, code, headers = format(content, request)
    return content, code, headers


@app.route('/download/<path:id>/<path:num>', methods=['GET'])
@app.route('/<path:server>/download/<path:id>/<path:num>', methods=['GET'])
def handle_download(server=mock_servers[0].IDENTIFIER, id="", num=0):
    releases = data_store[id]
    for release in releases[int(num):]:
        if realdebrid.download(release):
            break
    plex.library.refresh(release)
    content = {}
    content, code, headers = format(content, request)
    return content, code, headers


@app.route('/<path:server>/system/agents', methods=['GET'])
def handle_agents(server):
    mock_server = next((s for s in mock_servers if s.IDENTIFIER == server), None)
    content = mock_server.agents(requests.utils.unquote(request.full_path))
    content, code, headers = format(content, request)
    return content, code, headers


@app.route('/<path:server>/photo/:/transcode', methods=['GET'])
def handle_transcode(server):
    url = request.args.get('url', None)
    if "avatar" in url:
        url = 'https://i.ibb.co/w4BnkC9/GwxAcDV.png'
    response = session.get(url)
    content = response.content
    content, code, headers = format(content, request)
    return content, code, headers


@app.route('/library/sections/2/prefs', methods=['GET'])
@app.route('/:/prefs', methods=['GET'])
@app.route('/<path:server>/library/sections/2/prefs', methods=['GET'])
@app.route('/<path:server>/:/prefs', methods=['GET'])
def handle_prefs(server=mock_servers[0].IDENTIFIER):
    mock_server = next((s for s in mock_servers if s.IDENTIFIER == server), None)
    content = mock_server.prefs()
    content, code, headers = format(content, request)
    return content, code, headers


@app.route('/:/websockets/notifications', methods=['GET'])
@app.route('/updater/status', methods=['GET'])
@app.route('/updater/check', methods=['GET', 'PUT'])
@app.route('/accounts/1', methods=['GET'])
@app.route('/myplex/account', methods=['GET'])
@app.route('/<path:server>/:/websockets/notifications', methods=['GET'])
@app.route('/<path:server>/updater/status', methods=['GET'])
@app.route('/<path:server>/updater/check', methods=['GET', 'PUT'])
@app.route('/<path:server>/accounts/1', methods=['GET'])
@app.route('/<path:server>/myplex/account', methods=['GET'])
def handle_empty(server=mock_servers[0].IDENTIFIER):
    content = {"MediaContainer": {"size": 0}}
    content, code, headers = format(content, request)
    return content, code, headers


# Entry point of the script
if __name__ == "__main__":

    # Configure logging before main program execution
    configure_logging()

    for server in mock_servers:
        server.register()

    logging.info(f"mock servers running on ngrok https: {public_url}")
