from pathlib import Path
from typing import Optional

import requests


class OllamaSummarizer:
    """Generates SOAP notes from transcripts using Ollama (local LLM)."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def _load_prompt_template(self) -> str:
        """Load the SOAP note prompt template."""
        prompt_path = Path(__file__).parent.parent / "prompts" / "soap_prompt.txt"
        if prompt_path.exists():
            return prompt_path.read_text()
        return self._default_prompt()

    def _default_prompt(self) -> str:
        """Default SOAP note prompt if file not found."""
        return """You are an experienced physiotherapist writing clinical notes.

Based on the following conversation transcript from a patient session, create a structured SOAP note.

TRANSCRIPT:
{transcript}

Create a SOAP note with these sections:
- S (Subjective): Patient's reported symptoms, complaints, pain levels, history
- O (Objective): Clinical findings, measurements, range of motion, strength tests, special tests
- A (Assessment): Clinical reasoning, diagnosis, progress since last visit
- P (Plan): Treatment plan, exercises prescribed, frequency, follow-up

Format the output as a clean, professional clinical note. Use concise clinical language."""

    def generate_soap_note(self, transcript: str, custom_prompt: Optional[str] = None) -> Optional[str]:
        """
        Generate a SOAP note from a transcript.

        Args:
            transcript: The full session transcript
            custom_prompt: Optional custom prompt template

        Returns:
            Generated SOAP note or None if failed
        """
        prompt_template = custom_prompt or self._load_prompt_template()
        prompt = prompt_template.format(transcript=transcript)

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "top_p": 0.9,
                    },
                },
                timeout=120,
            )
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
        except requests.exceptions.ConnectionError:
            return "Error: Could not connect to Ollama. Please ensure Ollama is running."
        except Exception as e:
            return f"Error generating note: {e}"

    def is_available(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
