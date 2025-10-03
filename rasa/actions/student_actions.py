# rasa/actions/student_actions.py
"""
Student and Academic Management Actions for Rasa Chatbot
Handles student creation, enrollment, class management, and academic year/term operations
"""

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
from rasa_sdk.forms import FormValidationAction
from rasa_sdk.types import DomainDict
import requests
import logging
import re
from datetime import datetime
from typing import Dict, Text, Any, List

logger = logging.getLogger(__name__)

# Configuration - should match your FastAPI setup
FASTAPI_BASE_URL = "http://127.0.0.1:8000/api"


def normalize_class_name(class_name: str) -> str:
    """Normalize class name for consistency"""
    if not class_name:
        return class_name
    
    class_name = class_name.strip()
    
    # Handle grade/form patterns with letter suffixes
    grade_pattern = r'^(grade|form|jss|pp|class)\s*(\d+)([a-zA-Z])$'
    match = re.match(grade_pattern, class_name, re.IGNORECASE)
    if match:
        prefix, number, letter = match.groups()
        return f"{prefix.title()} {number}{letter.upper()}"
    
    # Handle simple patterns like "8a" -> "8A"
    simple_pattern = r'^(\d+)([a-zA-Z])$'
    match = re.match(simple_pattern, class_name, re.IGNORECASE)
    if match:
        number, letter = match.groups()
        return f"{number}{letter.upper()}"
    
    # Default: title case
    return class_name.title()


