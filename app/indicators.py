import datetime as dt
import logging

from . import schemas
from .market import Market
from .utils import PriceHistory


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class PositionType(schemas.Enum):
    long = 'long'
    short = 'short'


class Indicator:

    def __init__(self):
        self.market = None

    def _on_candle(self, candle: schemas.Candle):
        if not self.market:
            raise RuntimeError('You should call `start` method before receiving candles data!')

        self.on_candle(candle)

    def on_candle(self, candle: schemas.Candle):
        raise NotImplementedError

    def start(self, market: Market):
        self.market = market


# TODO: Check cases when SMA(i) = SMA(j)
class OrderedSMAIndicator(Indicator):
    """Индикатор, работающий на основе расположения SMA относительно друг друга

    SMA = [2, 8, 14, 20]

    Открытие long позиции: SMA(2) > SMA(8) > SMA(14) > SMA(20)
    Закрытие long позиции: SMA(2) < SMA(8)

    Открытие short позиции: SMA(2) < SMA(8) < SMA(14) < SMA(20)
    Закрытие short позиции: SMA(2) > SMA(8)
    """

    def __init__(self):
        super().__init__()

        self.history = PriceHistory(size=20)

        self.current_position: PositionType = None
        self.current_time: dt.datetime = None

    def on_candle(self, candle: schemas.Candle):
        self.history.add(candle.close, candle.time)
        self.current_time = candle.time

        if len(self.history) < 20:
            return

        current_sma = tuple(self.history.calc_sma(size) for size in (2, 8, 14, 20))

        if self.current_position is None:
            self._try_open_position(current_sma)

        elif self.current_position == PositionType.long:
            self._try_close_long_postition(current_sma)

        elif self.current_position == PositionType.short:
            self._try_close_short_postition(current_sma)

        else:
            raise RuntimeError('Wrong position type!')

    def _try_open_position(self, current_sma: tuple):
        sma2, sma8, sma14, sma20 = current_sma
        position = None

        if sma2 > sma8 > sma14 > sma20:
            position = PositionType.long

        elif sma2 < sma8 < sma14 < sma20:
            position = PositionType.short

        if position is not None:
            self.current_position = position
            self.market.open_position(position)

            logger.debug('Open %s position at %s', position, self.current_time)

    def _try_close_long_postition(self, current_sma: tuple):
        sma2, sma8, sma14, sma20 = current_sma

        if sma2 < sma8:
            self.market.close_position()
            self.current_position = None

        logger.debug('Close long position at %s', self.current_time)

    def _try_close_short_postition(self, current_sma: tuple):
        sma2, sma8, sma14, sma20 = current_sma

        if sma2 > sma8:
            self.market.close_position()
            self.current_position = None

        logger.debug('Close short position at %s', self.current_time)
