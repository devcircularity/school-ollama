# app/ai/actions/general_actions.py
"""
General Actions Handler
Handles conversational intents and onboarding guidance
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# General Intent Detection
# ============================================================================

def detect_general_intent(message: str) -> Optional[str]:
    """
    Detect general conversational intents
    
    Args:
        message: User message
        
    Returns:
        Intent string or None
    """
    message_lower = message.lower().strip()
    
    # IMPORTANT: Check for business actions FIRST to avoid false positives
    # If message contains business keywords, don't treat as general conversation
    business_keywords = [
        "enroll", "add student", "create student", "register student",
        "update student", "delete student", "remove student",
        "create class", "add class", "list students", "show students",
        "list classes", "show classes", "find student", "search student",
        "assign", "change class", "move student", "transfer student"
    ]
    
    if any(keyword in message_lower for keyword in business_keywords):
        return None  # Let business intent handlers process this
    
    # Greetings - must be standalone or at the start
    greeting_words = ["hello", "hi", "hey", "good morning", "good afternoon", 
                     "good evening", "greetings", "howdy"]
    
    # Check if message is ONLY a greeting (with optional punctuation)
    words = message_lower.strip('!.,?').split()
    if len(words) <= 3 and any(greeting in words for greeting in greeting_words):
        return "greeting"
    
    # Check if message starts with greeting + name/there
    if any(message_lower.startswith(f"{g} ") for g in greeting_words):
        # Make sure it's not followed by a business action
        remaining = message_lower.split(maxsplit=1)
        if len(remaining) > 1 and not any(kw in remaining[1] for kw in business_keywords):
            return "greeting"
    
    # Help requests - must be clear help requests
    help_phrases = [
        "help me", "what can you do", "what can you help",
        "show me what you can do", "capabilities", "what are your features",
        "how to use", "how do i use", "guide me", "need help",
        "can you help"
    ]
    
    if any(phrase in message_lower for phrase in help_phrases):
        return "help"
    
    # School setup/onboarding intents
    school_setup_phrases = [
        "create a school", "create school", "new school", "add a school",
        "setup school", "set up school", "register school", "start a school",
        "i want to create a school", "how do i create a school", "make a school"
    ]
    
    if any(phrase in message_lower for phrase in school_setup_phrases):
        return "school_setup"
    
    # Getting started
    getting_started_phrases = [
        "get started", "getting started", "where do i start", 
        "how to begin", "first steps", "onboarding", "setup guide",
        "how do i get started"
    ]
    
    if any(phrase in message_lower for phrase in getting_started_phrases):
        return "getting_started"
    
    # Thank you - must be standalone or clear thank you
    thank_you_phrases = [
        "thank you", "thanks", "thx", "appreciate it", 
        "thanks a lot", "thank you very much"
    ]
    
    # Check if it's a standalone thank you
    if any(phrase == message_lower.strip('!.,?') for phrase in thank_you_phrases):
        return "thanks"
    
    if any(message_lower.startswith(phrase) for phrase in thank_you_phrases):
        # Make sure it's not followed by a business request
        if not any(kw in message_lower for kw in business_keywords):
            return "thanks"
    
    # Goodbye - must be standalone
    goodbye_phrases = ["bye", "goodbye", "see you", "later", "exit", "quit"]
    
    if any(phrase == message_lower.strip('!.,?') for phrase in goodbye_phrases):
        return "goodbye"
    
    return None


def is_general_conversation(message: str) -> bool:
    """Check if message is general conversation vs business action"""
    return detect_general_intent(message) is not None


# ============================================================================
# Response Generation
# ============================================================================

def respond_to_general_intent(
    intent: str, 
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Generate response for general intents with context awareness
    
    Args:
        intent: Detected general intent
        context: User context (user_name, school_id, schools, etc.)
        
    Returns:
        Dict with message and suggestions
    """
    context = context or {}
    user_name = context.get("user_name", "there")
    schools = context.get("schools", [])
    has_school = len(schools) > 0
    current_school = context.get("current_school_name")
    
    responses = {
        "greeting": {
            "message": f"Hello {user_name}! 👋 How can I assist you with school management today?",
            "suggestions": [
                "Show me all students",
                "List all classes",
                "Show school statistics",
                "What can you help me with?"
            ]
        },
        
        "help": {
            "message": get_help_text(has_school=has_school),
            "suggestions": [
                "Show me all students",
                "List all classes",
                "Create a new student",
                "Show school information"
            ]
        },
        
        "school_setup": {
            "message": generate_school_setup_guidance(
                user_name=user_name,
                has_school=has_school,
                schools=schools,
                current_school=current_school
            ),
            "suggestions": get_school_setup_suggestions(has_school)
        },
        
        "getting_started": {
            "message": generate_onboarding_guide(
                user_name=user_name,
                has_school=has_school,
                schools=schools,
                current_school=current_school
            ),
            "suggestions": get_onboarding_suggestions(has_school)
        },
        
        "thanks": {
            "message": f"You're welcome, {user_name}! 😊 Let me know if you need anything else.",
            "suggestions": [
                "Show me all students",
                "List all classes",
                "What can you help me with?"
            ]
        },
        
        "goodbye": {
            "message": f"Goodbye, {user_name}! Have a great day! 👋",
            "suggestions": []
        }
    }
    
    return responses.get(intent, {
        "message": "I'm here to help! What would you like to do?",
        "suggestions": ["Show me all students", "List classes", "Get help"]
    })