class ActionCreateStudent(Action):
    def name(self) -> Text:
        return "action_create_student"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required. Please log in first.")
            return []
        
        admission_no = tracker.get_slot("admission_no")
        student_name = tracker.get_slot("student_name")
        class_name = tracker.get_slot("class_name")
        
        logger.info(f"Creating student - Admission: {admission_no}, Name: {student_name}, Class: {class_name}")
        
        if not student_name or not class_name or not admission_no:
            dispatcher.utter_message(
                text="Missing required information. Please provide student name, admission number, and class."
            )
            return []
        
        if class_name:
            class_name = normalize_class_name(class_name)
        
        name_parts = student_name.strip().split()
        if len(name_parts) == 1:
            first_name = name_parts[0]
            last_name = ""
        else:
            first_name = name_parts[0]
            last_name = " ".join(name_parts[1:])
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
                "X-School-ID": school_id
            }
            
            academic_setup_response = requests.get(
                f"{FASTAPI_BASE_URL}/academic/current-setup",
                headers=headers
            )
            
            if academic_setup_response.status_code != 200:
                lines = [
                    "```",
                    "⚠️  ACADEMIC SETUP REQUIRED",
                    "══════════════════════════════",
                    "",
                    "Cannot create students without proper academic setup.",
                    "",
                    "Required Steps:",
                    "1. 'create academic year 2025'",
                    "2. 'create term 1'",
                    "",
                    "Then try creating the student again.",
                    "```"
                ]
                dispatcher.utter_message(text="\n".join(lines))
                return [
                    SlotSet("admission_no", None),
                    SlotSet("student_name", None),
                    SlotSet("class_name", None)
                ]
            
            setup_data = academic_setup_response.json()
            
            if not setup_data.get("setup_complete"):
                missing_items = []
                next_steps = []
                
                if not setup_data.get("current_year"):
                    missing_items.append("Academic Year")
                    next_steps.append("'create academic year 2025'")
                
                if not setup_data.get("current_term"):
                    missing_items.append("Academic Term")
                    next_steps.append("'create term 1'")
                
                lines = [
                    "```",
                    "⚠️  ACADEMIC SETUP INCOMPLETE",
                    "═════════════════════════════",
                    "",
                    f"Missing: {' and '.join(missing_items)}",
                    "",
                    "Required Steps:"
                ]
                for i, step in enumerate(next_steps, 1):
                    lines.append(f"{i}. {step}")
                lines.extend([
                    "",
                    "Check status: 'check academic setup'",
                    "```"
                ])
                
                dispatcher.utter_message(text="\n".join(lines))
                return [
                    SlotSet("admission_no", None),
                    SlotSet("student_name", None),
                    SlotSet("class_name", None)
                ]
            
            current_year = setup_data["current_year"]["year"]
            current_term = setup_data["current_term"]["title"]
            current_year_id = setup_data["current_year"]["id"]
            current_term_id = setup_data["current_term"]["id"]
            
            class_response = requests.get(
                f"{FASTAPI_BASE_URL}/classes",
                headers=headers,
                params={"search": class_name}
            )
            
            if class_response.status_code != 200:
                dispatcher.utter_message(text="Error checking classes. Please try again.")
                return [
                    SlotSet("admission_no", None),
                    SlotSet("student_name", None),
                    SlotSet("class_name", None)
                ]
            
            classes_data = class_response.json()
            matching_class = None
            class_was_created = False
            
            for cls in classes_data.get("classes", []):
                cls_name_normalized = normalize_class_name(cls["name"])
                if (cls_name_normalized.lower() == class_name.lower() and 
                    cls["academic_year"] == current_year):
                    matching_class = cls
                    break
            
            if not matching_class:
                logger.info(f"Class '{class_name}' not found for {current_year}, creating it automatically")
                
                class_payload = {
                    "name": class_name,
                    "level": class_name,
                    "academic_year": current_year
                }
                
                create_class_response = requests.post(
                    f"{FASTAPI_BASE_URL}/classes",
                    json=class_payload,
                    headers=headers
                )
                
                if create_class_response.status_code == 201:
                    matching_class = create_class_response.json()
                    class_was_created = True
                    logger.info(f"Class '{class_name}' created for {current_year}")
                else:
                    dispatcher.utter_message(
                        text=f"Could not create class '{class_name}' for {current_year}. "
                             f"Please create the class manually first."
                    )
                    return [
                        SlotSet("admission_no", None),
                        SlotSet("student_name", None),
                        SlotSet("class_name", None)
                    ]
            
            student_payload = {
                "admission_no": admission_no,
                "first_name": first_name,
                "last_name": last_name,
                "class_id": matching_class["id"]
            }
            
            logger.info(f"Student payload: {student_payload}")
            
            response = requests.post(
                f"{FASTAPI_BASE_URL}/students",
                json=student_payload,
                headers=headers
            )
            
            logger.info(f"Create student response: {response.status_code} - {response.text}")
            
            if response.status_code == 201:
                student_data = response.json()
                
                lines = [
                    "```",
                    "✅ STUDENT CREATED SUCCESSFULLY",
                    "════════════════════════════════",
                    "",
                    f"Academic Context: {current_year} ({current_term})",
                    "",
                    "Student Details:",
                    f"  • Name: {first_name} {last_name}",
                    f"  • Admission #: {student_data.get('admission_no', admission_no)}",
                    f"  • Class: {class_name}",
                    f"  • Term: {current_term}",
                ]
                
                if class_was_created:
                    lines.extend([
                        "",
                        f"Note: Class '{class_name}' was created automatically for {current_year}."
                    ])
                
                lines.extend([
                    "",
                    "The student is now enrolled for the current term.",
                    "```"
                ])
                
                dispatcher.utter_message(text="\n".join(lines))
                
                return [
                    SlotSet("admission_no", None),
                    SlotSet("student_name", None),
                    SlotSet("class_name", None)
                ]
            
            elif response.status_code == 409:
                lines = [
                    "```",
                    "❌ DUPLICATE ADMISSION NUMBER",
                    "══════════════════════════════",
                    "",
                    f"A student with admission number {admission_no} already exists.",
                    "Please use a different admission number.",
                    "```"
                ]
                dispatcher.utter_message(text="\n".join(lines))
            elif response.status_code == 422:
                try:
                    error_data = response.json()
                    lines = [
                        "```",
                        "❌ VALIDATION ERROR",
                        "═══════════════════",
                        "",
                        "Invalid data provided.",
                        f"Details: {error_data.get('detail', 'Unknown validation error')}",
                        "```"
                    ]
                    dispatcher.utter_message(text="\n".join(lines))
                except:
                    dispatcher.utter_message(text="```\n❌ Cannot create student: Invalid data provided.\n```")
            elif response.status_code == 400:
                try:
                    error_data = response.json()
                    error_detail = error_data.get('detail', 'Bad request')
                    lines = [
                        "```",
                        "❌ ERROR",
                        "═════════",
                        "",
                        error_detail,
                        "```"
                    ]
                    dispatcher.utter_message(text="\n".join(lines))
                except:
                    dispatcher.utter_message(text="```\n❌ Cannot create student: Invalid data provided.\n```")
            elif response.status_code == 403:
                lines = [
                    "```",
                    "❌ PERMISSION DENIED",
                    "════════════════════",
                    "",
                    "You don't have permission to create students.",
                    "Please contact an administrator.",
                    "```"
                ]
                dispatcher.utter_message(text="\n".join(lines))
            else:
                error_msg = "Failed to create student."
                try:
                    error_data = response.json()
                    if "detail" in error_data:
                        error_msg = f"Error: {error_data['detail']}"
                except:
                    pass
                dispatcher.utter_message(text=f"```\n❌ {error_msg}\n```")
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating student: {e}")
            lines = [
                "```",
                "❌ CONNECTION ERROR",
                "═══════════════════",
                "",
                "Having trouble connecting to the system.",
                "Please try again in a moment.",
                "```"
            ]
            dispatcher.utter_message(text="\n".join(lines))
        except Exception as e:
            logger.error(f"Unexpected error in ActionCreateStudent: {e}")
            dispatcher.utter_message(text="```\n❌ An unexpected error occurred. Please try again.\n```")
        
        return [
            SlotSet("admission_no", None),
            SlotSet("student_name", None),
            SlotSet("class_name", None)
        ]


