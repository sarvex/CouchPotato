import os
import re
from base64 import b16encode, b32decode
from datetime import timedelta
from hashlib import sha1
from urllib.parse import urlparse

from bencode import bencode, bdecode
from rtorrent import RTorrent

from couchpotato.core._base.downloader.main import DownloaderBase, ReleaseDownloadList
from couchpotato.core.event import add_event
from couchpotato.core.helpers.encoding import sp
from couchpotato.core.helpers.variable import clean_host, split_string
from couchpotato.core.logger import CPLog

log = CPLog(__name__)

autoload = 'rTorrent'


class rTorrent(DownloaderBase):

    protocol = ['torrent', 'torrent_magnet']
    rt = None
    error_msg = ''

    # Migration url to host options
    def __init__(self):
        super(rTorrent, self).__init__()

        add_event('app.load', self.migrate)
        add_event('setting.save.rtorrent.*.after', self.settings_changed)

    def migrate(self):

        url = self.conf('url')
        if url:
            host_split = split_string(url.split('://')[-1], split_on='/')

            self.conf('ssl', value = url.startswith('https'))
            self.conf('host', value = host_split[0].strip())
            self.conf('rpc_url', value = '/'.join(host_split[1:]))

            self.deleteConf('url')

    def settings_changed(self):
        # Reset active connection if settings have changed
        if self.rt:
            log.debug('Settings have changed, closing active connection')

        self.rt = None
        return True

    def get_auth(self):
        if not self.conf('username') or not self.conf('password'):
            # Missing username or password parameter
            return None

        # Build authentication tuple
        return (
            self.conf('authentication'),
            self.conf('username'),
            self.conf('password')
        )

    def get_verify_ssl(self):
        # Ensure verification has been enabled
        if not self.conf('ssl_verify'):
            return False

        # Use ca bundle if defined
        ca_bundle = self.conf('ssl_ca_bundle')

        if ca_bundle and os.path.exists(ca_bundle):
            return ca_bundle

        # Use default ssl verification
        return True

    def connect(self, reconnect = False):
        # Already connected?
        if not reconnect and self.rt is not None:
            return self.rt

        url = clean_host(self.conf('host'), protocol=True, ssl=self.conf('ssl'))

        # Automatically add '+https' to 'httprpc' protocol if SSL is enabled
        if self.conf('ssl') and url.startswith('httprpc://'):
            url = url.replace('httprpc://', 'httprpc+https://')

        parsed = urlparse(url)

        # rpc_url is only used on http/https scgi pass-through
        if parsed.scheme in ['http', 'https']:
            url += self.conf('rpc_url')

        # Construct client
        self.rt = RTorrent(
            url, self.get_auth(),
            verify_ssl=self.get_verify_ssl()
        )

        self.error_msg = ''
        try:
            self.rt.connection.verify()
        except AssertionError as e:
            self.error_msg = e.message
            self.rt = None

        return self.rt

    def test(self):
        """ Check if connection works
        :return: bool
        """

        if self.connect(True):
            return True

        if self.error_msg:
            return False, 'Connection failed: ' + self.error_msg

        return False


    def download(self, data = None, media = None, filedata = None):
        """ Send a torrent/nzb file to the downloader

        :param data: dict returned from provider
            Contains the release information
        :param media: media dict with information
            Used for creating the filename when possible
        :param filedata: downloaded torrent/nzb filedata
            The file gets downloaded in the searcher and send to this function
            This is done to have failed checking before using the downloader, so the downloader
            doesn't need to worry about that
        :return: boolean
            One faile returns false, but the downloaded should log his own errors
        """

        if not media: media = {}
        if not data: data = {}

        log.debug('Sending "%s" to rTorrent.', (data.get('name')))

        if not self.connect():
            return False

        torrent_hash = 0
        torrent_params = {}
        if self.conf('label'):
            torrent_params['label'] = self.conf('label')

        if not filedata and data.get('protocol') == 'torrent':
            log.error('Failed sending torrent, no data')
            return False

        # Try download magnet torrents
        if data.get('protocol') == 'torrent_magnet':
            # Send magnet to rTorrent
            torrent_hash = re.findall('urn:btih:([\w]{32,40})', data.get('url'))[0].upper()
            # Send request to rTorrent
            try:
                torrent = self.rt.load_magnet(data.get('url'), torrent_hash)

                if not torrent:
                    log.error('Unable to find the torrent, did it fail to load?')
                    return False

            except Exception as err:
                log.error('Failed to send magnet to rTorrent: %s', err)
                return False

        if data.get('protocol') == 'torrent':
            info = bdecode(filedata)["info"]
            torrent_hash = sha1(bencode(info)).hexdigest().upper()

            # Convert base 32 to hex
            if len(torrent_hash) == 32:
                torrent_hash = b16encode(b32decode(torrent_hash))

            # Send request to rTorrent
            try:
                # Send torrent to rTorrent
                torrent = self.rt.load_torrent(filedata, verify_retries=10)

                if not torrent:
                    log.error('Unable to find the torrent, did it fail to load?')
                    return False

            except Exception as err:
                log.error('Failed to send torrent to rTorrent: %s', err)
                return False

        try:
            # Set label
            if self.conf('label'):
                torrent.set_custom(1, self.conf('label'))

            if self.conf('directory'):
                torrent.set_directory(self.conf('directory'))

            # Start torrent
            if not self.conf('paused', default = 0):
                torrent.start()

            return self.download_return_id(torrent_hash)

        except Exception as err:
            log.error('Failed to send torrent to rTorrent: %s', err)
            return False

    def get_torrent_status(self, torrent):
        if not torrent.complete:
            return 'busy'

        if torrent.open:
            return 'seeding'

        return 'completed'

    def get_all_download_status(self, ids):
        """ Get status of all active downloads

        :param ids: list of (mixed) downloader ids
            Used to match the releases for this downloader as there could be
            other downloaders active that it should ignore
        :return: list of releases
        """

        log.debug('Checking rTorrent download status.')

        if not self.connect():
            return []

        try:
            torrents = self.rt.get_torrents()

            release_downloads = ReleaseDownloadList(self)

            for torrent in torrents:
                if torrent.info_hash in ids:
                    torrent_directory = os.path.normpath(torrent.directory)
                    torrent_files = []

                    for file in torrent.get_files():
                        if not os.path.normpath(file.path).startswith(torrent_directory):
                            file_path = os.path.join(torrent_directory, file.path.lstrip('/'))
                        else:
                            file_path = file.path

                        torrent_files.append(sp(file_path))

                    release_downloads.append({
                        'id': torrent.info_hash,
                        'name': torrent.name,
                        'status': self.get_torrent_status(torrent),
                        'seed_ratio': torrent.ratio,
                        'original_status': torrent.state,
                        'timeleft': str(timedelta(seconds = float(torrent.left_bytes) / torrent.down_rate)) if torrent.down_rate > 0 else -1,
                        'folder': sp(torrent.directory),
                        'files': torrent_files
                    })

            return release_downloads

        except Exception as err:
            log.error('Failed to get status from rTorrent: %s', err)
            return []

    def pause(self, release_download, pause = True):
        if not self.connect():
            return False

        torrent = self.rt.find_torrent(release_download['id'])
        if torrent is None:
            return False

        if pause:
            return torrent.pause()
        return torrent.resume()

    def remove_failed(self, release_download):
        log.info('%s failed downloading, deleting...', release_download['name'])
        return self.process_complete(release_download, delete_files=True)

    def process_complete(self, release_download, delete_files):
        log.debug('Requesting rTorrent to remove the torrent %s%s.',
                  (release_download['name'], ' and cleanup the downloaded files' if delete_files else ''))

        if not self.connect():
            return False

        torrent = self.rt.find_torrent(release_download['id'])

        if torrent is None:
            return False

        if delete_files:
            for file_item in torrent.get_files(): # will only delete files, not dir/sub-dir
                os.unlink(os.path.join(torrent.directory, file_item.path))

            if torrent.is_multi_file() and torrent.directory.endswith(torrent.name):
                # Remove empty directories bottom up
                try:
                    for path, _, _ in os.walk(sp(torrent.directory), topdown = False):
                        os.rmdir(path)
                except OSError:
                    log.info('Directory "%s" contains extra files, unable to remove', torrent.directory)

        torrent.erase() # just removes the torrent, doesn't delete data

        return True


