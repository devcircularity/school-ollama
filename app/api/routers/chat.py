# app/api/routers/chat.py - Fixed to pass JWT token to Rasa
from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile, Request
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from sqlalchemy import select, desc
from typing import Dict, Any, List, Optional
from uuid import UUID
import logging
import time
from datetime import datetime, timezone

from app.core.db import get_db
from app.api.deps.tenancy import require_school
from app.models.chat import ChatConversation, ChatMessage, MessageType
from app.schemas.chat import (
    ChatMessage as ChatMessageSchema,
    ChatResponse,
    ConversationCreate,
    ConversationResponse,
    ConversationList,
    ConversationDetail,
    MessageResponse,
    UpdateConversation,
    FileAttachment,
    prepare_for_json_storage
)
from app.services.chat_service import ChatService

logger = logging.getLogger(__name__)
router = APIRouter()

def extract_auth_token(request: Request) -> Optional[str]:
    """Extract JWT token from Authorization header"""
    authorization = request.headers.get("Authorization")
    if authorization and authorization.startswith("Bearer "):
        return authorization[7:]  # Remove "Bearer " prefix
    return None

@router.post("/conversations", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    conversation_data: ConversationCreate,
    ctx: Dict[str, Any] = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Create a new chat conversation"""
    user = ctx["user"]
    school_id = ctx["school_id"]
    
    # Create timestamp for consistent use
    now = datetime.now(timezone.utc)
    
    new_conversation = ChatConversation(
        user_id=user.id,
        school_id=UUID(school_id),
        title=conversation_data.title,
        first_message=conversation_data.first_message,
        message_count=0,
        last_activity=now
    )
    
    db.add(new_conversation)
    
    try:
        db.commit()
        db.refresh(new_conversation)
        logger.info(f"New conversation created: {new_conversation.id} by {user.email}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating conversation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating conversation"
        )
    
    return ConversationResponse.from_attributes(new_conversation)

@router.get("/conversations", response_model=ConversationList)
async def get_conversations(
    ctx: Dict[str, Any] = Depends(require_school),
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    archived: Optional[bool] = Query(None)
):
    """Get user's chat conversations"""
    user = ctx["user"]
    school_id = ctx["school_id"]
    
    query = (
        select(ChatConversation)
        .where(
            ChatConversation.user_id == user.id,
            ChatConversation.school_id == UUID(school_id)
        )
    )
    
    if archived is not None:
        query = query.where(ChatConversation.is_archived == archived)
    
    query = query.order_by(desc(ChatConversation.last_activity))
    
    # Get total count
    total_query = query.with_only_columns(ChatConversation.id)
    total = len(db.execute(total_query).scalars().all())
    
    # Apply pagination
    offset = (page - 1) * limit
    conversations = db.execute(
        query.offset(offset).limit(limit)
    ).scalars().all()
    
    conversation_list = [
        ConversationResponse.from_attributes(conv) for conv in conversations
    ]
    
    has_next = total > page * limit
    
    return ConversationList(
        conversations=conversation_list,
        total=total,
        page=page,
        limit=limit,
        has_next=has_next
    )

@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    ctx: Dict[str, Any] = Depends(require_school),
    db: Session = Depends(get_db),
    include_messages: bool = Query(True)
):
    """Get conversation details with messages"""
    user = ctx["user"]
    school_id = ctx["school_id"]
    
    try:
        conv_uuid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format"
        )
    
    conversation = db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_uuid,
            ChatConversation.user_id == user.id,
            ChatConversation.school_id == UUID(school_id)
        )
    ).scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    result = ConversationDetail.from_attributes(conversation)
    
    if include_messages:
        messages = db.execute(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conv_uuid)
            .order_by(ChatMessage.created_at)
        ).scalars().all()
        
        result.messages = [MessageResponse.from_attributes(msg) for msg in messages]
    
    return result

