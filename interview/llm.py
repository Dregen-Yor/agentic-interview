from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

load_dotenv()

print(os.getenv("DEEPSEEK_API_KEY"))
deep_seek_model = ChatOpenAI(
    model="deepseek-r1-250528",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://ark.cn-beijing.volces.com/api/v3/",
)

gemini_model = ChatOpenAI(
    model="gemini-2.5-flash",
    api_key=os.getenv("GEMINI_API_KEY"),
    base_url="https://0-0.pro/v1",
)
