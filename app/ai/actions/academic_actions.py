# app/ai/actions/academic_actions.py
"""
Academic Actions Handler - Manage academic years, terms, and setup
Handles AI intents related to academic structure management
"""

import logging
import httpx
from typing import Dict, Any, Optional
from enum import Enum
from pydantic import BaseModel, ValidationError
from datetime import date

logger = logging.getLogger(__name__)


# ============================================================================
# Academic Intent Enum
# ============================================================================

class AcademicIntent(str, Enum):
    """Available academic management intents"""
    # Academic Year intents
    CREATE_ACADEMIC_YEAR = "create_academic_year"
    LIST_ACADEMIC_YEARS = "list_academic_years"
    GET_CURRENT_ACADEMIC_YEAR = "get_current_academic_year"
    ACTIVATE_ACADEMIC_YEAR = "activate_academic_year"
    DEACTIVATE_ACADEMIC_YEAR = "deactivate_academic_year"
    
    # Academic Term intents
    CREATE_TERM = "create_term"
    LIST_TERMS = "list_terms"
    GET_CURRENT_TERM = "get_current_term"
    ACTIVATE_TERM = "activate_term"
    COMPLETE_TERM = "complete_term"
    
    # Setup and status intents
    GET_ACADEMIC_STATUS = "get_academic_status"
    GET_CURRENT_SETUP = "get_current_setup"
    SETUP_ACADEMIC_STRUCTURE = "setup_academic_structure"  # Quick setup helper


# ============================================================================
# Parameter Models
# ============================================================================

class CreateAcademicYearParams(BaseModel):
    """Parameters for creating an academic year"""
    year: int
    title: Optional[str] = None
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD


class CreateTermParams(BaseModel):
    """Parameters for creating a term"""
    academic_year: int  # The year number (e.g., 2025)
    term: int           # Term number (1, 2, 3)
    title: Optional[str] = None
    start_date: str     # YYYY-MM-DD
    end_date: str       # YYYY-MM-DD


# ============================================================================
# Response Models
# ============================================================================

class ActionResponse(BaseModel):
    """Standard response from academic actions"""
    success: bool
    action: str
    message: str
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ============================================================================
# Academic Actions Handler
# ============================================================================

