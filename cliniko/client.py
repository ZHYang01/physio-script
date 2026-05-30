import base64
from typing import Optional

import requests


class ClinikoClient:
    """Client for interacting with the Cliniko REST API v1."""

    def __init__(self, api_key: str, shard: str = "au1", email: str = "physioscript@local"):
        self.base_url = f"https://api.{shard}.cliniko.com/v1"
        self.headers = {
            "Authorization": f"Basic {base64.b64encode((api_key + ':').encode()).decode()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"PhysioScript ({email})",
        }

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[dict]:
        """Make an authenticated request to the Cliniko API."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        try:
            response = requests.request(
                method, url, headers=self.headers, timeout=30, **kwargs
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            print(f"Cliniko API error: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            print(f"Cliniko request error: {e}")
            return None

    def get_patients(self, search: Optional[str] = None, page: int = 1, per_page: int = 50) -> list[dict]:
        """
        Get patients, optionally filtered by search term.

        Args:
            search: Optional search term (name, email, etc.)
            page: Page number
            per_page: Results per page (max 100)

        Returns:
            List of patient records
        """
        params = {"page": page, "per_page": per_page}
        if search:
            params["q[]"] = [
                f"first_name:~{search}",
                f"last_name:~{search}",
            ]

        data = self._request("GET", "patients", params=params)
        return data.get("patients", []) if data else []

    def get_patient(self, patient_id: str) -> Optional[dict]:
        """Get a single patient by ID."""
        return self._request("GET", f"patients/{patient_id}")

    def get_appointments(
        self,
        patient_id: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> list[dict]:
        """Get appointments, optionally filtered by patient."""
        params = {"page": page, "per_page": per_page}
        if patient_id:
            params["q[]"] = [f"patient_id:{patient_id}"]

        data = self._request("GET", "individual_appointments", params=params)
        return data.get("individual_appointments", []) if data else []

    def get_treatment_note_templates(self) -> list[dict]:
        """Get available treatment note templates."""
        data = self._request("GET", "treatment_note_templates")
        return data.get("treatment_note_templates", []) if data else []

    def create_treatment_note(
        self,
        patient_id: str,
        title: str,
        content: dict,
        treatment_note_template_id: Optional[str] = None,
        booking_id: Optional[str] = None,
        draft: bool = False,
    ) -> Optional[dict]:
        """
        Create a treatment note for a patient.

        Args:
            patient_id: Patient ID
            title: Note title
            content: Structured content with sections and questions
            treatment_note_template_id: Optional template ID
            booking_id: Optional booking/appointment ID
            draft: Whether to save as draft

        Returns:
            Created treatment note or None
        """
        payload = {
            "patient_id": patient_id,
            "title": title,
            "content": content,
            "draft": draft,
        }
        if treatment_note_template_id:
            payload["treatment_note_template_id"] = treatment_note_template_id
        if booking_id:
            payload["booking_id"] = booking_id

        return self._request("POST", "treatment_notes", json=payload)

    def create_soap_note(
        self,
        patient_id: str,
        soap_text: str,
        title: Optional[str] = None,
        booking_id: Optional[str] = None,
    ) -> Optional[dict]:
        """
        Create a SOAP treatment note from formatted text.

        Args:
            patient_id: Patient ID
            soap_text: The formatted SOAP note text
            title: Optional title (defaults to "Session Note - {date}")
            booking_id: Optional booking ID

        Returns:
            Created treatment note or None
        """
        from datetime import datetime

        if not title:
            title = f"Session Note - {datetime.now().strftime('%Y-%m-%d')}"

        # Parse SOAP sections
        content = self._parse_soap_content(soap_text)

        return self.create_treatment_note(
            patient_id=patient_id,
            title=title,
            content=content,
            booking_id=booking_id,
        )

    def _parse_soap_content(self, soap_text: str) -> dict:
        """Parse SOAP text into Cliniko's structured content format."""
        sections = []
        current_section = None
        current_lines = []

        for line in soap_text.split("\n"):
            stripped = line.strip()
            # Detect section headers (S, O, A, P)
            if stripped and (
                stripped.startswith("S ") or stripped.startswith("S:")
                or stripped.startswith("O ") or stripped.startswith("O:")
                or stripped.startswith("A ") or stripped.startswith("A:")
                or stripped.startswith("P ") or stripped.startswith("P:")
            ):
                if current_section:
                    sections.append({
                        "name": current_section,
                        "questions": [{"name": "Details", "answer": "\n".join(current_lines), "type": "paragraph"}],
                    })
                current_section = stripped.split(":")[0].split(" ")[0]
                current_lines = []
            elif stripped:
                current_lines.append(stripped)

        # Add the last section
        if current_section:
            sections.append({
                "name": current_section,
                "questions": [{"name": "Details", "answer": "\n".join(current_lines), "type": "paragraph"}],
            })

        # If no sections found, put everything in a single section
        if not sections:
            sections = [{
                "name": "Clinical Notes",
                "questions": [{"name": "Notes", "answer": soap_text, "type": "paragraph"}],
            }]

        return {"sections": sections}
