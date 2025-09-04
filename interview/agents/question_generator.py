"""
问题生成智能体
根据简历信息和RAG检索结果生成面试问题
"""

import json
from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage
from .base_agent import BaseAgent
from .retrieval import RetrievalSystem, KnowledgeExtractor


class QuestionGeneratorAgent(BaseAgent):
    """问题生成智能体"""
    
    def __init__(self, model, retrieval_system: RetrievalSystem):
        super().__init__(model, "QuestionGenerator")
        self.retrieval_system = retrieval_system
        self.base_system_prompt = """
你是一个大学内计算机拔尖班（科研方向）面试官。面试对象为大一新生，整体计算机知识储备可能有限。
面试将控制在5-6轮高效问答，需要在有限轮次内全面评估候选人。

目标与侧重点：
1. 核心重点：数理与逻辑基础（如离散数学思维、逻辑推理、抽象与形式化思考、基础概率/组合与算法直觉）
2. 次要但必考：基本素质与与人交往能力（沟通清晰度、合作意识、尊重他人）
3. 定向深挖：若候选人在自荐信/面试中明确提到学过某些计算机/数学/竞赛等内容，应根据该线索出题并逐步加深

问题生成原则：
- 先以可理解的数理逻辑题或情景化逻辑推理题开场，难度由浅入深；
- 对于明确自述的已学知识，设计追问与层层递进的探索（例如概念→原理→推导/例题→变式/开放题）；
- 避免依赖专业术语堆砌，确保大一新生可读；如需术语，请先给出通俗解释；
- 保持问题区分度，允许出现多步推理与简短演算；
- 适度穿插行为/沟通类问题以评估基本素质与社交能力；
- 必须在5-6轮内覆盖：数理逻辑、技术深度、行为面试；
- 根据前序回答质量，快速调整后续问题难度和方向；

输出要求（必须是严格的JSON格式）：
{
    "question": "具体问题文本（可含必要的引导/定义）",
    "type": "问题类型（math_logic/technical/behavioral/experience）",
    "difficulty": "难度等级（easy/medium/hard）",
    "reasoning": "为什么在当前阶段提出该题，以及区分度点"
}

**重要格式要求**：
1. 必须返回完整的JSON格式，确保所有大括号 {} 和引号 "" 配对
2. 不要在JSON前后添加任何额外文字、markdown标记或代码块符号
3. 确保最后一个字段后没有多余的逗号
4. 检查JSON的完整性，特别是结尾的 '}' 大括号
"""
    
    def get_system_prompt(self) -> str:
        return self.system_prompt or self.base_system_prompt
    
    def set_candidate_context(self, resume_data: Dict[str, Any]):
        """设置候选人上下文，将简历信息融入系统提示词"""
        position = KnowledgeExtractor.extract_position_from_resume(resume_data)
        skills = KnowledgeExtractor.extract_skills_from_resume(resume_data)
        experience_level = KnowledgeExtractor.extract_experience_level(resume_data)
        
        candidate_context = f"""
候选人信息：
- 目标职位: {position}
- 技能: {', '.join(skills) if skills else '未明确'}
- 经验水平: {experience_level}
- 简历详情: {json.dumps(resume_data, ensure_ascii=False, indent=2)}

请根据以上候选人信息生成合适的面试问题。
"""
        
        self.system_prompt = self.base_system_prompt + candidate_context
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成面试问题
        input_data包含:
        - resume_data: 简历信息
        - interview_stage: 面试阶段 (opening/technical/behavioral/closing)
        - previous_qa: 之前的问答记录
        - current_score: 当前评分情况
        """
        print(f"===== QuestionGenerator.process() 开始执行 =====")
        try:
            resume_data = input_data.get("resume_data", {})
            interview_stage = input_data.get("interview_stage", "technical")
            previous_qa = input_data.get("previous_qa", [])
            current_score = input_data.get("current_score", 0)
            
            # 如果是第一次生成问题，设置候选人上下文
            if not previous_qa and resume_data:
                self.set_candidate_context(resume_data)
            
            # 构建prompt
            prompt_parts = []
            
            if interview_stage == "opening":
                # 开场以数理逻辑/自我介绍的轻量题目为主，由于总轮次有限，需要高效
                prompt_parts.append(
                    "这是面试的开场阶段（总共只有5-6轮）：请生成一个既能了解背景又能体现数理逻辑基础的高效开场问题。问题要友好但有一定区分度，能快速了解候选人的思维能力。"
                )
            elif interview_stage == "technical":
                # 技术阶段在本场景下以数理逻辑为主；若候选人自述技能，则定向深挖该方向
                skills = KnowledgeExtractor.extract_skills_from_resume(resume_data)
                position = KnowledgeExtractor.extract_position_from_resume(resume_data)

                if skills:
                    rag_query = f"{position} {' '.join(skills)} 相关面试题（注重原理与推理）"
                    rag_results = self.retrieval_system.rag_search(rag_query, limit=2)
                    prompt_parts.append(f"知识库参考内容：\n{rag_results}")
                    prompt_parts.append(
                        "请围绕候选人自述/简历中的已学内容，设计一个高效的核心问题直达本质理解；同时体现数理基础与严谨性。由于总轮次有限，避免过多铺垫，直接考察核心能力。"
                    )
                else:
                    prompt_parts.append(
                        "候选人未明确自述技能，请生成一题数理逻辑基础题（如离散数学/组合/概率直觉/逻辑推理/不依赖编程的算法直觉），并给出一个可追问的后续变式。请将type设置为math_logic。"
                    )
            elif interview_stage == "behavioral":
                prompt_parts.append(
                    "请生成一个高效的行为面试问题，重点评估基本素质与与人交往能力，如合作、倾听、冲突解决、尊重他人与表达清晰度。问题需与校园科研/团队作业场景贴合，且能在一个回答中体现多个维度。"
                )
            
            # 添加历史问答信息
            if previous_qa:
                qa_history = "\n".join([f"Q: {qa.get('question', '')}\nA: {qa.get('answer', '')}" 
                                       for qa in previous_qa[-3:]])  # 只取最近3轮
                prompt_parts.append(f"之前的问答记录：\n{qa_history}")
                prompt_parts.append(f"当前平均分: {current_score}/10")
                prompt_parts.append(f"当前是第{len(previous_qa)+1}轮（总共5-6轮），请根据候选人的回答情况和剩余轮次，生成一个高效且有针对性的问题。")
            
            human_message_content = "\n\n".join(prompt_parts)
            
            messages = [
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=human_message_content)
            ]
            
            response = self._invoke_model(messages)
            
            # 输出原始响应内容
            print(f"===== QuestionGenerator 原始响应 =====")
            print(response)
            print("=====================================\n")
            
            # 尝试解析JSON响应
            try:
                # 首先尝试修复常见的JSON问题
                fixed_response = self._fix_common_json_issues(response)
                result = json.loads(fixed_response)
                if "question" not in result:
                    raise ValueError("Response missing 'question' field")
                return result
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Failed to parse JSON response: {e}")
                print(f"Raw response: {response}")

                # 如果JSON解析失败，直接返回原始字符串
                question_text = self._extract_question_from_raw_response(response)
                return {
                    "question": question_text,
                    "type": "general",
                    "difficulty": "medium",
                    "reasoning": "Generated question based on context"
                }
                
        except Exception as e:
            print(f"Error in QuestionGeneratorAgent: {e}")
            return {
                "question": "请介绍一下您的工作经验和技能背景。",
                "type": "general",
                "difficulty": "easy",
                "reasoning": "Default question due to error"
            }
    
    def generate_initial_questions(self, resume_data: Dict[str, Any], count: int = 3) -> List[Dict[str, Any]]:
        """生成初始问题集"""
        questions = []
        
        # 开场问题
        opening_result = self.process({
            "resume_data": resume_data,
            "interview_stage": "opening"
        })
        questions.append(opening_result)
        
        # 技术问题
        for i in range(count - 1):
            technical_result = self.process({
                "resume_data": resume_data,
                "interview_stage": "technical",
                "previous_qa": []
            })
            questions.append(technical_result)
        
        return questions

    def _fix_common_json_issues(self, response: str) -> str:
        """
        修复常见的JSON格式问题
        """
        # 清理响应
        cleaned = response.strip()
        
        # 移除markdown代码块标记
        if cleaned.startswith('```json'):
            cleaned = cleaned[7:]
        elif cleaned.startswith('```'):
            cleaned = cleaned[3:]
        if cleaned.endswith('```'):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        # 检查是否缺少结尾大括号
        open_braces = cleaned.count('{')
        close_braces = cleaned.count('}')
        
        if open_braces > close_braces:
            # 添加缺少的结尾大括号
            missing_braces = open_braces - close_braces
            cleaned += '}' * missing_braces
        
        # 移除可能的多余逗号（在大括号前的逗号）
        import re
        cleaned = re.sub(r',\s*}', '}', cleaned)
        cleaned = re.sub(r',\s*]', ']', cleaned)
        
        return cleaned
    
    def _extract_question_from_raw_response(self, raw_response: str) -> str:
        """
        从原始AI响应中提取问题文本
        JSON解析失败时直接返回整个字符串
        """
        return raw_response.strip()