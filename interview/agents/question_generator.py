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

输出要求（JSON）：
{
    "question": "具体问题文本（可含必要的引导/定义）",
    "type": "问题类型（math_logic/technical/behavioral/experience）",
    "difficulty": "难度等级（easy/medium/hard）",
    "reasoning": "为什么在当前阶段提出该题，以及区分度点"
}
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
                # 开场以数理逻辑/自我介绍的轻量题目为主
                prompt_parts.append(
                    "这是面试的开场阶段：请先生成一个简短自我介绍引导问题，随后追加一个非常基础的数理逻辑小题（可口头推理完成），以帮助热身。问题要友好易懂。"
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
                        "请围绕候选人自述/简历中的已学内容，设计逐步加深的原理-推理-变式链式问题；同时体现数理基础与严谨性。若该内容偏工程实现，请先问核心原理或数学直觉。"
                    )
                else:
                    prompt_parts.append(
                        "候选人未明确自述技能，请生成一题数理逻辑基础题（如离散数学/组合/概率直觉/逻辑推理/不依赖编程的算法直觉），并给出一个可追问的后续变式。请将type设置为math_logic。"
                    )
            elif interview_stage == "behavioral":
                prompt_parts.append(
                    "请生成一个行为面试问题，重点评估基本素质与与人交往能力，如合作、倾听、冲突解决、尊重他人与表达清晰度。问题需与校园科研/团队作业场景贴合。"
                )
            
            # 添加历史问答信息
            if previous_qa:
                qa_history = "\n".join([f"Q: {qa.get('question', '')}\nA: {qa.get('answer', '')}" 
                                       for qa in previous_qa[-3:]])  # 只取最近3轮
                prompt_parts.append(f"之前的问答记录：\n{qa_history}")
                prompt_parts.append(f"当前平均分: {current_score}/10")
                prompt_parts.append("请根据候选人的回答情况，生成下一个合适的问题。")
            
            human_message_content = "\n\n".join(prompt_parts)
            
            messages = [
                SystemMessage(content=self.get_system_prompt()),
                HumanMessage(content=human_message_content)
            ]
            
            response = self._invoke_model(messages)
            
            # 尝试解析JSON响应
            try:
                result = json.loads(response)
                if "question" not in result:
                    raise ValueError("Response missing 'question' field")
                return result
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Failed to parse JSON response: {e}")
                # 如果JSON解析失败，返回一个默认格式
                return {
                    "question": response,
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