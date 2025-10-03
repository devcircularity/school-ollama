# rasa/actions/academic_actions.py
"""
Academic Year, Term, and Class Management Actions for Rasa Chatbot
Handles academic years, terms, classes, and enrollment operations
"""

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet
import requests
import logging
from datetime import datetime
from typing import Dict, Text, Any, List
import re

logger = logging.getLogger(__name__)

# Configuration
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


class ActionCreateAcademicYear(Action):
    def name(self) -> Text:
        return "action_create_academic_year"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required. Please log in first.")
            return []
        
        academic_year = tracker.get_slot("academic_year")
        if not academic_year:
            academic_year = str(datetime.now().year)
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
                "X-School-ID": school_id
            }
            
            year_payload = {
                "year": int(academic_year),
                "title": f"Academic Year {academic_year}",
                "state": "active"
            }
            
            response = requests.post(
                f"{FASTAPI_BASE_URL}/academic/years",
                json=year_payload,
                headers=headers
            )
            
            if response.status_code == 201:
                dispatcher.utter_message(
                    text=f"Academic Year {academic_year} created successfully!\n\n"
                         f"Next step: Create terms for this academic year.\n"
                         f"Try: 'create term 1' or 'add term 1 to academic year {academic_year}'"
                )
            elif response.status_code == 409:
                dispatcher.utter_message(
                    text=f"Academic Year {academic_year} already exists.\n\n"
                         f"You can now create terms or check the academic setup status."
                )
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('detail', 'Failed to create academic year')
                dispatcher.utter_message(text=f"Error: {error_msg}")
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating academic year: {e}")
            dispatcher.utter_message(
                text="Sorry, I'm having trouble connecting to the system. Please try again in a moment."
            )
        except Exception as e:
            logger.error(f"Unexpected error in ActionCreateAcademicYear: {e}")
            dispatcher.utter_message(
                text="An unexpected error occurred. Please try again."
            )
        
        return [SlotSet("academic_year", None)]


