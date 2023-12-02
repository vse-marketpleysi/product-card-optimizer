import asyncio
import logging
from hashlib import sha256

import configobj

import re

import requests
from aiogram import types, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.enums.content_type import ContentType
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, \
    ReplyKeyboardMarkup, KeyboardButton

from src.utils.json_utils import load_json, save_json
from src.handlers.common import START_KEYBOARD

credentials = configobj.ConfigObj('configs/credentials/credentials.ini')
global_config = configobj.ConfigObj('configs/global.ini')

logger = logging.getLogger('tg_main')

payments_router = Router()

BOT_DB = global_config['bot_db_path']
PAYMENTS_PASSWORD = credentials['tg_bot']['PAYMENTS_PASSWORD']
TERMINAL_KEY = credentials['tg_bot']['TERMINAL_KEY']

# rub
PRICE_TO_TOKENS = {
    100: 1,
    490: 5,
    950: 10,
    4500: 50
}

TOKENS_TO_PRICE = {tokens: price for price, tokens in PRICE_TO_TOKENS.items()}

TARIFFS = [f'{tokens} кредитов за {price} руб.' for price, tokens in
           PRICE_TO_TOKENS.items()]

EMAIL_REGEX = re.compile(r"[^@]+@[^@]+\.[^@]+")

CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text='Отмена')
        ]
    ],
    resize_keyboard=True)


class ChangeEmail(StatesGroup):
    email = State()


def get_inline_payment_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=num_credits,
                                               callback_data=num_credits)]
                         for num_credits in TARIFFS] +
                        [[InlineKeyboardButton(text='Изменить почту',
                                               callback_data='change_email')]]
    )


async def increase_token(user_id: str, num_credits: int):
    bot_db = load_json(BOT_DB)
    bot_db['user_info'][user_id]['num_credits'] += num_credits
    save_json(BOT_DB, bot_db)


async def get_email(user_id: str):
    bot_db = load_json(BOT_DB)
    email = bot_db['user_info'][user_id]['email']
    return email


async def ask_email(message: types.Message, state: FSMContext):
    await message.answer("Напишите свою электронную почту, "
                         "куда будут приходить чеки",
                         reply_markup=CANCEL_KEYBOARD)
    await state.set_state(ChangeEmail.email)


@payments_router.message(Command('pay'))
@payments_router.message(F.text == 'Купить токены')
async def cmd_pay(message: types.Message, state: FSMContext):
    # проверяем наличие адреса почты в БД
    user_id = str(message.from_user.id)
    email = await get_email(user_id)
    if not email:
        await ask_email(message, state)
        return

    inline_payment_kb = get_inline_payment_keyboard()

    await message.answer("Выберите тариф. "
                         "1 токен = 1 видеообложка.",
                         reply_markup=inline_payment_kb)


@payments_router.callback_query(F.data == 'change_email')
async def change_email(callback: types.CallbackQuery, state: FSMContext):
    await ask_email(callback.message, state)
    await callback.answer()


def is_correct_email(email: str):
    if EMAIL_REGEX.match(email):
        return True
    else:
        return False


@payments_router.message(ChangeEmail.email)
async def process_change_email(message: types.Message, state: FSMContext):
    email = message.text
    user_id = str(message.from_user.id)
    username = message.from_user.username

    if not is_correct_email(email):
        await message.answer("Адрес электронной почты некорректен",
                             reply_markup=START_KEYBOARD)
        await state.clear()
        return

    bot_db = load_json(BOT_DB)
    bot_db['user_info'][user_id]['email'] = email
    save_json(BOT_DB, bot_db)
    logger.info(
        f'User @{username}({user_id}): email has been updated'
    )

    inline_payment_kb = get_inline_payment_keyboard()

    await message.answer("Выберите тариф. "
                         "1 токен = 1 видеообложка.",
                         reply_markup=inline_payment_kb)
    await state.clear()


def generate_token(params: dict, password: str):
    params_array = list(params.items())
    params_array.append(('Password', password))
    params_array.sort()
    params_array = [str(x[1]) for x in params_array]
    params_array_str = ''.join(params_array)
    token = sha256(params_array_str.encode('utf-8')).hexdigest()

    return token