@router.post("/conversations/{conversation_id}/messages", response_model=ChatResponse)
async def send_message(
    conversation_id: str,
    message_data: ChatMessageSchema,
    request: Request,  # Add Request to extract auth token
    ctx: Dict[str, Any] = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Send a message and get Rasa response"""
    user = ctx["user"]
    school_id = ctx["school_id"]
    
    # Extract JWT token from request
    auth_token = extract_auth_token(request)
    if not auth_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token"
        )
    
    try:
        conv_uuid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format"
        )
    
    # Verify conversation exists and belongs to user
    conversation = db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_uuid,
            ChatConversation.user_id == user.id,
            ChatConversation.school_id == UUID(school_id)
        )
    ).scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    start_time = time.time()
    
    # Create timestamp for consistent use across all operations
    message_timestamp = datetime.now(timezone.utc)
    
    # Store user message
    user_message = ChatMessage(
        conversation_id=conv_uuid,
        user_id=user.id,
        school_id=UUID(school_id),
        message_type=MessageType.USER,
        content=message_data.message,
        context_data=prepare_for_json_storage(message_data.context or {}),
        created_at=message_timestamp
    )
    
    # Handle attachments if present
    if message_data.attachments:
        user_message.response_data = prepare_for_json_storage({
            "attachments": [attachment.dict() for attachment in message_data.attachments]
        })
    
    db.add(user_message)
    
    try:
        # Get Rasa response using chat service
        chat_service = ChatService()
        
        # Build context for Rasa
        chat_context = {
            "user_id": str(user.id),
            "school_id": school_id,
            "conversation_id": conversation_id,
            "user_roles": user.roles,
            "context": message_data.context or {}
        }
        
        # Send message to Rasa WITH auth token
        rasa_response = await chat_service.send_to_rasa(
            message=message_data.message,
            sender_id=f"{user.id}_{conversation_id}",
            context=chat_context,
            attachments=message_data.attachments,
            auth_token=auth_token  # Pass the JWT token here
        )
        
        processing_time = int((time.time() - start_time) * 1000)
        
        # Store assistant response
        assistant_message = ChatMessage(
            conversation_id=conv_uuid,
            user_id=user.id,
            school_id=UUID(school_id),
            message_type=MessageType.ASSISTANT,
            content=rasa_response.get("response", "I'm sorry, I didn't understand that."),
            intent=rasa_response.get("intent"),
            context_data=prepare_for_json_storage(chat_context),
            response_data=prepare_for_json_storage(rasa_response),
            processing_time_ms=processing_time,
            created_at=message_timestamp
        )
        
        db.add(assistant_message)
        
        # Update conversation metadata with explicit timestamp
        conversation.last_activity = message_timestamp
        conversation.message_count += 2  # User + Assistant messages
        
        db.commit()
        
        logger.info(f"Message processed: conversation {conversation_id}, processing time: {processing_time}ms")
        logger.info("="*60)
        logger.info("ASSISTANT MESSAGE CONTENT (repr):")
        logger.info(repr(assistant_message.content))
        logger.info("="*60)
        logger.info("ASSISTANT MESSAGE CONTENT (raw):")
        logger.info(assistant_message.content)
        logger.info("="*60)
        
        # Return formatted response
        return ChatResponse(
            response=assistant_message.content,
            intent=assistant_message.intent,
            data=rasa_response.get("data"),
            action_taken=rasa_response.get("action_taken"),
            suggestions=rasa_response.get("suggestions", []),
            conversation_id=conversation_id,
            blocks=rasa_response.get("blocks"),
            attachment_processed=bool(message_data.attachments),
            message_id=str(assistant_message.id)
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing message: {e}")
        
        # Store error message for debugging
        error_message = ChatMessage(
            conversation_id=conv_uuid,
            user_id=user.id,
            school_id=UUID(school_id),
            message_type=MessageType.ASSISTANT,
            content="I'm sorry, I'm having trouble processing your message right now. Please try again.",
            context_data=prepare_for_json_storage(chat_context if 'chat_context' in locals() else {}),
            response_data=prepare_for_json_storage({"error": str(e)}),
            processing_time_ms=int((time.time() - start_time) * 1000),
            created_at=message_timestamp
        )
        
        db.add(error_message)
        
        # Update conversation with explicit timestamp even on error
        conversation.last_activity = message_timestamp
        conversation.message_count += 2
        
        try:
            db.commit()
        except Exception as commit_error:
            logger.error(f"Failed to save error message: {commit_error}")
            db.rollback()
        
        return ChatResponse(
            response="I'm sorry, I'm having trouble processing your message right now. Please try again.",
            conversation_id=conversation_id,
            message_id=str(error_message.id) if 'error_message' in locals() else None
        )


@router.post("/conversations/{conversation_id}/messages/{message_id}/rate")
async def rate_message(
    conversation_id: str,
    message_id: str,
    rating: dict,  # {"rating": 1} for thumbs up, {"rating": -1} for thumbs down
    ctx: Dict[str, Any] = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Rate an assistant message (thumbs up/down feedback)"""
    user = ctx["user"]
    school_id = ctx["school_id"]
    
    try:
        conv_uuid = UUID(conversation_id)
        msg_uuid = UUID(message_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid ID format"
        )
    
    # Verify conversation belongs to user
    conversation = db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_uuid,
            ChatConversation.user_id == user.id,
            ChatConversation.school_id == UUID(school_id)
        )
    ).scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Get the message
    message = db.execute(
        select(ChatMessage).where(
            ChatMessage.id == msg_uuid,
            ChatMessage.conversation_id == conv_uuid,
            ChatMessage.message_type == MessageType.ASSISTANT
        )
    ).scalar_one_or_none()
    
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )
    
    # Validate rating value
    rating_value = rating.get("rating")
    if rating_value not in [1, -1, None]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rating must be 1 (thumbs up), -1 (thumbs down), or null to remove rating"
        )
    
    # Update message rating
    message.rating = rating_value
    # FIXED: Use explicit timestamp for rated_at
    message.rated_at = datetime.now(timezone.utc) if rating_value is not None else None
    
    try:
        db.commit()
        logger.info(f"Message rated: {message_id} with {rating_value} by {user.email}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error rating message: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error saving rating"
        )
    
    return {"message": "Rating saved successfully"}

