from django.shortcuts import render
import json
import asyncio
from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from src.Agents.agents import problem_selector_agent # 确保此导入路径在settings.py中配置的sys.path下是正确的

# Create your views here.

@csrf_exempt # 仅用于测试目的。生产环境请正确配置CSRF。
async def select_problems_api(request: HttpRequest):
    if request.method == 'POST':
        try:
            # 解码请求体（假设为UTF-8编码）
            body_unicode = request.body.decode('utf-8')
            data = json.loads(body_unicode)
            
            num_easy = int(data.get('easy', 0))
            num_medium = int(data.get('medium', 0))
            num_hard = int(data.get('hard', 0))
            categories = data.get('categories', [])

            if not isinstance(categories, list):
                return JsonResponse({"error": "'categories' 应该是一个列表."}, status=400)

            total_questions = num_easy + num_medium + num_hard
            # 允许仅按类别选择，即使各类难度题目数量为0
            if total_questions == 0 and not categories:
                return JsonResponse({"error": "请为至少一个难度级别指定题目数量，或提供题目类别。"}, status=400)
            
            if total_questions > 10: # 设置一个请求题目总数的上限
                return JsonResponse({"error": "一次请求的总题目数量不能超过10个。"}, status=400)

            # 为 problem_selector_agent 构建自然语言提示
            prompt_parts = ["请帮我选择面试题目。"]
            difficulty_description_parts = []
            if num_easy > 0:
                difficulty_description_parts.append(f"{num_easy}道简单题目")
            if num_medium > 0:
                difficulty_description_parts.append(f"{num_medium}道中等难度题目")
            if num_hard > 0:
                difficulty_description_parts.append(f"{num_hard}道困难题目")
            
            if difficulty_description_parts:
                prompt_parts.append("，".join(difficulty_description_parts))
            
            if categories:
                prompt_parts.append(f"，题目类别应限定于：{'，'.join(categories)}")
            else:
                prompt_parts.append("，题目类别不限")
            
            prompt_parts.append("。请确保严格按照要求的数量、难度和类别选择，并以JSON字符串格式返回题目列表，不要包含任何额外的解释性文字。")
            user_prompt = "".join(prompt_parts)

            # 调用 agent
            agent_response_str = await problem_selector_agent.arun(user_prompt)

            # 尝试解析 agent 的响应
            try:
                selected_problems = json.loads(agent_response_str)
                if not isinstance(selected_problems, list):
                    # 如果 agent 返回的不是列表（例如，是一个包含 "problems" 键的字典）
                    # 这不理想，agent 应直接返回列表。
                    print(f"Agent response was not a direct JSON list: {agent_response_str}")
                    raise json.JSONDecodeError("Agent 返回的不是JSON列表.", agent_response_str, 0)
            except json.JSONDecodeError as e:
                print(f"直接解析JSON失败: {e}。 Agent 原始响应: {agent_response_str}")
                error_message = f"无法从Agent响应中解析题目。原始响应: {agent_response_str}"
                # 尝试从可能包含额外文本的响应中提取JSON数组
                try:
                    list_start = agent_response_str.find('[')
                    list_end = agent_response_str.rfind(']')
                    if list_start != -1 and list_end != -1 and list_start < list_end:
                        json_candidate = agent_response_str[list_start : list_end + 1]
                        selected_problems = json.loads(json_candidate)
                        if not isinstance(selected_problems, list):
                            raise json.JSONDecodeError("提取的部分不是JSON列表.", json_candidate, 0)
                        print(f"提取后成功解析: {selected_problems}")
                    else:
                        return JsonResponse({"error": error_message, "detail": "在响应中未找到JSON数组。"}, status=500)
                except json.JSONDecodeError as extraction_e:
                    print(f"尝试提取JSON也失败了: {extraction_e}")
                    return JsonResponse({"error": error_message, "detail": str(extraction_e)}, status=500)
            
            return JsonResponse({
                "status": "success",
                "requested_prompt": user_prompt,
                "problems": selected_problems,
                "agent_raw_response": agent_response_str
            })

        except json.JSONDecodeError:
            return JsonResponse({"error": "请求体中的JSON格式无效。"}, status=400)
        except ValueError as ve:
            # 例如 int() 转换失败
            return JsonResponse({"error": f"请求数据中的值无效: {str(ve)}"}, status=400)
        except Exception as e:
            # 记录未预料到的错误以供调试
            print(f"在 select_problems_api 中发生意外错误: {type(e).__name__} - {str(e)}")
            # 返回一个通用的服务器错误消息给客户端
            return JsonResponse({"error": f"服务器发生意外错误: {type(e).__name__}"}, status=500)
    
    return JsonResponse({"error": "只允许POST请求。"}, status=405)

# 如果您想添加其他视图，可以在这里继续。
