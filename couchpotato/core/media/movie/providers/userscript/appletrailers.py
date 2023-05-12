import re
import traceback

from couchpotato import tryInt, CPLog
from couchpotato.core.media._base.providers.userscript.base import UserscriptBase

log = CPLog(__name__)

autoload = 'AppleTrailers'


class AppleTrailers(UserscriptBase):

    includes = ['http://trailers.apple.com/trailers/*']

    def getMovie(self, url):

        try:
            data = self.getUrl(url)
        except:
            return

        try:
            id = re.search("FilmId.*=.*\'(?P<id>.*)\';", data)
            id = id['id']

            data = self.getJsonData(
                f'https://trailers.apple.com/trailers/feeds/data/{id}.json'
            )

            name = data['page']['movie_title']
            year = tryInt(data['page']['release_date'][:4])

            return self.search(name, year)
        except:
            log.error('Failed getting apple trailer info: %s', traceback.format_exc())
            return None