class ActionListStudents(Action):
    def name(self) -> Text:
        return "action_list_students"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required. Please log in first.")
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
                "X-School-ID": school_id
            }
            
            response = requests.get(
                f"{FASTAPI_BASE_URL}/students",
                headers=headers,
                params={"limit": 15}
            )
            
            if response.status_code == 200:
                data = response.json()
                students = data.get("students", [])
                
                if not students:
                    dispatcher.utter_message(text="No students found in the system.")
                    return []
                
                # Get current academic info
                setup_response = requests.get(
                    f"{FASTAPI_BASE_URL}/academic/current-setup",
                    headers=headers
                )
                
                current_term_info = ""
                if setup_response.status_code == 200:
                    setup_data = setup_response.json()
                    if setup_data.get("current_term"):
                        current_term_info = f" - {setup_data['current_term']['title']} {setup_data['current_year']['year']}"
                
                # Build markdown list with proper formatting
                lines = [
                    f"### Student List{current_term_info}",
                    ""  # CRITICAL: Empty line after header
                ]
                
                for i, student in enumerate(students, 1):
                    full_name = f"{student['first_name']} {student['last_name']}".strip()
                    class_name = student.get('class_name', 'No class assigned')
                    lines.append(f"{i}. **{full_name}** (#{student['admission_no']}) — {class_name}")
                
                total = data.get("total", len(students))
                lines.append("")  # Empty line before total
                lines.append(f"**Total:** {total} student{'s' if total != 1 else ''}")
                
                if total > 15:
                    lines.append("")
                    lines.append("*(Showing first 15 students)*")
                
                student_list = "\n".join(lines)
                dispatcher.utter_message(text=student_list)
                
            elif response.status_code == 403:
                dispatcher.utter_message(text="You don't have permission to view students. Please contact an administrator.")
            else:
                dispatcher.utter_message(text="Could not retrieve the student list. Please try again.")
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error listing students: {e}")
            dispatcher.utter_message(
                text="Sorry, I'm having trouble connecting to the system. Please try again in a moment."
            )
        except Exception as e:
            logger.error(f"Unexpected error in ActionListStudents: {e}")
            dispatcher.utter_message(text="An unexpected error occurred. Please try again.")
        
        return []


class ActionListStudentsByClass(Action):
    def name(self) -> Text:
        return "action_list_students_by_class"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required. Please log in first.")
            return []
        
        class_name = tracker.get_slot("class_name")
        
        if not class_name:
            message_text = tracker.latest_message.get("text", "").lower()
            words = message_text.split()
            
            for i, word in enumerate(words):
                if word == "grade" and i + 1 < len(words) and words[i + 1].isdigit():
                    class_name = f"Grade {words[i + 1]}"
                    break
                elif word == "in" and i + 1 < len(words):
                    if i + 2 < len(words) and words[i + 1] in ["grade", "form", "jss", "pp"]:
                        class_name = f"{words[i + 1].title()} {words[i + 2]}"
                    else:
                        class_name = words[i + 1]
                    break
        
        if not class_name:
            dispatcher.utter_message(text="Please specify which class you want to see students for.")
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
                "X-School-ID": school_id
            }
            
            class_response = requests.get(
                f"{FASTAPI_BASE_URL}/classes",
                headers=headers
            )
            
            if class_response.status_code != 200:
                dispatcher.utter_message(text="Sorry, I couldn't retrieve class information.")
                return []
            
            classes_data = class_response.json()
            all_classes = classes_data.get("classes", [])
            
            exact_matches = []
            partial_matches = []
            
            for cls in all_classes:
                cls_name = cls["name"].lower()
                search_name = class_name.lower()
                
                if cls_name == search_name:
                    exact_matches.append(cls)
                elif search_name in cls_name or cls_name in search_name:
                    partial_matches.append(cls)
            
            matching_classes = exact_matches or partial_matches
            
            if not matching_classes:
                dispatcher.utter_message(text=f"No classes found matching '{class_name}'.")
                return []
            
            if len(matching_classes) == 1:
                cls = matching_classes[0]
                
                students_response = requests.get(
                    f"{FASTAPI_BASE_URL}/students",
                    headers=headers,
                    params={"class_id": cls["id"], "limit": 50}
                )
                
                if students_response.status_code == 200:
                    data = students_response.json()
                    students = data.get("students", [])
                    
                    if not students:
                        dispatcher.utter_message(text=f"No students found in {cls['name']}.")
                        return []
                    
                    # CORRECT FORMAT: Header, blank line, subtitle, blank line, then list
                    student_list = f"### Students in {cls['name']}\n\n*Academic Year {cls['academic_year']}*\n\n"
                    
                    for i, student in enumerate(students, 1):
                        full_name = f"{student['first_name']} {student['last_name']}".strip()
                        student_list += f"{i}. **{full_name}** (#{student['admission_no']})\n"
                    
                    total = data.get('total', len(students))
                    student_list += f"\n**Total:** {total} student{'s' if total != 1 else ''}"
                    
                    if total > 50:
                        student_list += "\n\n*(Showing first 50 students)*"
                    
                    dispatcher.utter_message(text=student_list)
                else:
                    dispatcher.utter_message(text="Sorry, I couldn't retrieve students for this class.")
            
            else:
                # Multiple classes
                msg = f"### Classes matching '{class_name}'\n\n*Found {len(matching_classes)} classes*\n\n"
                
                total_students = 0
                for i, cls in enumerate(matching_classes, 1):
                    student_count = cls.get("student_count", 0)
                    total_students += student_count
                    msg += f"{i}. **{cls['name']}** ({cls['academic_year']}) — {student_count} student{'s' if student_count != 1 else ''}\n"
                
                msg += f"\n**Total:** {total_students} students"
                dispatcher.utter_message(text=msg)
                
        except Exception as e:
            logger.error(f"Error listing students by class: {e}")
            dispatcher.utter_message(text="An error occurred.")
        
        return []


