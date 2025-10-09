"""
Base Agent Abstract Class
Defines common interfaces and basic functionality for all specialized agents
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI


class BaseAgent(ABC):
    """Agent base class, defines common interfaces"""

    def __init__(self, model: ChatOpenAI, name: str):
        self.model = model
        self.name = name
        self.system_prompt = ""

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Get system prompt"""
        pass

    @abstractmethod
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process input data and return result"""
        pass

    def _invoke_model(self, messages: List[BaseMessage]) -> str:
        """Invoke LLM model"""
        try:
            print(f"===== {self.name} starting LLM invocation =====")
            response = self.model.invoke(messages)
            print(f"===== {self.name} LLM invocation completed =====")
            return response.content
        except Exception as e:
            print(f"Error invoking model in {self.name}: {e}")
            return f"Error: {str(e)}"

    def set_system_prompt(self, prompt: str):
        """Set system prompt"""
        self.system_prompt = prompt


class InterviewState:
    """interview state"""
    
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
        """add qa pair"""
        self.questions_asked.append(question)
        self.answers_given.append(answer)
        if score > 0:
            self.scores.append(score)
        self.total_questions += 1
    
    def get_current_context(self) -> Dict[str, Any]:
        """get current interview context"""
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
        """convert to dict"""
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