config = [{
    'name': 'rtorrent',
    'groups': [
        {
            'tab': 'downloaders',
            'list': 'download_providers',
            'name': 'rtorrent',
            'label': 'rTorrent',
            'description': 'Use <a href="https://rakshasa.github.io/rtorrent/" target="_blank">rTorrent</a> to download torrents.',
            'wizard': True,
            'options': [
                {
                    'name': 'enabled',
                    'default': 0,
                    'type': 'enabler',
                    'radio_group': 'torrent',
                },
                {
                    'name': 'ssl',
                    'label': 'SSL Enabled',
                    'order': 1,
                    'default': 0,
                    'type': 'bool',
                    'advanced': True,
                    'description': 'Use HyperText Transfer Protocol Secure, or <strong>https</strong>',
                },
                {
                    'name': 'ssl_verify',
                    'label': 'SSL Verify',
                    'order': 2,
                    'default': 1,
                    'type': 'bool',
                    'advanced': True,
                    'description': 'Verify SSL certificate on https connections',
                },
                {
                    'name': 'ssl_ca_bundle',
                    'label': 'SSL CA Bundle',
                    'order': 3,
                    'type': 'string',
                    'advanced': True,
                    'description': 'Path to a directory (or file) containing trusted certificate authorities',
                },
                {
                    'name': 'host',
                    'order': 4,
                    'default': 'localhost:80',
                    'description': 'RPC Communication URI. Usually <strong>scgi://localhost:5000</strong>, '
                                   '<strong>httprpc://localhost/rutorrent</strong> or <strong>localhost:80</strong>',
                },
                {
                    'name': 'rpc_url',
                    'order': 5,
                    'default': 'RPC2',
                    'type': 'string',
                    'advanced': True,
                    'description': 'Change if your RPC mount is at a different path.',
                },
                {
                    'name': 'authentication',
                    'order': 6,
                    'default': 'basic',
                    'type': 'dropdown',
                    'advanced': True,
                    'values': [('Basic', 'basic'), ('Digest', 'digest')],
                    'description': 'Authentication method used for http(s) connections',
                },
                {
                    'name': 'username',
                    'order': 7,
                },
                {
                    'name': 'password',
                    'order': 8,
                    'type': 'password',
                },
                {
                    'name': 'label',
                    'order': 9,
                    'description': 'Label to apply on added torrents.',
                },
                {
                    'name': 'directory',
                    'order': 10,
                    'type': 'directory',
                    'description': 'Download to this directory. Keep empty for default rTorrent download directory.',
                },
                {
                    'name': 'remove_complete',
                    'label': 'Remove torrent',
                    'order': 11,
                    'default': False,
                    'type': 'bool',
                    'advanced': True,
                    'description': 'Remove the torrent after it finishes seeding.',
                },
                {
                    'name': 'delete_files',
                    'label': 'Remove files',
                    'order': 12,
                    'default': True,
                    'type': 'bool',
                    'advanced': True,
                    'description': 'Also remove the leftover files.',
                },
                {
                    'name': 'paused',
                    'order': 13,
                    'type': 'bool',
                    'advanced': True,
                    'default': False,
                    'description': 'Add the torrent paused.',
                },
                {
                    'name': 'manual',
                    'order': 14,
                    'default': 0,
                    'type': 'bool',
                    'advanced': True,
                    'description': 'Disable this downloader for automated searches, but use it when I manually send a release.',
                },
            ],
        }
    ],
}]
