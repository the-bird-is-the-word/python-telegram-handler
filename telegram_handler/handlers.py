import logging
from io import BytesIO

import requests
from telethon import TelegramClient
import asyncio

from telegram_handler.formatters import HtmlFormatter

logger = logging.getLogger(__name__)
logger.setLevel(logging.NOTSET)
logger.propagate = False

__all__ = ['TelegramHandler']


MAX_MESSAGE_LEN = 4096


class TelegramHandler(logging.Handler):
    API_ENDPOINT = 'https://api.telegram.org'
    last_response = None

    def __init__(self, token, tg_client, chat_id=None, level=logging.NOTSET, timeout=2, disable_notification=False,
                 disable_web_page_preview=False, proxies=None):
        self.token = token
        self.disable_web_page_preview = disable_web_page_preview
        self.disable_notification = disable_notification
        self.timeout = timeout
        self.proxies = proxies
        self.chat_id = chat_id or self.get_chat_id()
        if not self.chat_id:
            level = logging.NOTSET
            logger.error('Did not get chat id. Setting handler logging level to NOTSET.')
        logger.info('Chat id: %s', self.chat_id)

        self.tg_client = tg_client
        self.msg_queue = asyncio.Queue()
        super(TelegramHandler, self).__init__(level=level)

        self.setFormatter(HtmlFormatter())

    @classmethod
    def format_url(cls, token, method):
        return '%s/bot%s/%s' % (cls.API_ENDPOINT, token, method)

    def get_chat_id(self):
        response = self.request('getUpdates')
        if not response or not response.get('ok', False):
            logger.error('Telegram response is not ok: %s', str(response))
            return
        try:
            return response['result'][-1]['message']['chat']['id']
        except:
            logger.exception('Something went terribly wrong while obtaining chat id')
            logger.debug(response)

    def request(self, method, **kwargs):
        url = self.format_url(self.token, method)

        kwargs.setdefault('timeout', self.timeout)
        kwargs.setdefault('proxies', self.proxies)
        response = None
        try:
            response = requests.post(url, **kwargs)
            self.last_response = response
            response.raise_for_status()
            return response.json()
        except:
            logger.exception('Error while making POST to %s', url)
            logger.debug(str(kwargs))
            if response is not None:
                logger.debug(response.content)

        return response

    def emit(self, record):
        text = self.format(record)
        self.msg_queue.put_nowait(text)

    def check_client_connected(self):
        if not self.tg_client.is_connected():
            raise RuntimeError("Telegram client not connected!")

    async def init(self):
        if not self.tg_client.is_connected():
            await self.tg_client.start(bot_token=self.token)
        asyncio.create_task(self.handle_messages())
        await asyncio.sleep(1)
        
    async def handle_messages(self):
        self.check_client_connected()

        while True:
            msg = await self.msg_queue.get()

            # Send message
            if len(msg) < MAX_MESSAGE_LEN:
                await self.tg_client.send_message(self.chat_id, msg)
            else:
                await self.tg_client.send_file(self.chat_id, BytesIO(msg.encode()), caption=msg[:1000])
