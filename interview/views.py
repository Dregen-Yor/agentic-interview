import json
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv

# 向后兼容：保留旧的导入以防某些地方仍在使用
from langchain_core.messages import AIMessage, HumanMessage
try:
    from .interviewer_agent import create_interviewer_agent
except ImportError:
    create_interviewer_agent = None

# 新的多智能体系统
from .agents import MultiAgentCoordinator
from .llm import deep_seek_model, gemini_model

# 在Django应用启动时加载环境变量
load_dotenv()

# 全局多智能体协调器实例
# 注意：在生产环境中，建议使用更好的实例管理方式
_global_coordinator = None

def get_coordinator():
    """获取全局协调器实例"""
    global _global_coordinator
    if _global_coordinator is None:
        models = {
            "question_model": deep_seek_model,
            "scoring_model": deep_seek_model,
            "security_model": gemini_model,
            "summary_model": deep_seek_model
        }
        _global_coordinator = MultiAgentCoordinator(models)
    return _global_coordinator


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
    POST: 使用新的多智能体系统处理用户消息。
    为了向后兼容，保留了旧的API格式。
    """
    if request.method == 'GET':
        # 如果是GET请求，清空session中的历史记录并渲染页面
        request.session['chat_history'] = []
        request.session['interview_session_id'] = None
        return render(request, 'interview/index.html')

    if request.method == 'POST':
        try:
            # 1. 解析用户输入
            data = json.loads(request.body)
            user_input = data.get('message')
            candidate_name = data.get('candidate_name') or data.get('username')  # 支持两种字段名
            
            if not user_input and not candidate_name:
                return JsonResponse({'error': 'Message or candidate name required'}, status=400)

            # 获取或创建会话ID
            session_id = request.session.get('interview_session_id')
            if not session_id and candidate_name:
                # 创建新会话
                import uuid
                session_id = f"http_session_{uuid.uuid4().hex[:8]}"
                request.session['interview_session_id'] = session_id
                
                # 启动面试
                coordinator = get_coordinator()
                result = coordinator.start_interview(session_id, candidate_name)
                
                if result["success"]:
                    # 返回第一个问题
                    return JsonResponse({
                        'response': result["first_question"],
                        'session_id': session_id,
                        'interview_started': True,
                        'question_type': result.get("question_type", "opening")
                    })
                else:
                    return JsonResponse({
                        'error': result["message"],
                        'details': result.get("error", "")
                    }, status=400)
            
            elif user_input and session_id:
                # 处理用户回答
                coordinator = get_coordinator()
                result = coordinator.process_answer(session_id, user_input)
                
                if result["success"]:
                    if result.get("interview_complete"):
                        # 面试完成
                        request.session['interview_session_id'] = None
                        return JsonResponse({
                            'response': result["message"],
                            'interview_complete': True,
                            'final_decision': result["final_decision"],
                            'overall_score': result["overall_score"],
                            'summary': result["summary"],
                            'total_questions': result["total_questions"]
                        })
                    else:
                        # 继续面试
                        response_data = {
                            'response': result["next_question"],
                            'score': result["score"],
                            'current_average': result["current_average"],
                            'total_questions': result["total_questions"],
                            'question_type': result.get("question_type", "technical")
                        }
                        
                        if result.get("security_warning"):
                            response_data['security_warning'] = "请注意您的回答内容"
                        
                        return JsonResponse(response_data)
                else:
                    if result.get("security_alert"):
                        return JsonResponse({
                            'error': result["message"],
                            'security_alert': True
                        }, status=400)
                    else:
                        return JsonResponse({
                            'error': result["message"]
                        }, status=400)
            else:
                # 如果没有会话ID但有用户输入，或者没有候选人姓名，使用旧系统作为后备
                return _fallback_to_old_system(request, user_input)

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            # 在生产环境中，应该使用更完善的日志记录
            print(f"An error occurred in index view: {e}")
            return JsonResponse({'error': 'Internal server error'}, status=500)

    return JsonResponse({'error': 'Unsupported method'}, status=405)


def _fallback_to_old_system(request, user_input):
    """
    后备方案：使用旧的面试系统
    """
    try:
        if create_interviewer_agent is None:
            return JsonResponse({'error': 'Old system not available'}, status=503)
        
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
        
        return JsonResponse({
            'response': ai_response,
            'legacy_mode': True
        })
        
    except Exception as e:
        print(f"Fallback system error: {e}")
        return JsonResponse({'error': 'Both new and old systems failed'}, status=500)


@csrf_exempt
def get_interview_status(request):
    """
    获取面试状态的API端点
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Only GET method allowed'}, status=405)
    
    session_id = request.session.get('interview_session_id')
    if not session_id:
        return JsonResponse({
            'has_active_session': False,
            'message': 'No active interview session'
        })
    
    try:
        coordinator = get_coordinator()
        status = coordinator.get_session_status(session_id)
        
        return JsonResponse({
            'has_active_session': status['exists'],
            'session_data': status if status['exists'] else None
        })
        
    except Exception as e:
        print(f"Error getting interview status: {e}")
        return JsonResponse({'error': 'Failed to get interview status'}, status=500)


@csrf_exempt
def end_interview(request):
    """
    手动结束面试的API端点
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    session_id = request.session.get('interview_session_id')
    if not session_id:
        return JsonResponse({'error': 'No active interview session'}, status=400)
    
    try:
        coordinator = get_coordinator()
        coordinator.cleanup_session(session_id)
        request.session['interview_session_id'] = None
        
        return JsonResponse({
            'success': True,
            'message': 'Interview session ended successfully'
        })
        
    except Exception as e:
        print(f"Error ending interview: {e}")
        return JsonResponse({'error': 'Failed to end interview'}, status=500)


@csrf_exempt
def face2face_chat(request):
    """
    处理面对面试的视图。
    此功能已由 WebSocket consumer 替代，但保留以确保向后兼容。
    """
    return JsonResponse(
        {
            'error': 'This endpoint is deprecated. Please use WebSocket connection.',
            'websocket_url': '/ws/interview/{chat_id}/',
            'migration_note': 'Face-to-face interviews now use WebSocket for real-time communication'
        }, 
        status=426  # Upgrade Required
    )
