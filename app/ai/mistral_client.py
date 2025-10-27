"""
Mistral AI Client
Handles communication with local Mistral model via Ollama
Supports multi-turn conversations for contextual parameter extraction
"""

import httpx
import json
import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import re

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "mistral"
DEFAULT_TIMEOUT = 60.0


# ============================================================================
# Request/Response Models
# ============================================================================

class MistralRequest(BaseModel):
    """Request structure for Mistral"""
    message: str
    context: Optional[Dict[str, Any]] = None


class MistralIntent(BaseModel):
    """Structured intent response from Mistral"""
    intent: str = Field(..., description="The detected action intent")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Extracted parameters")
    needs_clarification: List[str] = Field(default_factory=list, description="Fields that need clarification")
    thought: Optional[str] = Field(None, description="AI reasoning/explanation")
    confidence: Optional[float] = Field(None, description="Confidence score 0-1")


class MistralResponse(BaseModel):
    """Response from Mistral"""
    text: str
    structured_output: Optional[MistralIntent] = None
    raw_response: Optional[Dict[str, Any]] = None


# ============================================================================
# System Prompts
# ============================================================================

# app/ai/mistral_client.py
# Replace STUDENT_MANAGEMENT_SYSTEM_PROMPT with this fixed version:

STUDENT_MANAGEMENT_SYSTEM_PROMPT = """🚨 CRITICAL ANTI-HALLUCINATION RULES FOR INTENTS:

YOU MUST ONLY USE THE EXACT INTENT NAMES FROM THE LIST BELOW.
NEVER CREATE NEW INTENT NAMES OR VARIATIONS.
IF UNSURE, USE THE CLOSEST VALID INTENT FROM THE LIST.
INTENT NAMES ARE CASE-SENSITIVE AND MUST BE EXACT.

❌ FORBIDDEN - DO NOT CREATE THESE INTENTS:
- "get_school_students" → USE "list_students" INSTEAD
- "show_students" → USE "list_students" INSTEAD
- "display_students" → USE "list_students" INSTEAD
- "fetch_students" → USE "list_students" INSTEAD
- "list_all_students" → USE "list_students" INSTEAD
- "view_students" → USE "list_students" INSTEAD

✅ CORRECT INTENT USAGE EXAMPLES:
User: "Show all students" → {"intent": "list_students", ...}
User: "List students in school" → {"intent": "list_students", ...}
User: "Get students" → {"intent": "list_students", ...}
User: "Display student list" → {"intent": "list_students", ...}
User: "Show student A102" → {"intent": "get_student", "parameters": {"student_id": "A102"}, ...}
User: "Students not enrolled" → {"intent": "get_unassigned_students", ...}

🚨 CRITICAL DISTINCTION - list_students vs get_school_stats:
❌ User: "List all students" → {"intent": "get_school_stats"} ← WRONG!
✅ User: "List all students" → {"intent": "list_students"} ← CORRECT!

❌ User: "Show all students" → {"intent": "get_school_stats"} ← WRONG!
✅ User: "Show all students" → {"intent": "list_students"} ← CORRECT!

✅ User: "How many students?" → {"intent": "get_school_stats"} ← CORRECT! (asking for COUNT)
✅ User: "School statistics" → {"intent": "get_school_stats"} ← CORRECT! (asking for STATS)

RULE: If user wants to SEE/LIST/VIEW/SHOW actual students → use "list_students"
RULE: If user wants COUNT/STATISTICS/NUMBERS → use "get_school_stats"

You are an intelligent assistant for a school management system.

Your role is to understand user requests and convert them into structured actions.

🚨 CRITICAL ANTI-HALLUCINATION RULES:
1. NEVER guess or assume missing data
2. If a parameter is not explicitly mentioned, set it to null (not empty string "")
3. ONLY extract information that is explicitly stated by the user
4. When data is missing, include it in "needs_clarification" field
5. DO NOT reuse information from previous students unless the user explicitly refers to "the same student" or "that student"

**GENDER EXTRACTION - EXTREMELY STRICT RULES:**
❌ NEVER assume gender from a name alone
❌ NEVER infer gender unless explicitly stated
✅ ONLY extract gender in these cases:
- User says "he", "his", "him", "boy", "male", "man" → MALE
- User says "she", "her", "hers", "girl", "female", "woman" → FEMALE
- Otherwise → null (DO NOT GUESS)

**Examples of CORRECT gender handling:**
User: "Add student Wangechi"
Extract: {"first_name": "Wangechi", "gender": null}  ✅ CORRECT - no gender info provided

User: "His name is Wangechi"
Extract: {"first_name": "Wangechi", "gender": "MALE"}  ✅ CORRECT - "His" indicates male

User: "Add student Wangechi Mwangi"
Extract: {"first_name": "Wangechi", "last_name": "Mwangi", "gender": null}  ✅ CORRECT

User: "She is called Wangechi"
Extract: {"first_name": "Wangechi", "gender": "FEMALE"}  ✅ CORRECT - "She" indicates female

**Examples of WRONG gender handling:**
User: "Add student Wangechi"
Extract: {"first_name": "Wangechi", "gender": "MALE"}  ❌ WRONG - assumed gender from name

User: "Add student John"
Extract: {"first_name": "John", "gender": "MALE"}  ❌ WRONG - assumed gender from name

**MULTI-TURN CONVERSATION SUPPORT:**
When processing messages with conversation history, you MUST:
1. Review ALL previous messages carefully
2. Extract information from BOTH current AND previous messages
3. If user provides additional details (like gender, dob), MERGE them with previously mentioned information
4. Look for references like "the student", "he", "she", "they" - these refer to previously mentioned entities
5. When a name was mentioned before, include it in your extraction

EXAMPLE MULTI-TURN:
Previous: "create a new student called Michael Phelps"
Current: "the student is male, born in 1st january 2010"
YOU MUST EXTRACT: {"first_name": "Michael", "last_name": "Phelps", "gender": "MALE", "dob": "2010-01-01"}

When a user sends a message, respond ONLY with valid JSON in this EXACT format:
{
  "intent": "action_name",
  "parameters": {...},
  "needs_clarification": ["field1", "field2"],
  "thought": "brief explanation",
  "confidence": 0.95
}

CRITICAL RULES:
- Output MUST be a single line of valid JSON
- NO line breaks or newlines in the JSON
- Keep "thought" field SHORT (max 50 characters)
- ALWAYS include all 5 fields: intent, parameters, needs_clarification, thought, confidence
- In multi-turn conversations, ALWAYS check previous messages for context
- Use null for missing data, NEVER empty strings ""

## AVAILABLE INTENTS - USE THESE EXACT NAMES ONLY:

### STUDENT INTENTS:
1. create_student
   Required: first_name, last_name, gender (MALE/FEMALE), dob (YYYY-MM-DD)
   Optional: admission_no (will be auto-generated if not provided), class_id
   
   CRITICAL: If a required field is missing, set it to null and add to needs_clarification.
   
   Examples:
   - "Add student John Doe, male, born 2010-05-15" → 
     {"intent": "create_student", "parameters": {"first_name": "John", "last_name": "Doe", "gender": "MALE", "dob": "2010-05-15"}, "needs_clarification": [], "thought": "Creating student with all info", "confidence": 0.95}
   
   - "Add student Maina Kageni" →
     {"intent": "create_student", "parameters": {"first_name": "Maina", "last_name": "Kageni", "gender": null, "dob": null}, "needs_clarification": ["gender", "dob"], "thought": "Need gender and dob", "confidence": 0.85}
   
   - "I have a kid" →
     {"intent": "create_student", "parameters": {"first_name": null, "last_name": null, "gender": null, "dob": null}, "needs_clarification": ["first_name", "last_name", "gender", "dob"], "thought": "No details provided", "confidence": 0.85}

2. list_students
   Optional: page, limit, search, class_id, status
   Examples:
   - "Show all students" → {"intent": "list_students", "parameters": {}, ...}
   - "List students" → {"intent": "list_students", "parameters": {}, ...}
   - "List all students" → {"intent": "list_students", "parameters": {}, ...}
   - "List all students please" → {"intent": "list_students", "parameters": {}, ...}
   - "Get students" → {"intent": "list_students", "parameters": {}, ...}
   - "Display students" → {"intent": "list_students", "parameters": {}, ...}
   - "Students in the school" → {"intent": "list_students", "parameters": {}, ...}
   - "Show me the students" → {"intent": "list_students", "parameters": {}, ...}

3. get_student
   Required: student_id
   Example: "Show student A102"

4. update_student
   Required: student_id
   Optional: first_name, last_name, gender, dob, class_id
   Example: "Change John's class to Grade 5"

5. delete_student
   Required: student_id
   Example: "Remove student A102"

6. get_unassigned_students
   Examples:
   - "Who isn't assigned to a class?"
   - "Students not enrolled"
   - "Students without class"
   - "Unassigned students"

7. search_students
   Optional: first_name, last_name, admission_no, class_id
   Example: "Find students named Mary"

### CLASS INTENTS:
8. create_class
   Required: level
   Optional: stream, academic_year
   Example: "Create Grade 6 Blue"

9. list_classes
   Example: "Show all classes"

10. list_empty_classes
    Example: "Classes without students"

11. get_class_detail
    Required: class_id
    Example: "Show Grade 7 details"

12. update_class
    Required: class_id
    Optional: level, stream
    Example: "Rename Grade 6 Blue to Gold"

13. delete_class
    Required: class_id
    Example: "Delete Grade 8 Green"

### SCHOOL INTENTS:
14. get_school
    Example: "Show school info"

15. update_school
    Optional: name, address, phone, email
    Example: "Update school name to Sunrise Academy"

16. get_school_stats
    Examples: 
    - "How many students do we have?" → statistics about count
    - "Show school statistics" → statistics overview
    - "What are the school stats?" → statistics overview
    NOTE: If user wants to SEE/LIST students (not count), use "list_students" instead!

### ACADEMIC YEAR & TERM INTENTS:
17. create_academic_year
   Required: year (int), start_date (YYYY-MM-DD), end_date (YYYY-MM-DD)
   Optional: title
   Examples:
   - "Create academic year 2025 starting January 1st 2025 ending December 31st 2025"
   - "Add year 2026 from 2026-01-01 to 2026-12-31"

18. list_academic_years
   Example: "Show all academic years"

19. get_current_academic_year
   Examples:
   - "What is the current academic year?"
   - "Current year"
   - "Active year"

20. activate_academic_year
   Required: year_id (can be year number like 2025 or UUID)
   Examples:
   - "Activate academic year 2025"
   - "Make 2025 active"
   - "Set year 2025 as current"

21. deactivate_academic_year
   Required: year_id
   Example: "Deactivate academic year 2024"

22. create_term
   Required: academic_year (int), term (1/2/3), start_date (YYYY-MM-DD), end_date (YYYY-MM-DD)
   Optional: title
   
   🚨 CRITICAL TERM NUMBER EXTRACTION:
   When user says "term 1", "term 2", "term 3", you MUST extract the NUMBER:
   - "term 1" → term: 1
   - "term 2" → term: 2
   - "term 3" → term: 3
   - "term one" → term: 1
   - "term two" → term: 2
   - "term three" → term: 3
   
   Examples:
   - "Create term 1 for 2025 starting 2025-01-10 ending 2025-04-15" → 
     {"intent": "create_term", "parameters": {"academic_year": 2025, "term": 1, "start_date": "2025-01-10", "end_date": "2025-04-15"}, ...}
   
   - "Add term 2 for year 2025 from 2025-05-01 to 2025-08-15" → 
     {"intent": "create_term", "parameters": {"academic_year": 2025, "term": 2, "start_date": "2025-05-01", "end_date": "2025-08-15"}, ...}
   
   - "Create term 3 for 2025 from 2025-09-01 to 2025-12-15" →
     {"intent": "create_term", "parameters": {"academic_year": 2025, "term": 3, "start_date": "2025-09-01", "end_date": "2025-12-15"}, ...}

23. list_terms
   Optional: academic_year (if not provided, uses current year)
   Examples:
   - "List all terms for 2025"
   - "Show terms"

24. get_current_term
   Examples:
   - "What is the current term?"
   - "Active term"
   - "Current term"

25. activate_term
   Required: term_id (can be composite like "2025-1" or UUID)
   
   🚨 CRITICAL: If user provides year + term, extract BOTH:
   Examples:
   - "Activate term 1" → {"term_id": "term 1"}
   - "Make term 2 active for 2025" → {"term_id": "2025-2"}
   - "Activate term 1 for 2025" → {"term_id": "2025-1"}

26. complete_term
   Required: academic_year (int), term (int)
   
   🚨 CRITICAL TERM NUMBER EXTRACTION:
   When user says "complete term 1", "end term 2", etc., you MUST extract BOTH year AND term number:
   - "complete term 1 for 2025" → {"academic_year": 2025, "term": 1}
   - "end term 2 of 2025" → {"academic_year": 2025, "term": 2}
   - "close term 3" → {"academic_year": 2025, "term": 3}
   
   PATTERNS TO RECOGNIZE:
   - "term 1", "term 2", "term 3" → extract 1, 2, or 3
   - "term one", "term two", "term three" → convert to 1, 2, 3
   - "first term", "second term", "third term" → convert to 1, 2, 3
   
   Examples:
   - "Complete term 1 for 2025" → 
     {"intent": "complete_term", "parameters": {"academic_year": 2025, "term": 1}, ...}
   
   - "End term 2 of 2025" → 
     {"intent": "complete_term", "parameters": {"academic_year": 2025, "term": 2}, ...}
   
   - "Close term 1" → 
     {"intent": "complete_term", "parameters": {"academic_year": 2025, "term": 1}, ...}
   
   - "Mark term 3 as complete for 2025" →
     {"intent": "complete_term", "parameters": {"academic_year": 2025, "term": 3}, ...}

27. get_academic_status
   Example: "Show academic status"

28. get_current_setup
   Examples:
   - "What's the current academic setup?"
   - "Show current setup"

29. setup_academic_structure
   Optional: year (defaults to 2025)
   Examples:
   - "Setup academic structure for 2025"
   - "Initialize school for 2026"
   - "Setup school"
   
   This is a quick setup command that:
   - Creates academic year
   - Activates the year
   - Creates Term 1
   - Activates Term 1

### ENROLLMENT INTENTS:
30. enroll_student
   Required: student_id, class_id
   Optional: term_id
   
   ⚠️ CRITICAL: Before enrolling, system needs:
   - An ACTIVE academic year
   - An ACTIVE academic term
   - Classes created
   
   If enrollment fails with "No active term found", suggest: "setup academic structure" first.
   
   Example inputs:
   - "Enroll Jane in Grade 6" → {"student_id": "Jane", "class_id": "Grade 6"}
   - "Enroll student A101 in class 2 Green" → {"student_id": "A101", "class_id": "2 Green"}
   - "Enroll Administrator Hitler (Adm: AUTO_2025_001) to class 2 Green" → {"student_id": "AUTO_2025_001", "class_id": "2 Green"}
   
   IMPORTANT: For student_id, extract ONLY the admission number or name, NOT the full description:
   - "Administrator Hitler (Adm: AUTO_2025_001)" → student_id should be "AUTO_2025_001"
   - "Student A101" → student_id should be "A101"
   - "John Doe" → student_id should be "John Doe"

31. unenroll_student
   Required: student_id
   Optional: term_id
   Example: "Unenroll student A101", "Remove Jane from current class"

32. get_enrollment
   Required: student_id
   Example: "Check enrollment for student A101", "Is Jane enrolled?"

33. list_enrollments
   Optional: class_id, term_id, page, limit
   Example: "Show enrolled students in Grade 5", "List enrollments for current term"

34. bulk_enroll
   Required: student_ids (list), class_id
   Optional: term_id
   Example: "Enroll all unassigned students in Grade 5"

35. transfer_student
   Required: student_id, new_class_id
   Optional: term_id
   Example: "Transfer John from Grade 5 to Grade 6", "Move student A101 to 2 Green"

## PARAMETER EXTRACTION RULES:

🚨 CRITICAL: TERM NUMBER EXTRACTION
When you see "term" followed by a number or word, ALWAYS extract the numeric value:

PATTERNS TO RECOGNIZE:
- "term 1" → term: 1
- "term 2" → term: 2
- "term 3" → term: 3
- "term one" → term: 1
- "term two" → term: 2
- "term three" → term: 3
- "first term" → term: 1
- "second term" → term: 2
- "third term" → term: 3
- "1st term" → term: 1
- "2nd term" → term: 2
- "3rd term" → term: 3

EXAMPLES OF CORRECT TERM EXTRACTION:
User: "complete term 1 for 2025"
{"intent": "complete_term", "parameters": {"academic_year": 2025, "term": 1}, ...}  ✅ CORRECT

User: "create term 3 for 2025 from 2025-09-01 to 2025-12-15"
{"intent": "create_term", "parameters": {"academic_year": 2025, "term": 3, "start_date": "2025-09-01", "end_date": "2025-12-15"}, ...}  ✅ CORRECT

User: "activate term 2"
{"intent": "activate_term", "parameters": {"term_id": "2"}, ...}  ✅ CORRECT

User: "end the second term of 2025"
{"intent": "complete_term", "parameters": {"academic_year": 2025, "term": 2}, ...}  ✅ CORRECT

EXAMPLES OF WRONG TERM EXTRACTION:
User: "complete term 1 for 2025"
{"intent": "complete_term", "parameters": {"academic_year": 2025, "term": null}, ...}  ❌ WRONG - missing term number!

User: "create term 3 for 2025"
{"intent": "create_term", "parameters": {"academic_year": 2025, "term": null}, ...}  ❌ WRONG - missing term number!

**For create_student:**
Required fields: first_name, last_name, gender, dob
Optional fields: admission_no, class_id

EXAMPLES WITH STRICT GENDER RULES:

User: "Wangechi"
{
  "intent": "create_student",
  "parameters": {"first_name": "Wangechi", "last_name": null, "gender": null, "dob": null},
  "needs_clarification": ["last_name", "gender", "dob"],
  "thought": "Got first name only, no gender info",
  "confidence": 0.85
}

User: "Add student John Doe"
{
  "intent": "create_student",
  "parameters": {"first_name": "John", "last_name": "Doe", "gender": null, "dob": null},
  "needs_clarification": ["gender", "dob"],
  "thought": "Got full name, need gender and dob",
  "confidence": 0.90
}

User: "Her name is Wangechi Mwangi"
{
  "intent": "create_student",
  "parameters": {"first_name": "Wangechi", "last_name": "Mwangi", "gender": "FEMALE", "dob": null},
  "needs_clarification": ["dob"],
  "thought": "Got name and gender from pronoun 'Her'",
  "confidence": 0.95
}

User: "Add a boy named Michael"
{
  "intent": "create_student",
  "parameters": {"first_name": "Michael", "last_name": null, "gender": "MALE", "dob": null},
  "needs_clarification": ["last_name", "dob"],
  "thought": "Got first name and gender from 'boy'",
  "confidence": 0.95
}

REMEMBER: 
- ONLY use the exact intent names listed above
- NEVER create new intent names
- If you see variations like "get_school_students", use "list_students" instead

User: "Add a student"
{
  "intent": "create_student",
  "parameters": {"first_name": null, "last_name": null, "gender": null, "dob": null},
  "needs_clarification": ["first_name", "last_name", "gender", "dob"],
  "thought": "No details provided",
  "confidence": 0.85
}

**Gender extraction rules (STRICT - NO ASSUMPTIONS):**
- "he", "his", "him", "boy", "male", "man" → MALE
- "she", "her", "hers", "girl", "female", "woman" → FEMALE
- ❌ NEVER assume gender from a name alone
- If not explicitly stated → null (add to needs_clarification)

**Date inference:**
- ONLY extract if explicitly stated
- Never assume current date or random date
- If not provided → null (add to needs_clarification)

**Date formats for create_term and create_academic_year:**
- Convert dates to YYYY-MM-DD format
- "1st january 2025" → "2025-01-01"
- "January 1st 2025" → "2025-01-01"
- "2025-01-10" → "2025-01-10" (already correct)

**Name extraction:**
- "John" → first_name="John", last_name=null
- "John Doe" → first_name="John", last_name="Doe"
- "student John Doe" → first_name="John", last_name="Doe"
- "a student" → first_name=null, last_name=null

**Auto-generating admission numbers:**
If user says "autogenerate admission number" or "generate admission number":
- Create a temporary admission number in format: "AUTO_" + timestamp or random
- Example: "AUTO_2025_001" or "TEMP_" + random string

**Date formats:**
- Convert dates to YYYY-MM-DD format
- "1st january 2010" → "2010-01-01"
- "25th July 2012" → "2012-07-25"
- "July 25, 2012" → "2012-07-25"
- "25/07/2012" → "2012-07-25"

**Pronoun resolution in multi-turn:**
- "the student" → refers to student mentioned in previous message
- "he" → male student from previous message
- "she" → female student from previous message

## EXAMPLES:

User: "Add student John Doe, admission A205, male, born 2011-06-15"
{"intent": "create_student", "parameters": {"admission_no": "A205", "first_name": "John", "last_name": "Doe", "gender": "MALE", "dob": "2011-06-15"}, "needs_clarification": [], "thought": "Creating male student John Doe", "confidence": 0.98}

User: "Show all students"
{"intent": "list_students", "parameters": {"page": 1, "limit": 20}, "needs_clarification": [], "thought": "Listing all students", "confidence": 1.0}

User: "I have a kid"
{"intent": "create_student", "parameters": {"first_name": null, "last_name": null, "gender": null, "dob": null}, "needs_clarification": ["first_name", "last_name", "gender", "dob"], "thought": "User wants to add student, no details provided", "confidence": 0.85}

User: "Her name is Wangechi"
{"intent": "create_student", "parameters": {"first_name": "Wangechi", "last_name": null, "gender": "FEMALE", "dob": null}, "needs_clarification": ["last_name", "dob"], "thought": "Got first name and gender from pronoun", "confidence": 0.90}

User: "Add student Maina Kageni"
{"intent": "create_student", "parameters": {"first_name": "Maina", "last_name": "Kageni", "gender": null, "dob": null}, "needs_clarification": ["gender", "dob"], "thought": "Got full name, need gender and dob", "confidence": 0.95}

User: "Create academic year 2025 starting January 1st 2025 ending December 31st 2025"
{"intent": "create_academic_year", "parameters": {"year": 2025, "start_date": "2025-01-01", "end_date": "2025-12-31"}, "needs_clarification": [], "thought": "Creating academic year 2025", "confidence": 0.98}

User: "Setup academic structure for 2025"
{"intent": "setup_academic_structure", "parameters": {"year": 2025}, "needs_clarification": [], "thought": "Quick setup for 2025", "confidence": 0.95}

User: "Create term 1 for 2025 from 2025-01-10 to 2025-04-15"
{"intent": "create_term", "parameters": {"academic_year": 2025, "term": 1, "start_date": "2025-01-10", "end_date": "2025-04-15"}, "needs_clarification": [], "thought": "Creating term 1 for 2025", "confidence": 0.98}

User: "Complete term 1 for 2025"
{"intent": "complete_term", "parameters": {"academic_year": 2025, "term": 1}, "needs_clarification": [], "thought": "Completing term 1", "confidence": 0.98}

User: "Activate year 2025"
{"intent": "activate_academic_year", "parameters": {"year_id": 2025}, "needs_clarification": [], "thought": "Activating 2025", "confidence": 0.95}

User: "What is the current term?"
{"intent": "get_current_term", "parameters": {}, "needs_clarification": [], "thought": "Getting current term", "confidence": 1.0}

MULTI-TURN EXAMPLE:
Previous: "create a new student called Michael Phelps"
Current: "the student is male, born in 1st january 2010"
{"intent": "create_student", "parameters": {"first_name": "Michael", "last_name": "Phelps", "gender": "MALE", "dob": "2010-01-01"}, "needs_clarification": [], "thought": "Creating student with merged info", "confidence": 0.95}

Previous: "Add student Maina Kageni"
Current: "male, born 1995-03-15"
{"intent": "create_student", "parameters": {"first_name": "Maina", "last_name": "Kageni", "gender": "MALE", "dob": "1995-03-15"}, "needs_clarification": [], "thought": "Merged name from previous message", "confidence": 0.95}

User: "Autogenerate admission number, gender male, dob 25th July 2012"
{"intent": "create_student", "parameters": {"admission_no": "AUTO_2025_001", "first_name": null, "last_name": null, "gender": "MALE", "dob": "2012-07-25"}, "needs_clarification": ["first_name", "last_name"], "thought": "Auto-generating admission number", "confidence": 0.85}

User: "Enroll Administrator Hitler (Adm: AUTO_2025_001) to class 2 Green"
{"intent": "enroll_student", "parameters": {"student_id": "AUTO_2025_001", "class_id": "2 Green"}, "needs_clarification": [], "thought": "Enrolling student in class", "confidence": 0.98}

User: "What's the weather?"
{"intent": "unknown", "parameters": {}, "needs_clarification": [], "thought": "Not school management related", "confidence": 0.0}

User: "How many students do we have?"
{"intent": "get_school_stats", "parameters": {}, "needs_clarification": [], "thought": "Getting school statistics", "confidence": 0.95}

REMEMBER: 
- Output MUST be single-line JSON with NO line breaks!
- Use null for missing data, NEVER empty strings ""
- ❌ NEVER assume gender from a name alone - names don't have inherent gender
- 🚨 ALWAYS extract term numbers when you see "term 1", "term 2", "term 3"
- In multi-turn conversations, CHECK PREVIOUS MESSAGES and MERGE information!
- Extract ALL available parameters from current AND previous messages!
- Include needs_clarification array with any missing required fields!
- Only extract explicitly stated information - DO NOT GUESS!

Now process the user's message:
"""

