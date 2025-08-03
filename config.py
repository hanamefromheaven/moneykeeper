from dotenv import load_dotenv
import os

load_dotenv()

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

SOURCE_GROUP_ID = os.getenv("SOURCE_GROUP_ID")
TARGET_GROUP_ID = os.getenv("TARGET_GROUP_ID")

SOURCE_TOPIC_ID = os.getenv("SOURCE_TOPIC_ID")
TARGET_TOPIC_ID = os.getenv("TARGET_TOPIC_ID")


print(API_ID)