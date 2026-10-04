"""Reminder service"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass
import logging
from croniter import croniter


from beaver_storage.models.reminder import Reminder
from beaver_storage.repositories.base import BaseRepository
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from beaver_core.utils import ValidationError, ServiceError

logger = logging.getLogger(__name__)


@dataclass
class ReminderNotification:
    """Reminder notification"""
    reminder_id: str
    username: str
    title: str
    body: str
    due_at: datetime
    is_overdue: bool


class ReminderService:
    """Reminder service"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = BaseRepository(Reminder, db)
        self.notification_handlers: List[Callable[[ReminderNotification], None]] = []
    
    def add_notification_handler(self, handler: Callable[[ReminderNotification], None]):
        """Add notification handler"""
        self.notification_handlers.append(handler)
    
    async def create_reminder(self, username: str, title: str, body: str, 
                            due_at: Optional[datetime], 
                            repeat_rule: Optional[str] = None) -> Optional[Reminder]:
        """Create reminder"""
        if due_at is not None and due_at.tzinfo is not None:
            due_at = due_at.astimezone().replace(tzinfo=None)
        
        # Validate repeat rule
        if repeat_rule and not self._validate_repeat_rule(repeat_rule):
            raise ValidationError(f"Invalid rule: {repeat_rule}. Supported rules: daily, weekly, monthly, yearly")
        
        reminder_data = {
            "id": f"reminder_{username}_{int(datetime.now().timestamp())}",
            "username": username,
            "title": title,
            "body": body,
            "due_at": due_at,

            "repeat_rule": repeat_rule,
            "status": "pending",
            "created_at": datetime.now()
        }
        reminder = await self.repo.create(reminder_data)
        logger.info(f"Created reminder {reminder.id} for user {username}")
        return reminder
    
    def _validate_repeat_rule(self, repeat_rule: str) -> bool:
        """Validate repeat rule"""
        try:
            # Support simple keywords
            simple_rules = ['daily', 'weekly', 'monthly', 'yearly']
            if repeat_rule.lower() in simple_rules:
                return True
            
            # Validate cron expression
            croniter(repeat_rule)
            return True
            
        except Exception:
            return False
    
    async def get_user_reminders(self, username: str, status: Optional[str] = None, 
                                limit: int = 50) -> List[Reminder]:
        """Get user reminders"""
        query = select(Reminder).where(Reminder.username == username)
        if status:
            query = query.where(Reminder.status == status)
        query = query.order_by(Reminder.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_reminder_with_id(self, reminder_id: str) -> Optional[Reminder]:
        """Get reminder by ID"""
        return await self.repo.get(reminder_id)
    
    async def get_due_reminders(self, check_window_minutes: int = 5) -> List[Reminder]:
        """Get due reminders"""
        now = datetime.now()
        window_end = now + timedelta(minutes=check_window_minutes)
        result = await self.db.execute(
            select(Reminder)
            .where(and_(
                Reminder.status == "pending",
                Reminder.due_at <= window_end
            ))
            .order_by(Reminder.due_at)
        )
        return result.scalars().all()
    
    async def mark_reminder_completed(self, reminder_id: str) -> bool:
        """Mark reminder as completed"""
        reminder = await self.repo.get(reminder_id)
        if not reminder:
            raise ValidationError("Reminder not found", field="reminder_id")
        await self.repo.update(reminder_id, {"status": "completed"})
        if reminder.repeat_rule:
            await self._create_next_reminder(reminder)
        logger.info(f"Marked reminder {reminder_id} as completed")
        return True
    
    async def _create_next_reminder(self, reminder: Reminder):
        """Create next recurring reminder"""
        next_due = self._calculate_next_due_time(reminder.due_at, reminder.repeat_rule)
        if next_due:
            await self.create_reminder(
                username=reminder.username,
                title=reminder.title,
                body=reminder.body,
                due_at=next_due,

                repeat_rule=reminder.repeat_rule
            )
            logger.info(f"Created next reminder for {reminder.id}")
    
    def _calculate_next_due_time(self, current_due: datetime, repeat_rule: str) -> Optional[datetime]:
        """Calculate next reminder time"""
        simple_rules = {
            'daily': timedelta(days=1),
            'weekly': timedelta(weeks=1),
            'monthly': timedelta(days=30),
            'yearly': timedelta(days=365)
        }
        if repeat_rule.lower() in simple_rules:
            return current_due + simple_rules[repeat_rule.lower()]
        cron = croniter(repeat_rule, current_due)
        return cron.get_next(datetime)
    
    async def delete_reminder(self, reminder_id: str) -> bool:
        """Delete reminder"""
        success = await self.repo.delete(reminder_id)
        if success:
            logger.info(f"Deleted reminder {reminder_id}")
        return success
    
    async def process_due_reminders(self) -> List[ReminderNotification]:
        """Process due reminders"""
        due_reminders = await self.get_due_reminders()
        notifications: List[ReminderNotification] = []
        for reminder in due_reminders:
            notification = ReminderNotification(
                reminder_id=reminder.id,
                username=reminder.username,
                title=reminder.title,
                body=reminder.body or "",
                due_at=reminder.due_at,
                is_overdue=reminder.due_at < datetime.now()
            )
            notifications.append(notification)
            for handler in self.notification_handlers:
                try:
                    handler(notification)
                except Exception as e:
                    logger.error(f"Error in notification handler: {e}")
            if not reminder.repeat_rule:
                await self.repo.update(reminder.id, {"status": "triggered"})
            else:
                await self.mark_reminder_completed(reminder.id)
        if notifications:
            logger.info(f"Processed {len(notifications)} due reminders")
        return notifications
    
    async def get_upcoming_reminders(self, username: str, hours: int = 24) -> List[Reminder]:
        """Get upcoming reminders"""
        now = datetime.now()
        end_time = now + timedelta(hours=hours)
        result = await self.db.execute(
            select(Reminder)
            .where(and_(
                Reminder.username == username,
                Reminder.status == "pending",
                Reminder.due_at.between(now, end_time)
            ))
            .order_by(Reminder.due_at)
        )
        return result.scalars().all()