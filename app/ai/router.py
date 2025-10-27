# app/ai/router.py
"""
AI Chat Router
Handles chat messages and routes them to appropriate AI handlers
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
import logging
import os

from app.api.deps.tenancy import require_school
from app.ai.mistral_client import (
    get_mistral_client,
    process_student_query,
    MistralIntent
)
from app.ai.actions.student_actions import (
    StudentActionsHandler,
    StudentIntent,
    ActionResponse,
    format_response_for_chat
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["AI Assistant"])


# ============================================================================
# Request/Response Models
# ============================================================================

class ChatRequest(BaseModel):
    """Chat message request"""
    message: str = Field(..., min_length=1, max_length=2000, description="User message")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context")


class ChatResponse(BaseModel):
    """Chat message response"""
    success: bool
    message: str
    intent: Optional[str] = None
    action_result: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None


class ConversationMessage(BaseModel):
    """Single conversation message"""
    role: str = Field(..., description="Message role: user, assistant, or system")
    content: str = Field(..., description="Message content")
    timestamp: Optional[str] = None


class ConversationRequest(BaseModel):
    """Multi-turn conversation request"""
    message: str = Field(..., min_length=1, max_length=2000)
    history: Optional[List[ConversationMessage]] = Field(default_factory=list)


class HealthCheckResponse(BaseModel):
    """Health check response"""
    status: str
    mistral_available: bool
    model: str
    available_models: List[str]


# ============================================================================
# Core Chat Endpoint
# ============================================================================

@router.post("/chat", response_model=ChatResponse)
async def chat_with_assistant(
    request: ChatRequest,
    ctx: Dict[str, Any] = Depends(require_school),
):
    """
    Main AI chat endpoint - processes student management queries
    
    Workflow:
    1. Send message to Mistral for intent detection
    2. Extract structured intent and parameters
    3. Execute action via StudentActionsHandler
    4. Return formatted response
    """
    user = ctx["user"]
    school_id = ctx["school_id"]
    
    try:
        # Add user/school context to the request
        context = request.context or {}
        context.update({
            "user_email": user.email,
            "user_role": getattr(user, 'role', 'USER'),
            "school_id": school_id
        })
        
        logger.info(f"Processing chat message from {user.email}: {request.message}")
        
        # Step 1: Get structured intent from Mistral
        try:
            mistral_intent = await process_student_query(
                message=request.message,
                context=context
            )
            
            logger.info(f"Detected intent: {mistral_intent.intent} (confidence: {mistral_intent.confidence})")
            
        except Exception as e:
            logger.error(f"Mistral processing failed: {e}")
            return ChatResponse(
                success=False,
                message="Sorry, I couldn't understand your request. Could you rephrase it?",
                metadata={"error": str(e)}
            )
        
        # Step 2: Check if intent is unknown or confidence is too low
        if mistral_intent.intent == "unknown" or (
            mistral_intent.confidence and mistral_intent.confidence < 0.5
        ):
            return ChatResponse(
                success=True,
                message=f"I'm not sure I understood that correctly. {mistral_intent.thought or 'Could you be more specific?'}",
                intent="unknown",
                metadata={
                    "confidence": mistral_intent.confidence,
                    "thought": mistral_intent.thought
                }
            )
        
        # Step 3: Map Mistral intent to StudentIntent enum
        try:
            student_intent = StudentIntent(mistral_intent.intent)
        except ValueError:
            logger.warning(f"Unknown intent from Mistral: {mistral_intent.intent}")
            return ChatResponse(
                success=False,
                message=f"I detected the action '{mistral_intent.intent}' but I don't know how to perform it yet.",
                intent=mistral_intent.intent
            )
        
        # Step 4: Execute action via handler
        base_url = os.getenv("BACKEND_URL", "http://localhost:8000")
        auth_token = ctx.get("token", "")  # JWT token from auth
        
        handler = StudentActionsHandler(
            base_url=base_url,
            auth_token=auth_token,
            school_id=school_id
        )
        
        action_response = await handler.execute_action(
            intent=student_intent,
            parameters=mistral_intent.parameters
        )
        
        # Step 5: Format response for user
        formatted_message = format_response_for_chat(action_response)
        
        return ChatResponse(
            success=action_response.success,
            message=formatted_message,
            intent=mistral_intent.intent,
            action_result={
                "action": action_response.action,
                "data": action_response.data,
                "metadata": action_response.metadata
            } if action_response.success else None,
            metadata={
                "confidence": mistral_intent.confidence,
                "thought": mistral_intent.thought,
                "error": action_response.error if not action_response.success else None
            }
        )
    
    except Exception as e:
        logger.error(f"Unexpected error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred processing your request"
        )


# ============================================================================
# Conversational Chat (For General Queries)
# ============================================================================

@router.post("/chat/conversational")
async def conversational_chat(
    request: ConversationRequest,
    ctx: Dict[str, Any] = Depends(require_school),
):
    """
    General conversational endpoint (not action-based)
    Use this for general questions, help, explanations, etc.
    """
    user = ctx["user"]
    
    try:
        client = get_mistral_client()
        
        # Convert history to Mistral format
        history = [
            {"role": msg.role, "content": msg.content}
            for msg in request.history
        ]
        
        response_text = await client.query_conversational(
            message=request.message,
            conversation_history=history
        )
        
        return {
            "success": True,
            "message": response_text,
            "role": "assistant"
        }
    
    except Exception as e:
        logger.error(f"Conversational chat error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process conversational request"
        )


# ============================================================================
# Health Check & Status
# ============================================================================

@router.get("/health", response_model=HealthCheckResponse)
async def check_ai_health():
    """
    Check if AI services (Mistral/Ollama) are available
    """
    try:
        client = get_mistral_client()
        is_healthy = await client.health_check()
        available_models = await client.list_models() if is_healthy else []
        
        return HealthCheckResponse(
            status="healthy" if is_healthy else "unavailable",
            mistral_available=is_healthy,
            model=client.model,
            available_models=available_models
        )
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthCheckResponse(
            status="error",
            mistral_available=False,
            model="unknown",
            available_models=[]
        )


# ============================================================================
# Model Management
# ============================================================================

@router.get("/models")
async def list_available_models():
    """List all available Mistral models in Ollama"""
    try:
        client = get_mistral_client()
        models = await client.list_models()
        
        return {
            "success": True,
            "models": models,
            "current_model": client.model
        }
    
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve available models"
        )


# ============================================================================
# Intent Testing (Development/Debug)
# ============================================================================

@router.post("/test-intent")
async def test_intent_detection(
    request: ChatRequest,
    ctx: Dict[str, Any] = Depends(require_school),
):
    """
    Test intent detection without executing actions
    Useful for debugging and development
    """
    try:
        mistral_intent = await process_student_query(
            message=request.message,
            context=request.context
        )
        
        return {
            "success": True,
            "intent": mistral_intent.intent,
            "parameters": mistral_intent.parameters,
            "thought": mistral_intent.thought,
            "confidence": mistral_intent.confidence
        }
    
    except Exception as e:
        logger.error(f"Intent testing failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# Prompt Testing (Development)
# ============================================================================

@router.post("/test-prompt")
async def test_raw_prompt(
    request: ChatRequest,
):
    """
    Send raw prompt to Mistral and get response
    For debugging prompt engineering
    """
    try:
        client = get_mistral_client()
        response = await client.query_structured(
            message=request.message,
            context=request.context
        )
        
        return {
            "success": True,
            "text": response.text,
            "structured_output": response.structured_output.dict() if response.structured_output else None,
            "raw_response": response.raw_response
        }
    
    except Exception as e:
        logger.error(f"Prompt testing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


# ============================================================================
# Help & Documentation
# ============================================================================

@router.get("/help")
async def get_assistant_help():
    """
    Get information about what the AI assistant can do
    """
    return {
        "message": "I'm your school management assistant! Here's what I can help you with:",
        "capabilities": [
            {
                "category": "Student Management",
                "actions": [
                    "Create new students - 'Register a new student named John Doe'",
                    "List students - 'Show me all students' or 'List students in Grade 4'",
                    "Get student details - 'Tell me about student A102'",
                    "Update student info - 'Change John's class to Grade 5'",
                    "Delete students - 'Remove student A102'",
                    "Enroll students - 'Enroll Jane in Grade 6 for Term 1'",
                    "Find unassigned students - 'Who hasn't been assigned to a class?'",
                    "Search students - 'Find all students named Mary'"
                ]
            }
        ],
        "examples": [
            "Register a new student named Alice Johnson, admission A205, female, born 2011-06-15",
            "Show me all students in Grade 3",
            "Tell me about student A102",
            "Who hasn't been enrolled this term?",
            "Change student A205's class to Grade 4"
        ],
        "tips": [
            "Be specific with names, dates, and admission numbers",
            "Use dates in YYYY-MM-DD format",
            "Specify gender as MALE or FEMALE",
            "I can understand natural language - just ask!"
        ]
    }