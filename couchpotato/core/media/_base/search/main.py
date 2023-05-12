from couchpotato.api import addApiView
from couchpotato.core.event import fireEvent, addEvent
from couchpotato.core.helpers.variable import mergeDicts, getImdb
from couchpotato.core.logger import CPLog
from couchpotato.core.plugins.base import Plugin

log = CPLog(__name__)


class Search(Plugin):

    def __init__(self):

        addApiView('search', self.search, docs = {
            'desc': 'Search the info in providers for a movie',
            'params': {
                'q': {'desc': 'The (partial) movie name you want to search for'},
                'type': {'desc': 'Search for a specific media type. Leave empty to search all.'},
            },
            'return': {'type': 'object', 'example': """{
    'success': True,
    'movies': array,
    'show': array,
    etc
}"""}
        })

        addEvent('app.load', self.addSingleSearches)

    def search(self, q = '', types = None, **kwargs):

        # Make sure types is the correct instance
        if isinstance(types, (str, unicode)):
            types = [types]
        elif isinstance(types, (list, tuple, set)):
            types = list(types)

        imdb_identifier = getImdb(q)

        if types:
            result = {
                media_type: fireEvent(
                    f'{media_type}.info', identifier=imdb_identifier
                )
                if imdb_identifier
                else fireEvent(f'{media_type}.search', q=q)
                for media_type in types
            }
        elif imdb_identifier:
            result = fireEvent('movie.info', identifier = imdb_identifier, merge = True)
            result = {result['type']: [result]}
        else:
            result = fireEvent('info.search', q = q, merge = True)
        return mergeDicts({
            'success': True,
        }, result)

    def createSingleSearch(self, media_type):

        def singleSearch(q, **kwargs):
            return self.search(q, type = media_type, **kwargs)

        return singleSearch

    def addSingleSearches(self):

        for media_type in fireEvent('media.types', merge = True):
            addApiView(f'{media_type}.search', self.createSingleSearch(media_type))
