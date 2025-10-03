# app/services/chat_service.py - Enhanced error logging
import aiohttp
import asyncio
import logging
from typing import Dict, Any, List, Optional
import json

from app.core.config import settings
from app.schemas.chat import FileAttachment

logger = logging.getLogger(__name__)

class ChatService:
    """Service for handling chat operations and Rasa integration"""
    
    def __init__(self):
        self.rasa_url = settings.RASA_URL
        self.rasa_token = settings.RASA_TOKEN
        self.timeout = aiohttp.ClientTimeout(total=30)
        logger.info(f"ChatService initialized with Rasa URL: {self.rasa_url}")
    
    async def send_to_rasa(
        self, 
        message: str, 
        sender_id: str, 
        context: Dict[str, Any] = None,
        attachments: List[FileAttachment] = None,
        auth_token: str = None
    ) -> Dict[str, Any]:
        """
        Send message to Rasa and get response with authentication context
        
        Args:
            message: User message text
            sender_id: Unique sender identifier  
            context: Additional context for Rasa (user_id, school_id, etc.)
            attachments: List of file attachments
            auth_token: JWT token to pass to Rasa for FastAPI calls
        
        Returns:
            Dictionary with Rasa response data
        """
        logger.info(f"Attempting to send message to Rasa at: {self.rasa_url}")
        logger.debug(f"Message: '{message}', Sender: {sender_id}")
        
        try:
            # Prepare payload for Rasa with auth token in metadata
            payload = {
                "sender": sender_id,
                "message": message,
                "metadata": {
                    "auth_token": auth_token,
                    "school_id": context.get("school_id") if context else None,
                    "user_id": context.get("user_id") if context else None,
                    "context": context or {},
                    "attachments": [attachment.dict() for attachment in attachments] if attachments else []
                }
            }
            
            # Add authorization header if token is configured
            headers = {"Content-Type": "application/json"}
            if self.rasa_token:
                headers["Authorization"] = f"Bearer {self.rasa_token}"
            
            webhook_url = f"{self.rasa_url}/webhooks/rest/webhook"
            logger.info(f"Posting to Rasa webhook: {webhook_url}")
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    webhook_url,
                    json=payload,
                    headers=headers
                ) as response:
                    
                    logger.info(f"Rasa response status: {response.status}")
                    
                    if response.status == 200:
                        rasa_responses = await response.json()
                        logger.info(f"Rasa returned {len(rasa_responses)} response(s)")
                        logger.debug(f"Rasa responses: {rasa_responses}")
                        return self._process_rasa_response(rasa_responses, context)
                    else:
                        error_text = await response.text()
                        logger.error(f"Rasa error {response.status}: {error_text}")
                        return self._create_error_response("Rasa service unavailable")
        
        except asyncio.TimeoutError:
            logger.error(f"Rasa request timeout after {self.timeout.total}s")
            return self._create_error_response("Request timeout")
        
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Cannot connect to Rasa service at {self.rasa_url}")
            logger.error(f"Connection error type: {type(e).__name__}")
            logger.error(f"Connection error details: {str(e)}")
            logger.error(f"Ensure Rasa is running at {self.rasa_url}")
            return self._create_error_response("Chat service unavailable")
        
        except aiohttp.ClientError as e:
            logger.error(f"Aiohttp client error: {type(e).__name__}: {str(e)}")
            return self._create_error_response("Chat service error")
        
        except Exception as e:
            logger.error(f"Unexpected error communicating with Rasa: {e}", exc_info=True)
            return self._create_error_response("Unexpected error occurred")
    
    def _process_rasa_response(
        self, 
        rasa_responses: List[Dict[str, Any]], 
        context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Process and format Rasa response
        
        Args:
            rasa_responses: List of response objects from Rasa
            context: Original request context
        
        Returns:
            Formatted response dictionary
        """
        if not rasa_responses:
            logger.warning("No responses received from Rasa")
            return self._create_error_response("No response from chat service")
        
        # Combine all text responses
        text_responses = []
        attachments = []
        buttons = []
        custom_data = {}
        blocks = []
        intent = None
        action_taken = None
        
        for response in rasa_responses:
            # Text response
            if "text" in response:
                text_responses.append(response["text"])
            
            # Image attachments
            if "image" in response:
                attachments.append({
                    "type": "image",
                    "payload": {"src": response["image"]}
                })
            
            # Buttons/Quick replies
            if "buttons" in response:
                buttons.extend(response["buttons"])
            
            # Custom payload (for blocks/structured data)
            if "custom" in response:
                custom_payload = response["custom"]
                
                # Handle blocks (dashboard components)
                if "blocks" in custom_payload:
                    blocks.extend(custom_payload["blocks"])
                
                # Handle other custom data
                if "data" in custom_payload:
                    custom_data.update(custom_payload["data"])
                
                # Extract intent and action info
                if "intent" in custom_payload:
                    intent = custom_payload["intent"]
                
                if "action_taken" in custom_payload:
                    action_taken = custom_payload["action_taken"]
        
        # Use double newline to join responses to preserve formatting
        response_text = "\n\n".join(text_responses) if text_responses else "I understand, but I'm not sure how to help with that right now."
        
        # Generate suggestions based on context
        suggestions = self._generate_suggestions(intent, context)
        
        return {
            "response": response_text,
            "intent": intent,
            "data": custom_data,
            "action_taken": action_taken,
            "suggestions": suggestions,
            "blocks": blocks if blocks else None,
            "attachments": attachments if attachments else None,
            "buttons": buttons if buttons else None
        }
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create standardized error response"""
        logger.info(f"Creating error response: {error_message}")
        return {
            "response": "I'm sorry, I'm having trouble processing your message right now. Please try again in a moment.",
            "intent": None,
            "data": {"error": error_message},
            "action_taken": None,
            "suggestions": [
                "Try asking your question differently",
                "Check if all required information is provided",
                "Contact support if the problem persists"
            ],
            "blocks": None
        }
    
    def _generate_suggestions(
        self, 
        intent: str = None, 
        context: Dict[str, Any] = None
    ) -> List[str]:
        """
        Generate contextual suggestions for the user
        
        Args:
            intent: Detected intent from Rasa
            context: Request context with user/school info
        
        Returns:
            List of suggestion strings
        """
        suggestions = []
        
        # Default suggestions based on intent
        intent_suggestions = {
            "greet": [
                "Create a new student",
                "Add a new class",
                "List all students",
                "Show all classes"
            ],
            "create_student": [
                "List all students",
                "Create another student",
                "Show classes available"
            ],
            "create_class": [
                "Add students to this class",
                "Create another class",
                "List all classes"
            ],
            "list_students": [
                "Create a new student",
                "Search for a specific student",
                "Show class details"
            ],
            "list_classes": [
                "Create a new class",
                "Add students to a class",
                "View student details"
            ]
        }
        
        if intent and intent in intent_suggestions:
            suggestions = intent_suggestions[intent][:3]
        else:
            # Default suggestions
            suggestions = [
                "Create a new student",
                "Add a new class", 
                "Show all students",
                "List classes"
            ]
        
        return suggestions
    
    async def check_rasa_health(self) -> Dict[str, Any]:
        """
        Check if Rasa service is healthy
        
        Returns:
            Health status dictionary
        """
        try:
            headers = {}
            if self.rasa_token:
                headers["Authorization"] = f"Bearer {self.rasa_token}"
            
            status_url = f"{self.rasa_url}/status"
            logger.info(f"Checking Rasa health at: {status_url}")
            
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(status_url, headers=headers) as response:
                    if response.status == 200:
                        status_data = await response.json()
                        logger.info(f"Rasa health check successful: {status_data}")
                        return {
                            "healthy": True,
                            "rasa_version": status_data.get("version", "unknown"),
                            "model_loaded": status_data.get("model_file") is not None
                        }
                    else:
                        logger.error(f"Rasa health check failed with status {response.status}")
                        return {"healthy": False, "error": f"HTTP {response.status}"}
        
        except Exception as e:
            logger.error(f"Rasa health check failed: {type(e).__name__}: {str(e)}", exc_info=True)
            return {"healthy": False, "error": str(e)}