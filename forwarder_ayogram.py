import os
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.tl.types import Message, DocumentAttributeFilename
from telethon.errors import FloodWaitError
from config import API_ID, API_HASH, SOURCE_GROUP_ID, TARGET_GROUP_ID

# Максимальный уровень логирования
logging.basicConfig(
    level=logging.INFO,  # Уменьшил для читаемости
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ThreadCloner:
    def __init__(self, source_topic_id: int, target_topic_id: int, message_map: dict):
        self.source_topic_id = int(source_topic_id) if source_topic_id else None
        self.target_topic_id = int(target_topic_id)
        self.message_map = message_map
        logger.info(f"🔧 ThreadCloner created: {source_topic_id} → {target_topic_id}")

    def get_message_topic_id(self, message: Message):
        """Определяет ID топика для сообщения"""
        if not message.reply_to:
            # Сообщение не является ответом - это может быть:
            # 1. Обычное сообщение в общем чате (topic_id = None)
            # 2. Первое сообщение в топике (topic_id = message.id)
            return None
        
        # Если есть reply_to_top_id - это сообщение в топике
        if hasattr(message.reply_to, 'reply_to_top_id') and message.reply_to.reply_to_top_id:
            return message.reply_to.reply_to_top_id
        
        # Если есть forum_topic - это тоже сообщение в топике
        if hasattr(message.reply_to, 'forum_topic') and message.reply_to.forum_topic:
            return message.reply_to.reply_to_msg_id
            
        return None

    async def handle_message(self, client: TelegramClient, message: Message):
        logger.info(f"🔍 ANALYZING MESSAGE {message.id}")
        
        # Определяем топик сообщения
        message_topic_id = self.get_message_topic_id(message)
        logger.info(f"📌 Message topic: {message_topic_id}, looking for: {self.source_topic_id}")

        # Проверяем соответствие топику
        if self.source_topic_id is None:
            # Клонер для общих сообщений (не из топиков)
            if message_topic_id is not None:
                logger.info(f"❌ Message {message.id} is from topic {message_topic_id}, but we want general messages")
                return
        else:
            # Клонер для конкретного топика
            if message_topic_id != self.source_topic_id:
                logger.info(f"❌ Message {message.id} ignored (topic {message_topic_id} != {self.source_topic_id})")
                return

        logger.info(f"✅ PROCESSING message {message.id}")
        print(f"📨 Cloning message: {message.message[:50] if message.message else '[Media]'}")

        # Определяем reply_to для клонированного сообщения
        reply_to_msg_id = None
        if message.reply_to and message.reply_to.reply_to_msg_id:
            source_reply_id = message.reply_to.reply_to_msg_id
            reply_to_msg_id = self.message_map.get(source_reply_id)
            logger.info(f"🔗 Reply mapping: {source_reply_id} → {reply_to_msg_id}")

        # Подготовка параметров отправки
        kwargs = {
            'entity': TARGET_GROUP_ID,
            'message': message.message or '',
            'parse_mode': 'html' if message.entities else None,
            'link_preview': False,
        }

        # Настройка отправки в топик или общий чат
        if reply_to_msg_id:
            # Если это ответ на другое сообщение
            kwargs['reply_to'] = reply_to_msg_id
            logger.info(f"📤 Will reply to message: {reply_to_msg_id}")
        elif self.target_topic_id:
            # Отправляем в конкретный топик
            kwargs['reply_to'] = self.target_topic_id
            logger.info(f"📤 Will send to topic: {self.target_topic_id}")
        else:
            # Отправляем в общий чат (без reply_to)
            logger.info(f"📤 Will send to general chat")

        logger.info(f"📦 Send kwargs: {kwargs}")

        # Обработка медиа
        downloaded = None
        if message.media:
            logger.info(f"🖼️ Processing media for message {message.id}")
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
                logger.info(f"📁 Media downloaded: {downloaded}")

                if message.sticker:
                    kwargs['message'] = ''

            except Exception as e:
                logger.error(f"❌ Media download failed for message {message.id}: {e}")
                kwargs['message'] = '(Media unavailable)'

        # Отправка сообщения
        try:
            logger.info(f"🚀 SENDING MESSAGE...")
            sent = await client.send_message(**kwargs)
            self.message_map[message.id] = sent.id
            logger.info(f"✅ SUCCESS! Sent cloned message {sent.id} from source {message.id}")
            print(f"✅ Message cloned: {message.id} → {sent.id}")

        except FloodWaitError as e:
            logger.warning(f"⏳ FloodWaitError: sleeping for {e.seconds} seconds")
            await asyncio.sleep(e.seconds)
            await self.handle_message(client, message)
        except Exception as e:
            logger.error(f"❌ FAILED to send message {message.id}: {e}")
            logger.error(f"❌ Error type: {type(e)}")
            print(f"❌ Error sending message: {e}")
        finally:
            # Очистка файлов
            if downloaded and os.path.exists(downloaded):
                try:
                    os.remove(downloaded)
                    logger.debug(f"🗑️ Deleted temp file: {downloaded}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to delete temp file {downloaded}: {e}")


async def main():
    print("🚀 Starting Telegram cloner...")
    logger.info("Starting client...")
    
    client = TelegramClient("session", API_ID, API_HASH)
    await client.start()
    logger.info("✅ Client started successfully")

    # Получаем информацию о себе
    me = await client.get_me()
    logger.info(f"👤 Logged in as: {me.first_name} (@{me.username})")
    print(f"👤 Logged in as: {me.first_name} (@{me.username})")

    # Проверяем исходную группу
    logger.info(f"🔍 Resolving SOURCE_GROUP_ID: {SOURCE_GROUP_ID}")
    try:
        source_entity = await client.get_entity(SOURCE_GROUP_ID)
        logger.info(f"✅ Source entity: {source_entity.title} (ID: {source_entity.id})")
        print(f"📥 Source: {source_entity.title}")
        
        if hasattr(source_entity, 'forum') and source_entity.forum:
            logger.info("🏛️ Source is a forum group")
            print("🏛️ Source is a forum group")
        else:
            logger.warning("⚠️ Source might not be a forum group")
            print("⚠️ Source might not be a forum group")
            
    except Exception as e:
        logger.critical(f"❌ Failed to resolve SOURCE_GROUP_ID: {e}")
        print(f"❌ Cannot access source group: {e}")
        return

    # Проверяем целевую группу
    logger.info(f"🔍 Resolving TARGET_GROUP_ID: {TARGET_GROUP_ID}")
    try:
        target_entity = await client.get_entity(TARGET_GROUP_ID)
        logger.info(f"✅ Target entity: {target_entity.title} (ID: {target_entity.id})")
        print(f"📤 Target: {target_entity.title}")
        
        if hasattr(target_entity, 'forum') and target_entity.forum:
            logger.info("🏛️ Target is a forum group")
            print("🏛️ Target is a forum group")
        else:
            logger.warning("⚠️ Target might not be a forum group")
            print("⚠️ Target might not be a forum group")
            
    except Exception as e:
        logger.critical(f"❌ Failed to resolve TARGET_GROUP_ID: {e}")
        print(f"❌ Cannot access target group: {e}")
        return

    message_map = {}

    # ОБНОВЛЕННАЯ КОНФИГУРАЦИЯ
    cloners_config = [
        {'source_topic': 674, 'target_topic': 12},
        {'source_topic': 675, 'target_topic': 10},
        {'source_topic': 679, 'target_topic': 8},
        {'source_topic': 678, 'target_topic': 6},
        {'source_topic': 676, 'target_topic': 4},
        {'source_topic': 753, 'target_topic': 2}
     ]

    cloners = []
    for cfg in cloners_config:
        cloner = ThreadCloner(cfg['source_topic'], cfg['target_topic'], message_map)
        cloners.append(cloner)
        
        source_desc = f"Topic {cfg['source_topic']}" if cfg['source_topic'] else "General chat"
        target_desc = f"Topic {cfg['target_topic']}" if cfg['target_topic'] else "General chat"
        print(f"🔧 Cloner: {source_desc} → {target_desc}")

    @client.on(events.NewMessage(chats=source_entity))
    async def handle_new_message(event):
        print(f"⚡ NEW MESSAGE: {event.message.id}")
        msg = event.message
        
        print(f"📝 Text: {msg.message[:100] if msg.message else '[No text]'}")
        
        for i, cloner in enumerate(cloners):
            try:
                logger.info(f"🔄 Running cloner {i+1}")
                await cloner.handle_message(client, msg)
            except Exception as e:
                logger.error(f"❌ Error in cloner {i+1}: {e}")
                print(f"❌ Cloner {i+1} error: {e}")
    @client.on(events.MessageEdited(chats=source_entity))
    async def handle_edited_message(event):
        msg = event.message
        target_msg_id = message_map.get(msg.id)
        print(f"✏️ EDITED MESSAGE: {msg.id}")

        if not target_msg_id:
            logger.info(f"⚠️ Edited message {msg.id} не имеет копии, пропускаем")
            return

        try:
            await client.edit_message(TARGET_GROUP_ID, target_msg_id, msg.message or "")        
                # Редактируем уже пересланное сообщение                await client.edit_message(TARGET_GROUP_ID, target_msg_id, msg.message or "")
            logger.info(f"✅ Обновил сообщение {msg.id} → {target_msg_id}")
        except Exception as e:
                logger.error(f"❌ Ошибка при обновлении {msg.id}: {e}")

    logger.info("✅ Message handler registered")
    print("🎯 Bot is ready!")
    print("💡 Now send messages:")
    print("   - General messages (will be cloned by cloner 3)")
    print("   - Messages in Topic 1 (will be cloned by cloner 2)")  
    print("   - Messages in Topic 2 (will be cloned by cloner 1)")
    print("🔍 Waiting for messages...")
    
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())