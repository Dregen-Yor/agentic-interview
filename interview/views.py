import json
import logging
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from dotenv import load_dotenv

# 多智能体系统
from .agents import MultiAgentCoordinator
from .llm import gemini_model, chatgpt_model, kimi_model, qwen_model

# 在Django应用启动时加载环境变量
load_dotenv()

# 初始化logger
logger = logging.getLogger("interview.views")

# 全局多智能体协调器实例
# 注意：在生产环境中，建议使用更好的实例管理方式
_global_coordinator = None

def get_coordinator():
    """获取全局协调器实例"""
    global _global_coordinator
    if _global_coordinator is None:
        models = {
            "question_model": kimi_model,
            "scoring_model": kimi_model,
            "security_model": gemini_model,  # 使用不同模型进行安全检测
            "summary_model": gemini_model
        }
        _global_coordinator = MultiAgentCoordinator(models)
    return _global_coordinator


@csrf_exempt
def index(request):
    """
    处理面试聊天的主视图。
    GET: 呈现聊天界面。
    POST: 使用新的多智能体系统处理用户消息。
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
            candidate_name = data.get('candidate_name')
            
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
                return JsonResponse({'error': 'Invalid request: missing session or candidate name'}, status=400)

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            # 在生产环境中，应该使用更完善的日志记录
            logger.error(f"An error occurred in index view: {e}")
            return JsonResponse({'error': 'Internal server error'}, status=500)

    return JsonResponse({'error': 'Unsupported method'}, status=405)


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
        logger.error(f"Error getting interview status: {e}")
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
        logger.error(f"Error ending interview: {e}")
        return JsonResponse({'error': 'Failed to end interview'}, status=500)


