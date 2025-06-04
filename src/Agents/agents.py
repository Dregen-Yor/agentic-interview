from agents import Agent, Tool, OpenAIChatCompletionsModel, AsyncOpenAI
from .tools.mongo_tool import tool_get_random_problems as find_problems # Import the correct async tool function

# Instantiate the tool.
# The function itself is decorated with @function_tool, so it can be directly used.
mongo_find_problems_tool = Tool(
    name="find_problems_from_db", # Giving a descriptive name for the tool instance
    description="从MongoDB题库中检索面试题目。可以根据难度、类别进行筛选，并指定每个类别/难度的题目数量。例如：find_problems_from_db(difficulties=['easy', 'medium'], num_per_difficulty=2, categories=['Python'])",
    fn=find_problems
)

gemini_model_client = AsyncOpenAI( # Renamed from gemini_model to avoid conflict if we name an agent gemini_model
    api_key="sk-KwHkDHu1SaRuEs09LAtiZXzXfVNXThe1N4iQBYVKOcuUIDjv", # Placeholder, should use env vars
    base_url="https://0-0.pro/v1",
)

# Using a consistent model for all agents for now, can be changed later.
default_model_config = OpenAIChatCompletionsModel(
    model="gemini-2.5-flash", # Consider using a more capable model for complex reasoning if needed
    openai_client=gemini_model_client,
)

# Agent 1: Problem Selector Agent (RAG based)
problem_selector_agent = Agent(
    name="problem_selector_agent",
    instructions="你是一个面试题目选择助手。"
                 "你的任务是根据要求从题库中选择合适的面试题目组合。"
                 "请明确说明选择的题目数量和难度分布（例如：2道简单，3道中等，1道困难）。"
                 "使用 'find_problems_from_db' 工具来检索题目。"
                 "将选择的题目列表以JSON字符串格式返回，例如：\'[{\"id\": \"P001\", \"content\": \"...\", \"difficulty\": \"easy\", \"category\": \"Python\"}, ...]\' 。确保只返回JSON字符串，不包含其他任何解释性文本。"
                 "所有输出请使用中文。",
    tools=[mongo_find_problems_tool],
    model=default_model_config
)

# Agent 2: Grading Agent (updated problem_rating)
grading_agent = Agent(
    name="grading_agent",
    instructions="你是一个面试评分助手。"
                 "给定一个面试问题和候选人的回答，请对回答的质量、准确性、逻辑性和清晰度进行评分。"
                 "评分范围为1-10分（10分为最高）。"
                 "除了分数，还需要提供简短的文字评语，解释打分依据，并指出候选人回答中的亮点和不足之处。"
                 "所有输出请使用中文。",
    tools=[], # Typically, grading might not need external tools unless consulting specific rubrics
    model=default_model_config
)

# Agent 3: Skill Assessor Agent
skill_assessor_agent = Agent(
    name="skill_assessor_agent",
    instructions="你是一个候选人技能评估助手。"
                 "基于候选人在多道面试题目上的得分和评语，你需要综合评估其在以下几个核心维度的能力： "
                 "1. 数理基础 (Mathematical Foundations) "
                 "2. 逻辑思维 (Logical Thinking) "
                 "3. 问题解决能力 (Problem-Solving Skills) "
                 "4. 技术深度与广度 (Technical Depth and Breadth) "
                 "5. 沟通表达能力 (Communication Skills)。"
                 "请为每个维度给出1-10分的评分，并附上简要的评估说明。"
                 "所有输出请使用中文。",
    tools=[],
    model=default_model_config
)

# Agent 4: Comprehensive Evaluator Agent
comprehensive_evaluator_agent = Agent(
    name="comprehensive_evaluator_agent",
    instructions="你是一个面试综合评价助手。"
                 "你的任务是根据候选人的全部面试表现（包括所有题目、回答、评分、以及各单项技能评估结果），给出一个全面的面试评价报告。"
                 "报告应包括： "
                 "1. 整体表现总结。 "
                 "2. 主要优点和技术亮点。 "
                 "3. 存在的不足或潜在风险点。 "
                 "4. 综合评价等级 (例如：强烈推荐, 推荐, 一般, 不推荐)。"
                 "5. （可选）针对候选人的发展建议。"
                 "所有输出请使用中文。",
    tools=[],
    model=default_model_config
)


# Removed original problem_random_generator and problem_rating as they are superseded or updated.
# The deepseek_client and deepseek_model are kept if needed for other purposes or future use.
deepseek_client = AsyncOpenAI(
    api_key="YOUR_DEEPSEEK_API_KEY", # Placeholder, should use env vars
    base_url="https://ark.cn-beijing.volces.com/api/v3",
)

deepseek_model = OpenAIChatCompletionsModel(
    model="deepseek-r1-250528",
    openai_client=deepseek_client,
)

# Example of how one might use the problem selector:
# async def main():
#     response = await problem_selector_agent.arun("请帮我选择3道Python相关的面试题，要求1道简单，1道中等，1道困难。")
#     print(response)
#
# if __name__ == "__main__":
#    import asyncio
#    asyncio.run(main())










