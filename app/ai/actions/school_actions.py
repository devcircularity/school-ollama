# app/ai/actions/school_actions.py
"""
School Actions Handler
Handles AI intents related to school management
"""

import logging
import httpx
from typing import Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ============================================================================
# School Intent Enum
# ============================================================================

class SchoolIntent(str, Enum):
    """Available school management intents"""
    GET_SCHOOL = "get_school"
    UPDATE_SCHOOL = "update_school"
    GET_SCHOOL_STATS = "get_school_stats"


# ============================================================================
# Response Models
# ============================================================================

class ActionResponse(BaseModel):
    """Standard response from school actions"""
    success: bool
    action: str
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ============================================================================
# School Actions Handler
# ============================================================================

class SchoolActionsHandler:
    """
    Handles execution of school-related actions
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
        intent: SchoolIntent,
        parameters: Dict[str, Any]
    ) -> ActionResponse:
        """
        Execute a school management action
        
        Args:
            intent: The school intent to execute
            parameters: Action parameters from Mistral
            
        Returns:
            ActionResponse with results
        """
        logger.info(f"Executing school action: {intent.value} with params: {parameters}")
        
        try:
            # Route to appropriate handler method
            if intent == SchoolIntent.GET_SCHOOL:
                return await self._get_school()
            
            elif intent == SchoolIntent.UPDATE_SCHOOL:
                return await self._update_school(parameters)
            
            elif intent == SchoolIntent.GET_SCHOOL_STATS:
                return await self._get_school_stats()
            
            elif intent == SchoolIntent.LIST_ACADEMIC_YEARS:
                return await self._list_academic_years(parameters)
            
            elif intent == SchoolIntent.GET_CURRENT_ACADEMIC_YEAR:
                return await self._get_current_academic_year()
            
            elif intent == SchoolIntent.LIST_TERMS:
                return await self._list_terms(parameters)
            
            elif intent == SchoolIntent.GET_CURRENT_TERM:
                return await self._get_current_term()
            
            else:
                return ActionResponse(
                    success=False,
                    action=intent.value,
                    message=f"Unknown school action: {intent.value}",
                    error="Intent not implemented"
                )
        
        except Exception as e:
            logger.error(f"Error executing school action {intent.value}: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action=intent.value,
                message="Failed to execute action",
                error=str(e)
            )
    
    # ========================================================================
    # Action Implementations
    # ========================================================================
    
    async def _get_school(self) -> ActionResponse:
        """Get school information"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/schools/{self.school_id}",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    school_data = response.json()
                    return ActionResponse(
                        success=True,
                        action="get_school",
                        message="Retrieved school information successfully",
                        data=school_data
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="get_school",
                        message="Failed to retrieve school information",
                        error=f"Status {response.status_code}"
                    )
        
        except Exception as e:
            logger.error(f"Error getting school info: {e}")
            return ActionResponse(
                success=False,
                action="get_school",
                message="Error retrieving school information",
                error=str(e)
            )
    
    async def _update_school(self, params: Dict[str, Any]) -> ActionResponse:
        """Update school information"""
        try:
            # Build update payload from parameters
            update_data = {}
            allowed_fields = ["name", "address", "phone", "email", "motto", "logo_url", 
                            "boarding_type", "gender_type", "contact", "short_code", "currency"]
            
            for field in allowed_fields:
                if field in params:
                    update_data[field] = params[field]
            
            if not update_data:
                return ActionResponse(
                    success=False,
                    action="update_school",
                    message="No valid fields provided for update",
                    error="Missing update parameters"
                )
            
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.base_url}/api/schools/{self.school_id}",
                    headers=self.headers,
                    json=update_data,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    school_data = response.json()
                    return ActionResponse(
                        success=True,
                        action="update_school",
                        message="School information updated successfully",
                        data=school_data,
                        metadata={"updated_fields": list(update_data.keys())}
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="update_school",
                        message="Failed to update school information",
                        error=f"Status {response.status_code}: {response.text}"
                    )
        
        except Exception as e:
            logger.error(f"Error updating school: {e}")
            return ActionResponse(
                success=False,
                action="update_school",
                message="Error updating school information",
                error=str(e)
            )
    
    async def _get_school_stats(self) -> ActionResponse:
        """Get school statistics"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/schools/{self.school_id}/overview",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    stats_data = response.json()
                    return ActionResponse(
                        success=True,
                        action="get_school_stats",
                        message="Retrieved school statistics successfully",
                        data=stats_data
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="get_school_stats",
                        message="Failed to retrieve school statistics",
                        error=f"Status {response.status_code}"
                    )
        
        except Exception as e:
            logger.error(f"Error getting school stats: {e}")
            return ActionResponse(
                success=False,
                action="get_school_stats",
                message="Error retrieving school statistics",
                error=str(e)
            )
    
    async def _list_academic_years(self, params: Dict[str, Any]) -> ActionResponse:
        """List academic years"""
        try:
            page = params.get("page", 1)
            limit = params.get("limit", 20)
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/academic/years",
                    headers=self.headers,
                    params={"page": page, "limit": limit},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    years_data = response.json()
                    return ActionResponse(
                        success=True,
                        action="list_academic_years",
                        message="Retrieved academic years successfully",
                        data=years_data,
                        metadata={"page": page, "limit": limit}
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="list_academic_years",
                        message="Failed to retrieve academic years",
                        error=f"Status {response.status_code}"
                    )
        
        except Exception as e:
            logger.error(f"Error listing academic years: {e}")
            return ActionResponse(
                success=False,
                action="list_academic_years",
                message="Error retrieving academic years",
                error=str(e)
            )
    
    async def _get_current_academic_year(self) -> ActionResponse:
        """Get current academic year"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/academic/years/current",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    year_data = response.json()
                    return ActionResponse(
                        success=True,
                        action="get_current_academic_year",
                        message="Retrieved current academic year successfully",
                        data=year_data
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="get_current_academic_year",
                        message="Failed to retrieve current academic year",
                        error=f"Status {response.status_code}"
                    )
        
        except Exception as e:
            logger.error(f"Error getting current academic year: {e}")
            return ActionResponse(
                success=False,
                action="get_current_academic_year",
                message="Error retrieving current academic year",
                error=str(e)
            )
    
    async def _list_terms(self, params: Dict[str, Any]) -> ActionResponse:
        """List terms"""
        try:
            page = params.get("page", 1)
            limit = params.get("limit", 20)
            academic_year_id = params.get("academic_year_id")
            
            query_params = {"page": page, "limit": limit}
            if academic_year_id:
                query_params["academic_year_id"] = academic_year_id
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/academic/terms",
                    headers=self.headers,
                    params=query_params,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    terms_data = response.json()
                    return ActionResponse(
                        success=True,
                        action="list_terms",
                        message="Retrieved terms successfully",
                        data=terms_data,
                        metadata={"page": page, "limit": limit}
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="list_terms",
                        message="Failed to retrieve terms",
                        error=f"Status {response.status_code}"
                    )
        
        except Exception as e:
            logger.error(f"Error listing terms: {e}")
            return ActionResponse(
                success=False,
                action="list_terms",
                message="Error retrieving terms",
                error=str(e)
            )
    
    async def _get_current_term(self) -> ActionResponse:
        """Get current term"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/academic/terms/current",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    term_data = response.json()
                    return ActionResponse(
                        success=True,
                        action="get_current_term",
                        message="Retrieved current term successfully",
                        data=term_data
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="get_current_term",
                        message="Failed to retrieve current term",
                        error=f"Status {response.status_code}"
                    )
        
        except Exception as e:
            logger.error(f"Error getting current term: {e}")
            return ActionResponse(
                success=False,
                action="get_current_term",
                message="Error retrieving current term",
                error=str(e)
            )


# ============================================================================
# Keyword Detection (Fallback)
# ============================================================================

def detect_school_intent(message: str) -> Optional[str]:
    """
    Fallback keyword-based detection for school intents
    Used when Mistral is unavailable
    """
    message_lower = message.lower()
    
    # School info patterns
    if any(phrase in message_lower for phrase in [
        "school information", "school details", "school info", 
        "about school", "show school", "get school"
    ]):
        return "get_school"
    
    # School stats patterns
    if any(phrase in message_lower for phrase in [
        "school statistics", "school stats", "how many students",
        "total students", "school overview", "school metrics"
    ]):
        return "get_school_stats"
    
    # Update school patterns
    if any(phrase in message_lower for phrase in [
        "update school", "change school", "modify school",
        "edit school"
    ]):
        return "update_school"
    
    # Academic year patterns
    if any(phrase in message_lower for phrase in [
        "academic years", "school years", "list years"
    ]):
        return "list_academic_years"
    
    if any(phrase in message_lower for phrase in [
        "current year", "active year", "current academic year"
    ]):
        return "get_current_academic_year"
    
    # Term patterns
    if any(phrase in message_lower for phrase in [
        "list terms", "show terms", "all terms"
    ]):
        return "list_terms"
    
    if any(phrase in message_lower for phrase in [
        "current term", "active term", "which term"
    ]):
        return "get_current_term"
    
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
        return f"❌ {response.message}\n\n{response.error or 'Please try again.'}"
    
    action = response.action
    data = response.data or {}
    
    # Format based on action type
    if action == "get_school":
        name = data.get("name", "Unknown")
        address = data.get("address", "Not set")
        phone = data.get("phone", "Not set")
        email = data.get("email", "Not set")
        boarding_type = data.get("boarding_type", "Not set")
        gender_type = data.get("gender_type", "Not set")
        
        return f"""✅ **{name}**

