from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

load_dotenv()

deep_seek_model = ChatOpenAI(
    model="Moonshot-Kimi-K2-Instruct",
    api_key=os.getenv("ALIYUN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

gemini_model = ChatOpenAI(
    model="Moonshot-Kimi-K2-Instruct",
    api_key=os.getenv("ALIYUN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
