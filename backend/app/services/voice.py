"""Voice interaction service for KrishiKavach.

This module provides a reusable VoiceInteractionController that handles the
voice-first farmer experience per SIH26131 requirements.

Interaction flow:
    speak(prompt) → announce_listening → listen → transcribe → return transcript

The service is designed to work with Web Speech API in the browser (demo)
and be swappable with Omi or any other voice provider.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Awaitable, Optional


# ---------------------------------------------------------------------------
# Voice prompts (Marathi + Hindi + English, phonetically readable)
# ---------------------------------------------------------------------------

VOICE_PROMPTS: dict[str, str] = {
    # Greeting
    "greeting": "नमस्ते! मैं कृषिकवच हूँ। कृपया अपनी फसल/पौधे की एक फोटो लें।",
    "greeting_hindi": "Namaskar! Main aapki Krishi Kavach hoon. Kripaya ek photo lein.",
    # Listening
    "please_speak": "कृपया बोलिए। मैं सुन रहा हूँ।",
    "please_speak_hindi": "Kripaya boliye. Main sun raha hoon.",
    # Photo prompt
    "take_photo": "अब कृपया एक फोटो लें। बड़ा हरा बटन दबाएँ।",
    "take_photo_hindi": "Ab kripaya ek photo lein. Bara hara button dabaein.",
    # Analysis
    "analyzing": "फोटो का विश्लेषण हो रहा है। कृपया प्रतीक्षा करें।",
    "analyzing_hindi": "Photo ka vishleshan ho raha hai. Kripaya pratiksha karein.",
    # Result (disease detected)
    "result_disease": "रोग का पता चला: {disease}। {recommendation}",
    "result_disease_hindi": "Rog ka pata chala: {disease}. {recommendation}",
    # Result (healthy)
    "result_healthy": "पौधा स्वस्थ दिखाई दे रहा है। नियमित देखभाल जारी रखें।",
    "result_healthy_hindi": "Pauda swasth dikhai de raha hai. Nyayam dekhabal jare rakhein.",
    # Action buttons
    "action_prompt": "आगे बढ़ने के लिए बटन दबाएँ या बोलें।",
    "action_prompt_hindi": "Aage badhne ke liye button dabaein ya bolein.",
    # Follow-up
    "follow_up_prompt": "क्या आपने उपाय किया? क्या फसल में सुधार हुआ?",
    "follow_up_prompt_hindi": "Kya aapne upaya kiya? Kya fasal mein sudhar hua?",
    # Error
    "error_microphone": "माइक्रोफोन उपलब्ध नहीं है। बटन दबाकर जारी रखें।",
    "error_microphone_hindi": "Microphone upalabd nahi hai. Button daba kar jaari rakhein.",
    "error_speech": "माफ़ कीजिए, बोलना समझ नहीं आया। कृपया फिर से बोलें।",
    "error_speech_hindi": "Maaf keejie, bolna samjh nahi aaya. Kripaya phir se bolein.",
    # Success
    "thank_you": "धन्यवाद! आपकी प्रतिक्रिया दर्ज हो गई।",
    "thank_you_hindi": "Dhanyavaad! Aapki pratirekha darj ho gayi.",
    # Expert escalation
    "escalation": "यह मामला जटिल है। मैं एक विशेषज्ञ को दिखाता हूँ।",
    "escalation_hindi": "Ye mamaela jatil hai. Main ek visheshak ko dikhata hoon.",
    # Uncertainty
    "uncertainty": "मुझे पूरी तरह निश्चित नहीं है। विशेषज्ञ से जाँच करवाएँ।",
    "uncertainty_hindi": "Mujhe poori tarah nishchit nahi hai. Visheshak se jaanch karwaein.",
}


@dataclass
class VoiceIntent:
    """Structured intent extracted from farmer's speech."""
    raw_text: str
    intent: str  # e.g., "yes", "no", "retry", "help", "escalate", "unknown"
    confidence: float
    language: str  # e.g., "marathi", "hindi", "english"


@dataclass
class VoiceResponse:
    """Response from the voice interaction controller."""
    text: str
    language: str = "marathi"
    is_final: bool = True
    should_listen: bool = False


