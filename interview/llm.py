from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

load_dotenv()

chatgpt_model = ChatOpenAI(
    model="gpt-5-mini",
    api_key=os.getenv("GPT_API_KEY"),
    base_url=os.getenv("GPT_BASE_URL"),
)


qwen_model = ChatOpenAI(
    model="qwen-plus",
    api_key=os.getenv("ALIYUN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

gemini_model = ChatOpenAI(
    model="gemini-2.5-flash",
    api_key=os.getenv("GPT_API_KEY"),
    base_url=os.getenv("GPT_BASE_URL"),
)
