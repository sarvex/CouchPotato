from couchpotato.core.event import fire_event
from couchpotato.core.helpers.encoding import try_url_encode
from couchpotato.core.logger import CPLog
from couchpotato.core.media._base.providers.torrent.torrentshack import Base
from couchpotato.core.media.movie.providers.base import MovieProvider

log = CPLog(__name__)

autoload = 'TorrentShack'


class TorrentShack(MovieProvider, Base):

    # TorrentShack movie search categories
    #   Movies/x264 - 300
    #   Movies/DVD-R - 350
    #   Movies/XviD - 400
    #   Full Blu-ray - 970
    #
    #   REMUX - 320 (not included)
    #   Movies-HD Pack - 982 (not included)
    #   Movies-SD Pack - 983 (not included)

    cat_ids = [
        ([970, 320], ['bd50']),
        ([300, 320], ['720p', '1080p']),
        ([350], ['dvdr']),
        ([400], ['brrip', 'dvdrip']),
    ]
    cat_backup_id = 400

    def buildUrl(self, media, quality):
        query = (try_url_encode(fire_event('library.query', media, single=True)),
                 self.getSceneOnly(),
                 self.getCatId(quality)[0])
        return query