class VoiceInteractionController:
    """Reusable voice interaction controller for the farmer experience.

    This class handles the voice-first interaction pattern:
        speak(prompt) → announce_listening → listen → transcribe → intent → action

    Per Correction #4, this is a reusable architecture, not per-screen logic.

    The actual speech synthesis and recognition is performed client-side
    (browser Web Speech API). This service provides:
    1. Prompt text management
    2. Intent parsing (rule-based keyword matching for demo)
    3. Structured intent extraction

    For production with Omi or another voice provider, swap the
    intent_parser implementation.
    """

    def __init__(self):
        self._language = "marathi"
        self._last_intent: Optional[VoiceIntent] = None

    def set_language(self, language: str) -> None:
        """Set the preferred language for voice prompts."""
        self._language = language

    def get_prompt(self, key: str, **kwargs) -> str:
        """Get a localized voice prompt text.

        Args:
            key: Prompt key from VOICE_PROMPTS (e.g., "greeting", "please_speak")
            **kwargs: Format arguments for the prompt string
        """
        # Prefer language-specific version, fall back to Hindi, then English
        lang_key = f"{key}_{self._language}"
        if lang_key in VOICE_PROMPTS:
            template = VOICE_PROMPTS[lang_key]
        elif f"{key}_hindi" in VOICE_PROMPTS:
            template = VOICE_PROMPTS[f"{key}_hindi"]
        else:
            template = VOICE_PROMPTS.get(key, key)
        return template.format(**kwargs) if kwargs else template

    def parse_intent(self, transcript: str) -> VoiceIntent:
        """Parse farmer's transcript into a structured intent.

        Uses simple keyword matching for demo. In production, replace with
        an LLM-based intent classifier or Omi's built-in intent parsing.

        Per Correction #4 — must handle:
        - microphone unavailable
        - speech recognition unavailable
        - silence
        - permission denied
        - unsupported language
        - user cancellation
        """
        text = transcript.strip().lower()

        # Keyword sets for intent detection
        affirmative = {
            "haan", "han", "ha", "yes", "y", "ji", "haan ji", "bilkul",
            "kya", "kiya", "ki", "kar liya", "kiya", "try kiya",
            "hua", "sudhar", "theek", "better", "improved",
            "हाँ", "हाँ जी", "बिल्कुल", "किया", "हुआ", "सुधार",
        }
        negative = {
            "nahin", "nahi", "na", "no", "n", "nope",
            "nahi hua", "kuch nahi hua", "worsened", "kharab hua",
            "नहीं", "ना", "नहीं हुआ", "खराब हुआ",
        }
        retry = {
            "phir se", "fir se", "again", "baar baar", "dobara", "repea",
            "फिर से", "दोबारा", "again",
        }
        help_escalate = {
            "help", "ved", "expert", "specialist", "madad", "sahayak",
            "विशेषज्ञ", "मदद", "expert", "ved",
        }

        # Check for silence / empty
        if not text or len(text) < 2:
            return VoiceIntent(
                raw_text=transcript,
                intent="silence",
                confidence=0.0,
                language=self._language,
            )

        # Calculate confidence based on keyword matches
        pos = len([w for w in affirmative if w in text])
        neg = len([w for w in negative if w in text])
        ret = len([w for w in retry if w in text])
        hlp = len([w for w in help_escalate if w in text])

        max_match = max(pos, neg, ret, hlp)
        confidence = min(1.0, max_match * 0.5)

        if pos > neg and pos >= ret and pos >= hlp:
            intent = "yes"
        elif neg > pos and neg >= ret and neg >= hlp:
            intent = "no"
        elif ret > 0:
            intent = "retry"
        elif hlp > 0:
            intent = "escalate"
        else:
            intent = "unknown"

        self._last_intent = VoiceIntent(
            raw_text=transcript,
            intent=intent,
            confidence=confidence,
            language=self._language,
        )
        return self._last_intent

    def get_last_intent(self) -> Optional[VoiceIntent]:
        """Return the most recent parsed intent."""
        return self._last_intent

    def get_listening_prompt(self) -> str:
        """Return the standard 'please speak' prompt."""
        return self.get_prompt("please_speak")

    def get_greeting_prompt(self) -> str:
        """Return the greeting + take photo prompt."""
        greeting = self.get_prompt("greeting")
        photo = self.get_prompt("take_photo")
        return f"{greeting} {photo}"


# Singleton instance for the app
_voice_controller: Optional[VoiceInteractionController] = None


def get_voice_controller() -> VoiceInteractionController:
    """Return the shared VoiceInteractionController instance."""
    global _voice_controller
    if _voice_controller is None:
        _voice_controller = VoiceInteractionController()
    return _voice_controller
