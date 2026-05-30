import os
import sys

# Point Qt at its bundled plugins when running as a frozen app.
# PyInstaller's location for the PyQt6 plugins varies between layouts
# (.app bundles place them under Contents/Frameworks, one-dir builds under
# the executable dir), so probe the known candidates and use the first that
# actually contains the platform plugins.
if getattr(sys, "frozen", False):
    macos_dir = os.path.dirname(sys.executable)       # .../Contents/MacOS
    contents_dir = os.path.dirname(macos_dir)         # .../Contents

    candidates = [
        os.path.join(contents_dir, "Frameworks", "PyQt6", "Qt6", "plugins"),
        os.path.join(contents_dir, "Resources", "PyQt6", "Qt6", "plugins"),
        os.path.join(macos_dir, "PyQt6", "Qt6", "plugins"),
        os.path.join(getattr(sys, "_MEIPASS", macos_dir), "PyQt6", "Qt6", "plugins"),
    ]

    for plugin_path in candidates:
        if os.path.isdir(os.path.join(plugin_path, "platforms")):
            os.environ["QT_PLUGIN_PATH"] = plugin_path
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(
                plugin_path, "platforms"
            )
            break
