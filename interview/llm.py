from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

load_dotenv()

deep_seek_model = ChatOpenAI(
    model="deepseek-v3.1",
    api_key=os.getenv("ALIYUN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

gemini_model = ChatOpenAI(
    model="qwen-plus",
    api_key=os.getenv("ALIYUN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)
