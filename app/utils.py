import datetime as dt
import typing as t
from decimal import Decimal

import numpy as np
import pandas as pd


class PriceHistory:

    def __init__(self, size=50):
        self._size = size
        self.data = pd.Series(dtype=np.int)

    def add(self, price: Decimal, time: dt.datetime):
        self.data = self.data.append(
            pd.Series([int(price * 100)], index=[time])
        )
        if len(self.data) > self._size:
            self.data = self.data.iloc[1:]

    def calc_sma(self, sma_size: int) -> t.Tuple[dt.datetime, int]:
        if sma_size > self._size:
            raise ValueError(f"SMA size shouldn't be greater than {self._size}!")

        return self.data.index[-1], int(self.data.rolling(sma_size).mean()[-1])

    def __len__(self):
        return len(self.data)
