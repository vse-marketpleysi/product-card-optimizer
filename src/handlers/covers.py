import logging

import os
import configobj
import asyncio
from concurrent.futures import ThreadPoolExecutor
import uuid
import shutil
import traceback


from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, FSInputFile
from aiogram.filters import Command

from src.utils.json_utils import load_json, save_json
from src.handlers.common import START_KEYBOARD
from src.engine.animation_engine import apply_effect, Effect, get_effect_from_string, string_to_effect, effects_accepting_many_images
from src.adapters.exceptions import ProductNotFound
from src.adapters.OzonAdapter import OzonAdapter

executor = ThreadPoolExecutor()

global_config = configobj.ConfigObj('configs/global.ini')
logger = logging.getLogger('tg_main')
BOT_DB = global_config['bot_db_path']
covers_router = Router()


class CoversState(StatesGroup):
    token_edit = State()
    choose_sku = State()

button_names = [k for k, v in string_to_effect.items()]

AFTER_CHECKOUT_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Загрузить инфографику на Озон')],
        [KeyboardButton(text='Отмена')]
    ],
    resize_keyboard=True)

MANUAL_UPLOAD_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Перейти к созданию видеообложки')],
        [KeyboardButton(text='Отмена')]
    ],
    resize_keyboard=True)

CONFIRM_BUY_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Подтвердить покупку')],
        [KeyboardButton(text='Отмена')]
    ],
    resize_keyboard=True)

CHOOSE_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Улучшить описание товара')],
        [KeyboardButton(text='Создать инфографику')],
        [KeyboardButton(text='Отмена')]
    ],
    resize_keyboard=True)

CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Отмена')]
    ],
    resize_keyboard=True)


@covers_router.message(F.text == 'Добавить токен Озон')
async def cmd_add_ozon_token(message: types.Message, state: FSMContext):
    await request_token(message, state)


@covers_router.message(CoversState.token_edit)
async def cmd_add_ozon_token_followup(message: types.Message, state: FSMContext):
    ozon_token = message.text
    if not ozon_token:
        await message.answer('Введите токен магазина на Озон:', reply_markup=CANCEL_KEYBOARD)
        return

    ozon_adapter = OzonAdapter(ozon_token)
    is_success = await ozon_adapter.test_token()
    if is_success:
        await message.answer('Токен добавлен, Вы можете приступить к созданию видеообложек '
                             'товаров!', reply_markup=START_KEYBOARD)
        
        bot_db = load_json(BOT_DB)
        bot_db['user_info'][str(message.from_user.id)]['ozon_token'] = ozon_token
        save_json(BOT_DB, bot_db)

        await state.set_state()
    else:
        await message.answer('Неверный токен, мы не можем установить связь с магазином', reply_markup=CANCEL_KEYBOARD)


async def request_token(message: types.Message, state: FSMContext):
    img = FSInputFile('db/examples/api_key.png', filename=f'api_key.png')
    await message.answer_photo(img, 'Добавьте токен Озон, чтобы мы могли скачать изображения Ваших товаров. '
                                'Введите в формате client_id:api_key. Например для аккаунта приведенного '
                                'на скриншоте это будет 441451:dce..b74', reply_markup=CANCEL_KEYBOARD)
    img = FSInputFile('db/examples/permissions.png', filename=f'permissions.png')
    await message.answer_photo(img, 'Убедитесь, что у ключа доступа будет уровень "Администратор", '
                               'иначе мы не сможем загрузить видеообложку в Ваш магазин на Озон', 
                               reply_markup=CANCEL_KEYBOARD)
    await state.set_state(CoversState.token_edit)


@covers_router.message(F.text == 'Выбрать продукт на Озон')
async def cmd_choose_ozon_product(message: types.Message, state: FSMContext):
    bot_db = load_json(BOT_DB)
    if bot_db['user_info'][str(message.from_user.id)]['ozon_token']:
        await message.answer('Напишите артикул товара, чтобы мы смогли изучить карточку:', reply_markup=CANCEL_KEYBOARD)
        await state.set_state(CoversState.choose_sku)
    else:
        await request_token(message, state)


async def choose_sku_and_load_data(message: types.Message, state: FSMContext):
    bot_db = load_json(BOT_DB)
    ozon_token = bot_db['user_info'][str(message.from_user.id)]['ozon_token']
    ozon_adapter = OzonAdapter(ozon_token)

    sku = message.text
    cannot_access_store = False
    try:
        product = await ozon_adapter.get_product_data(sku)
    except ProductNotFound:
        product = None
    except:
        cannot_access_store = True

    if product:
        product_images = product['images']

    try:
        description = await ozon_adapter.get_product_description(sku)
    except ProductNotFound:
        description = None
    except:
        cannot_access_store = True

    if description:
        product_name = description['name']
        product_description = description['description']

    if cannot_access_store:
        await message.answer('Не смогли зайти в магазин, проверьте что введенный токен актуален', reply_markup=CANCEL_KEYBOARD)
    elif product is None:
        await message.answer('Не смогли найти такой товар в магазине', reply_markup=CANCEL_KEYBOARD)
    elif len(product_images) == 0:
        await message.answer('У выбранного товара нет изображений', reply_markup=CANCEL_KEYBOARD)
    else:
        await state.update_data(sku=sku,
                                images=product_images,
                                name=product_name,
                                description=product_description
                                )
        await message.answer('Товар найден')
        return True
    return False


@covers_router.message(CoversState.choose_sku)
async def cmd_choose_sku(message: types.Message, state: FSMContext):
    is_success = await choose_sku_and_load_data(message, state)

    if is_success:
        await state.set_state()
        await message.answer('Выберите опцию:', reply_markup=CHOOSE_KEYBOARD)


@covers_router.message(F.text == 'Улучшить описание товара')
async def improve_product_description(message: types.Message, state: FSMContext):
    data = await state.get_data()
    product_name = data['name']
    product_description = data['description']
    product_image = data['images']


def get_infographic_for_product(image_url, product_description):
    pass

@covers_router.message(F.text == 'Создать инфографику')
async def create_infographics(message: types.Message, state: FSMContext):
    data = await state.get_data()
    product_name = data['name']
    product_description = data['description']
    product_image = data['images'][0]

    infographic_path = get_infographic_for_product(product_image, product_description)

    infographic = open(infographic_path, 'rb')

    await message.answer_photo(infographic, 'Инфографика', reply_markup=AFTER_CHECKOUT_KEYBOARD)
