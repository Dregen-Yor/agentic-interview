from agents import Agent, Tool,OpenAIChatCompletionsModel,AsyncOpenAI

gemini_model = AsyncOpenAI(
    api_key="sk-KwHkDHu1SaRuEs09LAtiZXzXfVNXThe1N4iQBYVKOcuUIDjv",
    base_url="https://0-0.pro/v1",
)

deepseek_client = AsyncOpenAI(
    api_key="dc5a9745-ece2-4975-bb49-af91025f66eb",
    base_url="https://ark.cn-beijing.volces.com/api/v3",
)

deepseek_model = OpenAIChatCompletionsModel(
    model="deepseek-r1-250120",
    openai_client=deepseek_client,
)

inter_view_agent = Agent(
    name="inter_view_agent",
    instructions="A agent that can help with the interview process,answer all my questions in Chinese",
    tools=[],
    model = OpenAIChatCompletionsModel(
        model="gemini-2.5-flash",
        openai_client=gemini_model,
    )
)








