import json
import asyncio
import httpx
import base64
from channels.generic.websocket import AsyncWebsocketConsumer
from .agents import MultiAgentCoordinator
from .llm import deep_seek_model, gemini_model

class InterviewConsumer(AsyncWebsocketConsumer):
    """
    处理面试 WebSocket 连接的 Consumer。
    使用多智能体系统进行面试管理。
    """
    async def connect(self):
        # 从 URL 中获取 chatId
        self.chat_id = self.scope['url_route']['kwargs']['chat_id']
        self.group_name = f"interview_{self.chat_id}"
        self.interview_started = False
        
        # 初始化多智能体协调器
        models = {
            "question_model": deep_seek_model,
            "scoring_model": deep_seek_model,
            "security_model": gemini_model,  # 使用不同模型进行安全检测
            "summary_model": deep_seek_model
        }
        self.coordinator = MultiAgentCoordinator(models)
        
        # 加入 Channel Layer 组
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        
        print(f"WebSocket连接已建立: {self.chat_id}")

    async def disconnect(self, close_code):
        # 清理面试会话
        if hasattr(self, 'coordinator'):
            self.coordinator.cleanup_session(self.chat_id)
        
        # 离开 Channel Layer 组
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        
        print(f"WebSocket连接已断开: {self.chat_id}")

    async def receive(self, text_data):
        """
        从 WebSocket 接收消息，处理面试流程。
        """
        try:
            data = json.loads(text_data)
            user_input = data.get('message', '')
            username = data.get('username')
            
            # 如果面试还未开始且提供了用户名，启动面试
            if not self.interview_started and username:
                asyncio.create_task(self.start_interview(username))
                self.interview_started = True
            elif user_input and self.interview_started:
                # 处理用户回答
                asyncio.create_task(self.process_user_answer(user_input))
            else:
                await self.send_error("无效的输入格式")
                
        except json.JSONDecodeError:
            await self.send_error("无效的JSON格式")
        except Exception as e:
            print(f"接收消息时发生错误: {e}")
            await self.send_error("处理消息时发生错误")

    async def start_interview(self, candidate_name: str):
        """
        启动面试流程
        """
        try:
            result = self.coordinator.start_interview(self.chat_id, candidate_name)
            
            if result["success"]:
                # 发送首个问题
                message = {
                    'type': 'question',
                    'question': result["first_question"],
                    'question_type': result.get("question_type", "opening"),
                    'message': result["message"]
                }
                
                # 添加TTS音频
                audio_base64 = await self.generate_tts_audio(result["first_question"])
                if audio_base64:
                    message['audio'] = audio_base64
                
                await self.send(text_data=json.dumps(message))
            else:
                await self.send_error(result["message"])
                
        except Exception as e:
            print(f"启动面试时发生错误: {e}")
            await self.send_error("启动面试时发生系统错误")
    
    async def process_user_answer(self, user_answer: str):
        """
        处理用户回答
        """
        try:
            result = self.coordinator.process_answer(self.chat_id, user_answer)
            
            if result["success"]:
                if result.get("interview_complete"):
                    # 面试结束
                    message = {
                        'type': 'interview_complete',
                        'final_decision': result["final_decision"],
                        'overall_score': result["overall_score"],
                        'summary': result["summary"],
                        'total_questions': result["total_questions"],
                        'average_score': result["average_score"],
                        'message': result["message"]
                    }
                    
                    # 添加TTS音频
                    completion_message = f"面试已完成。{result['message']}"
                    audio_base64 = await self.generate_tts_audio(completion_message)
                    if audio_base64:
                        message['audio'] = audio_base64
                    
                    await self.send(text_data=json.dumps(message))
                    
                    # 延迟关闭连接
                    await asyncio.sleep(2)
                    await self.close()
                else:
                    # 继续面试，发送下一个问题
                    message = {
                        'type': 'question',
                        'question': result["next_question"],
                        'question_type': result.get("question_type", "technical"),
                        'score': result["score"],
                        'current_average': result["current_average"],
                        'total_questions': result["total_questions"]
                    }
                    
                    if result.get("security_warning"):
                        message['security_warning'] = "请注意您的回答内容"
                    
                    # 添加TTS音频
                    audio_base64 = await self.generate_tts_audio(result["next_question"])
                    if audio_base64:
                        message['audio'] = audio_base64
                    
                    await self.send(text_data=json.dumps(message))
            else:
                if result.get("security_alert"):
                    # 安全警报
                    await self.send_security_warning(result["message"])
                else:
                    await self.send_error(result["message"])
                    
        except Exception as e:
            print(f"处理用户回答时发生错误: {e}")
            await self.send_error("处理回答时发生系统错误")
    
    async def generate_tts_audio(self, text: str) -> str:
        """
        生成TTS音频并返回base64编码
        """
        try:
            tts_url = "http://101.76.216.150:9880/"
            params = {"text": text, "text_language": "zh"}
            
            async with httpx.AsyncClient() as client:
                tts_response = await client.get(tts_url, params=params, timeout=30.0)
                if tts_response.status_code == 200:
                    audio_content = tts_response.content
                    return base64.b64encode(audio_content).decode('utf-8')
                else:
                    print(f"TTS API错误: Status {tts_response.status_code}")
                    return None
        except Exception as e:
            print(f"TTS生成异常: {e}")
            return None
    
    async def send_error(self, error_message: str):
        """
        发送错误消息
        """
        message = {
            'type': 'error',
            'message': error_message
        }
        await self.send(text_data=json.dumps(message))
    
    async def send_security_warning(self, warning_message: str):
        """
        发送安全警告
        """
        message = {
            'type': 'security_warning',
            'message': warning_message
        }
        await self.send(text_data=json.dumps(message)) 