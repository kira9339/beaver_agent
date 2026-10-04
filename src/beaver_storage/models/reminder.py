"""Reminder model"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from ..database import Base


class Reminder(Base):
    """Reminder model"""
    __tablename__ = "reminders"
    
    id = Column(String, primary_key=True)
    username = Column(String, ForeignKey("users.username"), nullable=False, index=True)
    title = Column(String, nullable=False)
    body = Column(Text)
    due_at = Column(DateTime, nullable=True, index=True)

    repeat_rule = Column(String)  # Cron expression or RRULE
    status = Column(String, default="pending")  # pending/completed/cancelled
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    user = relationship("User", back_populates="reminders")
    
    def __repr__(self):
        return f"<Reminder(id={self.id}, title={self.title})>"