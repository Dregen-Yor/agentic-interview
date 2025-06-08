import json
import asyncio
from channels.generic.websocket import AsyncWebsocketConsumer
from langchain_core.messages import HumanMessage, AIMessage
from langchain.memory import ConversationBufferMemory
from .interviewer_agent import create_interviewer_agent

class InterviewConsumer(AsyncWebsocketConsumer):
    """
    处理面试 WebSocket 连接的 Consumer。
    为每个连接创建一个独立的 Agent 实例和聊天记录。
    """
    async def connect(self):
        # 从 URL 中获取 chatId
        self.chat_id = self.scope['url_route']['kwargs']['chat_id']
        self.group_name = f"interview_{self.chat_id}"
        self.count=0
        # 为每个连接创建独立的 Memory
        # `return_messages=True` 确保 memory 返回的是消息对象列表，而不是单个字符串
        self.memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
        
        # 创建 Agent，并传入 memory
        self.agent_executor = create_interviewer_agent(memory=self.memory)

        # 加入 Channel Layer 组
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # 离开 Channel Layer 组
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        """
        从 WebSocket 接收消息，调用 Agent，并返回结果。
        """
        data = json.loads(text_data)
        user_input = data.get('message')
        username = data.get('username')

        # 仅在对话刚开始（memory为空）且提供了用户名时，构造特殊输入以触发简历获取
        if self.count==0 and username:
            final_input = f"你好，我是候选人 {username}，请获取我的简历并开始面试。"
        elif user_input:
            final_input = user_input + f" 这是第{self.count}次回答"
        else:
            return
        self.count+=1
        print(self.count)
        print(self.memory.chat_memory.messages)
        # 在后台任务中运行 Agent 调用，以避免阻塞 WebSocket 连接
        asyncio.create_task(self.run_agent(final_input))

    async def run_agent(self, user_input):
        """
        运行 agent 并将结果发送回客户端。
        如果检测到面试结束，则发送消息后关闭连接。
        """
        # 调用 Agent。由于使用了 Memory，不再需要手动传递 chat_history
        response = self.agent_executor.invoke({"input": user_input})
        ai_response = response.get("output", "抱歉，处理时遇到问题，请重试。")

        # 构造要发送的数据
        message_to_send = {
            'response': ai_response,
            'type': 'message'
        }

        # 检测面试是否结束
        is_completed = "[再见]" in ai_response or "再见" in ai_response
        if is_completed:
            message_to_send['status'] = 'completed'

        # 发送响应回 WebSocket
        await self.send(text_data=json.dumps(message_to_send))

        # 如果面试结束，则在发送完消息后关闭连接
        if is_completed:
            await self.close() 