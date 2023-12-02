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
from src.handlers.payments import get_inline_payment_keyboard
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
    manual_images_upload = State()
    choose_sku = State()
    choose_sku_after_buy = State()
    choose_effect = State()
    buy_cover = State()

button_names = [k for k, v in string_to_effect.items()]


def get_effects_keyboard(add_token_button=False, buy_button=False):
    keyboard=[
            [KeyboardButton(text='Загрузить видеообложку на Озон')],
            [KeyboardButton(text='Отмена'), *[KeyboardButton(text=k) for k in button_names[:2]]],
            [*[KeyboardButton(text=k) for k in button_names[2:5]]],
            [*[KeyboardButton(text=k) for k in button_names[5:8]]],
            [*[KeyboardButton(text=k) for k in button_names[8:]]],
        ]
    if add_token_button:
        keyboard = [[KeyboardButton(text='Добавить токен Озон')]] + keyboard
    if buy_button:
        keyboard = [[KeyboardButton(text='Купить эту видеообложку')]] + keyboard
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


AFTER_CHECKOUT_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Загрузить видеообложку на Озон')],
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

CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text='Отмена')]
    ],
    resize_keyboard=True)



@covers_router.message(Command('show_me_demo'))
async def cmd_show_me_demo(message: types.Message, state: FSMContext):

    image_path = 'db/examples/demo_screen.png'
    image = FSInputFile(image_path, filename='demo_screen.png')
    await message.answer_photo(image, caption=f'Палитра с эффектами находится в клавиатуре. '
                               'Используйте их чтобы сгенерировать идеальную видеообложку для Вашей карточки товара')

    examples = ['BLUE_STARTS_MANY', 'SLIDES', 'CLOSE_UP_AND_SLIDE_DOWN']
    for example in examples:
        video_path = f'db/examples/example_{example}.mp4'
        video = FSInputFile(video_path, filename=f'example_{example}.mp4')
        await message.answer_video(video, caption=f'Пример эффекта {example}')

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


@covers_router.message(F.text == 'Добавить изображения вручную')
async def cmd_add_images_manually(message: types.Message, state: FSMContext):
    await message.answer('Отправьте нам изображения для создания видеообложки товара', reply_markup=MANUAL_UPLOAD_KEYBOARD)
    await state.set_state(CoversState.manual_images_upload)


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
    await state.update_data(video_path=None)

    bot_db = load_json(BOT_DB)
    if bot_db['user_info'][str(message.from_user.id)]['ozon_token']:
        await message.answer('Напишите артикул товара и мы скачаем его изображения:', reply_markup=CANCEL_KEYBOARD)
        await state.set_state(CoversState.choose_sku)
    else:
        await request_token(message, state)

@covers_router.message(CoversState.manual_images_upload, F.content_type == types.ContentType.PHOTO)
async def cmd_manual_images_upload(message: types.Message, state: FSMContext):
    await state.update_data(video_path=None, sku=None)

    image_folder = 'db/images'
    os.makedirs(image_folder, exist_ok=True)

    if message.photo is None:
        await message.reply('Не смогли скачать фото, загрузите фото еще раз')
        return

    file_id = message.photo[-1].file_id
    file_path = os.path.join(image_folder, f'{file_id}.jpg')

    file_info = await message.bot.get_file(file_id)
    await message.bot.download_file(file_info.file_path, file_path)

    current_data = await state.get_data()
    images = current_data.get('images', [])
    images.append(file_path)
    await state.update_data(images=images)

    await message.reply('Изображение загружено')


@covers_router.message(CoversState.manual_images_upload, F.text == 'Перейти к созданию видеообложки')
async def images_done(message: types.Message, state: FSMContext):
    await state.update_data(video_path=None)

    await message.answer('Выберите эффект:', reply_markup=get_effects_keyboard())
    await state.set_state(CoversState.choose_effect)


