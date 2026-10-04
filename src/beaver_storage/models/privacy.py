"""Privacy settings model"""

from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from ..database import Base


class UserPrivacy(Base):
    """User privacy settings model"""
    __tablename__ = "user_privacy"
    
    id = Column(String, primary_key=True)
    username = Column(String, ForeignKey("users.username"), nullable=False, index=True)
    key = Column(String, nullable=False)
    value = Column(JSON)
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    user = relationship("User", back_populates="privacy_settings")
    
    def __repr__(self):
        return f"<UserPrivacy(id={self.id}, key={self.key})>"