class ActionCreateAcademicTerm(Action):
    def name(self) -> Text:
        return "action_create_academic_term"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required.")
            return []
        
        term = tracker.get_slot("term")
        academic_year = tracker.get_slot("academic_year")
        
        if not term:
            dispatcher.utter_message(
                text="Which term would you like to create? (1, 2, or 3)\n"
                     "Example: 'create term 1'"
            )
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "X-School-ID": school_id
            }
            
            # Get current academic year if not specified
            if not academic_year:
                current_year_response = requests.get(
                    f"{FASTAPI_BASE_URL}/academic/current-year",
                    headers=headers
                )
                
                if current_year_response.status_code == 200:
                    year_data = current_year_response.json()
                    academic_year = year_data.get("year")
                else:
                    dispatcher.utter_message(
                        text="No active academic year found.\n"
                             "Please create and activate an academic year first:\n"
                             "'create academic year 2025'"
                    )
                    return [SlotSet("term", None)]
            
            # Create the term
            term_data = {
                "term": int(term),
                "academic_year": int(academic_year),
                "title": f"Term {term}"
            }
            
            response = requests.post(
                f"{FASTAPI_BASE_URL}/academic/terms",
                json=term_data,
                headers=headers
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                
                msg = f"Term {term} created successfully for Academic Year {academic_year}!\n\n"
                
                # Check if there are any active terms
                terms_response = requests.get(
                    f"{FASTAPI_BASE_URL}/academic/terms?academic_year={academic_year}",
                    headers=headers
                )
                
                if terms_response.status_code == 200:
                    terms = terms_response.json().get("terms", [])
                    active_terms = [t for t in terms if t.get("state") == "ACTIVE"]
                    
                    if not active_terms:
                        msg += f"Term {term} is PLANNED (not yet started).\n"
                        msg += f"To activate it for enrollment: 'activate term {term}'"
                    else:
                        msg += "Academic setup is ready for class and student creation."
                else:
                    msg += "Academic setup is ready for class and student creation."
                
                dispatcher.utter_message(text=msg)
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('detail', 'Failed to create term')
                
                # Handle specific error cases
                if "Academic year" in error_msg and "is DRAFT" in error_msg:
                    dispatcher.utter_message(
                        text=f"Academic year {academic_year} is DRAFT.\n\n"
                             f"Terms can only be created in ACTIVE years. To activate:\n"
                             f"'activate academic year {academic_year}'"
                    )
                elif "Academic year" in error_msg and "is CLOSED" in error_msg:
                    dispatcher.utter_message(
                        text=f"Academic year {academic_year} is CLOSED.\n\n"
                             f"Cannot create terms in closed years. Create a new academic year:\n"
                             f"'create academic year {int(academic_year) + 1}'"
                    )
                elif "already exists" in error_msg.lower():
                    dispatcher.utter_message(
                        text=f"Term {term} already exists for Academic Year {academic_year}.\n\n"
                             f"To view all terms: 'list academic terms'"
                    )
                elif "not found" in error_msg.lower():
                    dispatcher.utter_message(
                        text=f"Academic year {academic_year} does not exist.\n\n"
                             f"Create it first: 'create academic year {academic_year}'"
                    )
                else:
                    dispatcher.utter_message(text=f"Error: {error_msg}")
        
        except Exception as e:
            logger.error(f"Error creating term: {e}", exc_info=True)
            dispatcher.utter_message(text="An error occurred while creating the term.")
        
        return [
            SlotSet("term", None),
            SlotSet("academic_year", None)
        ]


class ActionCheckAcademicSetup(Action):
    def name(self) -> Text:
        return "action_check_academic_setup"

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
                f"{FASTAPI_BASE_URL}/academic/current-setup",
                headers=headers
            )
            
            if response.status_code == 200:
                setup_data = response.json()
                
                if setup_data.get("setup_complete"):
                    current_year = setup_data["current_year"]
                    current_term = setup_data["current_term"]
                    
                    status_msg = f"Current Academic Setup:\n\n"
                    status_msg += f"Academic Year: {current_year['year']} ({current_year['state']})\n"
                    status_msg += f"Current Term: {current_term['title']} "
                    
                    if current_term['state'] == "ACTIVE":
                        status_msg += "(ACTIVE - enrollment open)\n"
                    elif current_term['state'] == "PLANNED":
                        status_msg += "(PLANNED - not yet started)\n"
                        status_msg += f"\n⚠️ Note: Term is planned but not active.\n"
                        status_msg += f"To activate for student enrollment: 'activate term {current_term['term']}'\n"
                    elif current_term['state'] == "COMPLETED":
                        status_msg += "(COMPLETED - term ended)\n"
                    
                    status_msg += f"\nSystem status: "
                    if current_term['state'] == "ACTIVE":
                        status_msg += "Ready for operations"
                    else:
                        status_msg += "Term activation required for enrollment"
                    
                    dispatcher.utter_message(text=status_msg)
                else:
                    current_year = setup_data.get("current_year")
                    current_term = setup_data.get("current_term")
                    
                    status_msg = "Current Academic Setup:\n\n"
                    
                    if current_year:
                        status_msg += f"Academic Year: {current_year['year']} ({current_year['state']})\n"
                    else:
                        status_msg += "Academic Year: Not set\n"
                    
                    if current_term:
                        status_msg += f"Current Term: {current_term['title']} ({current_term['state']})\n"
                    else:
                        status_msg += "Current Term: Not set\n"
                    
                    status_msg += "\n"
                    if not current_year:
                        status_msg += "To set up academic year: 'create academic year 2025'\n"
                    if current_year and not current_term:
                        status_msg += "To add terms: 'create term 1'"
                    
                    dispatcher.utter_message(text=status_msg)
            else:
                dispatcher.utter_message(
                    text="Unable to check academic setup status. Please try again."
                )
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking academic setup: {e}")
            dispatcher.utter_message(
                text="Sorry, I'm having trouble connecting to the system. Please try again in a moment."
            )
        except Exception as e:
            logger.error(f"Unexpected error in ActionCheckAcademicSetup: {e}")
            dispatcher.utter_message(
                text="An unexpected error occurred. Please try again."
            )
        
        return []


