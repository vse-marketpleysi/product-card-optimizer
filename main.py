# Add parent dir to path
import sys
from os.path import dirname

import logging

import asyncio
import configobj
from pathlib import Path


from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiogram.enums.parse_mode import ParseMode

from aiogram.fsm.storage.redis import RedisStorage
from aioredis.client import Redis

from src.handlers.common import common_router
from src.handlers.payments import payments_router
from src.handlers.covers import covers_router
from src.of_logging import logging_middleware


from src.utils.json_utils import create_json_if_not_exist
from src.utils.usage_limit import UsageLimiter

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.append('/'.join(dirname(__file__).split('/')[:-2]))


credentials = configobj.ConfigObj('configs/credentials/credentials.ini')
global_config = configobj.ConfigObj('configs/global.ini')

usage_limiter = UsageLimiter(config_path='configs/global.ini', db_path_base='db/')

# Create logger
logger = logging.getLogger('tg_main')
logs_path = global_config['logs_path']
Path(logs_path).mkdir(parents=True, exist_ok=True)
logging.getLogger('googleapicliet.discovery_cache').setLevel(logging.ERROR)
logging.basicConfig(format='%(asctime)s: %(message)s',
                    datefmt='%d/%m/%Y %H:%M:%S',
                    level=logging.INFO,
                    handlers=[logging.FileHandler(logs_path + 'tg_bot.log',
                                                  mode='a'),
                              logging.StreamHandler()])

bot = Bot(token=credentials['tg_bot']['TOKEN'],
          parse_mode=ParseMode.HTML)

BOT_DB = global_config['bot_db_path']


async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="/start", description="Старт"),
        BotCommand(command="/cancel", description="Отменить действие"),
        BotCommand(command="/pay", description="Купить токены"),
    ]
    await bot.set_my_commands(commands)


async def main(loop):
    logger.info("Starting bot")

    # Создание json-файла, как db
    json_fields = {
        "users_nicknames_to_ids_map": {},
        "ids_to_users_nicknames_map": {},
        "user_info": {}
    }

    create_json_if_not_exist(BOT_DB, json_fields)

    redis_client = Redis.from_url("redis://localhost:6379/5")
    dp = Dispatcher(storage=RedisStorage(redis=redis_client))
    
    dp.update.outer_middleware(logging_middleware)

    dp.include_router(common_router)
    dp.include_router(payments_router)
    dp.include_router(covers_router)

    await set_commands(bot)

    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.gather(
        asyncio.create_task(dp.start_polling(bot)),
    )


if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main(loop))
