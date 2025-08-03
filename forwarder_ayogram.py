import json
import logging
from typing import Dict, Optional, Set
from telethon import TelegramClient, events
from telethon.tl.types import ( # type: ignore
    Message, MessageService, MessageActionTopicCreate,
    MessageActionTopicEdit, MessageFwdHeader, InputPeerChannel,
    Channel, User, DocumentAttributeFilename
)
from telethon.tl.functions.channels import GetForumTopicsRequest
from telethon.errors import FloodWaitError, ChatAdminRequiredError
import time
import asyncio
from config import API_ID, API_HASH, SOURCE_GROUP_ID, TARGET_GROUP_ID, SOURCE_TOPIC_ID, TARGET_TOPIC_ID


# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

class ThreadCloner:
    def __init__(self, api_id: int, api_hash: str, source_group_id: int, 
                 target_group_id: int, source_topic_id: int, target_topic_id: int):
        """
        Простой клонер одной ветки в другую.
        
        Args:
            api_id: Telegram API ID
            api_hash: Telegram API Hash
            source_group_id: ID исходной группы
            target_group_id: ID целевой группы
            source_topic_id: ID исходного топика
            target_topic_id: ID целевого топика
        """
        self.client = TelegramClient('session', api_id, api_hash)
        self.source_group_id = source_group_id
        self.target_group_id = target_group_id
        self.source_topic_id = source_topic_id
        self.target_topic_id = target_topic_id
        
        # Маппинг сообщений для корректных ответов
        self.message_map = {}

    async def start(self):
        """Запуск клиента и начало отслеживания"""
        await self.client.start()
        await self.start_monitoring()

    async def stop(self):
        """Остановка клиента"""
        await self.client.disconnect()

    async def get_topic_info(self, group_id: int, message: Message):
        """Получение информации о топике сообщения"""
        if not message.reply_to or not hasattr(message.reply_to, 'reply_to_top_id'):
            return None

        topic_id = message.reply_to.reply_to_top_id
        return topic_id

    async def clone_message_content(self, message: Message, reply_to_msg_id=None):
        """Клонирование содержимого сообщения"""
        try:
            target_entity = await self.client.get_entity(self.target_group_id)
            kwargs = {
                'entity': target_entity,
                'message': message.message or '',
                'reply_to': reply_to_msg_id,
                'parse_mode': 'html' if message.entities else None,
                'link_preview': False,
                'comment_to': self.target_topic_id
            }

            # Обработка медиафайлов
            if message.media:
                try:
                    # Получаем оригинальное имя файла
                    file_name = None
                    if message.document:
                        for attr in message.document.attributes:
                            if isinstance(attr, DocumentAttributeFilename):
                                file_name = attr.file_name
                                break
                    
                    # Скачиваем медиа во временную папку
                    if file_name:
                        temp_path = os.path.join('temp', file_name)
                        os.makedirs('temp', exist_ok=True)
                        downloaded_file = await message.download_media(temp_path)
                        kwargs['file'] = downloaded_file
                    else:
                        # Для медиа без имени файла (фото, стикеры и т.д.)
                        downloaded_file = await message.download_media('temp')
                        kwargs['file'] = downloaded_file

                    # Очищаем текст для стикеров
                    if message.sticker:
                        kwargs['message'] = ''
                        
                except Exception:
                    kwargs['message'] = '(Media unavailable)'

            # Отправляем сообщение
            sent_message = await self.client.send_message(**kwargs)

            # Очищаем временные файлы
            try:
                if 'downloaded_file' in locals() and os.path.exists(downloaded_file):
                    os.remove(downloaded_file)
            except:
                pass

            return sent_message.id

        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
            return await self.clone_message_content(message, reply_to_msg_id)
        except Exception:
            return None

    async def start_monitoring(self):
        """Запуск отслеживания новых сообщений"""
        @self.client.on(events.NewMessage(chats=self.source_group_id))
        async def handler(event):
            message = event.message
            
            # Проверяем, что сообщение из нужного топика
            msg_topic_id = await self.get_topic_info(self.source_group_id, message)
            
            if msg_topic_id != self.source_topic_id:
                return  # Пропускаем сообщения не из нашего топика

            # Определяем ответ на сообщение
            reply_to_msg_id = None
            if message.reply_to and message.reply_to.reply_to_msg_id:
                reply_source_id = message.reply_to.reply_to_msg_id
                if reply_source_id in self.message_map:
                    reply_to_msg_id = self.message_map[reply_source_id]

            # Клонируем сообщение
            cloned_msg_id = await self.clone_message_content(message, reply_to_msg_id)
            
            if cloned_msg_id:
                self.message_map[message.id] = cloned_msg_id

        print(f"Monitoring started: {self.source_group_id}:{self.source_topic_id} -> {self.target_group_id}:{self.target_topic_id}")

    async def run_forever(self):
        """Запуск и поддержание работы клонера"""
        await self.start()
        try:
            await self.client.run_until_disconnected()
        except KeyboardInterrupt:
            print("Stopping...")
        finally:
            await self.stop()


# Пример использования для создания 6 клонеров
async def main():
    
    # Конфигурация для 6 веток
    cloners_config = [
        {
            'source_topic': SOURCE_TOPIC_ID,
            'target_topic': TARGET_TOPIC_ID
        },
        {
            'source_topic': '',
            'target_topic': ''
        },
        {
            'source_topic': '',
            'target_topic': ''
        },
        {
            
        }
    ]
    
    cloners = []
    
    # Создаем клонеры для каждой ветки
    for config in cloners_config:
        cloner = ThreadCloner(
            api_id=API_ID,
            api_hash=API_HASH,
            source_group_id=SOURCE_GROUP_ID,
            target_group_id=TARGET_GROUP_ID,
            source_topic_id=config['source_topic'],
            target_topic_id=config['target_topic']
        )
        cloners.append(cloner)
    
    # Запускаем все клонеры параллельно
    tasks = [cloner.run_forever() for cloner in cloners]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
