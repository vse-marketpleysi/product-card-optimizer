import logging

import configobj

from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command

from src.utils.json_utils import load_json, save_json

global_config = configobj.ConfigObj('configs/global.ini')
logger = logging.getLogger('tg_main')
common_router = Router()

INTRO_MESSAGE = '''\
Добро пожаловать в бот для создания инфографики и оптимизации Ваших карточек товаров! Здесь вы сможете создать инфографику \
 и написать лучшее описание Вашего товара.

Для консультации, технической поддержки и предложений по улучшению \
бота обращайтесь к @omnifeed_assistant.

Продукт ООО "ОмниФид" (omnifeed.ru)
'''

BOT_DB = global_config['bot_db_path']

START_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='Добавить токен Озон')
        ],
        # [
        #     KeyboardButton(text='Добавить изображения вручную')
        # ],
        [
            KeyboardButton(text='Выбрать продукт на Озон')
        ],
        # [
        #     KeyboardButton(text='Купить токены')
        # ],
        # [
        #     KeyboardButton(text='Показать токены')
        # ],
    ],
    resize_keyboard=True
)


@common_router.message(Command('start', 'help'))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    user_id = str(message.from_user.id)
    username = message.from_user.username

    bot_db = load_json(BOT_DB)
    if user_id not in bot_db['ids_to_users_nicknames_map'].keys():
        bot_db['users_nicknames_to_ids_map'][username] = user_id
        bot_db['ids_to_users_nicknames_map'][user_id] = username
        bot_db['user_info'][user_id] = {}
        bot_db['user_info'][user_id]['num_credits'] = 2
        bot_db['user_info'][user_id]['ozon_token'] = ''
        bot_db['user_info'][user_id]['email'] = ''
        
        save_json(BOT_DB, bot_db)
        logger.info(
            f'User @{username}({user_id}): added to users_nicknames_to_ids_map'
        )

    await message.answer(INTRO_MESSAGE, reply_markup=START_KEYBOARD)


@common_router.message(Command('cancel'))
@common_router.message(F.text.casefold() == 'отмена')
async def cmd_cancel(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено",
                         reply_markup=START_KEYBOARD)