class ActionSearchStudent(Action):
    def name(self) -> Text:
        return "action_search_student"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required. Please log in first.")
            return []
        
        student_query = tracker.get_slot("student_query")
        
        if not student_query:
            message_text = tracker.latest_message.get("text", "")
            text_lower = message_text.lower()
            
            triggers = [
                "get information about ", "information about ", "about ",
                "student ", "find student ", "search for ", "search ",
                "find ", "look for ", "details for ", "show me "
            ]
            
            query_part = message_text
            for trigger in triggers:
                if trigger in text_lower:
                    pos = text_lower.find(trigger)
                    query_part = message_text[pos + len(trigger):].strip()
                    break
            
            student_query = query_part.strip()
        
        if not student_query:
            dispatcher.utter_message(
                text="Please specify which student you're looking for. You can search by name or admission number."
            )
            return []
        
        query = student_query.strip().replace("#", "")
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
                "X-School-ID": school_id
            }
            
            is_admission_search = query.isdigit()
            
            if is_admission_search:
                search_params = {"admission_no": query}
                
                students_response = requests.get(
                    f"{FASTAPI_BASE_URL}/students",
                    headers=headers,
                    params=search_params
                )
                
                if students_response.status_code == 200:
                    data = students_response.json()
                    students = data.get("students", [])
                    
                    exact_match = None
                    for student in students:
                        if student['admission_no'] == query:
                            exact_match = student
                            break
                    
                    if exact_match:
                        full_name = f"{exact_match['first_name']} {exact_match['last_name']}".strip()
                        
                        lines = [
                            "```",
                            "👤 STUDENT DETAILS",
                            "══════════════════",
                            "",
                            f"Name: {full_name}",
                            f"Admission #: {exact_match['admission_no']}",
                            f"Class: {exact_match.get('class_name', 'Not assigned')}",
                        ]
                        
                        if exact_match.get('gender'):
                            lines.append(f"Gender: {exact_match['gender']}")
                        
                        if exact_match.get('dob'):
                            lines.append(f"Date of Birth: {exact_match['dob']}")
                        
                        lines.extend([
                            f"Status: {exact_match['status']}",
                            f"Enrolled: {exact_match['created_at'][:10]}",
                            "```"
                        ])
                        
                        dispatcher.utter_message(text="\n".join(lines))
                    else:
                        dispatcher.utter_message(text=f"```\n❌ No student found with admission #{query}.\n```")
                else:
                    dispatcher.utter_message(text=f"```\n❌ No student found with admission #{query}.\n```")
            
            else:
                search_params = {"search": query}
                
                students_response = requests.get(
                    f"{FASTAPI_BASE_URL}/students",
                    headers=headers,
                    params=search_params
                )
                
                if students_response.status_code == 200:
                    data = students_response.json()
                    students = data.get("students", [])
                    
                    if not students:
                        dispatcher.utter_message(text=f"```\n❌ No students found matching '{query}'.\n```")
                    elif len(students) == 1:
                        student = students[0]
                        full_name = f"{student['first_name']} {student['last_name']}".strip()
                        
                        lines = [
                            "```",
                            "👤 STUDENT DETAILS",
                            "══════════════════",
                            "",
                            f"Name: {full_name}",
                            f"Admission #: {student['admission_no']}",
                            f"Class: {student.get('class_name', 'Not assigned')}",
                        ]
                        
                        if student.get('gender'):
                            lines.append(f"Gender: {student['gender']}")
                        
                        if student.get('dob'):
                            lines.append(f"Date of Birth: {student['dob']}")
                        
                        lines.extend([
                            f"Status: {student['status']}",
                            f"Enrolled: {student['created_at'][:10]}",
                            "```"
                        ])
                        
                        dispatcher.utter_message(text="\n".join(lines))
                    else:
                        lines = [
                            f"Here are students matching '{query}':",
                            "",
                            "```",
                            "🔍 SEARCH RESULTS",
                            "══════════════════════════════════════════════════",
                            ""
                        ]
                        
                        for i, student in enumerate(students[:20], 1):
                            full_name = f"{student['first_name']} {student['last_name']}".strip()
                            class_name = student.get('class_name', 'No class')
                            lines.append(f"{i}. {full_name} (#{student['admission_no']}) — {class_name}")
                        
                        if len(students) > 20:
                            lines.append(f"")
                            lines.append(f"... and {len(students) - 20} more students")
                        
                        lines.extend([
                            "",
                            f"Total: {len(students)} students",
                            "",
                            "To see details, search by admission number",
                            "```"
                        ])
                        
                        dispatcher.utter_message(text="\n".join(lines))
                else:
                    dispatcher.utter_message(text=f"```\n❌ No students found matching '{query}'.\n```")
        
        except Exception as e:
            logger.error(f"Error in ActionSearchStudent: {e}")
            dispatcher.utter_message(text="```\n❌ An error occurred while searching.\n```")
        
        return []