class ActionGetCurrentAcademicYear(Action):
    def name(self) -> Text:
        return "action_get_current_academic_year"

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
                f"{FASTAPI_BASE_URL}/academic/current-setup",
                headers=headers
            )
            
            if response.status_code == 200:
                setup_data = response.json()
                current_year = setup_data.get("current_year")
                
                if current_year and current_year.get("state") == "ACTIVE":
                    dispatcher.utter_message(
                        text=f"Current Academic Year: {current_year['year']} ({current_year['state']})"
                    )
                else:
                    years_response = requests.get(
                        f"{FASTAPI_BASE_URL}/academic/years",
                        headers=headers
                    )
                    
                    if years_response.status_code == 200:
                        years_data = years_response.json()
                        
                        if years_data:
                            draft_years = []
                            inactive_years = []
                            
                            for year in years_data:
                                if year["state"] == "DRAFT":
                                    draft_years.append(str(year["year"]))
                                elif year["state"] == "INACTIVE":
                                    inactive_years.append(str(year["year"]))
                            
                            message = "No ACTIVE academic year found.\n\n"
                            
                            if draft_years:
                                message += f"Draft years available: {', '.join(draft_years)}\n"
                            
                            if inactive_years:
                                message += f"Inactive years: {', '.join(inactive_years)}\n"
                            
                            if draft_years or inactive_years:
                                message += f"\nTo activate a year: 'activate academic year YYYY'"
                            else:
                                message += "No academic years found. Create one with: 'create academic year 2025'"
                            
                            dispatcher.utter_message(text=message)
                        else:
                            dispatcher.utter_message(
                                text="No academic years found in the system.\n\n"
                                     "Create one with: 'create academic year 2025'"
                            )
                    else:
                        dispatcher.utter_message(
                            text="No active academic year found.\n\n"
                                 "Create one with: 'create academic year 2025'"
                        )
            else:
                dispatcher.utter_message(
                    text="Unable to retrieve academic year information. Please try again."
                )
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting current academic year: {e}")
            dispatcher.utter_message(
                text="Sorry, I'm having trouble connecting to the system. Please try again in a moment."
            )
        except Exception as e:
            logger.error(f"Unexpected error in ActionGetCurrentAcademicYear: {e}")
            dispatcher.utter_message(
                text="An unexpected error occurred. Please try again."
            )
        
        return []


class ActionGetCurrentTerm(Action):
    def name(self) -> Text:
        return "action_get_current_term"

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
                f"{FASTAPI_BASE_URL}/academic/current-setup",
                headers=headers
            )
            
            if response.status_code == 200:
                setup_data = response.json()
                current_year = setup_data.get("current_year")
                current_term = setup_data.get("current_term")
                
                if current_term:
                    term_state = current_term['state']
                    
                    msg = f"Current Term: {current_term['title']} ({current_year['year']})\n"
                    msg += f"Status: {term_state}\n\n"
                    
                    if term_state == "ACTIVE":
                        msg += "✓ Enrollment is open\n"
                        msg += "✓ Students can be added and enrolled\n"
                        msg += "✓ Classes are running"
                    elif term_state == "PLANNED":
                        msg += "⚠️ Term is scheduled but not yet active\n"
                        msg += "• Students cannot be enrolled yet\n"
                        msg += f"• To activate: 'activate term {current_term['term']}'\n"
                        msg += "• Once activated, enrollment will open"
                    elif term_state == "COMPLETED":
                        msg += "✓ Term has ended\n"
                        msg += "• Enrollment is closed\n"
                        msg += "• Create next term to continue"
                    
                    dispatcher.utter_message(text=msg)
                elif current_year:
                    dispatcher.utter_message(
                        text=f"No term is currently set up for Academic Year {current_year['year']}.\n\n"
                             "To create one: 'create term 1'"
                    )
                else:
                    dispatcher.utter_message(
                        text="No academic year or term is set up.\n\n"
                             "First create an academic year: 'create academic year 2025'"
                    )
            else:
                dispatcher.utter_message(
                    text="Unable to retrieve term information. Please try again."
                )
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting current term: {e}")
            dispatcher.utter_message(
                text="Sorry, I'm having trouble connecting to the system. Please try again in a moment."
            )
        except Exception as e:
            logger.error(f"Unexpected error in ActionGetCurrentTerm: {e}")
            dispatcher.utter_message(
                text="An unexpected error occurred. Please try again."
            )
        
        return []


class ActionActivateAcademicYear(Action):
    def name(self) -> Text:
        return "action_activate_academic_year"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required. Please log in first.")
            return []
        
        academic_year = tracker.get_slot("academic_year")
        
        if not academic_year:
            dispatcher.utter_message(text="Please specify which academic year to activate. Example: 'activate academic year 2025'")
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
                "X-School-ID": school_id
            }
            
            years_response = requests.get(
                f"{FASTAPI_BASE_URL}/academic/years",
                headers=headers
            )
            
            if years_response.status_code != 200:
                dispatcher.utter_message(text="Could not retrieve academic years.")
                return []
            
            years = years_response.json()
            year_id = None
            year_found = None
            
            for year in years:
                if str(year["year"]) == str(academic_year):
                    year_id = year["id"]
                    year_found = year
                    break
            
            if not year_id:
                dispatcher.utter_message(text=f"Academic year {academic_year} not found.")
                return []
            
            if year_found["state"] == "ACTIVE":
                dispatcher.utter_message(text=f"Academic year {academic_year} is already active.")
                return []
            
            activate_response = requests.put(
                f"{FASTAPI_BASE_URL}/academic/years/{year_id}/activate",
                headers=headers
            )
            
            if activate_response.status_code == 200:
                dispatcher.utter_message(
                    text=f"Academic year {academic_year} activated successfully!\n\n"
                         f"This year is now the current active academic year.\n"
                         f"You can now create terms and enroll students."
                )
            else:
                error_data = activate_response.json() if activate_response.content else {}
                error_msg = error_data.get('detail', f'Failed to activate academic year {academic_year}')
                dispatcher.utter_message(text=f"Error: {error_msg}")
        
        except Exception as e:
            logger.error(f"Error activating academic year: {e}")
            dispatcher.utter_message(text="An error occurred while activating the academic year.")
        
        return [SlotSet("academic_year", None)]


