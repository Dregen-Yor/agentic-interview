"""
基础智能体抽象类
定义所有专门智能体的通用接口和基本功能
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI


class BaseAgent(ABC):
    """智能体基类，定义通用接口"""
    
    def __init__(self, model: ChatOpenAI, name: str):
        self.model = model
        self.name = name
        self.system_prompt = ""
    
    @abstractmethod
    def get_system_prompt(self) -> str:
        """获取系统提示词"""
        pass
    
    @abstractmethod
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """处理输入数据并返回结果"""
        pass
    
    def _invoke_model(self, messages: List[BaseMessage]) -> str:
        """调用LLM模型"""
        try:
            response = self.model.invoke(messages)
            return response.content
        except Exception as e:
            print(f"Error invoking model in {self.name}: {e}")
            return f"Error: {str(e)}"
    
    def set_system_prompt(self, prompt: str):
        """设置系统提示词"""
        self.system_prompt = prompt


class InterviewState:
    """面试状态管理类"""
    
    def __init__(self, candidate_name: str, resume_data: Dict[str, Any] = None):
        self.candidate_name = candidate_name
        self.resume_data = resume_data or {}
        self.questions_asked = []
        self.answers_given = []
        self.scores = []
        self.current_score = 0
        self.total_questions = 0
        self.interview_complete = False
        self.final_decision = None
        self.summary = ""
        self.security_alerts = []
        
    def add_qa_pair(self, question: str, answer: str, score: int = 0):
        """添加问答对"""
        self.questions_asked.append(question)
        self.answers_given.append(answer)
        if score > 0:
            self.scores.append(score)
        self.total_questions += 1
    
    def get_current_context(self) -> Dict[str, Any]:
        """获取当前面试上下文"""
        return {
            "candidate_name": self.candidate_name,
            "resume_data": self.resume_data,
            "questions_asked": self.questions_asked,
            "answers_given": self.answers_given,
            "scores": self.scores,
            "current_score": sum(self.scores) / len(self.scores) if self.scores else 0,
            "total_questions": self.total_questions,
            "interview_complete": self.interview_complete
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "candidate_name": self.candidate_name,
            "resume_data": self.resume_data,
            "questions_asked": self.questions_asked,
            "answers_given": self.answers_given,
            "scores": self.scores,
            "current_score": sum(self.scores) / len(self.scores) if self.scores else 0,
            "total_questions": self.total_questions,
            "interview_complete": self.interview_complete,
            "final_decision": self.final_decision,
            "summary": self.summary,
            "security_alerts": self.security_alerts
        }