class ActionListUnassignedStudents(Action):
    def name(self) -> Text:
        return "action_list_unassigned_students"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required. Please log in first.")
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
                "X-School-ID": school_id
            }
            
            setup_response = requests.get(
                f"{FASTAPI_BASE_URL}/academic/current-setup",
                headers=headers
            )
            
            if setup_response.status_code != 200:
                dispatcher.utter_message(
                    text="Cannot check unassigned students: Academic system not set up properly."
                )
                return []
            
            setup_data = setup_response.json()
            if not setup_data.get("setup_complete"):
                dispatcher.utter_message(
                    text="Cannot check unassigned students: No current academic term found. Please set up academic year and terms first."
                )
                return []
            
            current_term = setup_data["current_term"]["title"]
            current_year = setup_data["current_year"]["year"]
            current_term_state = setup_data["current_term"]["state"]
            
            response = requests.get(
                f"{FASTAPI_BASE_URL}/students/unassigned/current-term",
                headers=headers,
                params={"limit": 20}
            )
            
            if response.status_code == 200:
                data = response.json()
                students = data.get("students", [])
                
                if not students:
                    dispatcher.utter_message(
                        text=f"All students are enrolled for {current_term} ({current_year})! No unassigned students found."
                    )
                    return []
                
                # Build text ensuring ALL sections have proper newlines
                student_list = "**Unassigned Students**\n\n"
                student_list += f"{current_term} ({current_year})\n\n"
                
                for i, student in enumerate(students, 1):
                    full_name = f"{student['first_name']} {student['last_name']}".strip()
                    old_class = f" (was in {student['class_name']})" if student.get('class_name') else ""
                    student_list += f"{i}. {full_name} (#{student['admission_no']}){old_class}\n"
                
                total = data.get('total', len(students))
                student_list += f"\n**Total:** {total} student{'s' if total != 1 else ''} need{'s' if total == 1 else ''} enrollment\n\n"
                
                if data.get('total', len(students)) > 20:
                    student_list += "*(Showing first 20 students)*\n\n"
                
                # Add term state warning if needed
                if current_term_state == "PLANNED":
                    student_list += f"⚠️ **Note:** {current_term} is PLANNED. To activate for enrollment: 'activate term 3'\n\n"
                
                # Enhanced re-enrollment guidance with proper markdown list formatting
                student_list += f"\n**To re-enroll students for {current_term}:**\n\n"
                
                if len(students) > 0:
                    example_student = students[0]
                    example_name = f"{example_student['first_name']} {example_student['last_name']}"
                    example_class = example_student.get('class_name', '8A')
                    
                    # Use proper markdown list syntax (dash with space)
                    student_list += f"- enroll {example_name} in {example_class}\n"
                    student_list += f"- assign {example_student['admission_no']} to {example_class}\n"
                    student_list += f"- move {example_name} to Grade 4\n"
                    
                    if len(students) > 1:
                        second_student = students[1]
                        second_name = f"{second_student['first_name']} {second_student['last_name']}"
                        second_class = second_student.get('class_name', 'Form 1')
                        student_list += f"- assign {second_name} to {second_class}\n"
                    
                    student_list += "\n"
                
                student_list += f"You can also bulk enroll by saying: **'promote students to {current_term}'**"
                
                dispatcher.utter_message(text=student_list)
                
            elif response.status_code == 400:
                try:
                    error_data = response.json()
                    error_detail = error_data.get('detail', 'Cannot get unassigned students')
                    
                    if "term" in error_detail.lower():
                        dispatcher.utter_message(
                            text=f"Term issue detected: {error_detail}\n\n"
                                 f"Check academic setup with: 'check academic setup'\n"
                                 f"Or activate current term: 'activate term 3'"
                        )
                    else:
                        dispatcher.utter_message(text=f"Error: {error_detail}")
                except:
                    dispatcher.utter_message(
                        text="Cannot get unassigned students. Please check academic setup."
                    )
            elif response.status_code == 403:
                dispatcher.utter_message(
                    text="You don't have permission to view unassigned students. Please contact an administrator."
                )
            else:
                dispatcher.utter_message(
                    text="Sorry, I couldn't retrieve unassigned students. Please try again."
                )
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error listing unassigned students: {e}")
            dispatcher.utter_message(
                text="Sorry, I'm having trouble connecting to the system. Please try again in a moment."
            )
        except Exception as e:
            logger.error(f"Unexpected error in ActionListUnassignedStudents: {e}")
            dispatcher.utter_message(
                text="An unexpected error occurred. Please try again."
            )
        
        return []


