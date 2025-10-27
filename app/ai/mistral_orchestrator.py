# app/ai/mistral_orchestrator.py

import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.ai.mistral_client import get_mistral_client, process_student_query
from app.ai.entity_memory import get_entity_store, PartialEntity

from app.ai.actions.student_actions import (
    StudentActionsHandler,
    StudentIntent,
    format_response_for_chat as format_student_response,
    detect_student_intent
)
from app.ai.actions.class_actions import (
    ClassActionsHandler,
    ClassIntent,
    format_response_for_chat as format_class_response,
    detect_class_intent
)
from app.ai.actions.school_actions import (
    SchoolActionsHandler,
    SchoolIntent,
    format_response_for_chat as format_school_response,
    detect_school_intent
)
from app.ai.actions.enrollment_actions import (
    EnrollmentActionsHandler,
    EnrollmentIntent,
    format_response_for_chat as format_enrollment_response,
    detect_enrollment_intent
)
from app.ai.actions.general_actions import (
    detect_general_intent,
    respond_to_general_intent,
    is_general_conversation
)

from app.ai.actions.academic_actions import (
    AcademicActionsHandler,
    AcademicIntent,
    format_response_for_chat as format_academic_response,
    detect_academic_intent
)

logger = logging.getLogger(__name__)


# ============================================================================
# Intent Validation and Correction - PREVENTS HALLUCINATION
# ============================================================================

# Valid intents registry
VALID_INTENTS = {
    # Student intents
    "create_student",
    "list_students", 
    "get_student",
    "update_student",
    "delete_student",
    "get_unassigned_students",
    "search_students",
    
    # Class intents
    "create_class",
    "list_classes",
    "list_empty_classes",
    "get_class_detail",
    "update_class",
    "delete_class",
    
    # School intents
    "get_school",
    "update_school",
    "get_school_stats",
    "list_academic_years",  # MOVED from school to academic
    "get_current_academic_year",  # MOVED from school to academic
    "list_terms",  # MOVED from school to academic
    "get_current_term",  # MOVED from school to academic
    
    # Enrollment intents
    "enroll_student",
    "unenroll_student",
    "get_enrollment",
    "list_enrollments",
    "bulk_enroll",
    "transfer_student",
    
    # Academic intents (NEW)
    "create_academic_year",
    "activate_academic_year",
    "deactivate_academic_year",
    "create_term",
    "activate_term",
    "complete_term",
    "get_academic_status",
    "get_current_setup",
    "setup_academic_structure"
}


# Intent corrections mapping - maps hallucinated intents to correct ones
INTENT_CORRECTIONS = {
    # Common hallucinations for list_students
    "get_school_students": "list_students",
    "show_students": "list_students",
    "display_students": "list_students",
    "fetch_students": "list_students",
    "list_all_students": "list_students",
    "view_students": "list_students",
    "get_students": "list_students",
    "all_students": "list_students",
    "show_all_students": "list_students",
    "get_all_students": "list_students",
    "fetch_all_students": "list_students",
    "display_all_students": "list_students",
    "view_all_students": "list_students",
    "show_student_list": "list_students",
    "get_student_list": "list_students",
    
    # Common hallucinations for get_student
    "show_student": "get_student",
    "get_student_details": "get_student",
    "view_student": "get_student",
    "fetch_student": "get_student",
    "student_details": "get_student",
    
    # Common hallucinations for create_student
    "add_student": "create_student",
    "register_student": "create_student",
    "new_student": "create_student",
    
    # Common hallucinations for list_classes
    "get_classes": "list_classes",
    "show_classes": "list_classes",
    "view_classes": "list_classes",
    "all_classes": "list_classes",
    
    # Common hallucinations for enroll_student
    "assign_student": "enroll_student",
    "add_student_to_class": "enroll_student",
    "register_student_in_class": "enroll_student",



    # Academic intent corrections (NEW)
    "create_year": "create_academic_year",
    "new_year": "create_academic_year",
    "add_year": "create_academic_year",
    "show_years": "list_academic_years",
    "get_years": "list_academic_years",
    "current_year": "get_current_academic_year",
    "active_year": "get_current_academic_year",
    "what_year": "get_current_academic_year",
    "which_year": "get_current_academic_year",
    "set_year_active": "activate_academic_year",
    "make_year_active": "activate_academic_year",
    "add_term": "create_term",
    "new_term": "create_term",
    "show_terms": "list_terms",
    "get_terms": "list_terms",
    "current_term": "get_current_term",
    "active_term": "get_current_term",
    "what_term": "get_current_term",
    "which_term": "get_current_term",
    "set_term_active": "activate_term",
    "make_term_active": "activate_term",
    "end_term": "complete_term",
    "close_term": "complete_term",
    "finish_term": "complete_term",
    "setup_school": "setup_academic_structure",
    "initialize_school": "setup_academic_structure",
    "academic_setup": "setup_academic_structure",
    "quick_setup": "setup_academic_structure",
    "status": "get_academic_status",
    "school_status": "get_academic_status",

}


