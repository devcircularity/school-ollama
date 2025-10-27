# app/ai/actions/enrollment_actions.py - Enhanced with fallback parameter extraction
"""
Enrollment Actions Handler - Enhanced with regex-based parameter extraction for fallback
"""

import logging
import httpx
import re
from typing import Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, ValidationError
from datetime import date

logger = logging.getLogger(__name__)


# ============================================================================
# Fallback Parameter Extraction (when Mistral is unavailable)
# ============================================================================

def extract_enrollment_params_from_text(message: str) -> Dict[str, Any]:
    """
    Extract enrollment parameters from natural language using regex
    Used when Mistral is unavailable
    
    Examples:
    - "enroll Wangechi Johnstone to class 1B7" → {student_name: "Wangechi Johnstone", class_name: "1B7"}
    - "assign John Doe to Grade 5" → {student_name: "John Doe", class_name: "Grade 5"}
    - "add student 083117 to class 1B7" → {student_id: "083117", class_name: "1B7"}
    """
    params = {}
    message_lower = message.lower()
    
    # Pattern 1: "enroll NAME to class CLASS_NAME"
    match = re.search(r'enroll\s+([a-zA-Z\s]+?)\s+(?:to|in|into)\s+class\s+([a-zA-Z0-9\s]+)', message, re.IGNORECASE)
    if match:
        params['student_name'] = match.group(1).strip()
        params['class_name'] = match.group(2).strip()
        logger.info(f"Extracted via Pattern 1: {params}")
        return params
    
    # Pattern 2: "assign NAME to CLASS_NAME"
    match = re.search(r'(?:assign|add|put)\s+([a-zA-Z\s]+?)\s+(?:to|in|into)\s+(?:class\s+)?([a-zA-Z0-9\s]+)', message, re.IGNORECASE)
    if match:
        params['student_name'] = match.group(1).strip()
        params['class_name'] = match.group(2).strip()
        logger.info(f"Extracted via Pattern 2: {params}")
        return params
    
    # Pattern 3: "enroll student ADM_NO to class CLASS_NAME"
    match = re.search(r'enroll\s+student\s+([A-Z0-9_]+)\s+(?:to|in|into)\s+class\s+([a-zA-Z0-9\s]+)', message, re.IGNORECASE)
    if match:
        params['student_id'] = match.group(1).strip()
        params['class_name'] = match.group(2).strip()
        logger.info(f"Extracted via Pattern 3: {params}")
        return params
    
    # Pattern 4: Try to extract just the name and class from anywhere
    # Look for common patterns with "to class"
    match = re.search(r'([a-zA-Z]+\s+[a-zA-Z]+)\s+to\s+class\s+([a-zA-Z0-9]+)', message, re.IGNORECASE)
    if match:
        params['student_name'] = match.group(1).strip()
        params['class_name'] = match.group(2).strip()
        logger.info(f"Extracted via Pattern 4: {params}")
        return params
    
    logger.warning(f"Could not extract enrollment parameters from: {message}")
    return params


# ============================================================================
# Enrollment Intent Enum
# ============================================================================

class EnrollmentIntent(str, Enum):
    """Available enrollment management intents"""
    ENROLL_STUDENT = "enroll_student"
    UNENROLL_STUDENT = "unenroll_student"
    GET_ENROLLMENT = "get_enrollment"
    LIST_ENROLLMENTS = "list_enrollments"
    BULK_ENROLL = "bulk_enroll"
    TRANSFER_STUDENT = "transfer_student"


# ============================================================================
# Response Models
# ============================================================================

class ActionResponse(BaseModel):
    """Standard response from enrollment actions"""
    success: bool
    action: str
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ============================================================================
# Enrollment Actions Handler
# ============================================================================