class ActionDeactivateAcademicYear(Action):
    def name(self) -> Text:
        return "action_deactivate_academic_year"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required. Please log in first.")
            return []
        
        academic_year = tracker.get_slot("academic_year")
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
                "X-School-ID": school_id
            }
            
            if not academic_year:
                setup_response = requests.get(
                    f"{FASTAPI_BASE_URL}/academic/current-setup",
                    headers=headers
                )
                
                if setup_response.status_code == 200:
                    setup_data = setup_response.json()
                    current_year = setup_data.get("current_year")
                    if current_year:
                        academic_year = str(current_year["year"])
                        year_id = current_year["id"]
                    else:
                        dispatcher.utter_message(text="No active academic year found to deactivate.")
                        return []
                else:
                    dispatcher.utter_message(text="Could not check current academic setup.")
                    return []
            else:
                years_response = requests.get(
                    f"{FASTAPI_BASE_URL}/academic/years",
                    headers=headers
                )
                
                if years_response.status_code == 200:
                    years = years_response.json()
                    year_id = None
                    for year in years:
                        if str(year["year"]) == str(academic_year):
                            year_id = year["id"]
                            break
                    
                    if not year_id:
                        dispatcher.utter_message(text=f"Academic year {academic_year} not found.")
                        return []
                else:
                    dispatcher.utter_message(text="Could not retrieve academic years.")
                    return []
            
            deactivate_response = requests.put(
                f"{FASTAPI_BASE_URL}/academic/years/{year_id}/deactivate",
                headers=headers
            )
            
            if deactivate_response.status_code == 200:
                dispatcher.utter_message(
                    text=f"Academic year {academic_year} has been deactivated.\n\n"
                         f"Note: This will affect student enrollment and class operations.\n"
                         f"To reactivate, use: 'activate academic year {academic_year}'"
                )
            else:
                dispatcher.utter_message(text=f"Failed to deactivate academic year {academic_year}.")
        
        except Exception as e:
            logger.error(f"Error deactivating academic year: {e}")
            dispatcher.utter_message(text="An error occurred while deactivating the academic year.")
        
        return [SlotSet("academic_year", None)]


class ActionActivateTerm(Action):
    def name(self) -> Text:
        return "action_activate_term"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required. Please log in first.")
            return []
        
        term_number = tracker.get_slot("term")
        
        if not term_number:
            dispatcher.utter_message(text="Please specify which term to activate. Example: 'activate term 1'")
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "Content-Type": "application/json",
                "X-School-ID": school_id
            }
            
            setup_response = requests.get(f"{FASTAPI_BASE_URL}/academic/current-setup", headers=headers)
            
            if setup_response.status_code != 200:
                dispatcher.utter_message(text="Cannot check academic setup.")
                return []
            
            setup_data = setup_response.json()
            current_year = setup_data.get("current_year")
            
            if not current_year:
                dispatcher.utter_message(text="No active academic year found.")
                return []
            
            terms_response = requests.get(f"{FASTAPI_BASE_URL}/academic/years/{current_year['id']}/terms", headers=headers)
            
            if terms_response.status_code != 200:
                dispatcher.utter_message(text="Cannot retrieve terms.")
                return []
            
            terms = terms_response.json()
            target_term = None
            
            for term in terms:
                if str(term["term"]) == str(term_number):
                    target_term = term
                    break
            
            if not target_term:
                dispatcher.utter_message(text=f"Term {term_number} not found for {current_year['year']}.")
                return []
            
            activate_response = requests.put(f"{FASTAPI_BASE_URL}/academic/terms/{target_term['id']}/activate", headers=headers)
            
            if activate_response.status_code == 200:
                dispatcher.utter_message(
                    text=f"Term {term_number} activated successfully for {current_year['year']}!\n\n"
                         f"Students can now be enrolled and classes can begin."
                )
            else:
                dispatcher.utter_message(text=f"Failed to activate term {term_number}.")
        
        except Exception as e:
            logger.error(f"Error activating term: {e}")
            dispatcher.utter_message(text="An error occurred while activating the term.")
        
        return [SlotSet("term", None)]


