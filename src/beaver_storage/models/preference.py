"""Preference model"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Boolean, JSON, LargeBinary
from sqlalchemy.orm import relationship
from ..database import Base


class PreferenceRecord(Base):
    """Preference record model"""
    __tablename__ = "preference_records"
    
    id = Column(String, primary_key=True)
    username = Column(String, ForeignKey("users.username"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    embedding = Column(LargeBinary)  # embedding vector
    source_meta = Column(JSON)  # source metadata
    confidential = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    user = relationship("User", back_populates="preference_records")
    
    def __repr__(self):
        return f"<PreferenceRecord(id={self.id}, username={self.username})>"
