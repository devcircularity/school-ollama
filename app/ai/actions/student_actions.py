# app/ai/actions/student_actions.py
"""
Student Actions Handler - Enhanced with conversational error handling
Handles AI intents related to student management
"""

import logging
import httpx
from typing import Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, ValidationError
from datetime import date

logger = logging.getLogger(__name__)


# ============================================================================
# Student Intent Enum
# ============================================================================

class StudentIntent(str, Enum):
    """Available student management intents"""
    CREATE_STUDENT = "create_student"
    LIST_STUDENTS = "list_students"
    GET_STUDENT = "get_student"
    UPDATE_STUDENT = "update_student"
    DELETE_STUDENT = "delete_student"
    # REMOVE: ENROLL_STUDENT = "enroll_student"  # This should be in EnrollmentIntent only
    GET_UNASSIGNED_STUDENTS = "get_unassigned_students"
    SEARCH_STUDENTS = "search_students"


# ============================================================================
# Parameter Models
# ============================================================================

class CreateStudentParams(BaseModel):
    """Parameters for creating a student"""
    admission_no: str
    first_name: str
    last_name: str
    gender: str  # MALE or FEMALE
    dob: str  # YYYY-MM-DD
    class_id: Optional[str] = None


# ============================================================================
# Response Models
# ============================================================================

class ActionResponse(BaseModel):
    """Standard response from student actions"""
    success: bool
    action: str
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    missing_params: Optional[list] = None  # NEW: Track missing parameters


# ============================================================================
# Student Actions Handler
# ============================================================================