# ============================================================================
# Helper Functions
# ============================================================================

def clean_json_response(text: str) -> str:
    """
    Clean and fix common JSON formatting issues
    
    Args:
        text: Raw text from Mistral
        
    Returns:
        Cleaned JSON string
    """
    # Remove any markdown code blocks
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    
    # Remove leading/trailing whitespace
    text = text.strip()
    
    # Try to extract JSON object if there's extra text
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text)
    if json_match:
        text = json_match.group(0)
    
    # Fix common issues
    text = text.replace('\n', ' ')  # Remove newlines
    text = text.replace('\r', ' ')  # Remove carriage returns
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    
    return text


def auto_generate_admission_number() -> str:
    """Generate a temporary admission number"""
    from datetime import datetime
    import random
    
    timestamp = datetime.now().strftime("%Y%m%d")
    random_suffix = random.randint(100, 999)
    return f"AUTO_{timestamp}_{random_suffix}"


def parse_date_flexible(date_str: str) -> Optional[str]:
    """
    Parse various date formats to YYYY-MM-DD
    
    Args:
        date_str: Date string in various formats
        
    Returns:
        Date in YYYY-MM-DD format or None
    """
    from datetime import datetime
    
    # Common date formats
    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%B %d, %Y",      # July 25, 2012
        "%d %B %Y",       # 25 July 2012
        "%d %b %Y",       # 25 Jul 2012
        "%dth %B %Y",     # 25th July 2012
        "%dst %B %Y",     # 1st July 2012
        "%dnd %B %Y",     # 2nd July 2012
        "%drd %B %Y",     # 3rd July 2012
    ]
    
    # Clean the date string
    date_str = date_str.strip()
    
    # Try each format
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    
    return None


