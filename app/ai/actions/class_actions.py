# app/ai/actions/class_actions.py
"""
Class Actions Middleware
Handles AI intent detection and routing for class/stream management operations
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from uuid import UUID
import httpx
import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ============================================================================
# Intent Definitions
# ============================================================================

class ClassIntent(str, Enum):
    """Class management intents that the AI can detect"""
    CREATE_CLASS = "create_class"
    LIST_CLASSES = "list_classes"
    LIST_EMPTY_CLASSES = "list_empty_classes"  # NEW: Classes without students
    GET_CLASS = "get_class"
    GET_CLASS_DETAIL = "get_class_detail"
    UPDATE_CLASS = "update_class"
    DELETE_CLASS = "delete_class"
    ADD_STREAM = "add_stream"
    REMOVE_STREAM = "remove_stream"
    UNKNOWN = "unknown"


# ============================================================================
# Action Parameter Models
# ============================================================================

class CreateClassParams(BaseModel):
    """Parameters for creating a new class/stream"""
    level: str = Field(..., description="Class level (e.g., Grade 1, Grade 2)")
    stream: Optional[str] = Field(None, description="Stream name (e.g., Blue, Green)")
    academic_year: Optional[int] = Field(None, description="Academic year (e.g., 2025)")


class ListClassesParams(BaseModel):
    """Parameters for listing classes"""
    academic_year: Optional[int] = Field(None, description="Filter by academic year")
    page: int = Field(1, description="Page number")
    limit: int = Field(50, description="Results per page")


class GetClassParams(BaseModel):
    """Parameters for getting a specific class"""
    class_id: str = Field(..., description="Class UUID")


class UpdateClassParams(BaseModel):
    """Parameters for updating a class"""
    class_id: str = Field(..., description="Class UUID")
    level: Optional[str] = Field(None, description="New class level")
    stream: Optional[str] = Field(None, description="New stream name")
    academic_year: Optional[int] = Field(None, description="New academic year")


class StreamParams(BaseModel):
    """Parameters for stream operations"""
    class_id: str = Field(..., description="Class UUID")
    stream: str = Field(..., description="Stream name")


# ============================================================================
# Action Response Models
# ============================================================================

class ActionResponse(BaseModel):
    """Standardized response format for all actions"""
    success: bool
    action: str
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ============================================================================
# Class Actions Handler
# ============================================================================

class ClassActionsHandler:
    """
    Handles execution of class management actions
    Routes AI intents to appropriate backend endpoints
    """
    
    def __init__(self, base_url: str, auth_token: str, school_id: str):
        """
        Initialize the handler
        
        Args:
            base_url: Backend API base URL (e.g., "http://127.0.0.1:8000")
            auth_token: JWT authentication token
            school_id: Current school context UUID
        """
        self.base_url = base_url.rstrip('/')
        self.auth_token = auth_token
        self.school_id = school_id
        self.headers = {
            "Authorization": f"Bearer {auth_token}",
            "X-School-ID": school_id,
            "Content-Type": "application/json"
        }
    
    async def execute_action(
        self, 
        intent: ClassIntent, 
        parameters: Dict[str, Any]
    ) -> ActionResponse:
        """
        Execute an action based on detected intent
        
        Args:
            intent: The detected class management intent
            parameters: Extracted parameters from the AI
            
        Returns:
            ActionResponse with results
        """
        try:
            # Route to appropriate handler
            if intent == ClassIntent.CREATE_CLASS:
                return await self._create_class(CreateClassParams(**parameters))
            
            elif intent == ClassIntent.LIST_CLASSES:
                return await self._list_classes(ListClassesParams(**parameters))
            
            elif intent == ClassIntent.LIST_EMPTY_CLASSES:
                # Add filter for empty classes
                params = ListClassesParams(**parameters)
                return await self._list_empty_classes(params)
            
            elif intent in [ClassIntent.GET_CLASS, ClassIntent.GET_CLASS_DETAIL]:
                return await self._get_class(GetClassParams(**parameters))
            
            elif intent == ClassIntent.UPDATE_CLASS:
                return await self._update_class(UpdateClassParams(**parameters))
            
            elif intent == ClassIntent.DELETE_CLASS:
                return await self._delete_class(GetClassParams(**parameters))
            
            elif intent == ClassIntent.ADD_STREAM:
                return await self._add_stream(StreamParams(**parameters))
            
            elif intent == ClassIntent.REMOVE_STREAM:
                return await self._remove_stream(StreamParams(**parameters))
            
            else:
                return ActionResponse(
                    success=False,
                    action=intent.value,
                    message="Unknown or unsupported action",
                    error="UNKNOWN_INTENT"
                )
                
        except Exception as e:
            logger.error(f"Error executing action {intent.value}: {e}")
            return ActionResponse(
                success=False,
                action=intent.value,
                message=f"Failed to execute action: {str(e)}",
                error=str(e)
            )
    
    # ========================================================================
    # Private Action Handlers
    # ========================================================================
    
    async def _create_class(self, params: CreateClassParams) -> ActionResponse:
        """Create a new class/stream"""
        url = f"{self.base_url}/api/classes/level-stream"
        
        payload = params.dict(exclude_none=True)
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Format message based on response
                level = data.get('level', params.level)
                streams = data.get('streams', [])
                year = data.get('academic_year', params.academic_year or 'current year')
                
                if streams:
                    streams_text = ", ".join(streams)
                    message = f"Class {level} with stream(s) {streams_text} created successfully for {year}"
                else:
                    message = f"Class {level} created successfully for {year}"
                
                return ActionResponse(
                    success=True,
                    action="create_class",
                    message=message,
                    data=data
                )
                
            except httpx.HTTPStatusError as e:
                error_detail = e.response.json().get("detail", str(e))
                return ActionResponse(
                    success=False,
                    action="create_class",
                    message=f"Failed to create class: {error_detail}",
                    error=error_detail
                )
    
    async def _list_classes(self, params: ListClassesParams) -> ActionResponse:
        """List classes with optional filtering"""
        url = f"{self.base_url}/api/classes/"  # Added trailing slash
        
        query_params = {
            k: v for k, v in params.dict().items() 
            if v is not None
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    params=query_params,
                    headers=self.headers,
                    timeout=30.0,
                    follow_redirects=True  # Added this
                )
                response.raise_for_status()
                
                data = response.json()
                classes = data.get('classes', [])
                total = data.get('total', len(classes))
                
                # Format message
                if params.academic_year:
                    message = f"Found {total} classes for academic year {params.academic_year}"
                else:
                    message = f"Found {total} classes"
                
                return ActionResponse(
                    success=True,
                    action="list_classes",
                    message=message,
                    data=data,
                    metadata={
                        "count": len(classes),
                        "total": total,
                        "academic_year": params.academic_year
                    }
                )
                
            except httpx.HTTPStatusError as e:
                error_detail = e.response.json().get("detail", str(e))
                return ActionResponse(
                    success=False,
                    action="list_classes",
                    message=f"Failed to retrieve classes: {error_detail}",
                    error=error_detail
                )
            except Exception as e:
                logger.error(f"Unexpected error in list_classes: {e}")
                return ActionResponse(
                    success=False,
                    action="list_classes",
                    message=f"Failed to retrieve classes: {str(e)}",
                    error=str(e)
                )
    
    async def _list_empty_classes(self, params: ListClassesParams) -> ActionResponse:
        """List classes without any students enrolled"""
        url = f"{self.base_url}/api/classes/"
        
        query_params = {
            k: v for k, v in params.dict().items() 
            if v is not None
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    params=query_params,
                    headers=self.headers,
                    timeout=30.0,
                    follow_redirects=True
                )
                response.raise_for_status()
                
                data = response.json()
                all_classes = data.get('classes', [])
                
                # Filter to only classes with 0 students
                empty_classes = [c for c in all_classes if c.get('student_count', 0) == 0]
                
                total_empty = len(empty_classes)
                total_all = len(all_classes)
                
                # Format message
                if params.academic_year:
                    message = f"Found {total_empty} empty classes (out of {total_all} total) for academic year {params.academic_year}"
                else:
                    message = f"Found {total_empty} empty classes (out of {total_all} total)"
                
                return ActionResponse(
                    success=True,
                    action="list_empty_classes",
                    message=message,
                    data={"classes": empty_classes, "total": total_all},
                    metadata={
                        "empty_count": total_empty,
                        "total_count": total_all,
                        "academic_year": params.academic_year
                    }
                )
                
            except httpx.HTTPStatusError as e:
                error_detail = e.response.json().get("detail", str(e))
                return ActionResponse(
                    success=False,
                    action="list_empty_classes",
                    message=f"Failed to retrieve classes: {error_detail}",
                    error=error_detail
                )
            except Exception as e:
                logger.error(f"Unexpected error in list_empty_classes: {e}")
                return ActionResponse(
                    success=False,
                    action="list_empty_classes",
                    message=f"Failed to retrieve classes: {str(e)}",
                    error=str(e)
                )
    
    async def _get_class(self, params: GetClassParams) -> ActionResponse:
        """Get detailed information about a specific class - supports both UUID and class name"""
        
        # Try to parse as UUID first
        try:
            UUID(params.class_id)
            class_id = params.class_id
        except ValueError:
            # Not a UUID, search by name/level
            logger.info(f"Searching for class by name/level: '{params.class_id}'")
            
            try:
                search_response = await self._search_class_by_name(params.class_id)
                if not search_response or not search_response.get('classes'):
                    return ActionResponse(
                        success=False,
                        action="get_class_detail",
                        message=f"Class '{params.class_id}' not found",
                        error="CLASS_NOT_FOUND"
                    )
                
                classes = search_response['classes']
                
                if len(classes) > 1:
                    class_list = ", ".join([f"{c['level']}" + (f" ({', '.join(c.get('streams', []))})" if c.get('streams') else "") for c in classes])
                    return ActionResponse(
                        success=False,
                        action="get_class_detail",
                        message=f"Multiple classes found: {class_list}. Please be more specific.",
                        error="MULTIPLE_MATCHES",
                        data={"matches": classes}
                    )
                
                class_id = classes[0]['id']
                
            except Exception as e:
                return ActionResponse(
                    success=False,
                    action="get_class_detail",
                    message=f"Failed to find class: {str(e)}",
                    error=str(e)
                )
        
        url = f"{self.base_url}/api/classes/{class_id}/"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    url,
                    headers=self.headers,
                    timeout=30.0,
                    follow_redirects=True
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Format message with details
                level = data.get('level', 'Unknown')
                streams = data.get('streams', [])
                student_count = data.get('student_count', 0)
                year = data.get('academic_year', 'N/A')
                
                streams_text = f" ({', '.join(streams)})" if streams else ""
                
                message = f"Class {level}{streams_text} for {year} has {student_count} student(s) enrolled"
                
                return ActionResponse(
                    success=True,
                    action="get_class_detail",
                    message=message,
                    data=data
                )
                
            except httpx.HTTPStatusError as e:
                error_detail = e.response.json().get("detail", str(e))
                return ActionResponse(
                    success=False,
                    action="get_class_detail",
                    message=f"Failed to retrieve class details: {error_detail}",
                    error=error_detail
                )
    
    async def _update_class(self, params: UpdateClassParams) -> ActionResponse:
        """Update class information"""
        url = f"{self.base_url}/api/classes/{params.class_id}/"  # Added trailing slash
        
        # Extract only the fields to update
        update_data = params.dict(exclude={'class_id'}, exclude_none=True)
        
        if not update_data:
            return ActionResponse(
                success=False,
                action="update_class",
                message="No update data provided",
                error="NO_UPDATE_DATA"
            )
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    url,
                    json=update_data,
                    headers=self.headers,
                    timeout=30.0,
                    follow_redirects=True  # Added this
                )
                response.raise_for_status()
                
                data = response.json()
                
                level = data.get('level', 'Class')
                streams = data.get('streams', [])
                streams_text = f" ({', '.join(streams)})" if streams else ""
                
                message = f"Class updated successfully: {level}{streams_text}"
                
                return ActionResponse(
                    success=True,
                    action="update_class",
                    message=message,
                    data=data
                )
                
            except httpx.HTTPStatusError as e:
                error_detail = e.response.json().get("detail", str(e))
                return ActionResponse(
                    success=False,
                    action="update_class",
                    message=f"Failed to update class: {error_detail}",
                    error=error_detail
                )
    
    async def _delete_class(self, params: GetClassParams) -> ActionResponse:
        """Delete a class - supports both UUID and class name/level"""
        
        # Try to parse as UUID first
        try:
            UUID(params.class_id)
            class_id = params.class_id
        except ValueError:
            # Not a UUID, try to find class by name/level
            logger.info(f"Class ID '{params.class_id}' is not a UUID, searching by name/level...")
            
            # Search for the class by name or level
            try:
                search_response = await self._search_class_by_name(params.class_id)
                if not search_response or not search_response.get('classes'):
                    return ActionResponse(
                        success=False,
                        action="delete_class",
                        message=f"Class '{params.class_id}' not found. Please provide the exact class name or UUID.",
                        error="CLASS_NOT_FOUND"
                    )
                
                classes = search_response['classes']
                
                # If multiple matches, ask user to be more specific
                if len(classes) > 1:
                    class_list = ", ".join([f"{c['level']}" + (f" ({', '.join(c.get('streams', []))})" if c.get('streams') else "") for c in classes])
                    return ActionResponse(
                        success=False,
                        action="delete_class",
                        message=f"Multiple classes found matching '{params.class_id}': {class_list}. Please be more specific or use the class UUID.",
                        error="MULTIPLE_MATCHES",
                        data={"matches": classes}
                    )
                
                # Found exactly one match
                class_id = classes[0]['id']
                logger.info(f"Found class '{params.class_id}' with UUID: {class_id}")
                
            except Exception as e:
                logger.error(f"Error searching for class: {e}")
                return ActionResponse(
                    success=False,
                    action="delete_class",
                    message=f"Failed to find class '{params.class_id}': {str(e)}",
                    error=str(e)
                )
        
        url = f"{self.base_url}/api/classes/{class_id}/"
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.delete(
                    url,
                    headers=self.headers,
                    timeout=30.0,
                    follow_redirects=True
                )
                response.raise_for_status()
                
                return ActionResponse(
                    success=True,
                    action="delete_class",
                    message="Class deleted successfully",
                    data=response.json() if response.text else {}
                )
                
            except httpx.HTTPStatusError as e:
                error_detail = e.response.json().get("detail", str(e))
                return ActionResponse(
                    success=False,
                    action="delete_class",
                    message=f"Failed to delete class: {error_detail}",
                    error=error_detail
                )
    
    async def _search_class_by_name(self, name_or_level: str) -> dict:
        """Helper method to search for a class by name or level"""
        url = f"{self.base_url}/api/classes/"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                url,
                params={"search": name_or_level, "limit": 10},
                headers=self.headers,
                timeout=30.0,
                follow_redirects=True
            )
            response.raise_for_status()
            return response.json()
    
    async def _add_stream(self, params: StreamParams) -> ActionResponse:
        """Add a stream to an existing class"""
        url = f"{self.base_url}/api/classes/{params.class_id}/streams/"  # Added trailing slash
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    json={"name": params.stream},  # Changed from "stream" to "name"
                    headers=self.headers,
                    timeout=30.0,
                    follow_redirects=True  # Added this
                )
                response.raise_for_status()
                
                data = response.json()
                
                return ActionResponse(
                    success=True,
                    action="add_stream",
                    message=f"Stream '{params.stream}' added successfully",
                    data=data
                )
                
            except httpx.HTTPStatusError as e:
                error_detail = e.response.json().get("detail", str(e))
                return ActionResponse(
                    success=False,
                    action="add_stream",
                    message=f"Failed to add stream: {error_detail}",
                    error=error_detail
                )
    
    async def _remove_stream(self, params: StreamParams) -> ActionResponse:
        """Remove a stream from a class"""
        url = f"{self.base_url}/api/classes/{params.class_id}/streams/{params.stream}/"  # Added trailing slash
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.delete(
                    url,
                    headers=self.headers,
                    timeout=30.0,
                    follow_redirects=True  # Added this
                )
                response.raise_for_status()
                
                return ActionResponse(
                    success=True,
                    action="remove_stream",
                    message=f"Stream '{params.stream}' removed successfully",
                    data=response.json() if response.text else {}
                )
                
            except httpx.HTTPStatusError as e:
                error_detail = e.response.json().get("detail", str(e))
                return ActionResponse(
                    success=False,
                    action="remove_stream",
                    message=f"Failed to remove stream: {error_detail}",
                    error=error_detail
                )


# ============================================================================
# Helper Functions for Intent Detection
# ============================================================================

def detect_class_intent(user_message: str) -> ClassIntent:
    """
    Detect class management intent from user message
    Fallback keyword-based detector for when Mistral is unavailable
    """
    message_lower = user_message.lower()
    
    # Create class patterns
    if any(word in message_lower for word in ['create class', 'add class', 'new class', 'make class']):
        return ClassIntent.CREATE_CLASS
    
    # List classes patterns
    elif any(word in message_lower for word in ['list classes', 'show classes', 'all classes', 'get classes']):
        return ClassIntent.LIST_CLASSES
    
    # Get class details patterns
    elif any(phrase in message_lower for phrase in ['class details', 'show class', 'about class', 'class info']):
        return ClassIntent.GET_CLASS_DETAIL
    
    # Update class patterns
    elif any(word in message_lower for word in ['update class', 'change class', 'modify class', 'rename class', 'edit class']):
        return ClassIntent.UPDATE_CLASS
    
    # Delete class patterns
    elif any(word in message_lower for word in ['delete class', 'remove class', 'drop class']):
        return ClassIntent.DELETE_CLASS
    
    # Stream operations
    elif 'add stream' in message_lower or 'create stream' in message_lower:
        return ClassIntent.ADD_STREAM
    
    elif 'remove stream' in message_lower or 'delete stream' in message_lower:
        return ClassIntent.REMOVE_STREAM
    
    return ClassIntent.UNKNOWN


def format_response_for_chat(response: ActionResponse) -> str:
    """
    Format action response for display in chat
    Converts structured response into natural language
    """
    if not response.success:
        return f"❌ {response.message}"
    
    # Success response with context
    message = f"✅ {response.message}"
    
    # Add relevant data snippets
    if response.data:
        if response.action in ["list_classes", "list_empty_classes"] and response.data.get('classes'):
            classes = response.data['classes'][:10]  # Show first 10
            message += "\n\n🏫 **Classes:**\n"
            
            if response.action == "list_empty_classes" and not classes:
                message += "No empty classes found. All classes have students enrolled."
            else:
                for cls in classes:
                    level = cls.get('level', 'Unknown')
                    streams = cls.get('streams', [])
                    student_count = cls.get('student_count', 0)
                    
                    streams_text = f" - {', '.join(streams)}" if streams else ""
                    message += f"• {level}{streams_text} ({student_count} students)\n"
                
                if response.metadata:
                    if response.action == "list_empty_classes":
                        empty_count = response.metadata.get('empty_count', 0)
                        total_count = response.metadata.get('total_count', 0)
                        shown = len(classes)
                        if empty_count > shown:
                            message += f"\n...and {empty_count - shown} more empty classes"
                    else:
                        total = response.metadata.get('total', 0)
                        shown = len(classes)
                        if total > shown:
                            message += f"\n...and {total - shown} more classes"
        
        elif response.action == "get_class_detail":
            cls = response.data
            message += f"\n\n📘 **Class Details:**\n"
            message += f"Level: {cls.get('level', 'N/A')}\n"
            
            streams = cls.get('streams', [])
            if streams:
                message += f"Streams: {', '.join(streams)}\n"
            
            message += f"Academic Year: {cls.get('academic_year', 'N/A')}\n"
            message += f"Students Enrolled: {cls.get('student_count', 0)}\n"
            
            # Show some students if available
            students = cls.get('students', [])[:5]
            if students:
                message += f"\n**Sample Students:**\n"
                for student in students:
                    message += f"• {student.get('full_name', 'Unknown')}\n"
    
    return message