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
你是一个专业的面试官，负责根据候选人的简历和面试进展生成合适的面试问题。

你的职责：
1. 根据候选人的简历背景生成针对性的问题
2. 考虑面试的进展情况，确保问题的逻辑性和递进性
3. 结合知识库中的相关技术问题
4. 确保问题具有区分度，能够有效评估候选人的能力水平

问题生成原则：
- 问题应该清晰、具体、有针对性
- 避免过于简单或过于复杂的问题
- 结合候选人的经验水平调整问题难度
- 确保问题能够引出候选人的深度思考和具体经验分享

请以JSON格式返回结果，包含以下字段：
{
    "question": "生成的问题",
    "type": "问题类型（technical/behavioral/experience）",
    "difficulty": "难度等级（easy/medium/hard）",
    "reasoning": "选择这个问题的原因"
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
                prompt_parts.append("这是面试的开场阶段，请生成一个开场问题，让候选人自我介绍并分享相关经验。")
            elif interview_stage == "technical":
                # 从知识库获取技术问题参考
                skills = KnowledgeExtractor.extract_skills_from_resume(resume_data)
                position = KnowledgeExtractor.extract_position_from_resume(resume_data)
                
                if skills:
                    rag_query = f"{position} {' '.join(skills)} 技术面试题"
                    rag_results = self.retrieval_system.rag_search(rag_query, limit=2)
                    prompt_parts.append(f"知识库参考内容：\n{rag_results}")
                
                prompt_parts.append("请生成一个技术相关的问题，评估候选人的专业技能。")
            elif interview_stage == "behavioral":
                prompt_parts.append("请生成一个行为面试问题，评估候选人的软技能和工作态度。")
            
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