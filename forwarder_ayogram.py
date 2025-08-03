import os
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.tl.types import Message, DocumentAttributeFilename
from telethon.errors import FloodWaitError
from config import API_ID, API_HASH, SOURCE_GROUP_ID, TARGET_GROUP_ID

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ThreadCloner:
    def __init__(self, source_topic_id: int, target_topic_id: int, message_map: dict):
        self.source_topic_id = int(source_topic_id)
        self.target_topic_id = int(target_topic_id)
        self.message_map = message_map

    async def handle_message(self, client: TelegramClient, message: Message):
        logger.debug(f"Received message ID {message.id}")

        topic_id = getattr(message.reply_to, 'reply_to_top_id', None) if message.reply_to else None
        if topic_id != self.source_topic_id:
            logger.debug(f"Message {message.id} ignored (not in topic {self.source_topic_id})")
            return

        logger.info(f"Processing message {message.id} from topic {self.source_topic_id}")

        reply_to_msg_id = None
        if message.reply_to and message.reply_to.reply_to_msg_id:
            source_reply_id = message.reply_to.reply_to_msg_id
            reply_to_msg_id = self.message_map.get(source_reply_id)
            logger.debug(f"Reply target for message {message.id}: {reply_to_msg_id}")

        kwargs = {
            'entity': TARGET_GROUP_ID,
            'message': message.message or '',
            'reply_to': reply_to_msg_id,
            'parse_mode': 'html' if message.entities else None,
            'link_preview': False,
            'comment_to': self.target_topic_id
        }

        if message.media:
            logger.info(f"Message {message.id} has media, downloading...")
            try:
                file_name = None
                if message.document:
                    for attr in message.document.attributes:
                        if isinstance(attr, DocumentAttributeFilename):
                            file_name = attr.file_name
                            break

                os.makedirs('temp', exist_ok=True)

                if file_name:
                    path = os.path.join('temp', file_name)
                    downloaded = await message.download_media(path)
                else:
                    downloaded = await message.download_media('temp')

                kwargs['file'] = downloaded
                logger.info(f"Media for message {message.id} downloaded: {downloaded}")

                if message.sticker:
                    kwargs['message'] = ''

            except Exception as e:
                logger.warning(f"Failed to download media for message {message.id}: {e}")
                kwargs['message'] = '(Media unavailable)'

        try:
            sent = await client.send_message(**kwargs)
            self.message_map[message.id] = sent.id
            logger.info(f"Sent cloned message {sent.id} from source {message.id}")

            # Очистка
            if 'downloaded' in locals() and os.path.exists(downloaded):
                os.remove(downloaded)
                logger.debug(f"Deleted temp file: {downloaded}")

        except FloodWaitError as e:
            logger.warning(f"FloodWaitError: sleeping for {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            await self.handle_message(client, message)
        except Exception as e:
            logger.error(f"Failed to send message {message.id}: {e}")


async def main():
    logger.info("Starting client...")
    client = TelegramClient("session", API_ID, API_HASH)
    await client.start()
    logger.info("Client started successfully")

    logger.info(f"Resolving SOURCE_GROUP_ID: {SOURCE_GROUP_ID}")
    try:
        source_entity = await client.get_entity(SOURCE_GROUP_ID)
        logger.info(f"Resolved source entity: {source_entity}")
    except Exception as e:
        logger.critical(f"Failed to resolve SOURCE_GROUP_ID: {e}")
        return

    message_map = {}

    cloners_config = [
        {'source_topic': 126680, 'target_topic': 1},
        {'source_topic': 282788, 'target_topic': 674},
        {'source_topic': 279614, 'target_topic': 675},
        {'source_topic': 279611, 'target_topic': 679},
        {'source_topic': 297728, 'target_topic': 678},
        {'source_topic': 126568, 'target_topic': 676},
    ]

    cloners = []
    for cfg in cloners_config:
        cloner = ThreadCloner(cfg['source_topic'], cfg['target_topic'], message_map)
        logger.info(f"Initialized cloner: {cfg['source_topic']} → {cfg['target_topic']}")
        cloners.append(cloner)

    @client.on(events.NewMessage(chats=source_entity))
    async def handle_new_message(event):
        msg = event.message
        logger.debug(f"New incoming message {msg.id}")
        for cloner in cloners:
            await cloner.handle_message(client, msg)

    logger.info("Message handler registered. Bot is now running.")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())