from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import FollowupAction
from components.ollama_brain import get_brain

class ActionOllamaBridge(Action):
    def name(self):
        return "action_ollama_bridge"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain):
        user_message = tracker.latest_message.get("text", "")
        context = {
            "active_form": tracker.active_loop.get("name"),
            "slots": tracker.slots,
            "recent_actions": [
                e.get("name")
                for e in tracker.events
                if e.get("event") == "action"
            ],
        }

        brain = get_brain()
        result = brain.process(user_message, context)

        response = result.get("response", "")
        action = result.get("action")
        slots = result.get("slots", {})

        # --- Handle Ollama response ---
        if response:
            dispatcher.utter_message(text=response)

        events = []

        # Update slots if Ollama returned any
        for key, value in slots.items():
            events.append(SlotSet(key, value))

        # 🔥 Keep Ollama session active
        if not tracker.get_slot("ollama_conversation_active"):
            events.append(SlotSet("ollama_conversation_active", True))

        # Automatically set workflow type for context persistence
        if action == "action_create_student" or "student_name" in slots:
            events.append(SlotSet("ollama_workflow_type", "student_creation"))
        elif action == "action_add_guardian" or "guardian_name" in slots:
            events.append(SlotSet("ollama_workflow_type", "guardian_creation"))

        # If Ollama decided next step (like creating student)
        if action:
            events.append(FollowupAction(action))

        return events