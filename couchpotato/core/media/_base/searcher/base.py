from couchpotato.core.event import addEvent, fireEvent
from couchpotato.core.logger import CPLog
from couchpotato.core.plugins.base import Plugin

log = CPLog(__name__)


class SearcherBase(Plugin):

    in_progress = False

    def __init__(self):
        super(SearcherBase, self).__init__()

        addEvent('searcher.progress', self.getProgress)
        addEvent(f'{self.getType()}.searcher.progress', self.getProgress)

        self.initCron()

    def initCron(self):
        """ Set the searcher cronjob
            Make sure to reset cronjob after setting has changed
        """

        _type = self.getType()

        def setCrons():
            fireEvent(
                'schedule.cron',
                f'{_type}.searcher.all',
                self.searchAll,
                day=self.conf('cron_day'),
                hour=self.conf('cron_hour'),
                minute=self.conf('cron_minute'),
            )

        addEvent('app.load', setCrons)
        addEvent(f'setting.save.{_type}_searcher.cron_day.after', setCrons)
        addEvent(f'setting.save.{_type}_searcher.cron_hour.after', setCrons)
        addEvent(f'setting.save.{_type}_searcher.cron_minute.after', setCrons)

    def getProgress(self, **kwargs):
        """ Return progress of current searcher"""

        return {self.getType(): self.in_progress}
