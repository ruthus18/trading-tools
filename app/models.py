import peewee as pw
from playhouse.pool import PooledPostgresqlExtDatabase

from app import config

db = PooledPostgresqlExtDatabase(
    config.DB_NAME,
    user=config.DB_USER,
    password=config.DB_PASSWORD,
    host=config.DB_HOST,
    port=config.DB_PORT,
    max_connections=config.DB_MAX_CONNECTIONS,
    stale_timeout=config.DB_STALE_TIMEOUT,
    autoconnect=True,
    autocommit=True,
    autorollback=True,
)


class Instrument(pw.Model):
    name = pw.CharField(index=True, unique=True)
    ticker = pw.CharField(unique=True)
    figi = pw.CharField(unique=True)
    currency = pw.CharField(default='USD')

    class Meta:
        database = db
        table_name = 'instruments'


class Candle(pw.Model):
    instrument = pw.ForeignKeyField(Instrument, on_delete='CASCADE')
    interval = pw.CharField(max_length=5)

    open = pw.DecimalField(decimal_places=2)
    high = pw.DecimalField(decimal_places=2)
    low = pw.DecimalField(decimal_places=2)
    close = pw.DecimalField(decimal_places=2)
    volume = pw.DecimalField(decimal_places=2)
    time = pw.DateTimeField()

    class Meta:
        database = db
        table_name = 'candles'

        indexes = (
            (('instrument', 'interval', 'time'), True),  # unique
        )


__models = (Instrument, Candle)


def create_tables():
    with db:
        db.create_tables(__models)


def drop_tables():
    with db:
        db.drop_tables(__models)


def db_connect():
    if db.is_closed():
        db.connect()


def db_close():
    if not db.is_closed():
        db.close()


def select1():
    return db.execute_sql('SELECT 1').fetchone()[0]
