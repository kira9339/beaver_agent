"""Question value model"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, ForeignKey
from sqlalchemy.orm import relationship
from ..database import Base


class QuestionValue(Base):
    """Question value model"""
    __tablename__ = "question_values"
    
    username = Column(String, ForeignKey("users.username"), primary_key=True)
    qv = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    
    # Relationships
    user = relationship("User", back_populates="question_value")
    
    def __repr__(self):
        return f"<QuestionValue(username={self.username}, qv={self.qv})>"
