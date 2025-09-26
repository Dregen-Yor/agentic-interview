from langchain_openai import ChatOpenAI
import os
from dotenv import load_dotenv

load_dotenv()


def _env_first(*keys: str) -> str | None:
    """Return the first non-empty env value from given keys."""
    for k in keys:
        v = os.getenv(k)
        if v:
            return v
    return None

chatgpt_model = ChatOpenAI(
    model="gpt-5-mini",
    api_key=os.getenv("GPT_API_KEY"),
    base_url=os.getenv("GPT_BASE_URL"),
    timeout=30,
)


qwen_model = ChatOpenAI(
    model="qwen-plus",
    api_key=os.getenv("ALIYUN_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    timeout=30,
)

gemini_model = ChatOpenAI(
    model="gemini-2.5-flash",
    api_key=os.getenv("GPT_API_KEY"),
    base_url=os.getenv("GPT_BASE_URL"),
    timeout=30,
)
llm_kwargs={
   "extra_body": {
       "thinking": {"type":"disabled"}
   }
}
doubao_model = ChatOpenAI(
    model="doubao-seed-1-6-250615",
    api_key=os.getenv("DOUBAO_API_KEY"),
    base_url=_env_first("DOUBAO_BASE_URL", "DOUBA_BASE_URL"),
    timeout=30,
    **llm_kwargs
)

kimi_model = ChatOpenAI(
    model="kimi-k2-0711-preview",
    api_key=os.getenv("GPT_API_KEY"),
    base_url=os.getenv("GPT_BASE_URL"),
    timeout=30,
)