async def choose_sku_and_load_images(message: types.Message, state: FSMContext):
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

    if cannot_access_store:
        await message.answer('Не смогли зайти в магазин, проверьте что введенный токен актуален', reply_markup=CANCEL_KEYBOARD)
    elif product is None:
        await message.answer('Не смогли найти такой товар в магазине', reply_markup=CANCEL_KEYBOARD)
    elif len(product_images) == 0:
        await message.answer('У выбранного товара нет изображений', reply_markup=CANCEL_KEYBOARD)
    else:
        await state.update_data(sku=sku, images=product_images)
        await message.answer('Товар найден')
        return True
    return False


@covers_router.message(CoversState.choose_sku)
async def cmd_choose_sku(message: types.Message, state: FSMContext):
    await state.update_data(video_path=None)

    is_success = await choose_sku_and_load_images(message, state)

    if is_success:
        await state.set_state(CoversState.choose_effect)
        await message.answer('Выберите эффект', reply_markup=get_effects_keyboard())


async def create_and_send_video(message: types.Message, state: FSMContext, add_watermark: bool):
    user_data = await state.get_data()
    image_paths = user_data.get('images', [])
    effect_name = user_data.get('last_effect_chosen', '')
    effect = get_effect_from_string(effect_name)

    await message.answer(f'Начали готовить видеообложку с эффектом "{effect_name}"', reply_markup=CANCEL_KEYBOARD)
    
    results_folder = 'db/results'
    os.makedirs(results_folder, exist_ok=True)
    video_path = f'{results_folder}/{message.chat.id}-{effect_name}-{str(uuid.uuid4())}.mp4'

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(executor, apply_effect, image_paths, video_path, effect, add_watermark)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        print(f"Traceback: {traceback.format_exc()}")
    
    await state.update_data(video_path=video_path)
    video = FSInputFile(video_path, filename='video.mp4')
    buy_me_text = '' if not add_watermark else ' Купите видеообложку, чтобы получить результат без водяных знаков.'
    await message.answer_video(video, caption=f'Эффект "{effect_name}" применен.' + buy_me_text, 
                               reply_markup=get_effects_keyboard(buy_button=True))


@covers_router.message(F.text == 'Показать токены')
async def cmd_show_credits(message: types.Message, state: FSMContext):
    bot_db = load_json(BOT_DB)
    num_credits = bot_db['user_info'][str(message.from_user.id)]['num_credits']
    await message.answer(f'Текущий баланс: {num_credits} токенов')