class ActionListAcademicTerms(Action):
    def name(self) -> Text:
        return "action_list_academic_terms"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required. Please log in first.")
            return []
        
        academic_year = tracker.get_slot("academic_year")
        
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
                dispatcher.utter_message(text="Cannot retrieve academic setup.")
                return []
            
            setup_data = setup_response.json()
            current_year = setup_data.get("current_year")
            
            if not current_year:
                dispatcher.utter_message(text="No academic year found. Please create one first.")
                return []
            
            year_to_check = academic_year or str(current_year["year"])
            year_id = current_year["id"]
            
            terms_response = requests.get(
                f"{FASTAPI_BASE_URL}/academic/years/{year_id}/terms",
                headers=headers
            )
            
            if terms_response.status_code == 200:
                terms = terms_response.json()
                
                if not terms:
                    dispatcher.utter_message(
                        text=f"No terms found for Academic Year {year_to_check}.\n\n"
                             f"To create terms: 'create term 1', 'create term 2', etc."
                    )
                    return []
                
                terms_list = f"Academic Terms for {year_to_check}:\n\n"
                
                active_count = 0
                planned_count = 0
                completed_count = 0
                
                for term in terms:
                    state = term["state"].upper()
                    
                    if state == "ACTIVE":
                        indicator = "✓"
                        state_desc = "ACTIVE - enrollment open"
                        active_count += 1
                    elif state == "PLANNED":
                        indicator = "○"
                        state_desc = "PLANNED - not started"
                        planned_count += 1
                    elif state == "COMPLETED":
                        indicator = "✓"
                        state_desc = "COMPLETED - ended"
                        completed_count += 1
                    else:
                        indicator = "•"
                        state_desc = state
                    
                    terms_list += f"{indicator} Term {term['term']}: {term['title']} ({state_desc})\n"
                
                terms_list += f"\nTotal: {len(terms)} term{'s' if len(terms) != 1 else ''}"
                terms_list += f" ({active_count} active, {planned_count} planned, {completed_count} completed)"
                
                if planned_count > 0 and active_count == 0:
                    terms_list += f"\n\n⚠️ All terms are PLANNED (not yet started)\n"
                    terms_list += f"To activate a term for student enrollment:\n"
                    for term in terms:
                        if term["state"].upper() == "PLANNED":
                            terms_list += f"• 'activate term {term['term']}'\n"
                
                dispatcher.utter_message(text=terms_list)
            else:
                dispatcher.utter_message(text="Cannot retrieve terms information.")
        
        except Exception as e:
            logger.error(f"Error listing academic terms: {e}")
            dispatcher.utter_message(text="An error occurred while retrieving terms.")
        
        return [SlotSet("academic_year", None)]


