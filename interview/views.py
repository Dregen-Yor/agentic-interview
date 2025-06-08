import json
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from langchain_core.messages import AIMessage, HumanMessage
from dotenv import load_dotenv

from .interviewer_agent import create_interviewer_agent

# 在Django应用启动时加载环境变量
load_dotenv()


def deserialize_history(history_json):
    """从JSON反序列化聊天记录"""
    history = []
    if not history_json:
        return history
    for msg in history_json:
        if msg.get('type') == 'human':
            history.append(HumanMessage(content=msg.get('content')))
        elif msg.get('type') == 'ai':
            history.append(AIMessage(content=msg.get('content')))
    return history

def serialize_history(history):
    """将聊天记录序列化为JSON"""
    serializable_history = []
    for msg in history:
        if isinstance(msg, HumanMessage):
            serializable_history.append({'type': 'human', 'content': msg.content})
        elif isinstance(msg, AIMessage):
            serializable_history.append({'type': 'ai', 'content': msg.content})
    return serializable_history


@csrf_exempt
def index(request):
    """
    处理面试聊天的主视图。
    GET: 呈现聊天界面。
    POST: 处理用户消息，与Agent交互，并返回AI响应。
    """
    if request.method == 'GET':
        # 如果是GET请求，清空session中的历史记录并渲染页面
        request.session['chat_history'] = []
        return render(request, 'interview/index.html')

    if request.method == 'POST':
        try:
            # 1. 解析用户输入
            data = json.loads(request.body)
            user_input = data.get('message')
            if not user_input:
                return JsonResponse({'error': 'Message not provided'}, status=400)

            # 2. 从session恢复聊天记录
            history_json = request.session.get('chat_history', [])
            chat_history = deserialize_history(history_json)

            # 3. 创建并调用Agent
            agent_executor = create_interviewer_agent()
            response = agent_executor.invoke({
                "input": user_input,
                "chat_history": chat_history
            })
            ai_response = response.get("output", "Sorry, I had an issue processing that.")
            
            # 4. 将更新后的历史记录存回session
            chat_history.append(HumanMessage(content=user_input))
            chat_history.append(AIMessage(content=ai_response))
            request.session['chat_history'] = serialize_history(chat_history)

            if "再见" in ai_response:
                request.session['chat_history'] = []
            return JsonResponse({'response': ai_response})

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            # 在生产环境中，应该使用更完善的日志记录
            print(f"An error occurred: {e}")
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': 'Unsupported method'}, status=405)


@csrf_exempt
def face2face_chat(request):
    """
    处理面对面试的视图。
    POST: 处理用户语音输入，与Agent交互，并返回AI响应文本。
    """
    # 此视图的功能已由 WebSocket consumer `interview.consumers.InterviewConsumer` 替代。
    # 保留此端点以避免客户端出现404错误，但返回一个明确的提示。
    return JsonResponse(
        {'error': 'This endpoint is deprecated. Please use WebSocket connection.'}, 
        status=426 # Upgrade Required
    )