class AcademicActionsHandler:
    """
    Handles execution of academic-related actions
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
        intent: AcademicIntent,
        parameters: Dict[str, Any],
        original_message: Optional[str] = None
    ) -> ActionResponse:
        """
        Execute an academic management action
        
        Args:
            intent: The academic intent to execute
            parameters: Action parameters from Mistral
            original_message: Original user message (for fallback)
            
        Returns:
            ActionResponse with results
        """
        logger.info(f"Executing academic action: {intent.value} with params: {parameters}")
        
        try:
            # Route to appropriate handler method
            if intent == AcademicIntent.CREATE_ACADEMIC_YEAR:
                return await self._create_academic_year(parameters)
            
            elif intent == AcademicIntent.LIST_ACADEMIC_YEARS:
                return await self._list_academic_years(parameters)
            
            elif intent == AcademicIntent.GET_CURRENT_ACADEMIC_YEAR:
                return await self._get_current_academic_year(parameters)
            
            elif intent == AcademicIntent.ACTIVATE_ACADEMIC_YEAR:
                return await self._activate_academic_year(parameters)
            
            elif intent == AcademicIntent.DEACTIVATE_ACADEMIC_YEAR:
                return await self._deactivate_academic_year(parameters)
            
            elif intent == AcademicIntent.CREATE_TERM:
                return await self._create_term(parameters)
            
            elif intent == AcademicIntent.LIST_TERMS:
                return await self._list_terms(parameters)
            
            elif intent == AcademicIntent.GET_CURRENT_TERM:
                return await self._get_current_term(parameters)
            
            elif intent == AcademicIntent.ACTIVATE_TERM:
                return await self._activate_term(parameters)
            
            elif intent == AcademicIntent.COMPLETE_TERM:
                return await self._complete_term(parameters)
            
            elif intent == AcademicIntent.GET_ACADEMIC_STATUS:
                return await self._get_academic_status(parameters)
            
            elif intent == AcademicIntent.GET_CURRENT_SETUP:
                return await self._get_current_setup(parameters)
            
            elif intent == AcademicIntent.SETUP_ACADEMIC_STRUCTURE:
                return await self._setup_academic_structure(parameters)
            
            else:
                return ActionResponse(
                    success=False,
                    action=intent.value,
                    message=f"Unknown academic action: {intent.value}",
                    error="Intent not implemented"
                )
        
        except Exception as e:
            logger.error(f"Error executing academic action {intent.value}: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action=intent.value,
                message="Failed to execute action",
                error=str(e)
            )
    
    # ========================================================================
    # Academic Year Actions
    # ========================================================================
    
    async def _create_academic_year(self, params: Dict[str, Any]) -> ActionResponse:
        """Create a new academic year"""
        try:
            # Validate parameters
            year_params = CreateAcademicYearParams(**params)
            
            request_data = {
                "year": year_params.year,
                "title": year_params.title or f"Academic Year {year_params.year}",
                "start_date": year_params.start_date,
                "end_date": year_params.end_date
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/academic/years",
                    headers=self.headers,
                    json=request_data,
                    timeout=30.0
                )
                
                if response.status_code == 201:
                    year = response.json()
                    return ActionResponse(
                        success=True,
                        action="create_academic_year",
                        message=f"Academic year {year['year']} created successfully!",
                        data=year,
                        metadata={"next_step": "activate_year"}
                    )
                elif response.status_code == 409:
                    return ActionResponse(
                        success=False,
                        action="create_academic_year",
                        message=f"Academic year {year_params.year} already exists.",
                        error="Conflict"
                    )
                else:
                    error_detail = response.json().get('detail', 'Unknown error')
                    return ActionResponse(
                        success=False,
                        action="create_academic_year",
                        message=f"Failed to create academic year: {error_detail}",
                        error=error_detail
                    )
        
        except ValidationError as e:
            return ActionResponse(
                success=False,
                action="create_academic_year",
                message=f"Missing required information. Please provide: year, start_date (YYYY-MM-DD), end_date (YYYY-MM-DD)",
                error=str(e)
            )
        except Exception as e:
            logger.error(f"Error creating academic year: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="create_academic_year",
                message="An error occurred while creating the academic year.",
                error=str(e)
            )
    
    async def _list_academic_years(self, params: Dict[str, Any]) -> ActionResponse:
        """List all academic years"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/academic/years",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    years = response.json()
                    return ActionResponse(
                        success=True,
                        action="list_academic_years",
                        message=f"Found {len(years)} academic year(s)",
                        data={"years": years, "total": len(years)}
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="list_academic_years",
                        message="Failed to retrieve academic years",
                        error=response.text
                    )
        
        except Exception as e:
            logger.error(f"Error listing academic years: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="list_academic_years",
                message="An error occurred while retrieving academic years.",
                error=str(e)
            )
    
    async def _get_current_academic_year(self, params: Dict[str, Any]) -> ActionResponse:
        """Get the current/active academic year"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/academic/years/current",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    year = response.json()
                    return ActionResponse(
                        success=True,
                        action="get_current_academic_year",
                        message=f"Current academic year: {year['year']}",
                        data=year
                    )
                elif response.status_code == 404:
                    return ActionResponse(
                        success=False,
                        action="get_current_academic_year",
                        message="No academic year found. Please create one first.",
                        error="Not found",
                        metadata={"needs_setup": True}
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="get_current_academic_year",
                        message="Failed to get current academic year",
                        error=response.text
                    )
        
        except Exception as e:
            logger.error(f"Error getting current academic year: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="get_current_academic_year",
                message="An error occurred.",
                error=str(e)
            )
    
    async def _activate_academic_year(self, params: Dict[str, Any]) -> ActionResponse:
        """Activate an academic year"""
        year_id = params.get('year_id')
        
        if not year_id:
            return ActionResponse(
                success=False,
                action="activate_academic_year",
                message="Please specify which year to activate (provide year_id or year number)",
                error="Missing year_id"
            )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.base_url}/api/academic/years/{year_id}/activate",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return ActionResponse(
                        success=True,
                        action="activate_academic_year",
                        message=result.get('message', 'Academic year activated successfully!'),
                        data=result
                    )
                elif response.status_code == 404:
                    return ActionResponse(
                        success=False,
                        action="activate_academic_year",
                        message="Academic year not found",
                        error="Not found"
                    )
                else:
                    error_detail = response.json().get('detail', 'Unknown error')
                    return ActionResponse(
                        success=False,
                        action="activate_academic_year",
                        message=f"Failed to activate: {error_detail}",
                        error=error_detail
                    )
        
        except Exception as e:
            logger.error(f"Error activating academic year: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="activate_academic_year",
                message="An error occurred.",
                error=str(e)
            )
    
    async def _deactivate_academic_year(self, params: Dict[str, Any]) -> ActionResponse:
        """Deactivate an academic year"""
        year_id = params.get('year_id')
        
        if not year_id:
            return ActionResponse(
                success=False,
                action="deactivate_academic_year",
                message="Please specify which year to deactivate",
                error="Missing year_id"
            )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.base_url}/api/academic/years/{year_id}/deactivate",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return ActionResponse(
                        success=True,
                        action="deactivate_academic_year",
                        message=result.get('message', 'Academic year deactivated'),
                        data=result
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="deactivate_academic_year",
                        message="Failed to deactivate academic year",
                        error=response.text
                    )
        
        except Exception as e:
            logger.error(f"Error deactivating academic year: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="deactivate_academic_year",
                message="An error occurred.",
                error=str(e)
            )
    
    # ========================================================================
    # Academic Term Actions
    # ========================================================================
    
    async def _create_term(self, params: Dict[str, Any]) -> ActionResponse:
        """Create a new academic term"""
        try:
            # Validate parameters
            term_params = CreateTermParams(**params)
            
            # First, get the academic year ID
            async with httpx.AsyncClient() as client:
                years_response = await client.get(
                    f"{self.base_url}/api/academic/years",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if years_response.status_code != 200:
                    return ActionResponse(
                        success=False,
                        action="create_term",
                        message="Failed to find academic year",
                        error="Cannot retrieve years"
                    )
                
                years = years_response.json()
                target_year = next((y for y in years if y['year'] == term_params.academic_year), None)
                
                if not target_year:
                    return ActionResponse(
                        success=False,
                        action="create_term",
                        message=f"Academic year {term_params.academic_year} not found. Please create it first.",
                        error="Year not found"
                    )
                
                # Create the term
                request_data = {
                    "term": term_params.term,
                    "title": term_params.title or f"Term {term_params.term}",
                    "start_date": term_params.start_date,
                    "end_date": term_params.end_date,
                    "academic_year": term_params.academic_year
                }
                
                response = await client.post(
                    f"{self.base_url}/api/academic/years/{target_year['id']}/terms",
                    headers=self.headers,
                    json=request_data,
                    timeout=30.0
                )
                
                if response.status_code == 201:
                    term = response.json()
                    return ActionResponse(
                        success=True,
                        action="create_term",
                        message=f"Term {term['term']} created successfully for {term_params.academic_year}!",
                        data=term,
                        metadata={"next_step": "activate_term"}
                    )
                elif response.status_code == 409:
                    return ActionResponse(
                        success=False,
                        action="create_term",
                        message=f"Term {term_params.term} already exists for year {term_params.academic_year}",
                        error="Conflict"
                    )
                else:
                    error_detail = response.json().get('detail', 'Unknown error')
                    return ActionResponse(
                        success=False,
                        action="create_term",
                        message=f"Failed to create term: {error_detail}",
                        error=error_detail
                    )
        
        except ValidationError as e:
            return ActionResponse(
                success=False,
                action="create_term",
                message="Missing required information. Please provide: academic_year, term (1/2/3), start_date, end_date",
                error=str(e)
            )
        except Exception as e:
            logger.error(f"Error creating term: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="create_term",
                message="An error occurred while creating the term.",
                error=str(e)
            )
    
    async def _list_terms(self, params: Dict[str, Any]) -> ActionResponse:
        """List all terms for an academic year"""
        academic_year = params.get('academic_year')
        
        try:
            async with httpx.AsyncClient() as client:
                # Get the year first to find its ID
                years_response = await client.get(
                    f"{self.base_url}/api/academic/years",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if years_response.status_code != 200:
                    return ActionResponse(
                        success=False,
                        action="list_terms",
                        message="Failed to retrieve academic years",
                        error=years_response.text
                    )
                
                years = years_response.json()
                
                if academic_year:
                    target_year = next((y for y in years if y['year'] == academic_year), None)
                    if not target_year:
                        return ActionResponse(
                            success=False,
                            action="list_terms",
                            message=f"Academic year {academic_year} not found",
                            error="Year not found"
                        )
                    year_id = target_year['id']
                else:
                    # Get current year
                    current_year_response = await client.get(
                        f"{self.base_url}/api/academic/years/current",
                        headers=self.headers,
                        timeout=30.0
                    )
                    if current_year_response.status_code != 200:
                        return ActionResponse(
                            success=False,
                            action="list_terms",
                            message="No current academic year found",
                            error="No current year"
                        )
                    current_year = current_year_response.json()
                    year_id = current_year['id']
                    academic_year = current_year['year']
                
                # Get terms for this year
                terms_response = await client.get(
                    f"{self.base_url}/api/academic/years/{year_id}/terms",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if terms_response.status_code == 200:
                    terms = terms_response.json()
                    return ActionResponse(
                        success=True,
                        action="list_terms",
                        message=f"Found {len(terms)} term(s) for {academic_year}",
                        data={"terms": terms, "total": len(terms), "academic_year": academic_year}
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="list_terms",
                        message="Failed to retrieve terms",
                        error=terms_response.text
                    )
        
        except Exception as e:
            logger.error(f"Error listing terms: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="list_terms",
                message="An error occurred.",
                error=str(e)
            )
    
    async def _get_current_term(self, params: Dict[str, Any]) -> ActionResponse:
        """Get the current/active term"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/academic/terms/current",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    term = response.json()
                    return ActionResponse(
                        success=True,
                        action="get_current_term",
                        message=f"Current term: {term['title']}",
                        data=term
                    )
                elif response.status_code == 404:
                    error_detail = response.json().get('detail', 'No active term found')
                    return ActionResponse(
                        success=False,
                        action="get_current_term",
                        message=error_detail,
                        error="Not found",
                        metadata={"needs_setup": True}
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="get_current_term",
                        message="Failed to get current term",
                        error=response.text
                    )
        
        except Exception as e:
            logger.error(f"Error getting current term: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="get_current_term",
                message="An error occurred.",
                error=str(e)
            )
    
    async def _activate_term(self, params: Dict[str, Any]) -> ActionResponse:
        """Activate a term"""
        term_id = params.get('term_id')
        
        if not term_id:
            return ActionResponse(
                success=False,
                action="activate_term",
                message="Please specify which term to activate",
                error="Missing term_id"
            )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.base_url}/api/academic/terms/{term_id}/activate",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return ActionResponse(
                        success=True,
                        action="activate_term",
                        message=result.get('message', 'Term activated successfully!'),
                        data=result
                    )
                elif response.status_code == 404:
                    return ActionResponse(
                        success=False,
                        action="activate_term",
                        message="Term not found",
                        error="Not found"
                    )
                else:
                    error_detail = response.json().get('detail', 'Unknown error')
                    return ActionResponse(
                        success=False,
                        action="activate_term",
                        message=f"Failed to activate term: {error_detail}",
                        error=error_detail
                    )
        
        except Exception as e:
            logger.error(f"Error activating term: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="activate_term",
                message="An error occurred.",
                error=str(e)
            )
    
    async def _complete_term(self, params: Dict[str, Any]) -> ActionResponse:
        """Complete/close a term"""
        academic_year = params.get('academic_year')
        term = params.get('term')
        
        if not academic_year or not term:
            return ActionResponse(
                success=False,
                action="complete_term",
                message="Please specify academic_year and term number",
                error="Missing parameters"
            )
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.put(
                    f"{self.base_url}/api/academic/terms/{academic_year}/{term}/complete",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return ActionResponse(
                        success=True,
                        action="complete_term",
                        message=result.get('message', 'Term marked as complete'),
                        data=result
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="complete_term",
                        message="Failed to complete term",
                        error=response.text
                    )
        
        except Exception as e:
            logger.error(f"Error completing term: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="complete_term",
                message="An error occurred.",
                error=str(e)
            )
    
    # ========================================================================
    # Status and Setup Actions
    # ========================================================================
    
    async def _get_academic_status(self, params: Dict[str, Any]) -> ActionResponse:
        """Get current academic status"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/academic/status",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    status = response.json()
                    return ActionResponse(
                        success=True,
                        action="get_academic_status",
                        message="Academic status retrieved",
                        data=status
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="get_academic_status",
                        message="Failed to get academic status",
                        error=response.text
                    )
        
        except Exception as e:
            logger.error(f"Error getting academic status: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="get_academic_status",
                message="An error occurred.",
                error=str(e)
            )
    
    async def _get_current_setup(self, params: Dict[str, Any]) -> ActionResponse:
        """Get current academic setup"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/academic/current-setup",
                    headers=self.headers,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    setup = response.json()
                    return ActionResponse(
                        success=True,
                        action="get_current_setup",
                        message="Current setup retrieved",
                        data=setup
                    )
                else:
                    return ActionResponse(
                        success=False,
                        action="get_current_setup",
                        message="Failed to get current setup",
                        error=response.text
                    )
        
        except Exception as e:
            logger.error(f"Error getting current setup: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="get_current_setup",
                message="An error occurred.",
                error=str(e)
            )
    
    async def _setup_academic_structure(self, params: Dict[str, Any]) -> ActionResponse:
        """Quick setup: Create year + term and activate both"""
        year = params.get('year', 2025)
        
        try:
            # Step 1: Create academic year
            year_data = {
                "year": year,
                "title": f"Academic Year {year}",
                "start_date": f"{year}-01-01",
                "end_date": f"{year}-12-31"
            }
            
            async with httpx.AsyncClient() as client:
                year_response = await client.post(
                    f"{self.base_url}/api/academic/years",
                    headers=self.headers,
                    json=year_data,
                    timeout=30.0
                )
                
                if year_response.status_code not in [201, 409]:  # 409 = already exists
                    return ActionResponse(
                        success=False,
                        action="setup_academic_structure",
                        message="Failed to create academic year",
                        error=year_response.text
                    )
                
                year_obj = year_response.json() if year_response.status_code == 201 else None
                
                # If year already existed, get it
                if not year_obj:
                    years_response = await client.get(
                        f"{self.base_url}/api/academic/years",
                        headers=self.headers,
                        timeout=30.0
                    )
                    years = years_response.json()
                    year_obj = next((y for y in years if y['year'] == year), None)
                
                if not year_obj:
                    return ActionResponse(
                        success=False,
                        action="setup_academic_structure",
                        message="Could not find or create academic year",
                        error="Year not found"
                    )
                
                year_id = year_obj['id']
                
                # Step 2: Activate the year
                activate_response = await client.put(
                    f"{self.base_url}/api/academic/years/{year_id}/activate",
                    headers=self.headers,
                    timeout=30.0
                )
                
                # Step 3: Create Term 1
                term_data = {
                    "term": 1,
                    "title": "Term 1",
                    "start_date": f"{year}-01-10",
                    "end_date": f"{year}-04-15",
                    "academic_year": year
                }
                
                term_response = await client.post(
                    f"{self.base_url}/api/academic/years/{year_id}/terms",
                    headers=self.headers,
                    json=term_data,
                    timeout=30.0
                )
                
                if term_response.status_code not in [201, 409]:
                    logger.warning(f"Failed to create term: {term_response.text}")
                
                term_obj = term_response.json() if term_response.status_code == 201 else None
                
                # If term already existed, get it
                if not term_obj:
                    terms_response = await client.get(
                        f"{self.base_url}/api/academic/years/{year_id}/terms",
                        headers=self.headers,
                        timeout=30.0
                    )
                    if terms_response.status_code == 200:
                        terms = terms_response.json()
                        term_obj = next((t for t in terms if t['term'] == 1), None)
                
                if term_obj:
                    # Step 4: Activate the term
                    term_id = term_obj['id']
                    activate_term_response = await client.put(
                        f"{self.base_url}/api/academic/terms/{term_id}/activate",
                        headers=self.headers,
                        timeout=30.0
                    )
                
                return ActionResponse(
                    success=True,
                    action="setup_academic_structure",
                    message=f"✅ Academic structure set up successfully! Year {year} and Term 1 are now active.",
                    data={
                        "year": year_obj,
                        "term": term_obj,
                        "setup_complete": True
                    }
                )
        
        except Exception as e:
            logger.error(f"Error setting up academic structure: {e}", exc_info=True)
            return ActionResponse(
                success=False,
                action="setup_academic_structure",
                message="An error occurred during setup.",
                error=str(e)
            )


# ============================================================================
# Keyword Detection (Fallback)
# ============================================================================

def detect_academic_intent(message: str) -> Optional[str]:
    """
    Fallback keyword-based detection for academic intents
    Used when Mistral is unavailable
    """
    message_lower = message.lower()
    
    # Current academic year patterns (MOST SPECIFIC FIRST)
    if any(phrase in message_lower for phrase in [
        "current academic year", "current year", "active year", 
        "what year", "which year", "what's the year", "what is the year",
        "whats our academic year", "what's our academic year",
        "show current year", "get current year"
    ]):
        return "get_current_academic_year"
    
    # Create academic year patterns
    if any(phrase in message_lower for phrase in [
        "create academic year", "add academic year", "new academic year", 
        "create year", "add year", "new year"
    ]):
        return "create_academic_year"
    
    # List academic years patterns
    if any(phrase in message_lower for phrase in [
        "list academic years", "show academic years", "all academic years", 
        "view years", "show years", "list years", "get years"
    ]):
        return "list_academic_years"
    
    # Activate year patterns
    if any(phrase in message_lower for phrase in [
        "activate year", "activate academic year", "set year active",
        "make year active"
    ]):
        return "activate_academic_year"
    
    # Current term patterns (MOST SPECIFIC FIRST)
    if any(phrase in message_lower for phrase in [
        "current term", "active term", "what term", "which term",
        "what's the term", "what is the term",
        "whats our term", "what's our term",
        "show current term", "get current term"
    ]):
        return "get_current_term"
    
    # Create term patterns
    if any(phrase in message_lower for phrase in [
        "create term", "add term", "new term", "create academic term"
    ]):
        return "create_term"
    
    # List terms patterns
    if any(phrase in message_lower for phrase in [
        "list terms", "show terms", "all terms", "view terms", "get terms"
    ]):
        return "list_terms"
    
    # Activate term patterns
    if any(phrase in message_lower for phrase in [
        "activate term", "set term active", "make term active"
    ]):
        return "activate_term"
    
    # Complete term patterns
    if any(phrase in message_lower for phrase in [
        "complete term", "close term", "end term", "finish term"
    ]):
        return "complete_term"
    
    # Setup patterns
    if any(phrase in message_lower for phrase in [
        "setup academic", "academic setup", "setup school year", 
        "initialize academic", "quick setup", "setup school"
    ]):
        return "setup_academic_structure"
    
    # Status patterns
    if any(phrase in message_lower for phrase in [
        "academic status", "school status", "year status", "term status"
    ]):
        return "get_academic_status"
    
    # Current setup patterns
    if any(phrase in message_lower for phrase in [
        "current setup", "what's the setup", "show setup", "get setup"
    ]):
        return "get_current_setup"
    
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
    
    # Format based on action type
    if action == "create_academic_year":
        year = data
        return f"""✅ **Academic Year Created**

**Year {year.get('year')}**
- Title: {year.get('title', 'N/A')}
- Start Date: {year.get('start_date', 'N/A')}
- End Date: {year.get('end_date', 'N/A')}
- State: {year.get('state', 'DRAFT')}

💡 Next step: Activate this year to make it current."""
    
    elif action == "list_academic_years":
        years = data.get("years", [])
        total = data.get("total", 0)
        
        if not years:
            return "📅 No academic years found. Create one to get started!"
        
        years_list = "\n".join([
            f"• **{y.get('year')}** - {y.get('title', 'N/A')} ({y.get('state', 'DRAFT')})"
            for y in years
        ])
        
        return f"""📅 **Academic Years** (Total: {total})

{years_list}"""
    
    elif action == "get_current_academic_year":
        year = data
        return f"""📅 **Current Academic Year**

**Year {year.get('year')}**
- Title: {year.get('title', 'N/A')}
- State: {year.get('state', 'ACTIVE')}
- Start: {year.get('start_date', 'N/A')}
- End: {year.get('end_date', 'N/A')}"""
    
    elif action == "activate_academic_year":
        return f"✅ {response.message}\n\n💡 Now you can create and activate terms for this year."
    
    elif action == "deactivate_academic_year":
        return f"✅ {response.message}"
    
    elif action == "create_term":
        term = data
        return f"""✅ **Term Created**

**{term.get('title', f"Term {term.get('term')}")}**
- Academic Year: {term.get('academic_year', 'N/A')}
- Start Date: {term.get('start_date', 'N/A')}
- End Date: {term.get('end_date', 'N/A')}
- State: {term.get('state', 'PLANNED')}

💡 Next step: Activate this term to make it current."""
    
    elif action == "list_terms":
        terms = data.get("terms", [])
        total = data.get("total", 0)
        academic_year = data.get("academic_year", "")
        
        if not terms:
            return f"📚 No terms found for academic year {academic_year}. Create some terms!"
        
        terms_list = "\n".join([
            f"• **Term {t.get('term')}** - {t.get('title', 'N/A')} ({t.get('state', 'PLANNED')})"
            for t in terms
        ])
        
        return f"""📚 **Academic Terms for {academic_year}** (Total: {total})

{terms_list}"""
    
    elif action == "get_current_term":
        term = data
        return f"""📚 **Current Academic Term**

**{term.get('title', f"Term {term.get('term')}")}**
- State: {term.get('state', 'ACTIVE')}
- Start: {term.get('start_date', 'N/A')}
- End: {term.get('end_date', 'N/A')}"""
    
    elif action == "activate_term":
        return f"✅ {response.message}\n\n💡 You can now enroll students for this term."
    
    elif action == "complete_term":
        return f"✅ {response.message}\n\nThe term has been closed."
    
    elif action == "get_academic_status":
        status = data
        year = status.get('academic_year')
        term = status.get('active_term')
        setup_complete = status.get('setup_complete', False)
        warnings = status.get('warnings', [])
        
        year_text = f"**Year:** {year.get('name')} ({year.get('state')})" if year else "**Year:** Not configured ⚠️"
        term_text = f"**Term:** {term.get('name')} ({term.get('state')})" if term else "**Term:** Not configured ⚠️"
        status_icon = "✅" if setup_complete else "⚠️"
        
        warnings_text = ""
        if warnings:
            warnings_list = "\n".join([f"⚠️ {w}" for w in warnings])
            warnings_text = f"\n\n**Warnings:**\n{warnings_list}"
        
        return f"""{status_icon} **Academic Status**

{year_text}
{term_text}

**Setup Complete:** {'Yes ✅' if setup_complete else 'No ⚠️'}{warnings_text}"""
    
    elif action == "get_current_setup":
        setup = data
        current_year = setup.get('current_year')
        current_term = setup.get('current_term')
        setup_complete = setup.get('setup_complete', False)
        
        if setup_complete:
            return f"""✅ **Academic Setup Complete**

**Current Year:** {current_year.get('year')} - {current_year.get('title')}
**Current Term:** {current_term.get('title')}

Everything is configured and ready!"""
        else:
            needs_year = setup.get('needs_year', False)
            needs_term = setup.get('needs_term', False)
            
            message = "⚠️ **Academic Setup Incomplete**\n\n"
            
            if needs_year:
                message += "❌ No academic year found\n"
            elif current_year:
                message += f"✅ Academic year: {current_year.get('year')}\n"
            
            if needs_term:
                message += "❌ No academic term found\n"
            elif current_term:
                message += f"✅ Current term: {current_term.get('title')}\n"
            
            message += "\n💡 Use 'setup academic structure' for quick setup!"
            
            return message
    
    elif action == "setup_academic_structure":
        year = data.get('year', {})
        term = data.get('term', {})
        
        return f"""✅ **Academic Structure Setup Complete!**

**Academic Year {year.get('year')}** is now ACTIVE
**Term 1** is now ACTIVE

You're all set! You can now:
• Create classes
• Enroll students
• Start managing your school"""
    
    else:
        return f"✅ {response.message}"