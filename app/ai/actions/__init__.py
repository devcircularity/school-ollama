# app/ai/actions/__init__.py
"""
AI Actions Module
Contains all action handlers for different domains
"""

from app.ai.actions.student_actions import (
    StudentActionsHandler,
    StudentIntent,
    ActionResponse as StudentActionResponse,
    detect_student_intent,
    format_response_for_chat as format_student_response
)

from app.ai.actions.class_actions import (
    ClassActionsHandler,
    ClassIntent,
    ActionResponse as ClassActionResponse,
    detect_class_intent,
    format_response_for_chat as format_class_response
)

from app.ai.actions.school_actions import (
    SchoolActionsHandler,
    SchoolIntent,
    ActionResponse as SchoolActionResponse,
    detect_school_intent,
    format_response_for_chat as format_school_response
)

from app.ai.actions.enrollment_actions import (
    EnrollmentActionsHandler,
    EnrollmentIntent,
    ActionResponse as EnrollmentActionResponse,
    detect_enrollment_intent,
    format_response_for_chat as format_enrollment_response
)

from app.ai.actions.general_actions import (
    detect_general_intent,
    respond_to_general_intent,
    is_general_conversation,
    get_help_text
)

__all__ = [
    # Student Actions
    "StudentActionsHandler",
    "StudentIntent",
    "StudentActionResponse",
    "detect_student_intent",
    "format_student_response",
    
    # Class Actions
    "ClassActionsHandler",
    "ClassIntent",
    "ClassActionResponse",
    "detect_class_intent",
    "format_class_response",
    
    # School Actions
    "SchoolActionsHandler",
    "SchoolIntent",
    "SchoolActionResponse",
    "detect_school_intent",
    "format_school_response",
    
    # Enrollment Actions
    "EnrollmentActionsHandler",
    "EnrollmentIntent",
    "EnrollmentActionResponse",
    "detect_enrollment_intent",
    "format_enrollment_response",
    
    # General Actions
    "detect_general_intent",
    "respond_to_general_intent",
    "is_general_conversation",
    "get_help_text",
]