class ActionAssignStudentToClass(Action):
    def name(self) -> Text:
        return "action_assign_student_to_class"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required. Please log in first.")
            return []
        
        pending_student_name = tracker.get_slot("pending_student_name")
        pending_admission_no = tracker.get_slot("pending_admission_no")
        class_name = tracker.get_slot("class_name")
        
        if not pending_student_name:
            dispatcher.utter_message(
                text="I don't see a student waiting for class assignment. "
                     "Please create a student first with: 'create student [name]'"
            )
            return []
        
        if not class_name:
            class_name = tracker.get_slot("pending_class_name")
            
            if not class_name:
                dispatcher.utter_message(
                    text=f"Please specify which class {pending_student_name} should join. "
                         "For example: 'Grade 4', '8A', 'Form 1', 'PP1'"
                )
                return []
        
        if class_name:
            class_name = normalize_class_name(class_name)
        
        if not pending_admission_no:
            dispatcher.utter_message(
                text=f"I need an admission number for {pending_student_name}.\n\n"
                     f"You can either:\n"
                     f"1. Provide a specific number: 'admission number 12345'\n"
                     f"2. Let me generate one automatically: 'auto generate' or 'generate admission number'\n\n"
                     f"What would you prefer?"
            )
            return [SlotSet("pending_class_name", class_name)]
        
        name_parts = pending_student_name.strip().split()
        if len(name_parts) == 1:
            first_name = name_parts[0]
            last_name = ""
        else:
            first_name = name_parts[0]
            last_name = " ".join(name_parts[1:])
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
                "X-School-ID": school_id
            }
            
            academic_setup_response = requests.get(
                f"{FASTAPI_BASE_URL}/academic/current-setup",
                headers=headers
            )
            
            if academic_setup_response.status_code != 200:
                dispatcher.utter_message(
                    text="Academic Setup Required\n\n"
                         "Cannot assign students without proper academic setup.\n\n"
                         "Please complete these steps first:\n"
                         "1. 'create academic year 2025'\n"
                         "2. 'create term 1'\n\n"
                         "Then try assigning the student again."
                )
                return []
            
            setup_data = academic_setup_response.json()
            
            if not setup_data.get("setup_complete"):
                missing_items = []
                next_steps = []
                
                if not setup_data.get("current_year"):
                    missing_items.append("Academic Year")
                    next_steps.append("'create academic year 2025'")
                
                if not setup_data.get("current_term"):
                    missing_items.append("Academic Term")
                    next_steps.append("'create term 1'")
                
                dispatcher.utter_message(
                    text=f"Academic Setup Incomplete\n\n"
                         f"Missing: {' and '.join(missing_items)}\n\n"
                         f"Required steps:\n"
                         f"{chr(10).join(f'- {step}' for step in next_steps)}\n\n"
                         f"Complete academic setup is required for student enrollment.\n"
                         f"Check status anytime with: 'check academic setup'"
                )
                return []
            
            current_year = setup_data["current_year"]["year"]
            current_term = setup_data["current_term"]["title"]
            
            class_response = requests.get(
                f"{FASTAPI_BASE_URL}/classes",
                headers=headers,
                params={"search": class_name}
            )
            
            if class_response.status_code != 200:
                dispatcher.utter_message(
                    text="Error checking classes. Please try again."
                )
                return []
            
            classes_data = class_response.json()
            matching_class = None
            class_was_created = False
            
            for cls in classes_data.get("classes", []):
                cls_name_normalized = normalize_class_name(cls["name"])
                if (cls_name_normalized.lower() == class_name.lower() and 
                    cls["academic_year"] == current_year):
                    matching_class = cls
                    break
            
            if not matching_class:
                logger.info(f"Class '{class_name}' not found for {current_year}, creating it automatically")
                
                class_payload = {
                    "name": class_name,
                    "level": class_name,
                    "academic_year": current_year
                }
                
                create_class_response = requests.post(
                    f"{FASTAPI_BASE_URL}/classes",
                    json=class_payload,
                    headers=headers
                )
                
                if create_class_response.status_code == 201:
                    matching_class = create_class_response.json()
                    class_was_created = True
                    logger.info(f"Class '{class_name}' created for {current_year}")
                else:
                    dispatcher.utter_message(
                        text=f"Could not create class '{class_name}' for {current_year}. "
                             f"Please create the class manually first."
                    )
                    return []
            
            student_payload = {
                "admission_no": pending_admission_no,
                "first_name": first_name,
                "last_name": last_name,
                "class_id": matching_class["id"]
            }
            
            logger.info(f"Student payload: {student_payload}")
            
            response = requests.post(
                f"{FASTAPI_BASE_URL}/students",
                json=student_payload,
                headers=headers
            )
            
            logger.info(f"Create student response: {response.status_code} - {response.text}")
            
            if response.status_code == 201:
                student_data = response.json()
                
                success_message = f"Student Created Successfully!\n\n"
                success_message += f"Academic Context: {current_year} ({current_term})\n"
                success_message += f"Student: {first_name} {last_name}\n"
                success_message += f"Admission #: {student_data.get('admission_no')}\n"
                success_message += f"Class: {class_name}\n"
                success_message += f"Term: {current_term}\n\n"
                
                if class_was_created:
                    success_message += f"Note: Class '{class_name}' was created automatically for {current_year}.\n"
                
                success_message += f"The student is now enrolled for the current term."
                
                dispatcher.utter_message(text=success_message)
                
                return [
                    SlotSet("pending_student_name", None),
                    SlotSet("pending_admission_no", None),
                    SlotSet("pending_class_name", None),
                    SlotSet("class_name", None),
                    SlotSet("student_name", None),
                    SlotSet("admission_no", None)
                ]
            
            elif response.status_code == 409:
                dispatcher.utter_message(
                    text=f"A student with admission number {pending_admission_no} already exists. "
                         f"Please provide a different admission number for {pending_student_name}."
                )
                return []
                
            elif response.status_code == 422:
                try:
                    error_data = response.json()
                    dispatcher.utter_message(
                        text=f"Cannot create student: Invalid data provided.\n"
                             f"Details: {error_data.get('detail', 'Unknown validation error')}"
                    )
                except:
                    dispatcher.utter_message(
                        text="Cannot create student: Invalid data provided."
                    )
            else:
                error_msg = "Failed to create student."
                try:
                    error_data = response.json()
                    if "detail" in error_data:
                        error_msg = f"Error: {error_data['detail']}"
                except:
                    pass
                dispatcher.utter_message(text=error_msg)
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating student: {e}")
            dispatcher.utter_message(
                text="Sorry, I'm having trouble connecting to the system. Please try again in a moment."
            )
        except Exception as e:
            logger.error(f"Unexpected error in ActionAssignStudentToClass: {e}")
            dispatcher.utter_message(
                text="An unexpected error occurred. Please try again."
            )
        
        return []