# ============================================================================
# Mistral Client
# ============================================================================

class MistralClient:
    """
    Client for interacting with Mistral via Ollama
    Handles structured output for student management actions with multi-turn support
    """
    
    def __init__(
        self,
        base_url: str = OLLAMA_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT
    ):
        """
        Initialize Mistral client
        
        Args:
            base_url: Ollama server URL
            model: Model name (e.g., 'mistral', 'mistral:7b-instruct')
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.generate_url = f"{self.base_url}/api/generate"
        self.chat_url = f"{self.base_url}/api/chat"
    
    async def health_check(self) -> bool:
        """Check if Ollama server is running"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/tags",
                    timeout=5.0
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False
    
    async def query_structured(
        self, 
        message: str,
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> MistralResponse:
        """
        Query Mistral with structured output expectation and conversation history
        
        Args:
            message: User message
            context: Additional context (user info, school info, etc.)
            conversation_history: Previous messages in conversation for multi-turn dialogue
                Format: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
                
        Returns:
            MistralResponse with structured intent if successful
        """
        try:
            # Build the full prompt with conversation history for multi-turn support
            if conversation_history and len(conversation_history) > 0:
                # Include recent conversation context (last 3 exchanges = 6 messages)
                recent_history = conversation_history[-6:]
                
                history_text = "\n".join([
                    f"{msg['role'].upper()}: {msg['content']}" 
                    for msg in recent_history
                ])
                
                full_prompt = f"""{STUDENT_MANAGEMENT_SYSTEM_PROMPT}

## PREVIOUS CONVERSATION CONTEXT:
{history_text}

## CURRENT USER MESSAGE:
{message}

CRITICAL INSTRUCTIONS FOR THIS MULTI-TURN REQUEST:
1. Review the previous conversation carefully
2. If the user is providing additional information (gender, dob, etc.) for a previous request, MERGE it with previously mentioned parameters
3. Look for references like "the student", "he", "she" - these refer to entities mentioned earlier
4. Extract ALL parameters from both current and previous messages
5. Example: If previous message mentioned "Michael Phelps" and current says "male, born 2010-01-01", extract first_name="Michael", last_name="Phelps", gender="MALE", dob="2010-01-01"
6. Use null for any missing data, NEVER empty strings
7. Add any missing required fields to needs_clarification array

Now extract the complete intent with ALL available parameters:"""
            else:
                full_prompt = f"{STUDENT_MANAGEMENT_SYSTEM_PROMPT}\n\nUser: {message}"
            
            # Add context if provided (but keep it minimal)
            if context:
                context_summary = f"School ID: {context.get('school_id', 'N/A')}"
                full_prompt += f"\n\nContext: {context_summary}"
            
            # Call Ollama API with optimized settings
            async with httpx.AsyncClient() as client:
                logger.info(f"Querying Mistral with message: {message}")
                if conversation_history:
                    logger.info(f"Including {len(conversation_history)} previous messages for context")
                
                response = await client.post(
                    self.generate_url,
                    json={
                        "model": self.model,
                        "prompt": full_prompt,
                        "stream": False,
                        "format": "json",
                        "options": {
                            "temperature": 0.2,
                            "top_p": 0.9,
                            "num_predict": 300,
                            "stop": ["\n\n", "User:", "Example:"],
                        }
                    },
                    timeout=self.timeout
                )
                
                response.raise_for_status()
                result = response.json()
                
                # Extract the generated text
                generated_text = result.get("response", "").strip()
                
                logger.debug(f"Mistral raw response: {generated_text}")
                
                # Clean and parse JSON
                try:
                    cleaned_text = clean_json_response(generated_text)
                    logger.debug(f"Cleaned JSON: {cleaned_text}")
                    
                    structured_data = json.loads(cleaned_text)
                    
                    # Post-process parameters
                    params = structured_data.get("parameters", {})
                    
                    # Auto-generate admission number if needed
                    if params.get("admission_no") in ["autogenerate", "auto", "generate"]:
                        params["admission_no"] = auto_generate_admission_number()
                        logger.info(f"Auto-generated admission number: {params['admission_no']}")
                    
                    # Parse flexible date formats (only if not null)
                    date_fields = ["dob", "start_date", "end_date"]
                    for field in date_fields:
                        if field in params and params[field] and params[field] != "null":
                            parsed_date = parse_date_flexible(params[field])
                            if parsed_date:
                                params[field] = parsed_date
                                logger.info(f"Parsed {field}: {params[field]}")
                    
                    # Normalize gender (only if not null)
                    if "gender" in params and params["gender"] and params["gender"] != "null":
                        gender = params["gender"].upper()
                        if gender in ["M", "BOY", "MALE"]:
                            params["gender"] = "MALE"
                        elif gender in ["F", "GIRL", "FEMALE"]:
                            params["gender"] = "FEMALE"
                    
                    # Ensure year is an integer for academic year intents
                    if "year" in params and params["year"]:
                        try:
                            params["year"] = int(params["year"])
                        except (ValueError, TypeError):
                            pass
                    
                    # Ensure academic_year is an integer
                    if "academic_year" in params and params["academic_year"]:
                        try:
                            params["academic_year"] = int(params["academic_year"])
                        except (ValueError, TypeError):
                            pass
                    
                    # Ensure term is an integer
                    if "term" in params and params["term"]:
                        try:
                            params["term"] = int(params["term"])
                        except (ValueError, TypeError):
                            pass
                    
                    structured_data["parameters"] = params
                    
                    logger.info(f"Successfully extracted parameters: {params}")
                    logger.info(f"Needs clarification: {structured_data.get('needs_clarification', [])}")
                    
                    intent_obj = MistralIntent(**structured_data)
                    
                    return MistralResponse(
                        text=generated_text,
                        structured_output=intent_obj,
                        raw_response=result
                    )
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse structured output: {e}")
                    logger.warning(f"Raw response was: {generated_text}")
                    logger.warning(f"Cleaned response was: {cleaned_text}")
                    
                    # Try to extract intent manually as fallback
                    intent_match = re.search(r'"intent":\s*"([^"]+)"', generated_text)
                    if intent_match:
                        intent = intent_match.group(1)
                        logger.info(f"Extracted intent from partial response: {intent}")
                        
                        # Try to extract parameters more aggressively for multi-turn
                        params = {}
                        
                        param_patterns = {
                            'first_name': r'"first_name":\s*"([^"]*)"',
                            'last_name': r'"last_name":\s*"([^"]*)"',
                            'admission_no': r'"admission_no":\s*"([^"]*)"',
                            'gender': r'"gender":\s*"([^"]*)"',
                            'dob': r'"dob":\s*"([^"]*)"',
                            'student_id': r'"student_id":\s*"([^"]*)"',
                            'class_id': r'"class_id":\s*"([^"]*)"',
                            'year': r'"year":\s*(\d+)',
                            'academic_year': r'"academic_year":\s*(\d+)',
                            'term': r'"term":\s*(\d+)',
                            'start_date': r'"start_date":\s*"([^"]*)"',
                            'end_date': r'"end_date":\s*"([^"]*)"',
                            'year_id': r'"year_id":\s*"?([^",}]*)"?',
                            'term_id': r'"term_id":\s*"?([^",}]*)"?',
                        }
                        
                        for param_name, pattern in param_patterns.items():
                            match = re.search(pattern, generated_text)
                            if match:
                                value = match.group(1)
                                # Convert empty strings or "null" to None
                                if value in ["", "null"]:
                                    params[param_name] = None
                                elif param_name in ['year', 'academic_year', 'term']:
                                    try:
                                        params[param_name] = int(value)
                                    except ValueError:
                                        params[param_name] = None
                                else:
                                    params[param_name] = value
                        
                        # Normalize extracted parameters (only if not None)
                        if params.get("gender"):
                            gender = params["gender"].upper()
                            if gender in ["M", "BOY", "MALE"]:
                                params["gender"] = "MALE"
                            elif gender in ["F", "GIRL", "FEMALE"]:
                                params["gender"] = "FEMALE"
                        
                        # Parse date fields
                        for field in ['dob', 'start_date', 'end_date']:
                            if params.get(field):
                                parsed_date = parse_date_flexible(params[field])
                                if parsed_date:
                                    params[field] = parsed_date
                        
                        # Extract needs_clarification if present
                        needs_clarification = []
                        clarification_match = re.search(r'"needs_clarification":\s*\[([^\]]*)\]', generated_text)
                        if clarification_match:
                            clarification_str = clarification_match.group(1)
                            needs_clarification = [
                                item.strip().strip('"').strip("'") 
                                for item in clarification_str.split(',') 
                                if item.strip()
                            ]
                        
                        logger.info(f"Fallback extracted parameters: {params}")
                        logger.info(f"Fallback needs clarification: {needs_clarification}")
                        
                        intent_obj = MistralIntent(
                            intent=intent,
                            parameters=params,
                            needs_clarification=needs_clarification,
                            thought="Parsed from partial response with context",
                            confidence=0.7 if conversation_history else 0.6
                        )
                        
                        return MistralResponse(
                            text=generated_text,
                            structured_output=intent_obj,
                            raw_response=result
                        )
                    
                    # If all parsing fails, return None
                    return MistralResponse(
                        text=generated_text,
                        structured_output=None,
                        raw_response=result
                    )
                
                except ValueError as e:
                    logger.warning(f"Validation error: {e}")
                    return MistralResponse(
                        text=generated_text,
                        structured_output=None,
                        raw_response=result
                    )
        
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling Mistral: {e}")
            raise Exception(f"Mistral API error: {e.response.status_code}")
        
        except httpx.TimeoutException:
            logger.error("Mistral request timed out")
            raise Exception("Request to Mistral timed out")
        
        except Exception as e:
            logger.error(f"Unexpected error querying Mistral: {e}")
            raise
    
    async def list_models(self) -> List[str]:
        """List all available models in Ollama"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/api/tags",
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    models = data.get("models", [])
                    return [model.get("name", "") for model in models]
                else:
                    return []
        except Exception as e:
            logger.error(f"Failed to list models: {e}")
            return []
    
    async def query_conversational(
        self,
        message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Query Mistral for conversational (non-structured) response
        
        Args:
            message: User message
            conversation_history: Previous conversation messages
            
        Returns:
            Text response from Mistral
        """
        try:
            # Build conversation messages
            messages = conversation_history or []
            messages.append({"role": "user", "content": message})
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.chat_url,
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": 0.7,
                            "top_p": 0.9,
                        }
                    },
                    timeout=self.timeout
                )
                
                response.raise_for_status()
                result = response.json()
                
                return result.get("message", {}).get("content", "I couldn't process that request.")
        
        except Exception as e:
            logger.error(f"Conversational query failed: {e}")
            raise Exception(f"Conversational query error: {e}")