📍 **Address:** {address}
📞 **Phone:** {phone}
📧 **Email:** {email}
🏫 **Type:** {boarding_type} School
👥 **Gender:** {gender_type}"""
    
    elif action == "update_school":
        name = data.get("name", "School")
        updated_fields = response.metadata.get("updated_fields", [])
        
        return f"""✅ **School Updated Successfully**

**{name}** information has been updated.

**Updated fields:** {', '.join(updated_fields)}"""
    
    elif action == "get_school_stats":
        school_name = data.get("school_name", "School")
        students_total = data.get("students_total", 0)
        students_enrolled = data.get("students_enrolled", 0)
        students_unassigned = data.get("students_unassigned", 0)
        classes = data.get("classes", 0)
        guardians = data.get("guardians", 0)
        
        return f"""📊 **{school_name} Statistics**

👨‍🎓 **Students:**
- Total: {students_total}
- Enrolled: {students_enrolled}
- Unassigned: {students_unassigned}

📚 **Classes:** {classes}
👨‍👩‍👧‍👦 **Guardians:** {guardians}"""
    
    elif action == "list_academic_years":
        years = data.get("items", [])
        total = data.get("total", 0)
        
        if not years:
            return "📅 No academic years found."
        
        years_list = "\n".join([
            f"• {year.get('year_name', 'Unknown')} ({year.get('start_date', '')} - {year.get('end_date', '')})"
            for year in years[:10]
        ])
        
        return f"""📅 **Academic Years** (Total: {total})

{years_list}"""
    
    elif action == "get_current_academic_year":
        year_name = data.get("year_name", "Unknown")
        start_date = data.get("start_date", "")
        end_date = data.get("end_date", "")
        
        return f"""📅 **Current Academic Year**

**{year_name}**
- From: {start_date}
- To: {end_date}"""
    
    elif action == "list_terms":
        terms = data.get("items", [])
        total = data.get("total", 0)
        
        if not terms:
            return "📆 No terms found."
        
        terms_list = "\n".join([
            f"• {term.get('name', 'Unknown')} ({term.get('start_date', '')} - {term.get('end_date', '')})"
            for term in terms[:10]
        ])
        
        return f"""📆 **Terms** (Total: {total})

{terms_list}"""
    
    elif action == "get_current_term":
        term_name = data.get("name", "Unknown")
        start_date = data.get("start_date", "")
        end_date = data.get("end_date", "")
        
        return f"""📆 **Current Term**

**{term_name}**
- From: {start_date}
- To: {end_date}"""
    
    else:
        return f"✅ {response.message}"