class ActionProvideAdmissionNumber(Action):
    def name(self) -> Text:
        return "action_provide_admission_number"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        admission_no = tracker.get_slot("admission_no")
        pending_student_name = tracker.get_slot("pending_student_name")
        
        if not pending_student_name:
            dispatcher.utter_message(
                text="I don't see a student creation in progress. Please start by creating a student first."
            )
            return []
        
        if not admission_no:
            dispatcher.utter_message(
                text="Please provide a valid admission number. For example: 'admission number 12345'"
            )
            return []
        
        dispatcher.utter_message(
            text=f"Admission number {admission_no} noted for {pending_student_name}. "
                 f"Now, which class should {pending_student_name} be enrolled in?"
        )
        
        return [SlotSet("pending_admission_no", admission_no)]


class ActionAutoGenerateAdmission(Action):
    def name(self) -> Text:
        return "action_auto_generate_admission"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        pending_student_name = tracker.get_slot("pending_student_name")
        
        if not pending_student_name:
            dispatcher.utter_message(
                text="I don't see a student creation in progress. Please start by creating a student first."
            )
            return []
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required. Please log in first.")
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
                "X-School-ID": school_id
            }
            
            students_response = requests.get(
                f"{FASTAPI_BASE_URL}/students?limit=1",
                headers=headers
            )
            
            if students_response.status_code == 200:
                generated_admission_no = str(int(datetime.now().timestamp()))[-6:]
                
                dispatcher.utter_message(
                    text=f"Generated admission number {generated_admission_no} for {pending_student_name}. "
                         f"Now, which class should {pending_student_name} be enrolled in?"
                )
                
                return [SlotSet("pending_admission_no", generated_admission_no)]
            else:
                dispatcher.utter_message(
                    text="Could not generate admission number. Please provide one manually."
                )
                return []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error auto-generating admission number: {e}")
            dispatcher.utter_message(
                text="Sorry, I'm having trouble generating an admission number. Please provide one manually."
            )
            return []
        except Exception as e:
            logger.error(f"Unexpected error in ActionAutoGenerateAdmission: {e}")
            dispatcher.utter_message(
                text="An unexpected error occurred. Please provide an admission number manually."
            )
            return []


