import logging
import logging.config
from aiogram import types, BaseMiddleware
from aiogram.fsm.context import FSMContext

from aiogram.types import TelegramObject, Message, Update
from typing import Callable, Dict, Any, Awaitable
# Create a custom logger
logger = logging.getLogger('chat_logger')
logger.propagate = False
logger.setLevel(logging.INFO)

# Remove any default handlers
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Create handlers
file_handler = logging.FileHandler('db/logs/chat_logs.log')
stdout_handler = logging.StreamHandler()

# Create formatters and add them to handlers
formatter = logging.Formatter('%(asctime)s - %(message)s')
file_handler.setFormatter(formatter)
stdout_handler.setFormatter(formatter)

# Add handlers to the logger
logger.addHandler(file_handler)
logger.addHandler(stdout_handler)


async def logging_middleware(
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any]
    ) -> Any:

    if isinstance(event, Update) and event.message:
        message = event.message
        user_id = message.from_user.id
        username = "@" + message.from_user.username if message.from_user.username else "No Username"
        text = message.text or 'No Text'

        # Initialize file_id as empty, will remain empty if no files are in the message
        file_id = ''
        
        if message.document:
            file_id = f", File ID (Document): {message.document.file_id}"
        elif message.photo:
            file_id = f", File ID (Photo): {message.photo[-1].file_id}"  # Get largest resolution photo
        elif message.video:
            file_id = f", File ID (Video): {message.video.file_id}"
        # You can add more conditions for other media types

        logger.info(f"User: {user_id}, Username: {username}, Text: {text}{file_id}")

    return await handler(event, data)
