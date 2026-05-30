import pyperclip


class ClipboardManager:
    """Manages clipboard operations for copying notes."""

    def copy_to_clipboard(self, text: str) -> bool:
        """
        Copy text to the system clipboard.

        Args:
            text: Text to copy

        Returns:
            True if successful
        """
        try:
            pyperclip.copy(text)
            return True
        except Exception as e:
            print(f"Clipboard error: {e}")
            return False

    def paste_from_clipboard(self) -> str:
        """Get text from the system clipboard."""
        try:
            return pyperclip.paste()
        except Exception:
            return ""

    def copy_soap_note(self, soap_text: str) -> bool:
        """
        Copy a formatted SOAP note to clipboard with proper formatting.

        Args:
            soap_text: The SOAP note text

        Returns:
            True if successful
        """
        # Ensure clean formatting for pasting into Cliniko
        formatted = soap_text.strip()
        return self.copy_to_clipboard(formatted)