class ActionReenrollStudent(Action):
    def name(self) -> Text:
        return "action_reenroll_student"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required.")
            return []
        
        student_name = tracker.get_slot("student_name")
        admission_no = tracker.get_slot("admission_no")
        class_name = tracker.get_slot("class_name")
        
        if not (student_name or admission_no):
            dispatcher.utter_message(
                text="Please specify which student. Example:\n"
                     "'enroll Eric Mwirichia in 8A'"
            )
            return []
        
        if not class_name:
            dispatcher.utter_message(
                text="Please specify the class. Example:\n"
                     "'enroll Eric in 8A'"
            )
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "X-School-ID": school_id
            }
            
            # Find student
            search_params = {}
            if admission_no:
                clean_admission = str(admission_no).replace("#", "").strip()
                search_params["admission_no"] = clean_admission
            elif student_name:
                search_params["search"] = student_name
            
            students_response = requests.get(
                f"{FASTAPI_BASE_URL}/students",
                headers=headers,
                params=search_params
            )
            
            if students_response.status_code != 200:
                dispatcher.utter_message(text="Could not find student.")
                return []
            
            students = students_response.json().get("students", [])
            
            if not students:
                query = admission_no or student_name
                dispatcher.utter_message(text=f"No student found matching '{query}'.")
                return []
            
            if len(students) > 1:
                dispatcher.utter_message(text="Multiple students found. Please specify by admission number.")
                return []
            
            student = students[0]
            student_id = student["id"]
            
            # Find class
            classes_response = requests.get(
                f"{FASTAPI_BASE_URL}/classes",
                headers=headers,
                params={"search": class_name}
            )
            
            if classes_response.status_code != 200:
                dispatcher.utter_message(text="Could not find class.")
                return []
            
            classes = classes_response.json().get("classes", [])
            matching_class = None
            
            for cls in classes:
                if cls["name"].lower() == class_name.lower():
                    matching_class = cls
                    break
            
            if not matching_class:
                dispatcher.utter_message(
                    text=f"Class '{class_name}' not found.\n"
                         "Please check the class name and try again."
                )
                return []
            
            # Get current term
            term_response = requests.get(
                f"{FASTAPI_BASE_URL}/academic/current-term",
                headers=headers
            )
            
            if term_response.status_code != 200:
                dispatcher.utter_message(
                    text="No active term found.\n"
                         "Please activate a term first: 'activate term 3'"
                )
                return []
            
            term_data = term_response.json()
            term_id = term_data["id"]
            
            # Create enrollment
            enrollment_data = {
                "student_id": student_id,
                "class_id": matching_class["id"],
                "term_id": term_id
            }
            
            enroll_response = requests.post(
                f"{FASTAPI_BASE_URL}/enrollments",
                json=enrollment_data,
                headers=headers
            )
            
            if enroll_response.status_code in [200, 201]:
                full_name = f"{student['first_name']} {student['last_name']}"
                msg = f"✅ Student enrolled successfully!\n\n"
                msg += f"Student: {full_name} (#{student['admission_no']})\n"
                msg += f"Class: {matching_class['name']}\n"
                msg += f"Term: {term_data['title']}"
                
                dispatcher.utter_message(text=msg)
            else:
                error_data = enroll_response.json() if enroll_response.content else {}
                error_msg = error_data.get('detail', 'Failed to enroll student')
                
                if "already enrolled" in error_msg.lower():
                    dispatcher.utter_message(
                        text=f"{student['first_name']} {student['last_name']} is already enrolled in a class for this term."
                    )
                else:
                    dispatcher.utter_message(text=f"Error: {error_msg}")
        
        except Exception as e:
            logger.error(f"Error enrolling student: {e}", exc_info=True)
            dispatcher.utter_message(text="An error occurred while enrolling the student.")
        
        return [
            SlotSet("student_name", None),
            SlotSet("admission_no", None),
            SlotSet("class_name", None)
        ]


class ActionShowUnassignedStudents(Action):
    """Alias for ActionListUnassignedStudents"""
    def name(self) -> Text:
        return "action_show_unassigned_students"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        action = ActionListUnassignedStudents()
        return action.run(dispatcher, tracker, domain)


class ActionGetStudentDetails(Action):
    """Alias for ActionSearchStudent focusing on single results"""
    def name(self) -> Text:
        return "action_get_student_details"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        action = ActionSearchStudent()
        return action.run(dispatcher, tracker, domain)


class ValidateStudentCreationForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_student_creation_form"

    def validate_student_name(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate student name"""
        if not slot_value or len(str(slot_value).strip()) < 2:
            dispatcher.utter_message(text="Please provide a valid student name.")
            return {"student_name": None}
        return {"student_name": str(slot_value).strip()}

    def validate_admission_no(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate admission number"""
        
        if not slot_value:
            return {"admission_no": None}
        
        # Strip ALL # symbols from the beginning
        clean_value = str(slot_value).lstrip("#").strip()
        
        if clean_value.lower() in ["auto", "auto generate", "generate", "auto-generate"]:
            return {"admission_no": "AUTO_GENERATE"}
        
        if not clean_value.isdigit():
            dispatcher.utter_message(
                text="Admission number should be numeric. Please provide a valid number or say 'auto generate'."
            )
            return {"admission_no": None}
        
        return {"admission_no": clean_value}

    def validate_class_name(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Validate class name"""
        if not slot_value or len(str(slot_value).strip()) < 1:
            dispatcher.utter_message(text="Please provide a valid class name.")
            return {"class_name": None}
        return {"class_name": str(slot_value).strip()}
    
class ActionListStudentsWithBalances(Action):
    """Alias for listing students with outstanding balances"""
    def name(self) -> Text:
        return "action_list_students_with_balances"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        # Delegate to the unpaid invoices action
        action = ActionListUnpaidInvoices()
        return action.run(dispatcher, tracker, domain)