class EnrollmentActionsHandler:
    """Handles execution of enrollment-related actions"""
    
    def __init__(self, base_url: str, auth_token: str, school_id: str):
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
        intent: EnrollmentIntent,
        parameters: Dict[str, Any],
        original_message: Optional[str] = None  # NEW: Pass original message for fallback
    ) -> ActionResponse:
        """
        Execute an enrollment management action
        
        Args:
            intent: The enrollment intent to execute
            parameters: Action parameters (from Mistral or empty if fallback)
            original_message: Original user message (for fallback extraction)
        """
        logger.info(f"Executing enrollment action: {intent.value} with params: {parameters}")
        
        try:
            # If parameters are empty and we have original message, try to extract
            if not parameters and original_message and intent == EnrollmentIntent.ENROLL_STUDENT:
                logger.warning("Parameters empty, attempting fallback extraction from message")
                parameters = extract_enrollment_params_from_text(original_message)
            
            # Route to appropriate handler method
            if intent == EnrollmentIntent.ENROLL_STUDENT:
                return await self._enroll_student(parameters)
            
            elif intent == EnrollmentIntent.UNENROLL_STUDENT:
                return await self._unenroll_student(parameters)
            
            elif intent == EnrollmentIntent.GET_ENROLLMENT:
                return await self._get_enrollment(parameters)
            
            elif intent == EnrollmentIntent.LIST_ENROLLMENTS:
                return await self._list_enrollments(parameters)
            
            elif intent == EnrollmentIntent.BULK_ENROLL:
                return await self._bulk_enroll(parameters)
            
            elif intent == EnrollmentIntent.TRANSFER_STUDENT:
                return await self._transfer_student(parameters)
            
            else:
                return ActionResponse(
                    success=False,
                    action=intent.value,
                    message=f"Unknown enrollment action: {intent.value}",
                    error="Intent not implemented"
                )
        
        except Exception as e:
            logger.error(f"Error executing enrollment action {intent.value}: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action=intent.value,
                message="Failed to execute action",
                error=str(e)
            )
    
    async def _enroll_student(self, params: Dict[str, Any]) -> ActionResponse:
        """Enroll a student in a class"""
        
        # Check if we have either student_id/name and class_id/name
        has_student = params.get('student_id') or params.get('student_name')
        has_class = params.get('class_id') or params.get('class_name')
        
        if not has_student or not has_class:
            missing = []
            if not has_student:
                missing.append("student name or ID")
            if not has_class:
                missing.append("class name or ID")
            
            return ActionResponse(
                success=False,
                action="enroll_student",
                message=f"Missing required information: {', '.join(missing)}. Please specify which student and which class.",
                error="Missing parameters"
            )
        
        try:
            # Try to find student by name if only name is provided
            if params.get('student_name') and not params.get('student_id'):
                student_name = params['student_name']
                async with httpx.AsyncClient() as client:
                    search_response = await client.get(
                        f"{self.base_url}/api/students/",
                        headers=self.headers,
                        params={"search": student_name},
                        timeout=30.0
                    )
                    
                    if search_response.status_code == 200:
                        students = search_response.json()
                        if students and len(students) > 0:
                            # Use first match
                            params['student_id'] = students[0]['id']
                            logger.info(f"Found student: {students[0]['admission_no']} for name '{student_name}'")
                        else:
                            return ActionResponse(
                                success=False,
                                action="enroll_student",
                                message=f"Student '{student_name}' not found. Please check the name or use admission number.",
                                error="Student not found"
                            )
            
            # Try to find class by name if only name is provided
            if params.get('class_name') and not params.get('class_id'):
                class_name = params['class_name']
                async with httpx.AsyncClient() as client:
                    search_response = await client.get(
                        f"{self.base_url}/api/classes/",
                        headers=self.headers,
                        timeout=30.0
                    )
                    
                    if search_response.status_code == 200:
                        classes = search_response.json()
                        # Find exact or partial match
                        matching_class = next(
                            (c for c in classes if c['name'].lower() == class_name.lower()),
                            None
                        )
                        
                        if matching_class:
                            params['class_id'] = matching_class['id']
                            logger.info(f"Found class: {matching_class['name']} for name '{class_name}'")
                        else:
                            return ActionResponse(
                                success=False,
                                action="enroll_student",
                                message=f"Class '{class_name}' not found. Please check the class name.",
                                error="Class not found"
                            )
            
            # Get current term
            async with httpx.AsyncClient() as client:
                term_response = await client.get(
                    f"{self.base_url}/api/school/terms/current",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if term_response.status_code == 200:
                    current_term = term_response.json()
                    params['term_id'] = current_term['id']
                else:
                    return ActionResponse(
                        success=False,
                        action="enroll_student",
                        message="No active term found. Please set up an academic term first.",
                        error="No active term"
                    )
            
            # Create enrollment
            enrollment_data = {
                "student_id": params['student_id'],
                "class_id": params['class_id'],
                "term_id": params['term_id'],
                "enrolled_date": params.get('enrolled_date', str(date.today()))
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/enrollments/",
                    headers=self.headers,
                    json=enrollment_data,
                    timeout=30.0
                )
                
                if response.status_code == 201:
                    enrollment = response.json()
                    return ActionResponse(
                        success=True,
                        action="enroll_student",
                        message="Student enrolled successfully!",
                        data=enrollment
                    )
                elif response.status_code == 409:
                    return ActionResponse(
                        success=False,
                        action="enroll_student",
                        message="Student is already enrolled in a class for this term.",
                        error="Already enrolled"
                    )
                else:
                    error_detail = response.json().get('detail', 'Unknown error')
                    return ActionResponse(
                        success=False,
                        action="enroll_student",
                        message=f"Failed to enroll student: {error_detail}",
                        error=error_detail
                    )
        
        except Exception as e:
            logger.error(f"Error enrolling student: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="enroll_student",
                message="An error occurred while enrolling the student.",
                error=str(e)
            )
    


    async def _resolve_student_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        Resolve student by ID, admission number, or name
        WITH FUZZY MATCHING to handle typos and spelling variations
        
        Args:
            identifier: Student ID (UUID), admission number, or full name
            
        Returns:
            Student data or None
        """
        try:
            # Try direct ID lookup first
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/students/{identifier}",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    return response.json()
                
                # If not found by ID/admission number, try searching by name
                logger.info(f"Student not found by ID '{identifier}', trying name search")
                
                # Split potential full name
                name_parts = identifier.strip().split()
                
                if len(name_parts) >= 2:
                    # Try as "FirstName LastName"
                    search_response = await client.get(
                        f"{self.base_url}/api/students/",
                        headers=self.headers,
                        params={
                            "search": identifier,
                            "limit": 10
                        },
                        timeout=30.0
                    )
                    
                    if search_response.status_code == 200:
                        data = search_response.json()
                        students = data.get("students", [])
                        
                        if not students:
                            return None
                        
                        # IMPROVED: Use fuzzy matching to handle typos
                        from difflib import SequenceMatcher
                        
                        def similarity(a: str, b: str) -> float:
                            """Calculate similarity ratio between two strings (0-1)"""
                            return SequenceMatcher(None, a.lower(), b.lower()).ratio()
                        
                        # Score all students by name similarity
                        scored_students = []
                        identifier_lower = identifier.lower()
                        
                        for student in students:
                            full_name = f"{student.get('first_name', '')} {student.get('last_name', '')}".strip()
                            
                            # Calculate multiple similarity scores
                            full_name_score = similarity(full_name, identifier)
                            
                            # Also check individual name parts
                            first_name = student.get('first_name', '').lower()
                            last_name = student.get('last_name', '').lower()
                            
                            # Check if both name parts are in the identifier
                            parts_match_score = 0
                            if len(name_parts) >= 2:
                                first_match = similarity(first_name, name_parts[0].lower())
                                last_match = similarity(last_name, name_parts[-1].lower())
                                parts_match_score = (first_match + last_match) / 2
                            
                            # Use the best score
                            best_score = max(full_name_score, parts_match_score)
                            
                            scored_students.append({
                                'student': student,
                                'score': best_score,
                                'full_name': full_name
                            })
                        
                        # Sort by score descending
                        scored_students.sort(key=lambda x: x['score'], reverse=True)
                        
                        # Get best match
                        best_match = scored_students[0]
                        
                        # FUZZY MATCHING THRESHOLDS:
                        # 1.0 = Exact match
                        # 0.9+ = Very close (1 letter typo)
                        # 0.8+ = Close (2-3 letter typos)
                        # 0.7+ = Somewhat similar
                        # <0.7 = Too different
                        
                        if best_match['score'] >= 0.7:
                            # Check if there's a clear winner (significantly better than second)
                            if len(scored_students) > 1:
                                second_score = scored_students[1]['score']
                                if best_match['score'] - second_score >= 0.1:  # Clear winner
                                    logger.info(
                                        f"✓ Found student by fuzzy match (score: {best_match['score']:.2f}): "
                                        f"'{identifier}' → '{best_match['full_name']}'"
                                    )
                                    return best_match['student']
                            else:
                                # Only one match, and it's good enough
                                logger.info(
                                    f"✓ Found student by fuzzy match (score: {best_match['score']:.2f}): "
                                    f"'{identifier}' → '{best_match['full_name']}'"
                                )
                                return best_match['student']
                        
                        # If no clear match, return None
                        logger.warning(
                            f"No clear student match for '{identifier}'. "
                            f"Best match: '{best_match['full_name']}' (score: {best_match['score']:.2f})"
                        )
                        return None
                
                # Try single name (first name only)
                elif len(name_parts) == 1:
                    search_response = await client.get(
                        f"{self.base_url}/api/students/",
                        headers=self.headers,
                        params={
                            "search": identifier,
                            "limit": 10
                        },
                        timeout=30.0
                    )
                    
                    if search_response.status_code == 200:
                        data = search_response.json()
                        students = data.get("students", [])
                        
                        if len(students) == 1:
                            logger.info(f"✓ Found student by first name: {students[0].get('full_name')}")
                            return students[0]
                        elif len(students) > 1:
                            # Multiple matches - need clarification
                            names = [s.get('full_name', 'Unknown') for s in students[:5]]
                            logger.warning(f"Multiple students found with name '{identifier}': {names}")
                            return None  # Will trigger "multiple students found" error
                
                return None
                
        except Exception as e:
            logger.error(f"Error resolving student {identifier}: {e}")
            return None
    
    # In app/ai/actions/enrollment_actions.py

    async def _resolve_class_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        """
        Resolve class by ID, name, or level+stream combination
        
        Args:
            identifier: Class ID (UUID), class name, or "Level Stream" format (e.g. "2 Green")
            
        Returns:
            Class data or None
        """
        try:
            # Try direct ID lookup first
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/classes/{identifier}",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    return response.json()
                
                # If not found by ID, try searching by name/level+stream
                # Pattern 1: "2 Green" → level="2", stream="Green"
                # Pattern 2: "Grade 5 Blue" → level="Grade 5" or level="5", stream="Blue"
                
                parts = identifier.strip().split()
                
                if len(parts) >= 2:
                    # Try treating as level + stream
                    # Could be "2 Green", "Grade 5 Blue", "1 Red", etc.
                    
                    # Attempt 1: Last word is stream, rest is level
                    potential_stream = parts[-1]
                    potential_level = " ".join(parts[:-1])
                    
                    logger.info(f"Trying to resolve class as level='{potential_level}' + stream='{potential_stream}'")
                    
                    # Search for classes by level
                    search_response = await client.get(
                        f"{self.base_url}/api/classes/",
                        headers=self.headers,
                        params={"level": potential_level, "limit": 50},
                        timeout=30.0
                    )
                    
                    if search_response.status_code == 200:
                        data = search_response.json()
                        classes = data.get("classes", [])
                        
                        # Look for a class with matching level and stream
                        for cls in classes:
                            class_level = cls.get("level", "")
                            class_streams = cls.get("streams", [])
                            
                            # Check if level matches and stream exists
                            if class_level.lower() == potential_level.lower():
                                # Check if stream matches (case-insensitive)
                                for stream in class_streams:
                                    if stream.lower() == potential_stream.lower():
                                        logger.info(f"✓ Found class: {cls.get('name')} with stream {stream}")
                                        # Return the class with stream info
                                        return {
                                            **cls,
                                            "resolved_stream": stream
                                        }
                        
                        logger.warning(f"Found {len(classes)} classes with level '{potential_level}' but none have stream '{potential_stream}'")
                
                # If level+stream didn't work, try exact name search
                search_response = await client.get(
                    f"{self.base_url}/api/classes/",
                    headers=self.headers,
                    params={"search": identifier, "limit": 5},
                    timeout=30.0
                )
                
                if search_response.status_code == 200:
                    data = search_response.json()
                    classes = data.get("classes", [])
                    if classes:
                        # Return first match
                        logger.info(f"Found class by name search: {classes[0].get('name')}")
                        return classes[0]
                
                return None
                
        except Exception as e:
            logger.error(f"Error resolving class {identifier}: {e}")
            return None
    
    async def _get_current_term(self) -> Optional[str]:
        """Get current term ID"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/academic/terms/current",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    term_data = response.json()
                    return term_data.get("id")
                return None
        except Exception as e:
            logger.error(f"Error getting current term: {e}")
            return None
    
    # ========================================================================
    # Action Implementations
    # ========================================================================
    
    # app/ai/actions/enrollment_actions.py

    # app/ai/actions/enrollment_actions.py
# Fixed _enroll_student method with complete implementation

    
    
    async def _unenroll_student(self, params: Dict[str, Any]) -> ActionResponse:
        """Unenroll a student from a class"""
        try:
            student_id = params.get("student_id")
            term_id = params.get("term_id")
            
            if not student_id:
                return ActionResponse(
                    success=False,
                    action="unenroll_student",
                    message="Please specify which student to unenroll",
                    error="Missing student_id"
                )
            
            # Resolve student
            student = await self._resolve_student_identifier(student_id)
            if not student:
                return ActionResponse(
                    success=False,
                    action="unenroll_student",
                    message=f"Student '{student_id}' not found",
                    error="Student not found"
                )
            
            # Get current term if not specified
            if not term_id:
                term_id = await self._get_current_term()
            
            # TODO: Implement unenrollment endpoint on backend
            # For now, return a message
            return ActionResponse(
                success=False,
                action="unenroll_student",
                message="Unenrollment feature is not yet implemented. Please contact an administrator.",
                error="Not implemented"
            )
        
        except Exception as e:
            logger.error(f"Error unenrolling student: {e}")
            return ActionResponse(
                success=False,
                action="unenroll_student",
                message="An error occurred while unenrolling the student",
                error=str(e)
            )
    
    async def _get_enrollment(self, params: Dict[str, Any]) -> ActionResponse:
        """Get enrollment details for a student"""
        try:
            student_id = params.get("student_id")
            
            if not student_id:
                return ActionResponse(
                    success=False,
                    action="get_enrollment",
                    message="Please specify which student to check enrollment for",
                    error="Missing student_id"
                )
            
            # Resolve student
            student = await self._resolve_student_identifier(student_id)
            if not student:
                return ActionResponse(
                    success=False,
                    action="get_enrollment",
                    message=f"Student '{student_id}' not found",
                    error="Student not found"
                )
            
            # Get student details which includes enrollment info
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/students/{student['id']}",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    student_detail = response.json()
                    enrollment_info = student_detail.get("current_enrollment", {})
                    
                    student_name = f"{student.get('first_name', '')} {student.get('last_name', '')}".strip()
                    
                    return ActionResponse(
                        success=True,
                        action="get_enrollment",
                        message=f"Retrieved enrollment information for {student_name}",
                        data={
                            "student": student_detail,
                            "enrollment": enrollment_info
                        },
                        metadata={
                            "student_name": student_name,
                            "is_enrolled": enrollment_info.get("enrolled", False),
                            "class_name": enrollment_info.get("class_name"),
                            "term_title": enrollment_info.get("term_title")
                        }
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="get_enrollment",
                        message="Failed to retrieve enrollment information",
                        error=f"Status {response.status_code}"
                    )
        
        except Exception as e:
            logger.error(f"Error getting enrollment: {e}")
            return ActionResponse(
                success=False,
                action="get_enrollment",
                message="An error occurred while retrieving enrollment information",
                error=str(e)
            )
    
    async def _list_enrollments(self, params: Dict[str, Any]) -> ActionResponse:
        """List enrollments for a class or term"""
        try:
            class_id = params.get("class_id")
            term_id = params.get("term_id")
            page = params.get("page", 1)
            limit = params.get("limit", 20)
            
            if not class_id and not term_id:
                # Get current term
                term_id = await self._get_current_term()
                if not term_id:
                    return ActionResponse(
                        success=False,
                        action="list_enrollments",
                        message="Please specify a class or term to list enrollments",
                        error="Missing class_id or term_id"
                    )
            
            # Build query parameters
            query_params = {"page": page, "limit": limit}
            
            if class_id:
                # Resolve class
                class_obj = await self._resolve_class_identifier(class_id)
                if not class_obj:
                    return ActionResponse(
                        success=False,
                        action="list_enrollments",
                        message=f"Class '{class_id}' not found",
                        error="Class not found"
                    )
                query_params["class_id"] = class_obj["id"]
            
            if term_id:
                query_params["term_id"] = term_id
            
            # Get enrollments via students endpoint
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/students/",
                    headers=self.headers,
                    params=query_params,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    students = data.get("students", data.get("items", []))
                    total = data.get("total", len(students))
                    
                    return ActionResponse(
                        success=True,
                        action="list_enrollments",
                        message=f"Retrieved {len(students)} enrolled students",
                        data={
                            "students": students,
                            "total": total,
                            "page": page,
                            "limit": limit
                        },
                        metadata={
                            "class_id": class_id,
                            "term_id": term_id
                        }
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="list_enrollments",
                        message="Failed to retrieve enrollments",
                        error=f"Status {response.status_code}"
                    )
        
        except Exception as e:
            logger.error(f"Error listing enrollments: {e}")
            return ActionResponse(
                success=False,
                action="list_enrollments",
                message="An error occurred while listing enrollments",
                error=str(e)
            )
    
    async def _bulk_enroll(self, params: Dict[str, Any]) -> ActionResponse:
        """Enroll multiple students in a class"""
        try:
            student_ids = params.get("student_ids", [])
            class_id = params.get("class_id")
            term_id = params.get("term_id")
            
            if not student_ids:
                return ActionResponse(
                    success=False,
                    action="bulk_enroll",
                    message="Please provide a list of students to enroll",
                    error="Missing student_ids"
                )
            
            if not class_id:
                return ActionResponse(
                    success=False,
                    action="bulk_enroll",
                    message="Please specify which class to enroll students in",
                    error="Missing class_id"
                )
            
            # Resolve class
            class_obj = await self._resolve_class_identifier(class_id)
            if not class_obj:
                return ActionResponse(
                    success=False,
                    action="bulk_enroll",
                    message=f"Class '{class_id}' not found",
                    error="Class not found"
                )
            
            # Get current term if not specified
            if not term_id:
                term_id = await self._get_current_term()
                if not term_id:
                    return ActionResponse(
                        success=False,
                        action="bulk_enroll",
                        message="Could not determine current term",
                        error="No current term found"
                    )
            
            # Enroll each student
            results = {
                "successful": [],
                "failed": []
            }
            
            for student_id in student_ids:
                try:
                    student = await self._resolve_student_identifier(student_id)
                    if not student:
                        results["failed"].append({
                            "student_id": student_id,
                            "reason": "Student not found"
                        })
                        continue
                    
                    enrollment_data = {
                        "student_id": student["id"],
                        "class_id": class_obj["id"],
                        "term_id": term_id
                    }
                    
                    async with httpx.AsyncClient() as client:
                        response = await client.post(
                            f"{self.base_url}/api/enrollments/",
                            headers=self.headers,
                            json=enrollment_data,
                            timeout=30.0
                        )
                        
                        if response.status_code == 201:
                            results["successful"].append({
                                "student_id": student_id,
                                "student_name": f"{student.get('first_name', '')} {student.get('last_name', '')}".strip()
                            })
                        else:
                            error_detail = response.json().get("detail", "Unknown error")
                            results["failed"].append({
                                "student_id": student_id,
                                "reason": error_detail
                            })
                
                except Exception as e:
                    results["failed"].append({
                        "student_id": student_id,
                        "reason": str(e)
                    })
            
            success_count = len(results["successful"])
            failed_count = len(results["failed"])
            
            return ActionResponse(
                success=success_count > 0,
                action="bulk_enroll",
                message=f"Enrolled {success_count} students successfully. {failed_count} failed.",
                data=results,
                metadata={
                    "class_name": class_obj.get("name"),
                    "success_count": success_count,
                    "failed_count": failed_count
                }
            )
        
        except Exception as e:
            logger.error(f"Error in bulk enrollment: {e}")
            return ActionResponse(
                success=False,
                action="bulk_enroll",
                message="An error occurred during bulk enrollment",
                error=str(e)
            )
    
    async def _transfer_student(self, params: Dict[str, Any]) -> ActionResponse:
        """Transfer a student from one class to another"""
        try:
            student_id = params.get("student_id")
            new_class_id = params.get("new_class_id")
            term_id = params.get("term_id")
            
            if not student_id:
                return ActionResponse(
                    success=False,
                    action="transfer_student",
                    message="Please specify which student to transfer",
                    error="Missing student_id"
                )
            
            if not new_class_id:
                return ActionResponse(
                    success=False,
                    action="transfer_student",
                    message="Please specify the new class",
                    error="Missing new_class_id"
                )
            
            # Resolve student
            student = await self._resolve_student_identifier(student_id)
            if not student:
                return ActionResponse(
                    success=False,
                    action="transfer_student",
                    message=f"Student '{student_id}' not found",
                    error="Student not found"
                )
            
            # Resolve new class
            new_class = await self._resolve_class_identifier(new_class_id)
            if not new_class:
                return ActionResponse(
                    success=False,
                    action="transfer_student",
                    message=f"Class '{new_class_id}' not found",
                    error="Class not found"
                )
            
            # Get current term if not specified
            if not term_id:
                term_id = await self._get_current_term()
            
            # Update student's class
            async with httpx.AsyncClient() as client:
                update_response = await client.put(
                    f"{self.base_url}/api/students/{student['id']}",
                    headers=self.headers,
                    json={"class_id": new_class["id"]},
                    timeout=30.0
                )
                
                if update_response.status_code == 200:
                    student_name = f"{student.get('first_name', '')} {student.get('last_name', '')}".strip()
                    old_class_name = student.get("class_name", "previous class")
                    new_class_name = new_class.get("name", "new class")
                    
                    return ActionResponse(
                        success=True,
                        action="transfer_student",
                        message=f"Successfully transferred {student_name} from {old_class_name} to {new_class_name}",
                        data={
                            "student": student,
                            "old_class": student.get("class_name"),
                            "new_class": new_class
                        },
                        metadata={
                            "student_name": student_name,
                            "old_class_name": old_class_name,
                            "new_class_name": new_class_name
                        }
                    )
                else:
                    error_detail = update_response.json().get("detail", "Unknown error")
                    return ActionResponse(
                        success=False,
                        action="transfer_student",
                        message=f"Failed to transfer student: {error_detail}",
                        error=error_detail
                    )
        
        except Exception as e:
            logger.error(f"Error transferring student: {e}")
            return ActionResponse(
                success=False,
                action="transfer_student",
                message="An error occurred while transferring the student",
                error=str(e)
            )


# ============================================================================
# Keyword Detection (Fallback)
# ============================================================================

def detect_enrollment_intent(message: str) -> Optional[str]:
    """
    Fallback keyword-based detection for enrollment intents
    Used when Mistral is unavailable
    """
    message_lower = message.lower()
    
    # Enroll student patterns
    if any(phrase in message_lower for phrase in [
        "enroll student", "enrol student", "enroll", "assign student to class",
        "add student to class", "put student in class", "register student in"
    ]):
        return "enroll_student"
    
    # Unenroll patterns
    if any(phrase in message_lower for phrase in [
        "unenroll", "unenrol", "remove from class", "drop student"
    ]):
        return "unenroll_student"
    
    # Transfer patterns
    if any(phrase in message_lower for phrase in [
        "transfer student", "move student to", "change student class",
        "switch student to"
    ]):
        return "transfer_student"
    
    # Get enrollment patterns
    if any(phrase in message_lower for phrase in [
        "enrollment status", "is student enrolled", "check enrollment"
    ]):
        return "get_enrollment"
    
    # List enrollments patterns
    if any(phrase in message_lower for phrase in [
        "list enrollments", "show enrolled students", "students in class",
        "who is enrolled"
    ]):
        return "list_enrollments"
    
    return None


# ============================================================================
# Response Formatting
# ============================================================================

def format_response_for_chat(response: ActionResponse) -> str:
    """
    Format action response for chat display
    
    Args:
        response: Action response to format
        
    Returns:
        Human-readable message
    """
    if not response.success:
        return f"❌ {response.message}"
    
    action = response.action
    data = response.data or {}
    metadata = response.metadata or {}
    
    # Format based on action type
    if action == "enroll_student":
        student_name = metadata.get("student_name", "Student")
        class_name = metadata.get("class_name", "the class")
        admission_no = metadata.get("admission_no", "")
        
        return f"""✅ **Enrollment Successful!**

**{student_name}** (Adm: {admission_no}) has been enrolled in **{class_name}**.

The student can now attend classes and will appear on the class roster."""
    
    elif action == "get_enrollment":
        student_name = metadata.get("student_name", "Student")
        is_enrolled = metadata.get("is_enrolled", False)
        class_name = metadata.get("class_name")
        term_title = metadata.get("term_title")
        
        if is_enrolled and class_name:
            return f"""📋 **Enrollment Status**

**{student_name}** is currently enrolled in:
- **Class:** {class_name}
- **Term:** {term_title or "Current term"}
- **Status:** Active"""
        else:
            return f"""📋 **Enrollment Status**

**{student_name}** is not currently enrolled in any class for this term."""
    
    elif action == "list_enrollments":
        students = data.get("students", [])
        total = data.get("total", 0)
        
        if not students:
            return "📋 No enrolled students found."
        
        students_list = "\n".join([
            f"• **{s.get('first_name', '')} {s.get('last_name', '')}** (Adm: {s.get('admission_no', 'N/A')})"
            for s in students[:10]
        ])
        
        more = f"\n\n_...and {total - 10} more_" if total > 10 else ""
        
        return f"""📋 **Enrolled Students** (Total: {total})

{students_list}{more}"""
    
    elif action == "bulk_enroll":
        success_count = metadata.get("success_count", 0)
        failed_count = metadata.get("failed_count", 0)
        class_name = metadata.get("class_name", "the class")
        
        results = data
        successful = results.get("successful", [])
        failed = results.get("failed", [])
        
        message = f"✅ **Bulk Enrollment Complete**\n\n"
        message += f"Successfully enrolled **{success_count} students** in **{class_name}**."
        
        if failed_count > 0:
            message += f"\n\n⚠️ **{failed_count} students** could not be enrolled:"
            for fail in failed[:5]:
                message += f"\n• {fail['student_id']}: {fail['reason']}"
            
            if len(failed) > 5:
                message += f"\n• ...and {len(failed) - 5} more"
        
        return message
    
    elif action == "transfer_student":
        student_name = metadata.get("student_name", "Student")
        old_class_name = metadata.get("old_class_name", "previous class")
        new_class_name = metadata.get("new_class_name", "new class")
        
        return f"""✅ **Transfer Successful!**

**{student_name}** has been transferred:
- **From:** {old_class_name}
- **To:** {new_class_name}

The student's enrollment has been updated."""
    
    elif action == "unenroll_student":
        return f"✅ {response.message}"
    
    else:
        return f"✅ {response.message}"