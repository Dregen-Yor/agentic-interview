import os
import sys
from typing import List, Optional
import datetime
import json
import requests

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
import pymongo
from bson import json_util, ObjectId

# --- 加载环境变量 ---
# 将父目录添加到 sys.path 以便导入 llm_proxy 中的模型
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")
load_dotenv()

# 从 llm.py 导入已经配置好的模型
# 注意: 为了让这个导入生效，请确保您是从项目的根目录以模块方式运行此脚本
# 例如: python -m interview.interviewer_agent
try:
    from .llm import deep_seek_model
except (ImportError, ModuleNotFoundError):
    print("无法从 interview.llm 导入模型，将使用默认配置重新创建。")
    print("请确保您在正确的目录下并以正确的方式运行此脚本 (例如: python -m interview.interviewer_agent)。")
    deep_seek_model = ChatOpenAI(
        model="deepseek-r1-250528",
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://ark.cn-beijing.volces.com/api/v3/",
    )


# --- MongoDB 设置 ---
client = pymongo.MongoClient(os.getenv("MONGODB_URI"))
db = client[os.getenv("MONGODB_DB")]
resumes_collection = db["resumes"]
users_collection = db["users"]
result_collection = db["result"]
problem_collection = db["problem"]

# --- Embedding model settings ---
# Note: Make sure you are running ollama and have the model: ollama run Q78KG/gte-Qwen2-7B-instruct:latest
EMBEDDING_API_URL = "http://localhost:11434/api/embeddings"
EMBEDDING_MODEL = "Q78KG/gte-Qwen2-7B-instruct:latest"


def get_embedding(text: str) -> Optional[List[float]]:
    """
    Generates an embedding for the given text using a local model API.
    """
    try:
        payload = {"model": EMBEDDING_MODEL, "prompt": text}
        response = requests.post(EMBEDDING_API_URL, json=payload)
        response.raise_for_status()
        return response.json().get("embedding")
    except requests.exceptions.RequestException as e:
        print(f"Error generating embedding: {e}")
        return None


@tool
def getResumeByName(name: str) -> dict:
    """
    根据姓名查询候选人的简历。
    """
    print(f"--- TOOL CALLED: getResumeByName with name={name} ---")
    user = users_collection.find_one({"name": name})
    if user and "_id" in user:
        resume_id = str(user["_id"])
        resume = resumes_collection.find_one({"_id": ObjectId(resume_id)})
        if resume:
            return json.loads(json_util.dumps(resume))
        else:
            return {"error": f"找不到姓名为'{name}'的简历。"}
    return {"error": f"找不到姓名为'{name}'的用户。"}


@tool
def changeInterView(name: str, comment: str, result: bool) -> str:
    """
    结束面试并记录面试结果到数据库。
    
    Args:
        name (str): 候选人姓名。
        comment (str): 面试评语，需要总结候选人的表现，并给出是否录用的建议。
        result (bool): 面试结果，True为通过，False为不通过。
    """
    print(f"--- TOOL CALLED: changeInterView for {name} ---")
    interview_record = {
        "name": name,
        "comment": comment,
        "result": "通过" if result else "不通过",
        "timestamp": datetime.datetime.now(),
    }
    result_collection.insert_one(interview_record)
    print(f"面试结果: {'通过' if result else '不通过'}")
    print(f"评语: {comment}")
    return "面试结果已成功记录到数据库。"


@tool
def rag_search(query: str) -> str:
    """
    使用向量搜索在知识库中查找与查询相关的信息。
    知识库中包含编程问题、概念和最佳实践。
    当你需要回答技术问题、评估候选人的技术知识或提供编程示例时，请使用此工具。
    """
    print(f"--- TOOL CALLED: rag_search with query='{query}' ---")

    query_embedding = get_embedding(query)
    if not query_embedding:
        return "抱歉，无法为您的查询生成向量，无法进行搜索。"

    pipeline = [
        {
            "$vectorSearch": {
                "index": "vector_index",
                "path": "content_vector",
                "queryVector": query_embedding,
                "numCandidates": 100,
                "limit": 3,
            }
        },
        {
            "$project": {
                "_id": 0,
                "content": 1,
                "score": {"$meta": "vectorSearchScore"},
            }
        },
    ]

    try:
        results = list(problem_collection.aggregate(pipeline))
        if not results:
            return "在知识库中没有找到相关信息。"

        # Format the results
        formatted_results = "从知识库中找到以下相关信息：\n\n"
        for i, doc in enumerate(results):
            formatted_results += f"--- 相关文档 {i+1} (相似度: {doc['score']:.4f}) ---\n"
            formatted_results += doc.get("content", "没有内容。") + "\n\n"

        return formatted_results.strip()

    except Exception as e:
        return f"执行 RAG 搜索时出错: {e}"


def create_interviewer_agent(memory=None):
    """
    创建并返回一个面试官 Agent。
    
    Args:
        memory (Optional): 用于存储对话历史的 LangChain Memory 对象。
    """
    # 1. 加载系统提示
    try:
        with open("interview/prompt/Interview-face2face-System-Prompt.st", "r", encoding="utf-8") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        print("错误：找不到提示词文件 'interview/prompt/Interview-face2face-System-Prompt.st'。")
        print("请确保您在正确的目录下运行此脚本。")
        sys.exit(1)

    # 2. 定义 Agent 的输入 Prompt 结构
    # 这个结构告诉 Agent 它需要处理系统消息、用户历史消息，以及一个名为 "agent_scratchpad" 的临时空间用于思考
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    # 3. 定义工具列表
    tools = [getResumeByName, changeInterView, rag_search]

    # 4. 创建 Agent
    # 将模型、工具和 Prompt 结合在一起，创建一个能够调用工具的 Agent
    agent = create_tool_calling_agent(deep_seek_model, tools, prompt)

    # 5. 创建 Agent 执行器
    # AgentExecutor 负责实际运行 Agent、调用工具并返回结果
    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, memory=memory)

    return agent_executor


def run_interview():
    """
    运行面试交互流程。
    """
    print("你好，我是你的AI技术面试官。")
    print("请输入候选人的姓名开始面试，或者输入 'exit' 退出。")
    
    agent_executor = create_interviewer_agent()
    chat_history = []

    while True:
        try:
            user_input = input("你: ")
            if user_input.lower() in ['exit', 'quit']:
                print("面试官: 好的，本次面试结束。")
                break

            # 调用 agent
            response = agent_executor.invoke({
                "input": user_input,
                "chat_history": chat_history
            })
            
            # 打印并记录历史
            ai_message = response["output"]
            print(f"面试官: {ai_message}")
            
            chat_history.append(HumanMessage(content=user_input))
            chat_history.append(AIMessage(content=ai_message))

            if "[再见]" in ai_message:
                print("面试官: 面试已结束。")
                break

        except KeyboardInterrupt:
            print("\n面试官: 面试被中断。")
            break
        except Exception as e:
            print(f"发生错误: {e}")
            break


if __name__ == "__main__":
    run_interview()

# client.close() 