# ============================================================================
# School Setup Guidance
# ============================================================================

def generate_school_setup_guidance(
    user_name: str,
    has_school: bool,
    schools: list,
    current_school: Optional[str] = None
) -> str:
    """
    Generate context-aware school setup guidance
    
    Args:
        user_name: User's name
        has_school: Whether user has any schools
        schools: List of user's schools
        current_school: Name of currently selected school
        
    Returns:
        Formatted guidance message
    """
    if not has_school:
        # User has no schools - guide them to create one
        return f"""👋 **Welcome to School Assistant, {user_name}!**

I see you haven't set up a school yet. Let's get you started!

**To create your school:**
1. Go to the **Schools** section in the navigation menu
2. Click on **"Create School"** or **"Add New School"**
3. Fill in your school details:
   • School name
   • Address and contact information
   • Academic year start date
   • School type (Day/Boarding/Both)
   • Gender type (Boys/Girls/Mixed)

**Or ask me for help:**
- "Show me how to create a school"
- "What information do I need to set up a school?"

Once your school is set up, I can help you manage students, classes, fees, and much more! 🎓"""
    
    elif len(schools) == 1:
        # User has exactly one school
        school_name = current_school or schools[0].get('name', 'your school')
        return f"""✅ **You already have a school set up!**

**Current school:** {school_name}

You're all set to start managing your school. I can help you with:

📚 **Student Management**
- Add new students
- View and search students
- Enroll students in classes

🏫 **Class Management**
- Create classes
- Assign students to classes
- View class rosters

📊 **School Operations**
- View school statistics
- Manage academic terms
- Track enrollments

**Try asking:**
- "Show me all students"
- "List all classes"
- "Show school statistics"
- "Create a new student"

What would you like to do?"""
    
    else:
        # User has multiple schools
        school_names = "\n".join([f"• {s.get('name', 'Unnamed')}" for s in schools[:5]])
        more = f"\n• ...and {len(schools) - 5} more" if len(schools) > 5 else ""
        
        current_msg = f"\n**Currently working with:** {current_school}" if current_school else ""
        
        return f"""✅ **You have {len(schools)} schools!**

{school_names}{more}{current_msg}

**To create another school:**
1. Go to the **Schools** section
2. Click **"Add New School"**
3. Fill in the school details

**To switch schools:**
- Use the school selector in the navigation bar
- Select the school you want to work with

**Need help?** Just ask me about students, classes, or school management!"""


def get_school_setup_suggestions(has_school: bool) -> list:
    """Get context-aware suggestions for school setup"""
    if not has_school:
        return [
            "How do I create a school?",
            "What information do I need?",
            "Show me the setup process"
        ]
    else:
        return [
            "Show me all students",
            "List all classes",
            "Show school statistics",
            "Create a new student"
        ]


# ============================================================================
# Onboarding Guide
# ============================================================================

