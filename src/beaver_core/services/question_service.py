"""Proactive questioning service"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import logging

from beaver_models.base import ModelProvider, ModelMessage, ModelRole
from beaver_storage.models.question_value import QuestionValue
from beaver_storage.models.conversation import Conversation
from beaver_storage.models.message import Message
from beaver_storage.models.preference import PreferenceRecord
from beaver_storage.models.reminder import Reminder
from beaver_storage.repositories.base import BaseRepository
from beaver_storage.repositories.question_value import QuestionValueRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from beaver_core.utils import ValidationError, ServiceError

logger = logging.getLogger(__name__)


@dataclass
class QuestionCandidate:
    """Question candidate"""
    question: str
    score: float
    context: str
    category: str  # 'preference', 'reminder', 'conversation', 'general'


@dataclass
class QuestionConfig:
    """Question configuration"""
    alpha: float = 0.05  # Base growth rate (per hour)
    beta: float = 1.0    # Information gap weight
    gamma: float = 0.5   # Unanswered questions weight
    decay: float = 0.3   # Response decay
    max_qv: float = 10.0 # Maximum question value
    threshold: float = 3.0  # Trigger threshold
    max_questions: int = 3  # Maximum number of questions


class QuestionService:
    """Proactive questioning service"""
    
    def __init__(self, db: AsyncSession, model_provider: ModelProvider, config: Optional[QuestionConfig] = None):
        self.db = db
        self.model_provider = model_provider
        self.config = config or QuestionConfig()
        self.qv_repo = QuestionValueRepository(db)  # Use dedicated repository
    
    async def update_question_value(self, username: str, 
                                    info_gap_score: float = 0.0,
                                    unanswered_questions: int = 0,
                                    user_engagement_score: float = 0.0) -> float:
        """Update the user's question value"""
        qv_record = await self.qv_repo.get_by_username(username)
        if not qv_record:
            qv_record = await self.qv_repo.create({
                "username": username,
                "qv": 0.0,
                "last_updated": datetime.now()
            })
        now = datetime.now()
        delta_hours = (now - qv_record.last_updated).total_seconds() / 3600
        new_qv = qv_record.qv
        new_qv += self.config.alpha * delta_hours
        new_qv += self.config.beta * info_gap_score
        new_qv += self.config.gamma * (1 if unanswered_questions > 0 else 0)
        new_qv -= self.config.decay * user_engagement_score
        new_qv = max(0, min(new_qv, self.config.max_qv))
        await self.qv_repo.update(username, {"qv": new_qv, "last_updated": now})
        logger.info(f"Updated question value for user {username}: {qv_record.qv} -> {new_qv}")
        return new_qv
    
    async def should_ask_question(self, username: str) -> bool:
        """Determine whether a proactive question should be asked"""
        qv_record = await self.qv_repo.get_by_username(username)
        if not qv_record:
            return False
        return qv_record.qv >= self.config.threshold
    
    async def get_question_value(self, username: str) -> float:
        """Get the user's current question value"""
        qv_record = await self.qv_repo.get_by_username(username)
        if not qv_record:
            qv_record = await self.qv_repo.create({
                "username": username,
                "qv": 0.0,
                "last_updated": datetime.now()
            })
        return qv_record.qv
    
    async def generate_questions(self, username: str) -> List[QuestionCandidate]:
        """Generate candidate questions"""
        candidates: List[QuestionCandidate] = []
        conversation_questions = await self._generate_conversation_questions(username)
        candidates.extend(conversation_questions)
        preference_questions = await self._generate_preference_questions(username)
        candidates.extend(preference_questions)
        reminder_questions = await self._generate_reminder_questions(username)
        candidates.extend(reminder_questions)
        candidates.sort(key=lambda x: x.score, reverse=True)
        return candidates[:self.config.max_questions]
    
    async def _generate_conversation_questions(self, username: str) -> List[QuestionCandidate]:
        """Generate questions based on conversation context"""
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.username == username)
            .order_by(Conversation.updated_at.desc())
            .limit(3)
        )
        conversations = result.scalars().all()
        if not conversations:
            return []
        recent_messages: List[Message] = []
        for conv in conversations:
            msg_result = await self.db.execute(
                select(Message)
                .where(Message.conversation_id == conv.id)
                .order_by(Message.created_at.desc())
                .limit(5)
            )
            recent_messages.extend(msg_result.scalars().all())
        if not recent_messages:
            return []
        context = "\n".join([
            f"{msg.role}: {msg.content[:200]}" 
            for msg in sorted(recent_messages, key=lambda x: x.created_at)[-10:]
        ])
        messages = [ModelMessage(role=ModelRole.USER, content=(
            f"Generate 1-2 questions based on the following conversation history, "
            f"helping better understand the user's needs or provide assistance.\n\n"
            f"Conversation history:\n{context}\n\n"
            f"Please generate concise and relevant questions, each on a new line:"
        ))]
        response = await self.model_provider.generate(messages)
        questions = [q.strip() for q in response.content.split('\n') if q.strip()]
        return [
            QuestionCandidate(
                question=q,
                score=0.7,
                context=context[:500],
                category="conversation"
            )
            for q in questions[:2]
        ]
    
    async def _generate_preference_questions(self, username: str) -> List[QuestionCandidate]:
        """Generate questions based on user preferences"""
        result = await self.db.execute(
            select(PreferenceRecord)
            .where(PreferenceRecord.username == username)
            .order_by(PreferenceRecord.created_at.desc())
            .limit(5)
        )
        preferences = result.scalars().all()
        if not preferences:
            return []
        pref_context = "\n".join([pref.text for pref in preferences])
        messages = [ModelMessage(role=ModelRole.USER, content=(
            f"Generate a question based on the following user preferences, "
            f"helping better understand the user's needs or provide personalized suggestions:\n\n"
            f"User preferences:\n{pref_context}\n\n"
            f"Please generate a question that is helpful in understanding the user's preferences or providing personalized suggestions:"
        ))]
        response = await self.model_provider.generate(messages)
        question = response.content.strip()
        if question:
            return [QuestionCandidate(
                question=question,
                score=0.8,
                context=pref_context[:300],
                category="preference"
            )]
        return []
    
    async def _generate_reminder_questions(self, username: str) -> List[QuestionCandidate]:
        """Generate questions based on reminders"""
        now = datetime.now()
        soon = now + timedelta(hours=24)
        result = await self.db.execute(
            select(Reminder)
            .where(and_(
                Reminder.username == username,
                Reminder.status == "pending",
                Reminder.due_at.between(now, soon)
            ))
            .order_by(Reminder.due_at)
            .limit(3)
        )
        reminders = result.scalars().all()
        if not reminders:
            return []
        questions: List[QuestionCandidate] = []
        for reminder in reminders:
            time_left = reminder.due_at - now
            hours_left = int(time_left.total_seconds() / 3600)
            question = (
                f"Reminder: '{reminder.title}' is due in {hours_left} hours. "
                f"Do you need me to help prepare something for you?"
            )
            questions.append(QuestionCandidate(
                question=question,
                score=0.9,
                context=f"Reminder: {reminder.title} - {reminder.body or ''}",
                category="reminder"
            ))
        return questions
    
    async def decrease_question_value(self, username: str, amount: float = 1.0):
        """Decrease question value (after user responds)"""
        qv_record = await self.qv_repo.get_by_username(username)
        if qv_record:
            new_qv = max(0, qv_record.qv - amount)
            await self.qv_repo.update(username, {
                "qv": new_qv,
                "last_updated": datetime.now()
            })
            logger.info(f"Decreased question value for user {username}: {qv_record.qv} -> {new_qv}")