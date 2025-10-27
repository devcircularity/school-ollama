# app/ai/entity_memory.py
"""
Entity Memory Store - Tracks partial entity construction across conversation turns
Prevents hallucination by explicitly storing what we KNOW vs what we NEED
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class PartialEntity(BaseModel):
    """Represents a partially filled entity being constructed"""
    entity_type: str  # "student", "class", etc.
    intent: str  # "create_student", "update_student"
    parameters: Dict[str, Any]  # Filled parameters
    missing_fields: List[str]  # Required fields still missing
    optional_fields: List[str] = []  # Optional fields not yet provided
    created_at: datetime
    updated_at: datetime
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class EntityMemoryStore:
    """
    In-memory store for partial entities during conversation
    In production, this could be Redis or similar
    """
    
    def __init__(self):
        # conversation_id -> PartialEntity
        self._store: Dict[str, PartialEntity] = {}
    
    def set_entity(self, conversation_id: str, entity: PartialEntity):
        """Store or update a partial entity"""
        entity.updated_at = datetime.utcnow()
        self._store[conversation_id] = entity
        logger.info(f"Stored partial entity for conversation {conversation_id}: {entity.entity_type}")
    
    def get_entity(self, conversation_id: str) -> Optional[PartialEntity]:
        """Retrieve partial entity for conversation"""
        return self._store.get(conversation_id)
    
    def clear_entity(self, conversation_id: str):
        """Clear partial entity (after successful action or user cancellation)"""
        if conversation_id in self._store:
            del self._store[conversation_id]
            logger.info(f"Cleared partial entity for conversation {conversation_id}")
    
    def has_entity(self, conversation_id: str) -> bool:
        """Check if conversation has a partial entity"""
        return conversation_id in self._store


# Global singleton
_entity_store: Optional[EntityMemoryStore] = None


def get_entity_store() -> EntityMemoryStore:
    """Get or create entity memory store singleton"""
    global _entity_store
    if _entity_store is None:
        _entity_store = EntityMemoryStore()
    return _entity_store