def generate_onboarding_guide(
    user_name: str,
    has_school: bool,
    schools: list,
    current_school: Optional[str] = None
) -> str:
    """Generate comprehensive onboarding guide"""
    
    if not has_school:
        return f"""🚀 **Getting Started with School Assistant**

Welcome, {user_name}! Let me guide you through the setup process.

**Step 1: Create Your School** 🏫
First, you'll need to set up your school profile:
- Navigate to **Schools** → **Create School**
- Enter school name, address, and contact details
- Set your academic year start date
- Choose school type and gender settings

**Step 2: Set Up Academic Structure** 📅
Once your school is created:
- Create academic years (e.g., 2024/2025)
- Add academic terms (e.g., Term 1, Term 2, Term 3)
- Set up classes/grades (e.g., Grade 1, Grade 2)

**Step 3: Add Students** 👨‍🎓
You can add students by:
- Manually entering student information
- Importing from a spreadsheet (coming soon)
- Using the chat: "Add student John Doe, admission A101, male, born 2010-05-15"

**Step 4: Start Managing!** 🎉
Once set up, you can:
- Enroll students in classes
- Track attendance
- Manage fees and payments
- Generate reports

**Quick tip:** You can ask me questions in natural language! Try:
- "Show me all students"
- "How many students are in Grade 5?"
- "List empty classes"

Ready to create your school?"""
    
    else:
        school_name = current_school or schools[0].get('name', 'your school')
        return f"""🎓 **Quick Guide for {school_name}**

Great! You're already set up. Here's what you can do:

**📚 Student Management**
- "Add student John Doe, admission A101, male, born 2010-05-15"
- "Show me all students"
- "Find students in Grade 5"
- "Who hasn't been assigned to a class?"

**🏫 Class Management**
- "Create Grade 6 Blue class"
- "List all classes"
- "Show classes without students"
- "Show me Grade 7 details"

**📊 School Information**
- "Show school statistics"
- "How many students do we have?"
- "Show school information"
- "What's the current term?"

**💡 Pro Tips:**
- Use natural language - I'll understand!
- Be specific with dates (YYYY-MM-DD format)
- Include admission numbers for accuracy
- Ask for help anytime: "What can you help me with?"

**Common Tasks:**
- Enroll a student: "Enroll Jane in Grade 5"
- Update info: "Change John's class to Grade 6"
- Search: "Find students named Mary"

What would you like to do today?"""


def get_onboarding_suggestions(has_school: bool) -> list:
    """Get onboarding-specific suggestions"""
    if not has_school:
        return [
            "How do I create my school?",
            "Show me the setup steps",
            "What should I do first?"
        ]
    else:
        return [
            "Show me all students",
            "Create a new student",
            "List all classes",
            "Show school statistics"
        ]


# ============================================================================
# Help Text
# ============================================================================

def get_help_text(has_school: bool = True) -> str:
    """Generate comprehensive help text"""
    
    base_help = """🤖 **I'm your School Management Assistant!**

I can help you with:

**👨‍🎓 Student Management**
- Create students: "Add student John Doe, admission A101, male, born 2010-05-15"
- List students: "Show me all students" or "Students in Grade 5"
- Get details: "Tell me about student A101"
- Update info: "Change John's class to Grade 6"
- Search: "Find students named Mary"
- Unassigned: "Who hasn't been assigned to a class?"

**🏫 Class Management**
- Create classes: "Create Grade 6 Blue for 2025"
- List classes: "Show all classes"
- Empty classes: "Which classes have no students?"
- Class details: "Show me Grade 7 details"
- Update: "Rename Grade 6 Blue to Gold"

**📊 School Information**
- Statistics: "How many students do we have?"
- School details: "Show school information"
- Current term: "What term are we in?"
- Academic years: "Show all academic years"

**💡 Tips:**
- Use natural language - just ask!
- Dates: Use YYYY-MM-DD format (e.g., 2010-05-15)
- Gender: MALE or FEMALE
- Be specific for better results

**Examples:**
- "Register a new student Alice, admission A205, female, born 2011-06-15"
- "Show students in Grade 4"
- "How many students do we have in total?"
- "List empty classes"
- "Enroll student A101 in class 2 Green"

What would you like help with?"""
    
    if not has_school:
        return f"""🚀 **Welcome to School Assistant!**

Before we can start managing students and classes, you'll need to **create your school**.

**To get started:**
1. Navigate to the **Schools** section
2. Click **"Create School"**
3. Fill in your school information

{base_help}"""
    
    return base_help