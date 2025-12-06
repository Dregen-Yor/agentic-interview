"""
Memory management system
Provides structured interview memory storage and retrieval functionality
"""

from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import logging


class InterviewMemory:
    """Interview memory manager"""

    def __init__(self, candidate_name: str):
        self.candidate_name = candidate_name
        self.qa_history = []  # Q&A history
        self.score_history = []  # Score history
        self.context_memory = {}  # Context memory
        self.created_at = datetime.now()
        self.logger = logging.getLogger("interview.agents.memory")
        
    def add_question_answer(self, question: str, answer: str, timestamp: datetime = None, question_data: Dict[str, Any] = None):
        """Add Q&A pair, now supports storing complete question JSON object"""
        if timestamp is None:
            timestamp = datetime.now()

        qa_entry = {
            "question": question,
            "answer": answer,
            "timestamp": timestamp,
            "question_id": len(self.qa_history)
        }

        # If provided complete question data, also store it
        if question_data:
            qa_entry["question_data"] = question_data

        self.qa_history.append(qa_entry)

    def add_score(self, question_id: int, score: int, reasoning: str = ""):
        """Add score"""
        self.score_history.append({
            "question_id": question_id,
            "score": score,
            "reasoning": reasoning,
            "timestamp": datetime.now()
        })
    
    def get_recent_qa(self, count: int = 5) -> List[Dict[str, Any]]:
        """Get recent Q&A records"""
        return self.qa_history[-count:] if self.qa_history else []

    def get_all_qa(self) -> List[Dict[str, Any]]:
        """Get all Q&A records"""
        return self.qa_history

    def get_scores(self) -> List[Dict[str, Any]]:
        """Get all score records"""
        return self.score_history

    def get_average_score(self) -> float:
        """Get average score"""
        if not self.score_history:
            return 0.0
        return sum(s["score"] for s in self.score_history) / len(self.score_history)
    
    def set_context(self, key: str, value: Any):
        """Set context information"""
        self.context_memory[key] = value

    def get_context(self, key: str, default: Any = None) -> Any:
        """Get context information"""
        return self.context_memory.get(key, default)

    def get_formatted_history(self, include_scores: bool = True) -> str:
        """Get formatted history records"""
        formatted = f"Candidate: {self.candidate_name}\nInterview Start Time: {self.created_at}\n\n"

        for i, qa in enumerate(self.qa_history):
            formatted += f"Question {i+1}: {qa['question']}\n"

            # If provided complete question data, show more metadata
            if 'question_data' in qa and qa['question_data']:
                question_data = qa['question_data']
                formatted += f"Question Type: {question_data.get('type', 'N/A')}\n"
                formatted += f"Difficulty: {question_data.get('difficulty', 'N/A')}\n"
                # If provided other fields, also show them
                if 'reasoning' in question_data:
                    formatted += f"Question Generation Reasoning: {question_data['reasoning']}\n"

            formatted += f"Answer: {qa['answer']}\n"

            if include_scores:
                # Find corresponding score
                score_record = next((s for s in self.score_history if s["question_id"] == i), None)
                if score_record:
                    formatted += f"Score: {score_record['score']}/10\n"
                    if score_record['reasoning']:
                        formatted += f"Score Reasoning: {score_record['reasoning']}\n"

            formatted += "\n"

        if include_scores and self.score_history:
            formatted += f"Current Average Score: {self.get_average_score():.2f}/10\n"

        return formatted
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict, ensure all data can be serialized"""
        def serialize_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            return obj

        def serialize_data(obj):
            if isinstance(obj, dict):
                return {k: serialize_data(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [serialize_data(item) for item in obj]
            elif isinstance(obj, datetime):
                return obj.isoformat()
            else:
                return obj

        return {
            "candidate_name": self.candidate_name,
            "qa_history": serialize_data(self.qa_history),
            "score_history": serialize_data(self.score_history),
            "context_memory": serialize_data(self.context_memory),
            "created_at": serialize_datetime(self.created_at),
            "average_score": self.get_average_score()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'InterviewMemory':
        """Create instance from dict"""
        memory = cls(data["candidate_name"])
        memory.qa_history = data.get("qa_history", [])
        memory.score_history = data.get("score_history", [])
        memory.context_memory = data.get("context_memory", {})

        created_at_str = data.get("created_at")
        if created_at_str:
            try:
                memory.created_at = datetime.fromisoformat(created_at_str)
            except:
                memory.created_at = datetime.now()

        return memory


class MemoryManager:
    """memory manager, manage multiple interview sessions"""
    
    def __init__(self):
        self.memories = {}  # session_id -> InterviewMemory
    
    def create_memory(self, session_id: str, candidate_name: str) -> InterviewMemory:
        """create new interview memory"""
        memory = InterviewMemory(candidate_name)
        self.memories[session_id] = memory
        return memory
    
    def get_memory(self, session_id: str) -> Optional[InterviewMemory]:
        """get interview memory"""
        return self.memories.get(session_id)
    
    def remove_memory(self, session_id: str):
        """delete interview memory"""
        if session_id in self.memories:
            del self.memories[session_id]
    
    def get_all_memories(self) -> Dict[str, InterviewMemory]:
        """get all memories"""
        return self.memories.copy()

    def save_memory_to_storage(self, session_id: str, storage_interface) -> bool:
        """save memory to persistent storage"""
        try:
            memory = self.get_memory(session_id)
            if not memory:
                return False

            memory_data = {
                "session_id": session_id,
                "memory_data": memory.to_dict(),
                "saved_at": datetime.now().isoformat()
            }

            success = storage_interface.save_memory(memory_data)
            if success:
                self.logger.info(f"memory saved to storage: {session_id}")
            return success
        except Exception as e:
            self.logger.error(f"error saving memory: {e}")
            return False

    def load_memory_from_storage(self, session_id: str, storage_interface) -> Optional[InterviewMemory]:
        """load memory from persistent storage"""
        try:
            memory_data = storage_interface.load_memory(session_id)
            if not memory_data or "memory_data" not in memory_data:
                return None

            memory = InterviewMemory.from_dict(memory_data["memory_data"])
            self.memories[session_id] = memory
            self.logger.info(f"memory loaded from storage: {session_id}")
            return memory
        except Exception as e:
            self.logger.error(f"error: {e}")
            return None

    def save_all_memories_to_storage(self, storage_interface) -> Dict[str, bool]:
        """save all active memories to persistent storage"""
        results = {}
        for session_id in list(self.memories.keys()):
            results[session_id] = self.save_memory_to_storage(session_id, storage_interface)
        return results

    def get_memory_summary(self, session_id: str) -> Optional[Dict[str, Any]]:
        """get memory summary information"""
        memory = self.get_memory(session_id)
        if not memory:
            return None

        return {
            "candidate_name": memory.candidate_name,
            "total_questions": len(memory.qa_history),
            "average_score": memory.get_average_score(),
            "created_at": memory.created_at.isoformat() if isinstance(memory.created_at, datetime) else memory.created_at,
            "has_context": bool(memory.context_memory)
        }