@router.put("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    update_data: UpdateConversation,
    ctx: Dict[str, Any] = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Update conversation (title, archive status)"""
    user = ctx["user"]
    school_id = ctx["school_id"]
    
    try:
        conv_uuid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format"
        )
    
    conversation = db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_uuid,
            ChatConversation.user_id == user.id,
            ChatConversation.school_id == UUID(school_id)
        )
    ).scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Update fields if provided
    if update_data.title is not None:
        conversation.title = update_data.title
    
    if update_data.is_archived is not None:
        conversation.is_archived = update_data.is_archived
    
    try:
        db.commit()
        logger.info(f"Conversation updated: {conversation_id} by {user.email}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating conversation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error updating conversation"
        )
    
    return {"message": "Conversation updated successfully"}

@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    ctx: Dict[str, Any] = Depends(require_school),
    db: Session = Depends(get_db)
):
    """Delete a conversation and all its messages"""
    user = ctx["user"]
    school_id = ctx["school_id"]
    
    try:
        conv_uuid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid conversation ID format"
        )
    
    conversation = db.execute(
        select(ChatConversation).where(
            ChatConversation.id == conv_uuid,
            ChatConversation.user_id == user.id,
            ChatConversation.school_id == UUID(school_id)
        )
    ).scalar_one_or_none()
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    try:
        db.delete(conversation)  # This will cascade delete messages
        db.commit()
        logger.info(f"Conversation deleted: {conversation_id} by {user.email}")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting conversation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error deleting conversation"
        )
    
    return {"message": "Conversation deleted successfully"}

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    ctx: Dict[str, Any] = Depends(require_school)
):
    """Upload a file for chat (placeholder for file upload service)"""
    user = ctx["user"]
    school_id = ctx["school_id"]
    
    # TODO: Implement file upload to Cloudinary
    # This is a placeholder implementation
    
    if file.size > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum size is 10MB."
        )
    
    # For now, return a mock response
    return {
        "attachment_id": "mock_attachment_id",
        "original_filename": file.filename,
        "content_type": file.content_type,
        "file_size": file.size,
        "cloudinary_url": "https://example.com/mock_url",
        "upload_timestamp": "2024-01-01T00:00:00Z"
    }

@router.get("/health")
async def chat_health():
    """Health check for chat service"""
    # TODO: Check Rasa connection
    return {
        "status": "healthy",
        "rasa_connected": False,  # Placeholder
        "timestamp": time.time()
    }