def validate_and_correct_intent(intent: str) -> str:
    """
    Validate intent and correct common hallucinations
    
    This function prevents Mistral from creating non-existent intents by:
    1. Checking if the intent is in the valid list
    2. Applying known corrections for common hallucinations
    3. Using fuzzy matching for unknown variations
    
    Args:
        intent: The intent detected by Mistral
        
    Returns:
        Corrected intent name (guaranteed to be valid)
    """
    # Already valid - return as-is
    if intent in VALID_INTENTS:
        logger.debug(f"✓ Intent '{intent}' is valid")
        return intent
    
    # Check if we have a known correction
    if intent in INTENT_CORRECTIONS:
        corrected = INTENT_CORRECTIONS[intent]
        logger.warning(
            f"⚠️ CORRECTED HALLUCINATED INTENT: '{intent}' → '{corrected}'\n"
            f"   Mistral created a non-existent intent, auto-corrected it."
        )
        return corrected
    
    # Fuzzy matching for unknown variations
    intent_lower = intent.lower()
    
    # PRIORITY CHECK: Student-related queries take precedence
    # This prevents "list all students" from being routed to get_school_stats
    if "student" in intent_lower:
        # List/show/get all students
        if any(keyword in intent_lower for keyword in ["list", "show", "get", "all", "display", "view", "fetch"]):
            # Check if it's asking for unassigned students
            if any(keyword in intent_lower for keyword in ["unassigned", "not_enrolled", "no_class", "without"]):
                logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'get_unassigned_students'")
                return "get_unassigned_students"
            # Otherwise it's list students (takes priority over any school-related intents)
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'list_students'")
            return "list_students"
        
        # Create/add student
        elif any(keyword in intent_lower for keyword in ["create", "add", "new", "register"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'create_student'")
            return "create_student"
        
        # Update/modify student
        elif any(keyword in intent_lower for keyword in ["update", "modify", "edit", "change"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'update_student'")
            return "update_student"
        
        # Delete/remove student
        elif any(keyword in intent_lower for keyword in ["delete", "remove", "drop"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'delete_student'")
            return "delete_student"
        
        # Search student
        elif any(keyword in intent_lower for keyword in ["search", "find", "look"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'search_students'")
            return "search_students"
        
        # Enroll student
        elif any(keyword in intent_lower for keyword in ["enroll", "assign", "add_to"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'enroll_student'")
            return "enroll_student"
    
    # Class-related fuzzy matching
    elif "class" in intent_lower:
        if any(keyword in intent_lower for keyword in ["list", "show", "get", "all", "display", "view"]):
            if any(keyword in intent_lower for keyword in ["empty", "no_student", "without"]):
                logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'list_empty_classes'")
                return "list_empty_classes"
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'list_classes'")
            return "list_classes"
        elif any(keyword in intent_lower for keyword in ["create", "add", "new"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'create_class'")
            return "create_class"
    
    # School-related fuzzy matching
    elif "school" in intent_lower:
        if any(keyword in intent_lower for keyword in ["stats", "statistics", "count", "number"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'get_school_stats'")
            return "get_school_stats"
        elif any(keyword in intent_lower for keyword in ["info", "details", "get", "show"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'get_school'")
            return "get_school"
        elif any(keyword in intent_lower for keyword in ["update", "change", "modify"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'update_school'")
            return "update_school"
    
    # Academic-related fuzzy matching
    elif any(keyword in intent_lower for keyword in ["year", "academic"]):
        if any(keyword in intent_lower for keyword in ["create", "add", "new"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'create_academic_year'")
            return "create_academic_year"
        elif any(keyword in intent_lower for keyword in ["list", "show", "get", "all"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'list_academic_years'")
            return "list_academic_years"
        elif any(keyword in intent_lower for keyword in ["current", "active", "what", "which"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'get_current_academic_year'")
            return "get_current_academic_year"
        elif any(keyword in intent_lower for keyword in ["activate", "set_active"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'activate_academic_year'")
            return "activate_academic_year"
    
    elif "term" in intent_lower:
        if any(keyword in intent_lower for keyword in ["create", "add", "new"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'create_term'")
            return "create_term"
        elif any(keyword in intent_lower for keyword in ["list", "show", "get", "all"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'list_terms'")
            return "list_terms"
        elif any(keyword in intent_lower for keyword in ["current", "active", "what", "which"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'get_current_term'")
            return "get_current_term"
        elif any(keyword in intent_lower for keyword in ["activate", "set_active"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'activate_term'")
            return "activate_term"
        elif any(keyword in intent_lower for keyword in ["complete", "close", "end", "finish"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'complete_term'")
            return "complete_term"
    
    elif any(keyword in intent_lower for keyword in ["setup", "initialize"]):
        if any(keyword in intent_lower for keyword in ["academic", "school", "structure"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'setup_academic_structure'")
            return "setup_academic_structure"
    
    elif any(keyword in intent_lower for keyword in ["status", "check"]):
        if any(keyword in intent_lower for keyword in ["academic", "school", "current"]):
            logger.warning(f"⚠️ FUZZY CORRECTED: '{intent}' → 'get_academic_status'")
            return "get_academic_status"
        
    # If we still can't correct it, log error and return as-is
    # This will cause a proper error message to be shown to the user
    logger.error(
        f"❌ UNKNOWN INTENT: '{intent}'\n"
        f"   This intent doesn't exist and couldn't be auto-corrected.\n"
        f"   Valid intents: {', '.join(sorted(VALID_INTENTS))}"
    )
    return intent


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
        logger.info(f"✓ Extracted via Pattern 1: student='{params['student_name']}', class='{params['class_name']}'")
        return params
    
    # Pattern 2: "assign NAME to CLASS_NAME" (without "class" keyword)
    match = re.search(r'(?:assign|add|put)\s+([a-zA-Z\s]+?)\s+(?:to|in|into)\s+(?:class\s+)?([a-zA-Z0-9\s]+)', message, re.IGNORECASE)
    if match:
        params['student_name'] = match.group(1).strip()
        params['class_name'] = match.group(2).strip()
        logger.info(f"✓ Extracted via Pattern 2: student='{params['student_name']}', class='{params['class_name']}'")
        return params
    
    # Pattern 3: "enroll student ADM_NO to class CLASS_NAME"
    match = re.search(r'enroll\s+student\s+([A-Z0-9_]+)\s+(?:to|in|into)\s+class\s+([a-zA-Z0-9\s]+)', message, re.IGNORECASE)
    if match:
        params['student_id'] = match.group(1).strip()
        params['class_name'] = match.group(2).strip()
        logger.info(f"✓ Extracted via Pattern 3: admission='{params['student_id']}', class='{params['class_name']}'")
        return params
    
    # Pattern 4: Try to extract just the name and class from anywhere
    # Look for common patterns with "to class"
    match = re.search(r'([a-zA-Z]+\s+[a-zA-Z]+)\s+to\s+class\s+([a-zA-Z0-9]+)', message, re.IGNORECASE)
    if match:
        params['student_name'] = match.group(1).strip()
        params['class_name'] = match.group(2).strip()
        logger.info(f"✓ Extracted via Pattern 4: student='{params['student_name']}', class='{params['class_name']}'")
        return params
    
    logger.warning(f"❌ Could not extract enrollment parameters from: '{message}'")
    return params


# ============================================================================
# Parameter Cleaning Functions
# ============================================================================

def _clean_enrollment_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean enrollment parameters extracted by Mistral
    Extracts admission numbers from patterns like "Adm: AUTO_2025_001"
    
    Args:
        params: Raw parameters from Mistral
        
    Returns:
        Cleaned parameters
    """
    cleaned = params.copy()
    
    # Clean student_id - extract admission number from patterns like "Adm: AUTO_2025_001"
    if "student_id" in cleaned:
        student_id = str(cleaned["student_id"])
        
        # Pattern 1: "Adm: AUTO_2025_001" or "Adm:AUTO_2025_001"
        if "adm:" in student_id.lower():
            parts = student_id.lower().split("adm:")
            if len(parts) > 1:
                cleaned["student_id"] = parts[1].strip()
                logger.info(f"Cleaned student_id from '{student_id}' to '{cleaned['student_id']}'")
        
        # Pattern 2: "Name (Adm: AUTO_2025_001)" or any parentheses pattern
        elif "(" in student_id and ")" in student_id:
            match = re.search(r'\((?:adm:\s*)?([^\)]+)\)', student_id, re.IGNORECASE)
            if match:
                cleaned["student_id"] = match.group(1).strip()
                logger.info(f"Cleaned student_id from '{student_id}' to '{cleaned['student_id']}'")
    
    # Remove any extra parameters that shouldn't be there
    allowed_enrollment_params = {"student_id", "student_name", "class_id", "class_name", "term_id", "new_class_id", "student_ids"}
    cleaned = {k: v for k, v in cleaned.items() if k in allowed_enrollment_params}
    
    return cleaned


def _clean_parameters(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean parameters by removing empty strings, None values, and invalid inferences
    
    Args:
        params: Raw parameters from Mistral
        
    Returns:
        Cleaned parameters
    """
    cleaned = {}
    
    for key, value in params.items():
        # Skip None, empty strings, and empty lists
        if value is None or value == '' or value == []:
            continue
        
        # For strings, strip whitespace
        if isinstance(value, str):
            value = value.strip()
            # Skip if empty after stripping
            if not value:
                continue
        
        # SPECIAL VALIDATION: Gender should only be MALE or FEMALE
        if key == "gender":
            value_upper = value.upper()
            if value_upper not in ["MALE", "FEMALE"]:
                logger.warning(f"Invalid gender value '{value}' detected, removing it")
                continue
        
        cleaned[key] = value
    
    return cleaned


def _validate_gender_extraction(
    params: Dict[str, Any],
    message: str,
    conversation_history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """
    Validate gender extraction - remove if it wasn't explicitly stated
    This prevents hallucination where AI assumes gender from names
    
    Args:
        params: Extracted parameters
        message: Current user message
        conversation_history: Previous messages
        
    Returns:
        Validated parameters with gender removed if it was hallucinated
    """
    if "gender" not in params or params["gender"] is None:
        return params
    
    # Check if gender was explicitly stated in current message
    message_lower = message.lower()
    
    # Explicit gender keywords that definitively indicate gender
    male_keywords = ["he", "his", "him", "boy", "male", "man", "mr", "mr.", "gentleman", "son"]
    female_keywords = ["she", "her", "hers", "girl", "female", "woman", "ms", "ms.", "mrs", "mrs.", "lady", "madam", "daughter"]
    
    has_male_keyword = any(keyword in message_lower for keyword in male_keywords)
    has_female_keyword = any(keyword in message_lower for keyword in female_keywords)
    
    # If no explicit gender keyword found in current message, check previous messages
    if not has_male_keyword and not has_female_keyword and conversation_history:
        # Check last 3 user messages for gender context
        for msg in reversed(conversation_history[-6:]):  # Last 3 exchanges = 6 messages
            if msg["role"] == "user":
                msg_lower = msg["content"].lower()
                has_male_keyword = any(keyword in msg_lower for keyword in male_keywords)
                has_female_keyword = any(keyword in msg_lower for keyword in female_keywords)
                if has_male_keyword or has_female_keyword:
                    logger.info(f"Found gender context in previous message: {msg['content'][:50]}")
                    break
    
    # If still no explicit gender keyword found, REMOVE the gender parameter
    if not has_male_keyword and not has_female_keyword:
        logger.warning(
            f"Gender '{params['gender']}' was inferred without explicit mention in message '{message}', "
            f"removing it to prevent hallucination"
        )
        validated_params = params.copy()
        del validated_params["gender"]
        return validated_params
    
    # Validate that extracted gender matches the keywords found
    if params["gender"] == "MALE" and not has_male_keyword:
        logger.warning(f"Gender 'MALE' extracted but no male keywords found, removing it")
        validated_params = params.copy()
        del validated_params["gender"]
        return validated_params
    
    if params["gender"] == "FEMALE" and not has_female_keyword:
        logger.warning(f"Gender 'FEMALE' extracted but no female keywords found, removing it")
        validated_params = params.copy()
        del validated_params["gender"]
        return validated_params
    
    logger.info(f"Gender '{params['gender']}' validated - found explicit keyword in message")
    return params


def _merge_partial_entity(
    current_params: Dict[str, Any],
    stored_entity: Optional[PartialEntity]
) -> Dict[str, Any]:
    """
    Merge current parameters with stored partial entity
    Current params take precedence (user is updating)
    
    Args:
        current_params: Parameters from current message
        stored_entity: Previously stored partial entity
        
    Returns:
        Merged parameters
    """
    if not stored_entity:
        return current_params
    
    # Start with stored parameters
    merged = stored_entity.parameters.copy()
    
    # Update with current parameters (overwrite with new info)
    for key, value in current_params.items():
        if value is not None:  # Only update if new value provided
            merged[key] = value
    
    logger.info(f"Merged parameters: stored={stored_entity.parameters}, current={current_params}, result={merged}")
    
    return merged


def _check_required_fields(
    intent: str,
    params: Dict[str, Any]
) -> tuple[List[str], List[str]]:
    """
    Check which required fields are missing for an intent
    
    Args:
        intent: The action intent
        params: Current parameters
        
    Returns:
        Tuple of (missing_required, missing_optional)
    """
    # Define required and optional fields per intent
    field_requirements = {
        "create_student": {
            "required": ["first_name", "last_name", "gender", "dob"],
            "optional": ["admission_no", "class_id"]
        },
        "update_student": {
            "required": ["student_id"],
            "optional": ["first_name", "last_name", "gender", "dob", "class_id"]
        },
        "enroll_student": {
            "required": ["student_id", "class_id"],
            "optional": ["term_id"]
        },
        "transfer_student": {
            "required": ["student_id", "new_class_id"],
            "optional": ["term_id"]
        },
        "create_class": {
            "required": ["level"],
            "optional": ["stream", "academic_year"]
        },
        "update_class": {
            "required": ["class_id"],
            "optional": ["level", "stream", "academic_year"]
        },
    }
    
    requirements = field_requirements.get(intent, {"required": [], "optional": []})
    
    missing_required = []
    for field in requirements["required"]:
        if field not in params or params[field] is None or params[field] == "":
            missing_required.append(field)
    
    missing_optional = []
    for field in requirements["optional"]:
        if field not in params or params[field] is None or params[field] == "":
            missing_optional.append(field)
    
    return missing_required, missing_optional


# ============================================================================
# Main Orchestrator Function
# ============================================================================

async def handle_ai_logic(
    message: str,
    school_id: str,
    auth_token: str,
    context: Optional[Dict[str, Any]] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    conversation_id: Optional[str] = None,
    base_url: str = "http://127.0.0.1:8000"
) -> Dict[str, Any]:
    """
    Main orchestrator function with anti-hallucination pattern and fallback extraction
    
    Pipeline:
    0. Check if it's a general intent (greeting, help, etc.) → respond immediately
    1. Send message to Mistral for intent detection
    2. VALIDATE AND CORRECT INTENT (prevents hallucination)
    3. Validate and clean parameters (remove hallucinations)
    4. Check for partial entities in memory and merge
    5. Validate required fields and prompt if missing
    6. If Mistral failed and params empty, try fallback extraction
    7. Route to appropriate handler and execute
    8. Format response for chat display
    
    Args:
        message: User message
        school_id: School context UUID
        auth_token: JWT authentication token
        context: Additional context (user info, etc.)
        conversation_history: Previous messages for multi-turn support
        conversation_id: Conversation ID for entity memory tracking
        base_url: Backend API base URL
        
    Returns:
        Dictionary with:
            - intent: Detected action intent
            - thought: AI reasoning
            - formatted: Human-readable response
            - raw_response: Full action response
            - confidence: Confidence score
            - action_taken: Action name
            - data: Response data from action
            - metadata: Additional metadata (partial_entity, missing_fields, etc.)
    """
    
    try:
        # Get entity store
        entity_store = get_entity_store()
        
        # LAYER 0: Check for general conversational intents first
        logger.info(f"Processing message: {message}")
        
        general_intent = detect_general_intent(message)
        if general_intent:
            logger.info(f"Detected general intent: {general_intent} (handled locally)")
            
            # Clear any partial entities if user is changing topic
            if conversation_id and general_intent in ["greeting", "help"]:
                entity_store.clear_entity(conversation_id)
            
            # Build enhanced context with school information
            user_context = {}
            if context:
                user_email = context.get("user_email", "")
                if user_email:
                    user_context["user_name"] = user_email.split("@")[0].title()
                
                # Add school context
                user_context["schools"] = context.get("schools", [])
                user_context["current_school_name"] = context.get("school_name")
            
            response = respond_to_general_intent(general_intent, user_context)
            
            return {
                "intent": general_intent,
                "thought": "Handled as general conversation (no backend action needed)",
                "formatted": response["message"],
                "raw_response": None,
                "confidence": 1.0,
                "action_taken": None,
                "data": None,
                "suggestions": response["suggestions"],
                "is_general": True
            }
        
        # LAYER 1: Try Mistral for structured business intents
        logger.info(f"Not a general intent, querying Mistral...")
        
        mistral_failed = False
        try:
            mistral_intent = await process_student_query(
                message=message,
                context=context,
                conversation_history=conversation_history
            )
            
            intent = mistral_intent.intent
            
            # CRITICAL: VALIDATE AND CORRECT INTENT (prevents hallucination)
            intent = validate_and_correct_intent(intent)
            
            params = mistral_intent.parameters
            needs_clarification = mistral_intent.needs_clarification or []
            thought = mistral_intent.thought
            confidence = mistral_intent.confidence or 0.0
            
            # CRITICAL: Clean parameters - remove empty strings and None values
            params = _clean_parameters(params)
            
            # CRITICAL: Validate gender extraction to prevent hallucination
            params = _validate_gender_extraction(params, message, conversation_history)
            
            logger.info(f"Mistral detected: intent={intent}, params={params}, needs_clarification={needs_clarification}")
            
            # Check if we have a partial entity in memory
            stored_entity = entity_store.get_entity(conversation_id) if conversation_id else None
            
            if stored_entity and stored_entity.intent == intent:
                logger.info(f"Found stored partial entity, merging parameters")
                params = _merge_partial_entity(params, stored_entity)
            
            # Check for missing required fields
            missing_required, missing_optional = _check_required_fields(intent, params)
            
            logger.info(f"Field check: missing_required={missing_required}, missing_optional={missing_optional}")
            
            # If required fields are missing, store partial entity and ask for clarification
            if missing_required:
                # Store partial entity
                if conversation_id:
                    partial_entity = PartialEntity(
                        entity_type="student" if "student" in intent else "class",
                        intent=intent,
                        parameters=params,
                        missing_fields=missing_required,
                        optional_fields=missing_optional,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    entity_store.set_entity(conversation_id, partial_entity)
                    logger.info(f"Stored partial entity: {partial_entity.dict()}")
                
                # Build clarification message
                field_names = {
                    "first_name": "first name",
                    "last_name": "last name",
                    "gender": "gender (MALE or FEMALE)",
                    "dob": "date of birth (YYYY-MM-DD format, e.g., 2010-01-15)",
                    "student_id": "student ID or admission number",
                    "class_id": "class name or ID",
                    "new_class_id": "new class name or ID",
                    "level": "class level (e.g., Grade 5, Form 2)"
                }
                
                missing_friendly = [field_names.get(f, f) for f in missing_required]
                missing_text = ", ".join(missing_friendly)
                
                # Show what we already have
                provided_info = []
                for key, value in params.items():
                    if value is not None and value != "":
                        friendly_key = field_names.get(key, key)
                        provided_info.append(f"**{friendly_key}**: {value}")
                
                message_text = f"💬 I need some more information. Please provide: **{missing_text}**"
                
                if provided_info:
                    provided_bullets = "\n• ".join(provided_info)
                    message_text += f"\n\n✓ I already have:\n• {provided_bullets}"
                
                # Add optional field hints
                if missing_optional:
                    optional_friendly = [field_names.get(f, f) for f in missing_optional]
                    optional_text = ", ".join(optional_friendly)
                    message_text += f"\n\n💡 You can also optionally provide: {optional_text}"
                
                return {
                    "intent": intent,
                    "thought": thought,
                    "formatted": message_text,
                    "raw_response": None,
                    "confidence": confidence,
                    "action_taken": None,
                    "data": None,
                    "suggestions": [
                        f"Provide: {missing_text}",
                        "Say 'cancel' to start over",
                        "Ask 'what do you have so far?'"
                    ],
                    "metadata": {
                        "partial_entity": True,
                        "missing_fields": missing_required,
                        "optional_fields": missing_optional,
                        "provided_params": params
                    }
                }
            
            # All required fields present - clear partial entity and execute
            if conversation_id:
                entity_store.clear_entity(conversation_id)
                logger.info(f"Cleared partial entity - all required fields present")
            
        except Exception as e:
            logger.warning(f"Mistral processing failed, using fallback: {e}")
            mistral_failed = True
            
            # LAYER 2: Fallback to keyword-based detection
            intent = (
                detect_enrollment_intent(message) or
                detect_student_intent(message) or 
                detect_class_intent(message) or 
                detect_school_intent(message) or
                detect_academic_intent(message) or  # ADDED: Academic intent detection
                "unknown"
            )
            params = {}
            thought = f"Using fallback intent detection: {intent}"
            confidence = 0.5 if intent != "unknown" else 0.0
            
            logger.info(f"Fallback detected intent: {intent} (confidence: {confidence})")
            
            # CRITICAL: If it's an enrollment intent and Mistral failed, try to extract params from text
            if intent == "enroll_student" and not params:
                logger.info("Attempting fallback parameter extraction for enrollment")
                params = extract_enrollment_params_from_text(message)
                if params:
                    logger.info(f"✓ Fallback extraction successful: {params}")
                else:
                    logger.warning(f"✗ Fallback extraction failed for: {message}")
        
        # IMPORTANT: If we have a valid intent, set minimum confidence
        if intent != "unknown" and confidence < 0.6:
            confidence = 0.75
            logger.info(f"Adjusted confidence to {confidence} for intent: {intent}")
        
        # Check if intent is unknown or confidence too low
        if intent == "unknown" or confidence < 0.4:
            logger.warning(f"Intent rejected: {intent}, confidence: {confidence}")
            return {
                "intent": "unknown",
                "thought": thought or "I'm not sure I understood that correctly.",
                "formatted": f"I'm not quite sure what you're asking. {thought or 'Could you rephrase or be more specific about what you need help with?'}",
                "raw_response": None,
                "confidence": confidence,
                "action_taken": None,
                "data": None,
                "suggestions": [
                    "Try asking: 'Show me all students'",
                    "Try: 'List all classes'",
                    "Try: 'Enroll student A101 in Grade 5'",
                    "Ask: 'What can you help me with?'"
                ]
            }
        
        # LAYER 3: Route to appropriate handler
        handler = None
        formatter = None
        intent_enum = None
        handler_type = None

        # Try Enrollment Actions FIRST (before student actions to avoid conflict)
        try:
            intent_enum = EnrollmentIntent(intent)
            handler = EnrollmentActionsHandler(
                base_url=base_url,
                auth_token=auth_token,
                school_id=school_id
            )
            formatter = format_enrollment_response
            handler_type = "enrollment"
            logger.info(f"✓ Routing to EnrollmentActionsHandler for intent: {intent}")
        except ValueError:
            logger.debug(f"Intent '{intent}' is not an enrollment intent")

        # Try Student Actions if not enrollment
        if handler is None:
            try:
                intent_enum = StudentIntent(intent)
                handler = StudentActionsHandler(
                    base_url=base_url,
                    auth_token=auth_token,
                    school_id=school_id
                )
                formatter = format_student_response
                handler_type = "student"
                logger.info(f"✓ Routing to StudentActionsHandler for intent: {intent}")
            except ValueError:
                logger.debug(f"Intent '{intent}' is not a student intent")

        # Try Class Actions if not enrollment or student
        if handler is None:
            try:
                intent_enum = ClassIntent(intent)
                handler = ClassActionsHandler(
                    base_url=base_url,
                    auth_token=auth_token,
                    school_id=school_id
                )
                formatter = format_class_response
                handler_type = "class"
                logger.info(f"✓ Routing to ClassActionsHandler for intent: {intent}")
            except ValueError:
                logger.debug(f"Intent '{intent}' is not a class intent")

        # ⭐ NEW: Try Academic Actions BEFORE School Actions
        if handler is None:
            try:
                intent_enum = AcademicIntent(intent)
                handler = AcademicActionsHandler(
                    base_url=base_url,
                    auth_token=auth_token,
                    school_id=school_id
                )
                formatter = format_academic_response
                handler_type = "academic"
                logger.info(f"✓ Routing to AcademicActionsHandler for intent: {intent}")
            except ValueError:
                logger.debug(f"Intent '{intent}' is not an academic intent")

        # Try School Actions LAST (after academic actions)
        if handler is None:
            try:
                intent_enum = SchoolIntent(intent)
                handler = SchoolActionsHandler(
                    base_url=base_url,
                    auth_token=auth_token,
                    school_id=school_id
                )
                formatter = format_school_response
                handler_type = "school"
                logger.info(f"✓ Routing to SchoolActionsHandler for intent: {intent}")
            except ValueError:
                logger.debug(f"Intent '{intent}' is not a school intent")

        # If no handler matched
        if handler is None or intent_enum is None:
            logger.error(f"❌ No handler found for intent: {intent}")
            return {
                "intent": intent,
                "thought": thought,
                "formatted": f"I detected the action '{intent}' but I don't know how to perform it yet.",
                "raw_response": None,
                "confidence": confidence,
                "action_taken": None,
                "data": None
            }
        
        # Try Class Actions if not enrollment or student
        if handler is None:
            try:
                intent_enum = ClassIntent(intent)
                handler = ClassActionsHandler(
                    base_url=base_url,
                    auth_token=auth_token,
                    school_id=school_id
                )
                formatter = format_class_response
                handler_type = "class"
                logger.info(f"✓ Routing to ClassActionsHandler for intent: {intent}")
            except ValueError:
                logger.debug(f"Intent '{intent}' is not a class intent")
        
        # Try School Actions if not enrollment, student, or class
        if handler is None:
            try:
                intent_enum = SchoolIntent(intent)
                handler = SchoolActionsHandler(
                    base_url=base_url,
                    auth_token=auth_token,
                    school_id=school_id
                )
                formatter = format_school_response
                handler_type = "school"
                logger.info(f"✓ Routing to SchoolActionsHandler for intent: {intent}")
            except ValueError:
                logger.debug(f"Intent '{intent}' is not a school intent")
        
        # ADDED: Try Academic Actions if not enrollment, student, class, or school
        if handler is None:
            try:
                intent_enum = AcademicIntent(intent)
                handler = AcademicActionsHandler(
                    base_url=base_url,
                    auth_token=auth_token,
                    school_id=school_id
                )
                formatter = format_academic_response
                handler_type = "academic"
                logger.info(f"✓ Routing to AcademicActionsHandler for intent: {intent}")
            except ValueError:
                logger.debug(f"Intent '{intent}' is not an academic intent")

        # If no handler matched
        if handler is None or intent_enum is None:
            logger.error(f"❌ No handler found for intent: {intent}")
            logger.error(f"Available handlers: EnrollmentActionsHandler, StudentActionsHandler, ClassActionsHandler, SchoolActionsHandler, AcademicActionsHandler")
            return {
                "intent": intent,
                "thought": thought,
                "formatted": f"I detected the action '{intent}' but I don't know how to perform it yet. This feature may be coming soon!",
                "raw_response": None,
                "confidence": confidence,
                "action_taken": None,
                "data": None,
                "suggestions": [
                    "Try: 'Show me all students'",
                    "Try: 'List all classes'",
                    "Try: 'Enroll student A101 in Grade 5'",
                    "Ask: 'What can you do?'"
                ]
            }
        
        logger.info(f"Executing {handler_type} action: {intent} with params: {params}")
        
        # Clean parameters for enrollment actions (admission number extraction)
        if handler_type == "enrollment":
            params = _clean_enrollment_params(params)
            logger.info(f"Cleaned enrollment params: {params}")
        
        # CRITICAL: Pass original message to handler for fallback extraction
        # Check if handler supports original_message parameter
        action_response = None
        try:
            # Try calling with original_message parameter (for enhanced handlers)
            action_response = await handler.execute_action(
                intent=intent_enum,
                parameters=params,
                original_message=message  # Pass original message for fallback
            )
        except TypeError:
            # Fallback to old signature if handler doesn't support original_message
            logger.debug(f"Handler doesn't support original_message parameter, using basic call")
            action_response = await handler.execute_action(
                intent=intent_enum,
                parameters=params
            )
        
        formatted_message = formatter(action_response)
        
        logger.info(f"Action executed: success={action_response.success}, handler={handler_type}")
        
        return {
            "intent": intent,
            "thought": thought,
            "formatted": formatted_message,
            "raw_response": action_response.dict(),
            "confidence": confidence,
            "action_taken": action_response.action if action_response.success else None,
            "data": action_response.data,
            "suggestions": _generate_suggestions(intent, action_response.success),
            "metadata": action_response.metadata,
            "is_general": False,
            "handler_type": handler_type
        }
        
    except Exception as e:
        logger.error(f"Error in AI orchestrator: {e}", exc_info=True)
        
        return {
            "intent": "error",
            "thought": f"An error occurred: {str(e)}",
            "formatted": "I'm sorry, I encountered an error processing your request. Please try again or rephrase your question.",
            "raw_response": None,
            "confidence": 0.0,
            "action_taken": None,
            "data": None,
            "error": str(e),
            "suggestions": [
                "Try: 'What can you help me with?'",
                "Ask: 'Show me all students'"
            ]
        }


# ============================================================================
# Helper Functions
# ============================================================================

def _generate_suggestions(intent: str, success: bool) -> list:
    """Generate helpful suggestions based on intent and success"""
    
    if not success:
        return [
            "Try rephrasing your request",
            "Check if you provided all required information",
            "Ask for help with: 'What can you do?'"
        ]
    
    # Success suggestions based on intent category
    suggestions_map = {
        # Student intents
        "create_student": [
            "Enroll this student in a class",
            "View all students",
            "Add another student"
        ],
        "list_students": [
            "Get details about a specific student",
            "Show unassigned students",
            "Create a new student"
        ],
        "get_student": [
            "Update this student's information",
            "Enroll student in a class",
            "View all students"
        ],
        "update_student": [
            "View updated student details",
            "List all students",
            "Update another student"
        ],
        "get_unassigned_students": [
            "Enroll a student",
            "View student details",
            "Create a new student"
        ],
        "search_students": [
            "Get details about found students",
            "View all students",
            "Create a new student"
        ],
        "delete_student": [
            "View remaining students",
            "Create a new student",
            "Show unassigned students"
        ],
        
        # Enrollment intents
        "enroll_student": [
            "Check enrollment status",
            "View enrolled students",
            "Enroll another student"
        ],
        "get_enrollment": [
            "Enroll student in a class",
            "View all enrollments",
            "Check another student"
        ],
        "list_enrollments": [
            "Enroll a student",
            "View class details",
            "Show unassigned students"
        ],
        "transfer_student": [
            "View student details",
            "Check enrollment status",
            "Transfer another student"
        ],
        "bulk_enroll": [
            "View enrolled students",
            "Check class roster",
            "Enroll more students"
        ],
        "unenroll_student": [
            "View student details",
            "Check unassigned students",
            "Enroll in different class"
        ],
        
        # Class intents
        "create_class": [
            "Add students to this class",
            "View all classes",
            "Create another class"
        ],
        "list_classes": [
            "Get details about a specific class",
            "Show empty classes",
            "Create a new class"
        ],
        "list_empty_classes": [
            "Enroll students in empty classes",
            "View all classes",
            "Delete unused classes"
        ],
        "get_class_detail": [
            "Update this class",
            "View students in class",
            "List all classes"
        ],
        "update_class": [
            "View updated class details",
            "Add students to class",
            "List all classes"
        ],
        "delete_class": [
            "View remaining classes",
            "Create a new class",
            "List all classes"
        ],
        
        # School intents
        "get_school": [
            "Update school information",
            "View school statistics",
            "List all classes"
        ],
        "update_school": [
            "View updated school details",
            "Show school statistics",
            "List students"
        ],
        "get_school_stats": [
            "View detailed class breakdown",
            "Show all students",
            "Update school information"
        ],
        
        # Academic intents - Academic Years
        "create_academic_year": [
            "Activate this academic year",
            "Create terms for this year",
            "View all academic years"
        ],
        "list_academic_years": [
            "Create a new academic year",
            "Activate a specific year",
            "View current academic year"
        ],
        "get_academic_year": [
            "View terms in this year",
            "Activate this year",
            "Update academic year details"
        ],
        "get_current_academic_year": [
            "Create terms for this year",
            "View academic status",
            "List all academic years"
        ],
        "activate_academic_year": [
            "Create terms for this year",
            "Check academic status",
            "Enroll students"
        ],
        "update_academic_year": [
            "View updated details",
            "Create terms",
            "List all academic years"
        ],
        
        # Academic intents - Terms
        "create_term": [
            "Activate this term",
            "List all terms",
            "View current term"
        ],
        "list_terms": [
            "Create a new term",
            "Activate a specific term",
            "View current term"
        ],
        "get_term": [
            "View exams in this term",
            "Activate this term",
            "Update term details"
        ],
        "get_current_term": [
            "Enroll students",
            "List enrollments",
            "Check academic status"
        ],
        "activate_term": [
            "Enroll students in classes",
            "View enrolled students",
            "Check academic status"
        ],
        "update_term": [
            "View updated details",
            "Create exams",
            "List all terms"
        ],
        "complete_term": [
            "Create next term",
            "Promote students",
            "View academic status"
        ],
        
        # Academic intents - Subjects
        "create_subject": [
            "Assign subject to a class",
            "Create another subject",
            "View all subjects"
        ],
        "list_subjects": [
            "Create a new subject",
            "View subject details",
            "Assign subjects to classes"
        ],
        "get_subject": [
            "Update subject details",
            "View classes teaching this subject",
            "List all subjects"
        ],
        "update_subject": [
            "View updated details",
            "Assign to classes",
            "List all subjects"
        ],
        "delete_subject": [
            "View remaining subjects",
            "Create a new subject",
            "List all subjects"
        ],
        "assign_subject_to_class": [
            "View class subjects",
            "Assign another subject",
            "List all subjects"
        ],
        "list_class_subjects": [
            "Assign new subject to class",
            "View subject details",
            "Update class information"
        ],
        
        # Academic intents - Exams
        "create_exam": [
            "Record grades for this exam",
            "View exam details",
            "List all exams"
        ],
        "list_exams": [
            "Create a new exam",
            "View exam results",
            "Record grades"
        ],
        "get_exam": [
            "Record grades for this exam",
            "Update exam details",
            "View exam results"
        ],
        "update_exam": [
            "View updated details",
            "Record grades",
            "List all exams"
        ],
        "delete_exam": [
            "View remaining exams",
            "Create a new exam",
            "List all exams"
        ],
        
        # Academic intents - Grades
        "record_grade": [
            "View student's grades",
            "Record another grade",
            "Generate report card"
        ],
        "bulk_record_grades": [
            "View exam results",
            "Generate report cards",
            "List student grades"
        ],
        "get_student_grades": [
            "Record new grades",
            "Generate report card",
            "View term performance"
        ],
        "get_exam_results": [
            "Record grades for students",
            "Generate class report",
            "View student performance"
        ],
        "update_grade": [
            "View updated grades",
            "Generate report card",
            "List student grades"
        ],
        "delete_grade": [
            "Record correct grade",
            "View remaining grades",
            "Generate report card"
        ],
        
        # Academic intents - Reports
        "generate_report_card": [
            "View student performance",
            "Generate class report",
            "Record more grades"
        ],
        "generate_class_report": [
            "View individual report cards",
            "Generate term report",
            "View class performance"
        ],
        "generate_term_report": [
            "View class reports",
            "Generate report cards",
            "View academic status"
        ],
        
        # Academic intents - Setup & Status
        "get_academic_status": [
            "Setup academic structure",
            "Create academic year",
            "Create term"
        ],
        "get_current_setup": [
            "Setup academic structure",
            "Activate academic year",
            "Activate term"
        ],
        "setup_academic_structure": [
            "Create classes",
            "Enroll students",
            "View academic status"
        ]
    }
    
    return suggestions_map.get(intent, [
        "Ask me about students, classes, or school info",
        "Get help with: 'What can you help me with?'"
    ])


async def check_mistral_health() -> Dict[str, Any]:
    """Check if Mistral/Ollama is available and responsive"""
    try:
        client = get_mistral_client()
        is_healthy = await client.health_check()
        
        if is_healthy:
            models = await client.list_models()
            return {
                "status": "healthy",
                "mistral_available": True,
                "model": client.model,
                "available_models": models,
                "message": "Mistral is ready. All handlers (enrollment, student, class, school) are active with anti-hallucination protection."
            }
        else:
            return {
                "status": "degraded",
                "mistral_available": False,
                "model": client.model,
                "available_models": [],
                "message": "Mistral unavailable, but general intents still work. Business actions use keyword fallback with parameter extraction."
            }
    
    except Exception as e:
        logger.error(f"Mistral health check failed: {e}")
        return {
            "status": "degraded",
            "mistral_available": False,
            "model": "unknown",
            "available_models": [],
            "error": str(e),
            "message": "Mistral unavailable. General intents and keyword-based fallback with regex extraction are active."
        }