class StudentActionsHandler:
    """
    Handles execution of student-related actions
    Communicates with backend API endpoints
    """
    
    def __init__(self, base_url: str, auth_token: str, school_id: str):
        """
        Initialize handler
        
        Args:
            base_url: Backend API base URL
            auth_token: JWT authentication token
            school_id: School context UUID
        """
        self.base_url = base_url.rstrip('/')
        self.auth_token = auth_token
        self.school_id = school_id
        self.headers = {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
            "X-School-ID": school_id
        }
    
    async def execute_action(
        self,
        intent: StudentIntent,
        parameters: Dict[str, Any]
    ) -> ActionResponse:
        """
        Execute a student management action
        
        Args:
            intent: The student intent to execute
            parameters: Action parameters from Mistral
            
        Returns:
            ActionResponse with results
        """
        logger.info(f"Executing student action: {intent.value} with params: {parameters}")
        
        try:
            # Route to appropriate handler method
            if intent == StudentIntent.CREATE_STUDENT:
                return await self._create_student(parameters)
            
            elif intent == StudentIntent.LIST_STUDENTS:
                return await self._list_students(parameters)
            
            elif intent == StudentIntent.GET_STUDENT:
                return await self._get_student(parameters)
            
            elif intent == StudentIntent.UPDATE_STUDENT:
                return await self._update_student(parameters)
            
            elif intent == StudentIntent.DELETE_STUDENT:
                return await self._delete_student(parameters)
            
            # REMOVED: ENROLL_STUDENT handler - this is now in EnrollmentActionsHandler
            
            elif intent == StudentIntent.GET_UNASSIGNED_STUDENTS:
                return await self._get_unassigned_students(parameters)
            
            elif intent == StudentIntent.SEARCH_STUDENTS:
                return await self._search_students(parameters)
            
            else:
                return ActionResponse(
                    success=False,
                    action=intent.value,
                    message=f"Unknown student action: {intent.value}",
                    error="Intent not implemented"
                )
        
        except Exception as e:
            logger.error(f"Error executing student action {intent.value}: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action=intent.value,
                message="Failed to execute action",
                error=str(e)
            )
    
    # ========================================================================
    # Action Implementations
    # ========================================================================
    
    async def _create_student(self, params: Dict[str, Any]) -> ActionResponse:
        """Create a new student with conversational error handling"""
        try:
            # Validate parameters with better error messages
            try:
                student_params = CreateStudentParams(**params)
            except ValidationError as e:
                # Extract missing fields
                missing_fields = []
                for error in e.errors():
                    if error['type'] == 'missing':
                        field_name = error['loc'][0]
                        missing_fields.append(field_name)
                
                # Create friendly error message
                if missing_fields:
                    friendly_names = {
                        'admission_no': 'admission number',
                        'first_name': 'first name',
                        'last_name': 'last name',
                        'gender': 'gender (MALE or FEMALE)',
                        'dob': 'date of birth (YYYY-MM-DD format)'
                    }
                    
                    missing_friendly = [friendly_names.get(f, f) for f in missing_fields]
                    
                    return ActionResponse(
                        success=False,
                        action="create_student",
                        message=f"I need some more information to create this student. Please provide: {', '.join(missing_friendly)}",
                        missing_params=missing_fields,
                        metadata={
                            "provided": list(params.keys()),
                            "example": "Try: 'Add student John Doe, admission A123, male, born 2010-05-15'"
                        }
                    )
                
                # Other validation errors
                return ActionResponse(
                    success=False,
                    action="create_student",
                    message=f"There's an issue with the student information provided: {str(e)}",
                    error=str(e)
                )
            
            # Prepare request data
            request_data = {
                "admission_no": student_params.admission_no,
                "first_name": student_params.first_name,
                "last_name": student_params.last_name,
                "gender": student_params.gender.upper(),
                "dob": student_params.dob
            }
            
            if student_params.class_id:
                request_data["class_id"] = student_params.class_id
            
            # Call backend API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/students/",
                    headers=self.headers,
                    json=request_data,
                    timeout=30.0
                )
                
                if response.status_code == 201:
                    student_data = response.json()
                    return ActionResponse(
                        success=True,
                        action="create_student",
                        message="Student created successfully",
                        data=student_data
                    )
                else:
                    error_detail = response.json().get("detail", "Unknown error")
                    return ActionResponse(
                        success=False,
                        action="create_student",
                        message=f"Failed to create student: {error_detail}",
                        error=error_detail
                    )
        
        except Exception as e:
            logger.error(f"Error creating student: {e}")
            return ActionResponse(
                success=False,
                action="create_student",
                message="An error occurred while creating the student",
                error=str(e)
            )
    
    async def _list_students(self, params: Dict[str, Any]) -> ActionResponse:
        """List all students"""
        try:
            # Build query parameters
            query_params = {}
            
            if "page" in params:
                query_params["page"] = params["page"]
            if "limit" in params:
                query_params["limit"] = params["limit"]
            if "search" in params:
                query_params["search"] = params["search"]
            if "class_id" in params:
                query_params["class_id"] = params["class_id"]
            if "status" in params:
                query_params["status"] = params["status"]
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/students/",
                    headers=self.headers,
                    params=query_params,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return ActionResponse(
                        success=True,
                        action="list_students",
                        message="Students retrieved successfully",
                        data=data
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="list_students",
                        message="Failed to retrieve students",
                        error=f"Status {response.status_code}"
                    )
        
        except Exception as e:
            logger.error(f"Error listing students: {e}")
            return ActionResponse(
                success=False,
                action="list_students",
                message="Error retrieving students",
                error=str(e)
            )
    
    async def _get_student(self, params: Dict[str, Any]) -> ActionResponse:
        """Get student by ID or admission number"""
        try:
            student_id = params.get("student_id")
            if not student_id:
                return ActionResponse(
                    success=False,
                    action="get_student",
                    message="Student ID is required",
                    error="Missing student_id parameter"
                )
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/students/{student_id}",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    student_data = response.json()
                    return ActionResponse(
                        success=True,
                        action="get_student",
                        message="Student details retrieved",
                        data=student_data
                    )
                elif response.status_code == 404:
                    return ActionResponse(
                        success=False,
                        action="get_student",
                        message=f"Student '{student_id}' not found",
                        error="Student not found"
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="get_student",
                        message="Failed to retrieve student",
                        error=f"Status {response.status_code}"
                    )
        
        except Exception as e:
            logger.error(f"Error getting student: {e}")
            return ActionResponse(
                success=False,
                action="get_student",
                message="Error retrieving student",
                error=str(e)
            )
    
    async def _update_student(self, params: Dict[str, Any]) -> ActionResponse:
        """Update student information"""
        try:
            student_id = params.get("student_id")
            if not student_id:
                return ActionResponse(
                    success=False,
                    action="update_student",
                    message="Student ID is required",
                    error="Missing student_id parameter"
                )
            
            # Extract update fields
            update_data = {}
            updatable_fields = ["first_name", "last_name", "gender", "dob", "class_id", "admission_no"]
            
            for field in updatable_fields:
                if field in params and field != "student_id":
                    update_data[field] = params[field]
            
            if not update_data:
                return ActionResponse(
                    success=False,
                    action="update_student",
                    message="No fields to update",
                    error="No update parameters provided"
                )
            
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.base_url}/api/students/{student_id}",
                    headers=self.headers,
                    json=update_data,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    student_data = response.json()
                    return ActionResponse(
                        success=True,
                        action="update_student",
                        message="Student updated successfully",
                        data=student_data,
                        metadata={"updated_fields": list(update_data.keys())}
                    )
                elif response.status_code == 404:
                    return ActionResponse(
                        success=False,
                        action="update_student",
                        message=f"Student '{student_id}' not found",
                        error="Student not found"
                    )
                else:
                    error_detail = response.json().get("detail", "Unknown error")
                    return ActionResponse(
                        success=False,
                        action="update_student",
                        message=f"Failed to update student: {error_detail}",
                        error=error_detail
                    )
        
        except Exception as e:
            logger.error(f"Error updating student: {e}")
            return ActionResponse(
                success=False,
                action="update_student",
                message="Error updating student",
                error=str(e)
            )
    
    async def _delete_student(self, params: Dict[str, Any]) -> ActionResponse:
        """Delete a student"""
        try:
            student_id = params.get("student_id")
            if not student_id:
                return ActionResponse(
                    success=False,
                    action="delete_student",
                    message="Student ID is required",
                    error="Missing student_id parameter"
                )
            
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.base_url}/api/students/{student_id}",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 204:
                    return ActionResponse(
                        success=True,
                        action="delete_student",
                        message="Student deleted successfully",
                        data={"student_id": student_id}
                    )
                elif response.status_code == 404:
                    return ActionResponse(
                        success=False,
                        action="delete_student",
                        message=f"Student '{student_id}' not found",
                        error="Student not found"
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="delete_student",
                        message="Failed to delete student",
                        error=f"Status {response.status_code}"
                    )
        
        except Exception as e:
            logger.error(f"Error deleting student: {e}")
            return ActionResponse(
                success=False,
                action="delete_student",
                message="Error deleting student",
                error=str(e)
            )
    
    # FIXED: get_unassigned_students now properly filters
    async def _get_unassigned_students(self, params: Dict[str, Any]) -> ActionResponse:
        """Get students who are not assigned to any class"""
        try:
            # Query for students without class assignment
            query_params = {
                "unassigned": "true",  # Add filter for unassigned students
                "page": params.get("page", 1),
                "limit": params.get("limit", 100)
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/students/",
                    headers=self.headers,
                    params=query_params,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return ActionResponse(
                        success=True,
                        action="get_unassigned_students",
                        message="Unassigned students retrieved",
                        data=data
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="get_unassigned_students",
                        message="Failed to retrieve unassigned students",
                        error=f"Status {response.status_code}"
                    )
        
        except Exception as e:
            logger.error(f"Error getting unassigned students: {e}")
            return ActionResponse(
                success=False,
                action="get_unassigned_students",
                message="Error retrieving unassigned students",
                error=str(e)
            )
    
    async def _search_students(self, params: Dict[str, Any]) -> ActionResponse:
        """Search for students"""
        try:
            search_params = {}
            
            if "first_name" in params:
                search_params["first_name"] = params["first_name"]
            if "last_name" in params:
                search_params["last_name"] = params["last_name"]
            if "admission_no" in params:
                search_params["admission_no"] = params["admission_no"]
            if "class_id" in params:
                search_params["class_id"] = params["class_id"]
            if "search" in params:
                search_params["search"] = params["search"]
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/students/",
                    headers=self.headers,
                    params=search_params,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return ActionResponse(
                        success=True,
                        action="search_students",
                        message="Search completed successfully",
                        data=data,
                        metadata={"search_params": search_params}
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="search_students",
                        message="Failed to search students",
                        error=f"Status {response.status_code}"
                    )
        
        except Exception as e:
            logger.error(f"Error searching students: {e}")
            return ActionResponse(
                success=False,
                action="search_students",
                message="Error searching students",
                error=str(e)
            )


# ============================================================================
# Keyword Detection (Fallback)
# ============================================================================

def detect_student_intent(message: str) -> Optional[str]:
    """
    Fallback keyword-based detection for student intents
    Used when Mistral is unavailable
    """
    message_lower = message.lower()
    
    # Create student patterns
    if any(phrase in message_lower for phrase in [
        "add student", "create student", "register student", "new student", "enroll student"
    ]):
        return "create_student"
    
    # List students patterns
    if any(phrase in message_lower for phrase in [
        "list students", "show students", "all students", "view students", "get students"
    ]):
        return "list_students"
    
    # Get student patterns
    if any(phrase in message_lower for phrase in [
        "student details", "about student", "show student", "get student", "find student"
    ]):
        return "get_student"
    
    # Update student patterns
    if any(phrase in message_lower for phrase in [
        "update student", "change student", "modify student", "edit student"
    ]):
        return "update_student"
    
    # Delete student patterns
    if any(phrase in message_lower for phrase in [
        "delete student", "remove student", "drop student"
    ]):
        return "delete_student"
    
    # Unassigned students patterns
    if any(phrase in message_lower for phrase in [
        "unassigned students", "students without class", "not enrolled"
    ]):
        return "get_unassigned_students"
    
    # Search students patterns
    if any(phrase in message_lower for phrase in [
        "search student", "find student", "look for student"
    ]):
        return "search_students"
    
    return None


# ============================================================================
# Response Formatting
# ============================================================================

def format_response_for_chat(response: ActionResponse) -> str:
    """
    Format action response for chat display with better missing param handling
    
    Args:
        response: Action response to format
        
    Returns:
        Human-readable message
    """
    if not response.success:
        # Handle missing parameters conversationally
        if response.missing_params:
            return f"💬 {response.message}"
        
        # Handle other errors
        return f"❌ {response.message}"
    
    action = response.action
    data = response.data or {}
    
    # Format based on action type
    if action == "create_student":
        student = data
        name = f"{student.get('first_name', '')} {student.get('last_name', '')}"
        admission = student.get('admission_no', 'N/A')
        
        return f"""✅ **Student Created Successfully**

**{name}**
- Admission No: {admission}
- Gender: {student.get('gender', 'N/A')}
- Date of Birth: {student.get('dob', 'N/A')}

The student has been added to the system."""
    
    elif action == "list_students":
        # FIXED: Check for both possible response structures
        students = data.get("students", data.get("items", []))
        total = data.get("total", len(students))
        
        logger.info(f"Formatting list_students: found {len(students)} students, total={total}")
        
        if not students or len(students) == 0:
            return "📚 No students found."
        
        # Format student list - Display ALL students without truncation
        students_list = "\n".join([
            f"• **{s.get('first_name', '')} {s.get('last_name', '')}** (Adm: {s.get('admission_no', 'N/A')})"
            for s in students
        ])
        
        return f"""📚 **Students List** (Total: {total})

{students_list}"""
    
    elif action == "get_student":
        student = data
        name = f"{student.get('first_name', '')} {student.get('last_name', '')}"
        admission = student.get('admission_no', 'N/A')
        gender = student.get('gender', 'N/A')
        dob = student.get('dob', 'N/A')
        status = student.get('status', 'N/A')
        
        return f"""👨‍🎓 **Student Details**

**{name}**
- Admission No: {admission}
- Gender: {gender}
- Date of Birth: {dob}
- Status: {status}"""
    
    elif action == "update_student":
        student = data
        name = f"{student.get('first_name', '')} {student.get('last_name', '')}"
        updated_fields = response.metadata.get("updated_fields", []) if response.metadata else []
        
        return f"""✅ **Student Updated Successfully**

**{name}** information has been updated.

**Updated fields:** {', '.join(updated_fields)}"""
    
    elif action == "delete_student":
        return "✅ **Student Deleted Successfully**\n\nThe student has been removed from the system."
    
    elif action == "get_unassigned_students":
        # FIXED: Same formatting fixes as list_students
        students = data.get("students", data.get("items", []))
        total = data.get("total", len(students))
        
        if not students or len(students) == 0:
            return "✅ Great! All students are assigned to classes."
        
        # Format student list - Display ALL students without truncation
        students_list = "\n".join([
            f"• **{s.get('first_name', '')} {s.get('last_name', '')}** (Adm: {s.get('admission_no', 'N/A')})"
            for s in students
        ])
        
        return f"""📋 **Unassigned Students** (Total: {total})

{students_list}

These students haven't been assigned to any class yet."""
    
    elif action == "search_students":
        # FIXED: Same formatting fixes
        students = data.get("students", data.get("items", []))
        total = data.get("total", len(students))
        
        if not students or len(students) == 0:
            return "🔍 No students found matching your search criteria."
        
        # Format student list - Display ALL students without truncation
        students_list = "\n".join([
            f"• **{s.get('first_name', '')} {s.get('last_name', '')}** (Adm: {s.get('admission_no', 'N/A')})"
            for s in students
        ])
        
        return f"""🔍 **Search Results** (Found: {total})

{students_list}"""
    
    else:
        return f"✅ {response.message}"