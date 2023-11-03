"""Main module for running tasks.

This module sets up a mock plex server using Flask, ngrok for public HTTPS access, and defines routes for handling different tasks. It includes functionality for session management, encoding content, caching, handling media provider routes, metadata, availability, search, download, and agent routes. It also sets up the mock servers based on configurations and runs the Flask application in a separate thread.
"""

from flask import Flask, request
from flask_caching import Cache
from pyngrok import ngrok, conf, process
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
import os

# Initialize a session object from the common module for HTTP requests
session = common.session()

# Specify the port number for the Flask application
PORT = 8008


def configure_logging():
    """Configure logging settings for the application."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s (%(levelname)s) [%(module)s.%(funcName)s] %(message)s'
    )


# Initialize the Flask application
app = Flask(__name__)
# Set up caching for the Flask application with simple backend and default timeout
cache = Cache(app, config={'CACHE_TYPE': 'simple', "CACHE_DEFAULT_TIMEOUT": 300})

# Configure the default region for ngrok and connect to establish a public URL
conf.get_default().region = 'us'
public_url = ngrok.connect(PORT)

# Silence the Flask and dicttoxml loggers
logging.getLogger('werkzeug').disabled = True
logging.getLogger('dicttoxml').setLevel(logging.WARNING)
logging.getLogger('ngrok').disabled = True
logging.getLogger('pyngrok').disabled = True
logging.getLogger('process').disabled = True
process.logger.disabled = True
process.ngrok_logger.disabled = True
# Start the Flask application in a separate thread to allow concurrent processing
threading.Thread(target=app.run, kwargs={
    'use_reloader': False,
    'debug': False,
    'port': PORT
}).start()

# Initialize mock Plex servers based on settings and the obtained ngrok public URL
mock_servers = [plex.mockserver(server, public_url.public_url) for server in settings.get("versions")]


def zlib_encode(content):
    """Compress content using zlib with highest compression level."""
    zlib_compress = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS)
    data = zlib_compress.compress(content) + zlib_compress.flush()
    return data


def deflate_encode(content):
    """Compress content using deflate algorithm."""
    deflate_compress = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    data = deflate_compress.compress(content) + deflate_compress.flush()
    return data


def gzip_encode(content):
    """Compress content using gzip algorithm."""
    gzip_compress = zlib.compressobj(9, zlib.DEFLATED, zlib.MAX_WBITS | 16)
    data = gzip_compress.compress(content) + gzip_compress.flush()
    return data


def format(content, request):
    """Encode and format the response content based on the request's accepted MIME types.

    Args:
        content: The response content to be encoded and formatted.
        request: The Flask request object containing the client's request details.

    Returns:
        A tuple containing the encoded content, HTTP status code, and response headers.
    """
    # Convert content to XML or JSON based on request's accepted MIME types
    if request.accept_mimetypes.best == 'application/xml' and isinstance(content, dict):
        content = dicttoxml(content, root=False, attr_type=False)
    elif isinstance(content, dict):
        content = json.dumps(content).encode('utf-8')
    # Compress the content and prepare headers for the response
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


# Define global variables for managing state and locks for thread safety
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
    """Handle requests for media providers.

    This route is used to determine if a server is online via regular polling.
    Its also used to define the servers name as shown in the Plex UI.

    Args:
        server: The optional identifier for a specific mock server.

    (Mobile and TV clients dont respect the "server" identifier in /<path:server>/... and rather call the endpoint directly /... )

    Returns:
        The response content, status code, and headers as formatted by the `format` function.
    """
    # Select the appropriate mock server based on the server identifier
    mock_server = next((s for s in mock_servers if s.IDENTIFIER == server), None)
    # Decode the request's full path
    path = requests.utils.unquote(request.full_path)
    # Get content from the mock server's provider method
    content = mock_server.provider('includePreferences=1' in path)
    # Format the content based on the request headers and return the response
    content, code, headers = format(content, request)
    return content, code, headers


@app.route('/<path:server>/library/metadata/<path:guid>', methods=['GET'])
def handle_metadata(server, guid):
    """Handle requests for metadata.

    This (currently unused) route can be used to fake the presence of media items in your mocked libraries

    Args:
        server: The optional identifier for a specific mock server.

    (Mobile and TV clients dont respect the "server" identifier in /<path:server>/... and rather call the endpoint directly /... )

    Returns:
        The response content, status code, and headers as formatted by the `format` function.
    """
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
    """Handle requests for library availability.

    This route checks the availability of items in the mocked library by scraping releases
    and comparing them against a debrid service. Found releases are returned as library entries.

    Args:
        server: The optional identifier for a specific mock server.

    (Mobile and TV clients dont respect the "server" identifier in /<path:server>/... and rather call the endpoint directly /... )

    Returns:
        The response content, status code, and headers as formatted by the `format` function.
    """
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
    """Handle search requests.

    This route searches torrentio by search query and returns search results by scraping releases
    and comparing them against a debrid service. Found releases are returned as library entries.

    Args:
        server: The optional identifier for a specific mock server.

    (Mobile and TV clients dont respect the "server" identifier in /<path:server>/... and rather call the endpoint directly /... )

    Returns:
        The response content, status code, and headers as formatted by the `format` function.
    """
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
                    "score": "1",
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
    """Handle download requests.

    This (only internally used) route actually downloads the releases

    Args:
        server: The optional identifier for a specific mock server.

    (Mobile and TV clients dont respect the "server" identifier in /<path:server>/... and rather call the endpoint directly /... )

    Returns:
        The response content, status code, and headers as formatted by the `format` function.
    """
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
    """Handle search requests.

    This (currently unused) route would be called when accessing the mock servers "agent" settings.
    The idea would be to allow the user to control this programs settings through the official plex UI.

    Args:
        server: The optional identifier for a specific mock server.

    (Mobile and TV clients dont respect the "server" identifier in /<path:server>/... and rather call the endpoint directly /... )

    Returns:
        The response content, status code, and headers as formatted by the `format` function.
    """
    mock_server = next((s for s in mock_servers if s.IDENTIFIER == server), None)
    content = mock_server.agents(requests.utils.unquote(request.full_path))
    content, code, headers = format(content, request)
    return content, code, headers


@app.route('/photo/:/transcode', methods=['GET'])
@app.route('/<path:server>/photo/:/transcode', methods=['GET'])
def handle_transcode(server):
    """Handle photo transcode requests.

    This route is used by Plex to request a client specific resize of metadata pictures.
    It also allows us to respond with a different user profile picture for our mock servers.

    Args:
        server: The optional identifier for a specific mock server.

    (Mobile and TV clients dont respect the "server" identifier in /<path:server>/... and rather call the endpoint directly /... )

    Returns:
        The response content, status code, and headers as formatted by the `format` function.
    """
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
    """Handle preference requests.

    These routes are used by Plex to request a servers preferences.
    This is also where the mock server name is once again asked for.

    Args:
        server: The optional identifier for a specific mock server.

    (Mobile and TV clients dont respect the "server" identifier in /<path:server>/... and rather call the endpoint directly /... )

    Returns:
        The response content, status code, and headers as formatted by the `format` function.
    """
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
    """Handle keep-alive requests.

    These routes are used by Plex to determine a variety of things, but they can be handled by empty responses.
    Its just important to respond at all, to keep the server alive in the eyes of plex.

    Args:
        server: The optional identifier for a specific mock server.

    (Mobile and TV clients dont respect the "server" identifier in /<path:server>/... and rather call the endpoint directly /... )

    Returns:
        The response content, status code, and headers as formatted by the `format` function.
    """
    content = {"MediaContainer": {"size": 0}}
    content, code, headers = format(content, request)
    return content, code, headers


# Entry point of the script
if __name__ == "__main__":
    # Configure logging before main program execution
    configure_logging()

    # Register mock servers for handling routes
    for server in mock_servers:
        server.register()

    # Log the information about ngrok public URL where the mock servers are running
    logging.info(f"mock servers running on ngrok https: {public_url}")
