"""
Ollama Preprocessing Layer for School Management AI
Normalizes natural language before Rasa NLU processing
"""

import requests
import json
import logging
import re  # ← Add this import
from typing import Dict, List, Any, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import asyncio
import httpx

logger = logging.getLogger(__name__)

# Global thread pool for async operations
_executor = ThreadPoolExecutor(max_workers=3)


class OllamaPreprocessor:
    """
    Preprocesses user messages using Ollama to:
    1. Normalize terminology (grade → class, form → class level)
    2. Extract structured entities
    3. Expand abbreviations (PP1, Std 5, etc.)
    4. Maintain conversation context
    5. Semantic normalization for intent matching
    """
    
    def __init__(
        self,
        model: str = None,
        ollama_url: str = None,
        temperature: float = None
    ):
        # Load from config if not provided
        try:
            from components.config import get_ollama_config
            config = get_ollama_config()
            
            self.model = model or config.model
            self.ollama_url = ollama_url or config.url
            self.temperature = temperature if temperature is not None else config.temperature
            self.timeout = config.timeout
            self.enabled = config.enabled
            
            logger.info(f"Initialized OllamaPreprocessor with model: {self.model}")
        except ImportError:
            # Fallback to defaults if config not available
            self.model = model or "llama3.2:latest"
            self.ollama_url = ollama_url or "http://localhost:11434"
            self.temperature = temperature if temperature is not None else 0.1
            self.timeout = 10
            self.enabled = True
            logger.warning("Config module not found, using default settings")
        
        self.conversation_history: List[Dict] = []
        self._cache: Dict[str, Dict] = {}
    
    def normalize_semantics(self, text: str) -> str:
        """
        Lightweight semantic normalization to standardize user queries
        This runs BEFORE Ollama to catch common patterns instantly
        """
        text_lower = text.lower().strip()
        original_text = text_lower  # Keep for logging
        
        # Define semantic rewrite rules (order matters!)
        replacements = [
            # ========================================
            # STUDENT LISTING PATTERNS
            # ========================================
            (r"(list|show|display|see|view).*(students?).*(school|system|database)", "list all students"),
            (r"(do we have|are there|how many).*(students?)", "list all students"),
            (r"(show|list|display|get).*(all)?.*(students?)", "list all students"),
            (r"(students?).*(list|show|display)", "list all students"),
            (r"(view|check).*(students?)", "list all students"),
            
            # ========================================
            # CLASS LISTING PATTERNS
            # ========================================
            (r"(list|show|display|see).*(class(?:es)?|grade(?:s)?).*(school)", "list all classes"),
            (r"(what|which).*(class(?:es)?|grade(?:s)?).*(have|exist)", "list all classes"),
            (r"(show|list).*(all)?.*(class(?:es)?)", "list all classes"),
            
            # ========================================
            # GUARDIAN PATTERNS
            # ========================================
            (r"(list|show|display).*(guardians?|parents?)", "list all guardians"),
            (r"(students?).*(without|no).*(guardians?|parents?)", "list students without guardians"),
            
            # ========================================
            # ACADEMIC SETUP PATTERNS
            # ========================================
            (r"(check|show|view).*(academic|school).*(setup|configuration)", "check academic setup"),
            (r"(what|which).*(academic year|term).*(active|current)", "check academic setup"),
            
            # ========================================
            # TERMINOLOGY NORMALIZATION
            # ========================================
            (r"\bgrade\s+(\d+)", r"class \1"),  # "grade 5" → "class 5"
            (r"\bform\s+1\b", "class 9"),
            (r"\bform\s+2\b", "class 10"),
            (r"\bform\s+3\b", "class 11"),
            (r"\bform\s+4\b", "class 12"),
            (r"\bstd\s+(\d+)", r"class \1"),  # "std 5" → "class 5"
            (r"\bstandard\s+(\d+)", r"class \1"),
            (r"\bpp1\b", "pre-primary 1"),
            (r"\bpp2\b", "pre-primary 2"),
            
            # ========================================
            # SYNONYM NORMALIZATION
            # ========================================
            (r"\bparent(?:s)?\b", "guardian"),
            (r"\bcaregiver(?:s)?\b", "guardian"),
            (r"\bmum\b", "mother"),
            (r"\bmom\b", "mother"),
            (r"\bdad\b", "father"),
            (r"\bpapa\b", "father"),
            
            # ========================================
            # ACTION SYNONYMS
            # ========================================
            (r"\bregister\b", "create"),
            (r"\badd new\b", "create"),
            (r"\benroll\b", "create"),
            (r"\bremove\b", "delete"),
            (r"\berase\b", "delete"),
        ]
        
        # Apply replacements
        for pattern, replacement in replacements:
            text_lower = re.sub(pattern, replacement, text_lower, flags=re.IGNORECASE)
        
        # Log normalization if text changed
        if text_lower != original_text:
            logger.info(f"Semantic normalization: '{original_text}' → '{text_lower}'")
        
        return text_lower
        
    def preprocess(self, user_message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Main preprocessing function with semantic normalization
        
        Flow:
        1. Apply semantic normalization (instant)
        2. Check cache (instant)
        3. Check quick patterns (instant)
        4. Call Ollama if needed (async, 10s timeout)
        
        Returns:
            {
                "normalized_text": str,
                "suggested_intent": str,
                "entities": List[Dict],
                "confidence": float,
                "context_update": Dict
            }
        """
        
        # Check if Ollama is enabled
        if not self.enabled:
            return self._get_safe_default(user_message)
        
        # ========================================
        # STEP 1: SEMANTIC NORMALIZATION (instant)
        # ========================================
        normalized_message = self.normalize_semantics(user_message)
        
        # ========================================
        # STEP 2: CHECK CACHE (instant)
        # ========================================
        cache_key = normalized_message.lower().strip()
        if cache_key in self._cache:
            logger.debug(f"Cache hit for: {cache_key}")
            return self._cache[cache_key]
        
        # ========================================
        # STEP 3: QUICK PATTERN MATCHING (instant)
        # ========================================
        quick_response = self._check_quick_patterns(normalized_message)
        if quick_response:
            return quick_response
        
        # ========================================
        # STEP 4: OLLAMA PROCESSING (async, timeout)
        # ========================================
        prompt = self._build_preprocessing_prompt(normalized_message, context)
        
        try:
            # Call Ollama asynchronously with timeout
            response = self._call_ollama_async_wrapper(prompt)
            result = self._parse_ollama_response(response)
            
            # Use the semantically normalized text if Ollama didn't improve it
            if not result.get("normalized_text") or result["normalized_text"] == user_message:
                result["normalized_text"] = normalized_message
            
            # Cache common responses
            if cache_key in ["hi", "hello", "hey", "greet", "list all students", "list all classes"]:
                self._cache[cache_key] = result
            
            # Add to conversation history
            self.conversation_history.append({
                "user": user_message,
                "processed": result
            })
            
            # Keep only last 5 exchanges
            if len(self.conversation_history) > 5:
                self.conversation_history = self.conversation_history[-5:]
            
            return result
            
        except Exception as e:
            logger.error(f"Ollama preprocessing failed: {e}")
            # Return semantically normalized text as fallback
            return {
                "normalized_text": normalized_message,
                "suggested_intent": None,
                "entities": [],
                "confidence": 0.5,  # Medium confidence for semantic normalization
                "context_update": {}
            }
    
    def _check_quick_patterns(self, message: str) -> Optional[Dict]:
        """Fast pattern matching for common inputs (after semantic normalization)"""
        msg_lower = message.lower().strip()
        
        # Common greetings - skip Ollama entirely
        if msg_lower in ["hi", "hello", "hey", "greetings", "good morning", "good afternoon"]:
            return {
                "normalized_text": message,
                "suggested_intent": "greet",
                "entities": [],
                "confidence": 0.95,
                "context_update": {}
            }
        
        # Quick goodbye detection
        if msg_lower in ["bye", "goodbye", "see you", "exit", "quit"]:
            return {
                "normalized_text": message,
                "suggested_intent": "goodbye",
                "entities": [],
                "confidence": 0.95,
                "context_update": {}
            }
        
        # After semantic normalization, check for exact matches
        if msg_lower == "list all students":
            return {
                "normalized_text": "list all students",
                "suggested_intent": "list_students",
                "entities": [],
                "confidence": 0.90,
                "context_update": {}
            }
        
        if msg_lower == "list all classes":
            return {
                "normalized_text": "list all classes",
                "suggested_intent": "list_classes",
                "entities": [],
                "confidence": 0.90,
                "context_update": {}
            }
        
        if msg_lower == "check academic setup":
            return {
                "normalized_text": "check academic setup",
                "suggested_intent": "check_academic_setup",
                "entities": [],
                "confidence": 0.90,
                "context_update": {}
            }
        
        return None
    
    def _call_ollama_async_wrapper(self, prompt: str) -> str:
        """
        Wrapper to call async Ollama function from sync context
        Uses thread pool to avoid blocking Rasa
        """
        try:
            # Run async call in thread pool with timeout
            future = _executor.submit(self._run_async_ollama, prompt)
            response = future.result(timeout=self.timeout)
            return response
            
        except FutureTimeoutError:
            logger.warning(f"Ollama request timed out after {self.timeout}s")
            raise TimeoutError(f"Ollama timeout after {self.timeout}s")
        except Exception as e:
            logger.error(f"Async Ollama call failed: {e}")
            raise
    
    def _run_async_ollama(self, prompt: str) -> str:
        """
        Run async Ollama call using httpx
        This runs in a separate thread via ThreadPoolExecutor
        """
        return asyncio.run(self._call_ollama_async(prompt))
    
    async def _call_ollama_async(self, prompt: str) -> str:
        """Async Ollama API call using httpx"""
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "temperature": self.temperature,
            "system": "You are a JSON output generator. Always respond with valid JSON only, no explanations.",
            "format": "json",
            "options": {
                "num_predict": 300,
                "temperature": self.temperature,
                "top_p": 0.9,
                "top_k": 40
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json=payload
                )
                response.raise_for_status()
                
                result = response.json()["response"]
                logger.debug(f"Ollama raw response: {result[:200]}")
                
                return result
                
        except httpx.TimeoutException:
            logger.error(f"Ollama async request timed out after {self.timeout}s")
            raise
        except httpx.RequestError as e:
            logger.error(f"Ollama async API error: {e}")
            raise

    def _build_preprocessing_prompt(self, message: str, context: Optional[Dict]) -> str:
        """Build the prompt for Ollama with school-specific instructions"""
        
        context_str = ""
        if context:
            context_str = f"\nCurrent Context: {json.dumps(context, indent=2)}"
        
        history_str = ""
        if self.conversation_history:
            recent = self.conversation_history[-2:]
            history_str = "\nRecent:\n" + "\n".join([
                f"User: {h['user']}" for h in recent
            ])
        
        return f"""You are a JSON-only preprocessing system for a Kenyan school management assistant. Your ONLY job is to output valid JSON.

CRITICAL: Respond with ONLY a single line of valid JSON. No explanations, no markdown, no extra text.

{history_str}{context_str}

**Entity Types to Extract:**
- student_name, admission_no, class_name, level, stream
- guardian_name, phone, relationship
- academic_year, amount

User Message: "{message}"

Output ONLY this JSON (one line):
{{"normalized_text": "{message}", "suggested_intent": "intent_name", "entities": [], "confidence": 0.85, "context_update": {{}}}}

JSON:"""

    def _parse_ollama_response(self, response: str) -> Dict[str, Any]:
        """Parse Ollama's JSON response with robust error handling"""
        
        try:
            response = response.strip()
            
            # Remove markdown code blocks if present
            if response.startswith("```json"):
                response = response.replace("```json", "").replace("```", "").strip()
            elif response.startswith("```"):
                response = response.replace("```", "").strip()
            
            # Find JSON object
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            
            if json_start == -1 or json_end == 0:
                logger.warning(f"No JSON found in Ollama response: {response[:100]}")
                raise ValueError("No JSON found in response")
            
            json_str = response[json_start:json_end]
            result = json.loads(json_str)
            
            # Validate and fix
            result = self._validate_and_fix_result(result, response)
            
            return result
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse Ollama JSON: {e}")
            return self._fallback_parsing(response)
        
        except Exception as e:
            logger.error(f"Unexpected error parsing Ollama response: {e}")
            return self._get_safe_default(response)
    
    def _validate_and_fix_result(self, result: Dict, original_response: str) -> Dict:
        """Validate and fix the parsed result"""
        
        required_fields = {
            "normalized_text": "",
            "suggested_intent": None,
            "entities": [],
            "confidence": 0.5,
            "context_update": {}
        }
        
        for field, default in required_fields.items():
            if field not in result:
                result[field] = default
        
        if not result.get("normalized_text"):
            result["normalized_text"] = original_response.strip()[:200]
        
        if not isinstance(result.get("entities"), list):
            result["entities"] = []
        
        try:
            conf = float(result.get("confidence", 0.5))
            result["confidence"] = max(0.0, min(1.0, conf))
        except (ValueError, TypeError):
            result["confidence"] = 0.5
        
        return result
    
    def _fallback_parsing(self, response: str) -> Dict[str, Any]:
        """Fallback parsing when JSON fails"""
        
        normalized_text = response.strip()
        intent_match = None
        
        if "greet" in response.lower() or "hello" in response.lower():
            intent_match = "greet"
        elif "student" in response.lower() and "create" in response.lower():
            intent_match = "create_student"
        
        return {
            "normalized_text": normalized_text[:200],
            "suggested_intent": intent_match,
            "entities": [],
            "confidence": 0.3,
            "context_update": {}
        }
    
    def _get_safe_default(self, original_text: str) -> Dict[str, Any]:
        """Get a safe default response"""
        return {
            "normalized_text": original_text.strip() if original_text else "",
            "suggested_intent": None,
            "entities": [],
            "confidence": 0.0,
            "context_update": {}
        }
    
    def reset_context(self):
        """Clear conversation history"""
        self.conversation_history = []
        self._cache.clear()


# Singleton instance
_preprocessor_instance = None

def get_preprocessor() -> OllamaPreprocessor:
    """Get or create preprocessor singleton"""
    global _preprocessor_instance
    if _preprocessor_instance is None:
        _preprocessor_instance = OllamaPreprocessor()
    return _preprocessor_instance