class ActionPromoteStudents(Action):
    def name(self) -> Text:
        return "action_promote_students"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required.")
            return []
        
        target_term = tracker.get_slot("target_term")
        source_term = tracker.get_slot("source_term")
        
        # If no target term specified, ask for it
        if not target_term:
            dispatcher.utter_message(
                text="Which term should students be promoted to?\n"
                     "Example: 'promote students to term 3'"
            )
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "X-School-ID": school_id
            }
            
            # If source term not specified, use current active term
            if not source_term:
                current_term_response = requests.get(
                    f"{FASTAPI_BASE_URL}/academic/current-term",
                    headers=headers
                )
                
                if current_term_response.status_code == 200:
                    current_term_data = current_term_response.json()
                    source_term = str(current_term_data.get("term"))
                else:
                    # No current term, so just proceed with promotion to target
                    source_term = None
            
            # Call promotion endpoint
            promotion_data = {
                "target_term": int(target_term)
            }
            
            if source_term:
                promotion_data["source_term"] = int(source_term)
            
            response = requests.post(
                f"{FASTAPI_BASE_URL}/academic/promote-students",
                json=promotion_data,
                headers=headers
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                students_promoted = data.get("students_promoted", 0)
                
                msg = f"✅ Student promotion completed!\n\n"
                msg += f"Students promoted: {students_promoted}\n"
                msg += f"Target term: Term {target_term}\n\n"
                
                if students_promoted > 0:
                    msg += f"All eligible students have been enrolled in Term {target_term}."
                else:
                    msg += "No students were eligible for promotion."
                
                dispatcher.utter_message(text=msg)
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('detail', 'Failed to promote students')
                dispatcher.utter_message(text=f"Error: {error_msg}")
        
        except Exception as e:
            logger.error(f"Error promoting students: {e}", exc_info=True)
            dispatcher.utter_message(text="An error occurred while promoting students.")
        
        return [
            SlotSet("target_term", None),
            SlotSet("source_term", None)
        ]


# ============================================================================
# CLASS MANAGEMENT ACTIONS
# ============================================================================

class ActionCreateClass(Action):
    def name(self) -> Text:
        return "action_create_class"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required. Please log in first.")
            return []
        
        class_name = tracker.get_slot("name")
        level = tracker.get_slot("level")
        stream = tracker.get_slot("stream")
        academic_year = tracker.get_slot("academic_year")
        
        message_text = tracker.latest_message.get("text", "").lower()
        
        if not class_name and not level:
            words = message_text.split()
            for i, word in enumerate(words):
                if word in ["class", "grade"] and i + 1 < len(words):
                    potential_class = words[i + 1]
                    if not level:
                        level = potential_class
                    if not class_name:
                        class_name = potential_class
                    break
        
        if not level and not class_name:
            dispatcher.utter_message(
                text="I need more information. Please specify the class level (e.g., 'Grade 8', 'Form 1', '8A')"
            )
            return []
        
        if not class_name:
            class_name = level
            if stream:
                class_name += f" {stream}"
        
        if not level:
            level = class_name
        
        if class_name:
            class_name = normalize_class_name(class_name)
        if level:
            level = normalize_class_name(level)
        if stream:
            stream = stream.strip().upper() if stream else None
        
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
                         "Cannot create classes without proper academic setup.\n\n"
                         "Please complete these steps first:\n"
                         "1. 'create academic year 2025'\n"
                         "2. 'create term 1'\n\n"
                         "Then try creating the class again."
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
                         f"Complete academic setup is required before creating classes.\n"
                         f"Check status anytime with: 'check academic setup'"
                )
                return []
            
            if not academic_year:
                academic_year = str(setup_data["current_year"]["year"])
            
            class_payload = {
                "name": class_name,
                "level": level,
                "stream": stream,
                "academic_year": int(academic_year)
            }
            
            response = requests.post(
                f"{FASTAPI_BASE_URL}/classes",
                json=class_payload,
                headers=headers
            )
            
            if response.status_code == 201:
                class_data = response.json()
                stream_text = f" - Stream {stream}" if stream else ""
                dispatcher.utter_message(
                    text=f"Class created successfully!\n\n"
                         f"Class Details:\n"
                         f"Name: {class_name}\n"
                         f"Level: {level}{stream_text}\n"
                         f"Academic Year: {academic_year}\n\n"
                         f"The class is ready for student enrollment!"
                )
                
                return [
                    SlotSet("name", None),
                    SlotSet("level", None),
                    SlotSet("stream", None),
                    SlotSet("academic_year", None)
                ]
            
            elif response.status_code == 409:
                dispatcher.utter_message(
                    text=f"A class named '{class_name}' already exists for {academic_year}. Please use a different name."
                )
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('detail', 'Failed to create class')
                dispatcher.utter_message(text=f"Error: {error_msg}")
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating class: {e}")
            dispatcher.utter_message(
                text="Sorry, I'm having trouble connecting to the system. Please try again in a moment."
            )
        except Exception as e:
            logger.error(f"Unexpected error in ActionCreateClass: {e}")
            dispatcher.utter_message(
                text="An unexpected error occurred. Please try again."
            )
        
        return []


class ActionListClasses(Action):
    def name(self) -> Text:
        return "action_list_classes"

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
                f"{FASTAPI_BASE_URL}/classes",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                classes = data.get("classes", [])
                
                if not classes:
                    dispatcher.utter_message(text="No classes found in the system.")
                    return []
                
                class_list = "Class List:\n\n"
                for i, cls in enumerate(classes, 1):
                    stream_text = f" - {cls['stream']}" if cls.get('stream') else ""
                    student_count = cls.get('student_count', 0)
                    class_list += f"{i}. {cls['name']} ({cls['level']}{stream_text}) - {student_count} student{'s' if student_count != 1 else ''} - {cls['academic_year']}\n"
                
                dispatcher.utter_message(text=class_list)
                
            elif response.status_code == 403:
                dispatcher.utter_message(
                    text="You don't have permission to view classes. Please contact an administrator."
                )
            else:
                dispatcher.utter_message(
                    text="Sorry, I couldn't retrieve the class list. Please try again."
                )
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error listing classes: {e}")
            dispatcher.utter_message(
                text="Sorry, I'm having trouble connecting to the system. Please try again in a moment."
            )
        except Exception as e:
            logger.error(f"Unexpected error in ActionListClasses: {e}")
            dispatcher.utter_message(
                text="An unexpected error occurred. Please try again."
            )
        
        return []