@payments_router.callback_query(F.data.in_(TARIFFS))
async def pay_callback(callback: types.CallbackQuery,
                       state: FSMContext):
    user_id = str(callback.from_user.id)
    username = str(callback.message.from_user.username)
    message_id = str(callback.message.message_id)
    description = callback.data

    # Готовим данные для генерации ссылки на оплату
    m = re.match(r'(?P<num_credits>.*) токенов за (?P<price>.*) руб.',
                 description)
    num_credits = int(m.group('num_credits'))
    price = int(m.group('price'))
    email = await get_email(user_id)
    init_url = 'https://securepay.tinkoff.ru/v2/Init'
    order_id = user_id+'_'+message_id
    init_params = dict(
        TerminalKey=TERMINAL_KEY,
        Amount=price*100,  # в копейках
        OrderId=order_id,
        Description=description,
    )
    init_token = generate_token(init_params, PAYMENTS_PASSWORD)
    init_params['Token'] = init_token
    init_params['DATA'] = dict(
        UserId=user_id,
        NumTokens=num_credits
    )
    init_params['Receipt'] = dict(
        Email=email,
        Taxation='usn_income',
        FfdVersion='1.2',
        Items=[dict(
            Name=f'Токены для видеообложек',
            Price=price*100 // num_credits,  # в копейках
            Quantity=num_credits,
            Amount=price*100,  # в копейках
            Tax='none',
            PaymentMethod='full_prepayment',
            PaymentObject='service',
            MeasurementUnit='шт'
        )]
    )

    # Создаем ссылку на оплату
    payment_request = requests.post(init_url, json=init_params)
    payment_request = payment_request.json()

    if not payment_request['Success']:
        logger.info(f'User @{username}({user_id}):\n'
                    f'Код ошибки: {payment_request["ErrorCode"]}\n'
                    f'Текст ошибки: {payment_request["Message"]}\n'
                    f'URL запроса: {init_url}\n'
                    f'Параметры запроса: {init_params}\n')

    payment_url = payment_request['PaymentURL']
    payment_id = payment_request['PaymentId']

    await callback.message.answer(f'Произведите оплату по данной ссылке:\n'
                                  f'{payment_url}')

    # Ждем оплаты...
    total_waiting_time = 3600  # 1 hour
    period_time = 5  # 5 sec
    num_iters = total_waiting_time // period_time
    get_state_url = 'https://securepay.tinkoff.ru/v2/GetState'
    get_state_params = dict(
        TerminalKey=TERMINAL_KEY,
        PaymentId=payment_id
    )
    get_state_token = generate_token(get_state_params, PAYMENTS_PASSWORD)
    get_state_params['Token'] = get_state_token

    for i in range(num_iters):
        get_state_request = requests.post(get_state_url, json=get_state_params)
        get_state_request = get_state_request.json()
        if not get_state_request['Success']:
            logger.info(f'User @{username}({user_id}):\n'
                        f'Код ошибки: {get_state_request["ErrorCode"]}\n'
                        f'Текст ошибки: {get_state_request["Message"]}\n'
                        f'URL запроса: {get_state_url}\n'
                        f'Параметры запроса: {get_state_params}\n')

        status = get_state_request['Status']
        if status == 'CONFIRMED':
            # Отсылаем закрывающий чек
            send_closing_receipt_url = ('https://securepay.tinkoff.ru/v2'
                                        '/SendClosingReceipt')
            send_closing_receipt_params = get_state_params.copy()
            send_closing_receipt_params['Receipt'] = init_params['Receipt']
            send_closing_receipt_request = requests.post(
                send_closing_receipt_url,
                json=send_closing_receipt_params
            )
            send_closing_receipt_request = send_closing_receipt_request.json()
            if not send_closing_receipt_request['Success']:
                logger.info(f'User @{username}({user_id}):\n'
                            f'Код ошибки: '
                            f'{send_closing_receipt_request["ErrorCode"]}\n'
                            f'Текст ошибки: '
                            f'{send_closing_receipt_request["Message"]}\n'
                            f'URL запроса: '
                            f'{send_closing_receipt_url}\n'
                            f'Параметры запроса: '
                            f'{send_closing_receipt_params}\n')

            # Начисляем токены на аккаунт
            await increase_token(user_id, num_credits)
            logger.info(f'User @{username}({user_id}): '
                        f'The transaction was successful!\n'
                        f'Price: {price}\n'
                        f'NumTokens: {num_credits}\n'
                        f'PaymentId: {payment_id}\n'
                        f'OrderId: {order_id}')

            await callback.message.answer(f'Платеж на сумму {price} руб. за '
                                          f'{num_credits} токенов получен!',
                                          reply_markup=START_KEYBOARD)
            break

        await asyncio.sleep(period_time)
    # await callback.answer()