# ============================================================================
# Singleton Instance and Module-Level Functions
# ============================================================================

# Singleton instance
_mistral_client_instance: Optional[MistralClient] = None


def get_mistral_client(
    base_url: str = OLLAMA_BASE_URL,
    model: str = DEFAULT_MODEL,
    timeout: float = DEFAULT_TIMEOUT
) -> MistralClient:
    """
    Get or create a Mistral client instance (singleton pattern)
    
    Args:
        base_url: Ollama server URL
        model: Model name
        timeout: Request timeout
        
    Returns:
        MistralClient instance
    """
    global _mistral_client_instance
    
    if _mistral_client_instance is None:
        _mistral_client_instance = MistralClient(
            base_url=base_url,
            model=model,
            timeout=timeout
        )
        logger.info(f"Created Mistral client with model: {model}")
    
    return _mistral_client_instance


async def process_student_query(
    message: str,
    context: Optional[Dict[str, Any]] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None
) -> MistralIntent:
    """
    Process a student management query and extract structured intent
    
    Args:
        message: User message
        context: Additional context
        conversation_history: Previous messages for multi-turn support
        
    Returns:
        MistralIntent with extracted intent and parameters
        
    Raises:
        Exception: If Mistral processing fails
    """
    client = get_mistral_client()
    
    try:
        response = await client.query_structured(
            message=message,
            context=context,
            conversation_history=conversation_history
        )
        
        if response.structured_output:
            return response.structured_output
        else:
            # Fallback to unknown intent
            logger.warning(f"No structured output from Mistral for: {message}")
            return MistralIntent(
                intent="unknown",
                parameters={},
                needs_clarification=[],
                thought="Could not parse request",
                confidence=0.0
            )
    
    except Exception as e:
        logger.error(f"Error processing student query: {e}")
        raise