class ActionListEmptyClasses(Action):
    def name(self) -> Text:
        return "action_list_empty_classes"

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
                f"{FASTAPI_BASE_URL}/classes",
                headers=headers
            )
            
            if response.status_code == 200:
                data = response.json()
                classes = data.get("classes", [])
                
                if not classes:
                    dispatcher.utter_message(text="No classes found in the system.")
                    return []
                
                empty_classes = [cls for cls in classes if cls.get('student_count', 0) == 0]
                
                if not empty_classes:
                    dispatcher.utter_message(
                        text="All classes have students enrolled. No empty classes found."
                    )
                    return []
                
                class_list = f"**Empty Classes ({len(empty_classes)} found):**\n\n"
                
                for i, cls in enumerate(empty_classes, 1):
                    stream_text = f" - {cls['stream']}" if cls.get('stream') else ""
                    class_list += f"{i}. **{cls['name']}** ({cls['level']}{stream_text}) - {cls['academic_year']}\n"
                
                class_list += f"\n**Total: {len(empty_classes)} class{'es' if len(empty_classes) != 1 else ''} with no students**"
                class_list += f"\n\nThese classes are ready for student enrollment"
                
                dispatcher.utter_message(text=class_list)
                
            elif response.status_code == 403:
                dispatcher.utter_message(
                    text="You don't have permission to view classes. Please contact an administrator."
                )
            else:
                dispatcher.utter_message(
                    text="Sorry, I couldn't retrieve the class list. Please try again."
                )
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Error listing empty classes: {e}")
            dispatcher.utter_message(
                text="Sorry, I'm having trouble connecting to the system. Please try again in a moment."
            )
        except Exception as e:
            logger.error(f"Unexpected error in ActionListEmptyClasses: {e}")
            dispatcher.utter_message(
                text="An unexpected error occurred. Please try again."
            )
        
        return []


class ActionDeleteClass(Action):
    def name(self) -> Text:
        return "action_delete_class"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required.")
            return []
        
        class_name = tracker.get_slot("class_name")
        
        if not class_name:
            dispatcher.utter_message(
                text="Please specify which class to delete. Example: 'delete class 8A'"
            )
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "X-School-ID": school_id
            }
            
            class_response = requests.get(
                f"{FASTAPI_BASE_URL}/classes",
                headers=headers,
                params={"search": class_name}
            )
            
            if class_response.status_code != 200:
                dispatcher.utter_message(text="Error finding class.")
                return []
            
            classes_data = class_response.json()
            matching_classes = []
            
            for cls in classes_data.get("classes", []):
                if cls["name"].lower() == class_name.lower():
                    matching_classes.append(cls)
            
            if not matching_classes:
                dispatcher.utter_message(text=f"Class '{class_name}' not found.")
                return []
            
            if len(matching_classes) > 1:
                msg = f"Multiple classes found matching '{class_name}':\n\n"
                for i, cls in enumerate(matching_classes, 1):
                    msg += f"{i}. {cls['name']} ({cls['academic_year']}) - {cls.get('student_count', 0)} students\n"
                msg += f"\nPlease be more specific or delete from the web interface."
                dispatcher.utter_message(text=msg)
                return []
            
            target_class = matching_classes[0]
            
            if target_class.get('student_count', 0) > 0:
                dispatcher.utter_message(
                    text=f"Cannot delete '{target_class['name']}' - it has {target_class['student_count']} enrolled students.\n\n"
                         f"Please transfer students to another class first."
                )
                return []
            
            delete_response = requests.delete(
                f"{FASTAPI_BASE_URL}/classes/{target_class['id']}",
                headers=headers
            )
            
            if delete_response.status_code == 200:
                dispatcher.utter_message(
                    text=f"Class '{target_class['name']}' deleted successfully!"
                )
            else:
                error_data = delete_response.json() if delete_response.content else {}
                error_msg = error_data.get('detail', 'Failed to delete class')
                dispatcher.utter_message(text=f"Error: {error_msg}")
        
        except Exception as e:
            logger.error(f"Error deleting class: {e}")
            dispatcher.utter_message(text="An error occurred while deleting the class.")
        
        return [SlotSet("class_name", None)]


