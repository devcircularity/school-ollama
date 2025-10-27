from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, FollowupAction
from components.ollama_brain import get_brain
import logging

logger = logging.getLogger(__name__)

class ActionOllamaBrainRouter(Action):
    def name(self):
        return "action_ollama_brain_router"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain):
        """
        Main integration point between Rasa and OllamaBrain.
        - Sends latest user message and context to Ollama
        - Receives JSON {response, action, slots}
        - Updates slots and optionally triggers a Rasa action
        """

        # Extract user message and context
        user_message = tracker.latest_message.get("text", "")
        context = {
            "active_form": tracker.active_loop.get("name"),
            "slots": tracker.current_slot_values(),
            "recent_actions": [
                e.get("name")
                for e in tracker.events
                if e.get("event") == "action"
            ]
        }

        # Send to Ollama Brain
        brain = get_brain()
        result = brain.process(user_message, context)

        # Extract fields from response
        ai_text = result.get("response", "")
        action_name = result.get("action")
        slot_updates = result.get("slots", {})

        logger.info(f"🧠 Ollama Brain Output → Action: {action_name} | Slots: {slot_updates}")

        # Speak response first
        if ai_text:
            dispatcher.utter_message(text=ai_text)

        # Prepare slot events
        events = [SlotSet(slot, val) for slot, val in slot_updates.items() if val is not None]

        # If an action is ready, trigger it directly
        if action_name:
            logger.info(f"⚙️ Triggering follow-up action: {action_name}")
            events.append(FollowupAction(action_name))

        # Otherwise, just continue conversation
        return events