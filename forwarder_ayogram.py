import os
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.tl.types import Message, DocumentAttributeFilename
from telethon.errors import FloodWaitError

from config import API_ID, API_HASH, SOURCE_GROUP_ID, TARGET_GROUP_ID

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ThreadCloner:
    def __init__(self, source_topic_id: int, target_topic_id: int, message_map: dict):
        self.source_topic_id = int(source_topic_id)
        self.target_topic_id = int(target_topic_id)
        self.message_map = message_map

    async def handle_message(self, client: TelegramClient, message: Message):
        topic_id = getattr(message.reply_to, 'reply_to_top_id', None) if message.reply_to else None
        if topic_id != self.source_topic_id:
            return

        reply_to_msg_id = None
        if message.reply_to and message.reply_to.reply_to_msg_id:
            source_reply_id = message.reply_to.reply_to_msg_id
            reply_to_msg_id = self.message_map.get(source_reply_id)

        kwargs = {
            'entity': TARGET_GROUP_ID,
            'message': message.message or '',
            'reply_to': reply_to_msg_id,
            'parse_mode': 'html' if message.entities else None,
            'link_preview': False,
            'comment_to': self.target_topic_id
        }

        # Медиа
        if message.media:
            try:
                file_name = None
                if message.document:
                    for attr in message.document.attributes:
                        if isinstance(attr, DocumentAttributeFilename):
                            file_name = attr.file_name
                            break

                os.makedirs('temp', exist_ok=True)
                if file_name:
                    downloaded = await message.download_media(os.path.join('temp', file_name))
                else:
                    downloaded = await message.download_media('temp')

                kwargs['file'] = downloaded
                if message.sticker:
                    kwargs['message'] = ''

            except Exception:
                kwargs['message'] = '(Media unavailable)'

        try:
            sent = await client.send_message(**kwargs)
            self.message_map[message.id] = sent.id
            logger.info(f"Cloned msg {message.id} -> {sent.id}")
        except FloodWaitError as e:
            logger.warning(f"Flood wait: sleeping {e.seconds}s")
            await asyncio.sleep(e.seconds)
            await self.handle_message(client, message)
        except Exception as e:
            logger.error(f"Error sending: {e}")


async def main():
    # ОДИН ЕДИНСТВЕННЫЙ клиент
    client = TelegramClient("session", API_ID, API_HASH)
    await client.start()

    # Одна общая карта соответствий
    message_map = {}

    # Настройка всех клонеров
    cloners_config = [
        {'source_topic': 126680, 'target_topic': 1},
        {'source_topic': 282788, 'target_topic': 674},
        {'source_topic': 279614, 'target_topic': 675},
        {'source_topic': 279611, 'target_topic': 679},
        {'source_topic': 297728, 'target_topic': 678},
        {'source_topic': 126568, 'target_topic': 676},
    ]

    cloners = [
        ThreadCloner(cfg['source_topic'], cfg['target_topic'], message_map)
        for cfg in cloners_config
    ]

    @client.on(events.NewMessage(chats=SOURCE_GROUP_ID))
    async def handle_new_message(event):
        msg = event.message
        for cloner in cloners:
            await cloner.handle_message(client, msg)

    logger.info("Bot started. Monitoring messages...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())