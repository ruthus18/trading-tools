import environs
import pytz


env = environs.Env()
env.read_env()


DB_HOST = env.str('DB_HOST', 'localhost')
DB_PORT = env.int('BD_PORT', 5432)
DB_NAME = env.str('DB_NAME', 'trading')
DB_USER = env.str('DB_USER', 'trading')
DB_PASSWORD = env.str('DB_PASSWORD', 'trading')


TINKOFF_URL = 'https://api-invest.tinkoff.ru/openapi/'
TINKOFF_SANDBOX_URL = TINKOFF_URL + 'sandbox/'

TINKOFF_SANDBOX_TOKEN = env.str('TINKOFF_SANDBOX_TOKEN')
TINKOFF_TRADING_TOKEN = env.str('TINKOFF_TRADING_TOKEN')


TZ_NAME = env.str('TZ_NAME', 'Asia/Yekaterinburg')
TIMEZONE = pytz.timezone(TZ_NAME) 
