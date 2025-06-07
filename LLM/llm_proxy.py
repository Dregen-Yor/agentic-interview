from langchain.chatmodels import ChatOpenAI
from langchain_openai import OpenAIEmbeddings
from langchain.document_loaders import TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.vectorstores import MongoDBAtlasVectorSearch
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
import os
from dotenv import load_dotenv

load_dotenv()

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

# --- MongoDB 和嵌入模型设置 ---
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("请设置 'MONGO_URI' 环境变量，值为您的 MongoDB Atlas 连接字符串。")
DB_NAME = "langchain_db"
COLLECTION_NAME = "rag_collection"
INDEX_NAME = "vector_index"

embeddings = OpenAIEmbeddings(
    model="bge-large-zh",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://ark.cn-beijing.volces.com/api/v3/"
)

# --- RAG 流程 ---
loader = TextLoader("knowledge_base.txt", encoding="utf-8")
documents = loader.load()
text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
texts = text_splitter.split_documents(documents)

# 初始化 MongoDB Atlas 向量搜索
vectorstore = MongoDBAtlasVectorSearch.from_documents(
    documents=texts,
    embedding=embeddings,
    collection_name=COLLECTION_NAME,
    db_name=DB_NAME,
    connection_string=MONGO_URI,
    index_name=INDEX_NAME,
)

retriever = vectorstore.as_retriever()


# --- 用于生成问题的自定义提示词和链 ---

# 定义一个提示词模板，指导模型根据上下文生成问题
generation_template = """你是一个善于提问的AI助手。你的任务是根据下面提供的背景材料，生成3个有深度、有启发性的问题。

背景材料:
{context}

请根据以上材料生成3个问题:"""
GENERATION_PROMPT = PromptTemplate(template=generation_template, input_variables=["context"])


# 创建一个 LLMChain
llm_chain = LLMChain(
    llm=deep_seek_model,
    prompt=GENERATION_PROMPT
)

def generate_questions(input_topic):
    """
    根据输入的主题，从向量数据库检索相关文档，并生成问题。
    """
    docs = retriever.get_relevant_documents(input_topic)
    if not docs:
        return "抱歉，根据您输入的主题，我没有在知识库中找到相关信息来生成问题。"
    
    context = "\n\n".join([doc.page_content for doc in docs])
    
    response = llm_chain.predict(context=context)
    return response

if __name__ == '__main__':
    print("您好！我是AI问题生成助手。请输入一个主题，我会根据知识库生成相关问题。输入 '退出' 来结束。")
    while True:
        try:
            user_input = input("请输入主题: ")
            if user_input.lower() in ['退出', 'exit', 'quit']:
                print("AI: 再见！")
                break
            ai_response = generate_questions(user_input)
            print(f"AI生成的问题:\n{ai_response}")
        except KeyboardInterrupt:
            print("\nAI: 程序已中断。再见！")
            break