@covers_router.message(CoversState.choose_effect, F.text.in_(set(button_names)))
async def choose_effect(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    image_paths = user_data.get('images', [])
    current_jobs_number = user_data.get('current_jobs_number', 0)
    
    if not image_paths:
        await message.answer('Загрузите изображения товара', reply_markup=MANUAL_UPLOAD_KEYBOARD)
        await state.set_state(CoversState.manual_images_upload)
        return
    
    if current_jobs_number > 0:
        await message.answer('Обрабатываем ваши предыдущие запросы, вы сможете отправить новый запрос как '
                             'только мы завершим работу над ними')
        return
    
    effect_name = message.text
    effect = get_effect_from_string(effect_name)
    if effect in effects_accepting_many_images and len(image_paths) < 2:
        await message.answer(f'Эффект "{effect_name}" может быть применен только к серии картинок')
        return

    await state.update_data(current_jobs_number=current_jobs_number + 1,
                            last_effect_chosen=effect_name)

    try:
        await create_and_send_video(message, state, add_watermark=True)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        print(f"Traceback: {traceback.format_exc()}")

    user_data = await state.get_data()
    current_jobs_number = user_data.get('current_jobs_number', 0)
    await state.update_data(current_jobs_number=current_jobs_number - 1)


@covers_router.message(CoversState.choose_sku_after_buy)
async def cmd_choose_sku_after_buy(message: types.Message, state: FSMContext):
    is_success = await choose_sku_and_load_images(message, state)
    if is_success:
        await state.set_state(CoversState.buy_cover)
        await message.answer('Товар выбран', reply_markup=AFTER_CHECKOUT_KEYBOARD)


@covers_router.message(CoversState.buy_cover, F.text == 'Загрузить видеообложку на Озон')
async def cmd_upload_video_to_ozon(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    video_path = user_data.get('video_path', '')
    sku = user_data.get('sku', '')

    if not sku:
        await message.answer('Напишите артикул товара и мы загрузим видеообложку для него:', 
                             reply_markup=CANCEL_KEYBOARD)
        await state.set_state(CoversState.choose_sku_after_buy)
        return

    bot_db = load_json(BOT_DB)
    ozon_token = bot_db['user_info'][str(message.from_user.id)]['ozon_token']

    ozon_adapter = OzonAdapter(ozon_token)


    video_path_shared = 'db/hosted_files'
    file_name = os.path.basename(video_path)
    destination = os.path.join(video_path_shared, file_name)
    shutil.copy(video_path, destination)
    video_url = f'http://allmarketplaces.mooo.com/files/omnifeed-covers/{file_name}'

    response = await ozon_adapter.set_video_preview(sku, video_url)
    if response['is_success']:
        await message.answer('Видеообложка загружена на Озон. Обновление карточки товара займет '
                             'несколько минут. Видеообложка будет показываться в поиске, если для данного товара включено какое-либо продвижение', reply_markup=START_KEYBOARD)
        await state.update_data(video_path=None, sku=None, images=[])
        await state.set_state()
    else:
        await message.answer(f'Произошла ошибка: {response["error"]}', reply_markup=get_effects_keyboard())


@covers_router.message(CoversState.choose_effect, F.text == 'Загрузить видеообложку на Озон')
async def cmd_upload_video_to_ozon(message: types.Message, state: FSMContext):
    bot_db = load_json(BOT_DB)
    ozon_token = bot_db['user_info'][str(message.from_user.id)]['ozon_token']
    if not ozon_token:
        await message.answer('Добавьте токен Озон, чтобы мы могли загрузить получившуюся видеообложку '
                             'для Вашего товара на Озон',
                             reply_markup=get_effects_keyboard(add_token_button=True))
        return

    user_data = await state.get_data()
    video_path = user_data.get('video_path', '')

    if not video_path:
        await message.answer('Выберите эффект:', reply_markup=get_effects_keyboard())
        return
    
    await message.answer('Пожалуйста, подтвердите покупку', reply_markup=CONFIRM_BUY_KEYBOARD)
    await state.set_state(CoversState.buy_cover)


@covers_router.message(CoversState.choose_effect, F.text.in_({'Купить эту видеообложку'}))
async def cmd_buy_cover_confirm(message: types.Message, state: FSMContext):
    await message.answer('Пожалуйста, подтвердите покупку', reply_markup=CONFIRM_BUY_KEYBOARD)
    await state.set_state(CoversState.buy_cover)

@covers_router.message(CoversState.buy_cover, F.text.in_({'Подтвердить покупку'}))
async def cmd_buy_cover(message: types.Message, state: FSMContext):
    bot_db = load_json(BOT_DB)
    num_credits = bot_db['user_info'][str(message.from_user.id)]['num_credits']
    if num_credits < 1:
        await message.answer('Недостаточно токенов. Приобретите токены для продолжения работы',
                                reply_markup=get_inline_payment_keyboard())
        await state.set_state()
        return

    await create_and_send_video(message, state, add_watermark=False)

    bot_db = load_json(BOT_DB)
    bot_db['user_info'][str(message.from_user.id)]['num_credits'] -= 1
    save_json(BOT_DB, bot_db)

    await message.answer('Поздравляем, видеообложка Ваша! Теперь вы можете скачать её или сразу '
                         'загрузить на Озон', reply_markup=AFTER_CHECKOUT_KEYBOARD)

@covers_router.message(CoversState.buy_cover, F.text.in_({'Отмена'}))
async def cmd_buy_cover_cancel(message: types.Message, state: FSMContext):
    await message.answer('Покупка отменена', reply_markup=get_effects_keyboard())
    await state.set_state(CoversState.choose_effect)