class ActionHelp(Action):
    def name(self) -> Text:
        return "action_help"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        help_text = """
**School Assistant Help**

Here's what I can help you with:

**Students:**
• Search for a student: "student eric" or "student 5555"
• Create a student: "Add student [admission_no] named [full name] to class [class name]"
• List all students: "Show me all students" or "List students"
• List students by class: "List students in Grade 4"
• Show unassigned students: "Show unassigned students"

**Classes:**
• Create a class: "Create class [name]" or "New class [level]"
• List all classes: "Show me all classes" or "List classes"
• Show class details: "Show Grade 4 details"
• Find empty classes: "Show empty classes"

**Academic Management:**
The system now uses academic years and terms for proper enrollment tracking.
Students are automatically enrolled in the current term when created.

**Search Examples:**
• "student eric" - Search by first name
• "student 5555" - Search by admission number  
• "student #5555" - Search by admission number with hashtag
• "find john doe" - Search by full name

**Class Examples:**
• "list students in Grade 4" - Students in specific class
• "show students in 8A" - Students in specific class
• "show Grade 4 details" - Class overview
• "empty classes" - Classes with no students
• "unassigned students" - Students not enrolled in current term

**Quick Tips:**
• Use admission numbers for exact student matches
• Use names for broader student searches
• Be specific with class names for best results
• Academic setup (year/term) is required for student creation

Need more specific help? Just ask!
        """
        
        dispatcher.utter_message(text=help_text)
        return []
    

class ActionCompleteTerm(Action):
    def name(self) -> Text:
        return "action_complete_term"

    def run(self, dispatcher: CollectingDispatcher, 
            tracker: Tracker, domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        
        metadata = tracker.latest_message.get("metadata", {})
        auth_token = metadata.get("auth_token")
        school_id = metadata.get("school_id")
        
        if not auth_token:
            dispatcher.utter_message(text="Authentication required.")
            return []
        
        term = tracker.get_slot("term")
        academic_year = tracker.get_slot("academic_year")
        
        if not term:
            dispatcher.utter_message(
                text="Which term would you like to close?\n"
                     "Example: 'close term 3'"
            )
            return []
        
        try:
            headers = {
                "Authorization": f"Bearer {auth_token}",
                "X-School-ID": school_id
            }
            
            # Get current year if not specified
            if not academic_year:
                year_response = requests.get(
                    f"{FASTAPI_BASE_URL}/academic/current-year",
                    headers=headers
                )
                if year_response.status_code == 200:
                    year_data = year_response.json()
                    academic_year = str(year_data.get("year"))
                
                if not academic_year:
                    dispatcher.utter_message(
                        text="No active academic year found. Please specify the year:\n"
                             "Example: 'close term 3 for 2025'"
                    )
                    return [SlotSet("term", None)]
            
            academic_year = str(academic_year)
            
            # Complete the term
            response = requests.put(
                f"{FASTAPI_BASE_URL}/academic/terms/{academic_year}/{term}/complete",
                headers=headers
            )
            
            if response.status_code == 200:
                msg = f"Term {term} for Academic Year {academic_year} has been closed.\n\n"
                
                # Check if this was the last term
                if term == "3":
                    msg += "This was the final term of the academic year.\n\n"
                    msg += "Next steps:\n"
                    msg += f"• Close academic year {academic_year}: 'close academic year {academic_year}'\n"
                    msg += f"• Or create next academic year: 'create academic year {int(academic_year) + 1}'"
                else:
                    next_term = int(term) + 1
                    msg += f"To continue operations:\n"
                    msg += f"• Create term {next_term}: 'add term {next_term} to {academic_year}'\n"
                    msg += f"• Then activate it: 'activate term {next_term}'\n"
                    msg += f"• Promote students: 'promote students to term {next_term}'"
                
                dispatcher.utter_message(text=msg)
            else:
                error_data = response.json() if response.content else {}
                error_msg = error_data.get('detail', 'Failed to close term')
                dispatcher.utter_message(text=f"Error: {error_msg}")
        
        except Exception as e:
            logger.error(f"Error completing term: {e}", exc_info=True)
            dispatcher.utter_message(text="An error occurred while closing the term.")
        
        return [
            SlotSet("term", None),
            SlotSet("academic_year", None)
        ]