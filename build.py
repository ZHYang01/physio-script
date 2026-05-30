#!/usr/bin/env python3
"""
Build script for Physio Script - macOS Desktop App

Usage:
    python build.py            # Build .app bundle
    python build.py --dmg      # Build .app + DMG installer
    python build.py --clean    # Clean build artifacts first
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"
SPEC_FILE = PROJECT_ROOT / "physio_script.spec"


def run(cmd: list[str], check: bool = True):
    """Run a command and print it."""
    print(f"  > {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if check and result.returncode != 0:
        print(f"ERROR: Command failed with exit code {result.returncode}")
        sys.exit(1)
    return result


def clean():
    """Remove build artifacts."""
    print("\nCleaning build artifacts...")
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  Removed {d}/")
    # Remove __pycache__ dirs
    for cache in PROJECT_ROOT.rglob("__pycache__"):
        shutil.rmtree(cache)
    print("  Clean complete.")


def check_prerequisites():
    """Check that required tools are installed."""
    print("Checking prerequisites...")

    # Check PyInstaller
    try:
        import PyInstaller
        print(f"  PyInstaller: {PyInstaller.__version__}")
    except ImportError:
        print("  ERROR: PyInstaller not installed. Run: pip install pyinstaller")
        sys.exit(1)

    # Check if main.py exists
    if not (PROJECT_ROOT / "main.py").exists():
        print("  ERROR: main.py not found")
        sys.exit(1)

    # Check prompts directory
    if not (PROJECT_ROOT / "prompts").exists():
        print("  ERROR: prompts/ directory not found")
        sys.exit(1)

    print("  All prerequisites OK.")


def build_app():
    """Build the .app bundle using PyInstaller."""
    print("\nBuilding PhysioScript.app...")

    # When using a .spec file, only pass --clean, --noconfirm, and paths
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        str(SPEC_FILE),
    ]

    run(cmd)

    app_path = DIST_DIR / "PhysioScript.app"
    if app_path.exists():
        size_mb = sum(f.stat().st_size for f in app_path.rglob("*") if f.is_file()) / (1024 * 1024)
        print(f"\n  Build successful!")
        print(f"  App: {app_path}")
        print(f"  Size: {size_mb:.1f} MB")
        return app_path
    else:
        print("  ERROR: .app bundle not found after build")
        sys.exit(1)


def create_dmg(app_path: Path):
    """Create a DMG installer from the .app bundle."""
    print("\nCreating DMG installer...")

    dmg_name = "PhysioScript-Installer.dmg"
    dmg_path = DIST_DIR / dmg_name

    # Remove old DMG if exists
    if dmg_path.exists():
        dmg_path.unlink()

    # Use hdiutil to create DMG
    # First create a temporary directory with the app and a symlink to Applications
    temp_dmg = DIST_DIR / "temp_dmg"
    if temp_dmg.exists():
        shutil.rmtree(temp_dmg)
    temp_dmg.mkdir()

    # Copy app with `ditto`, NOT shutil.copytree. PyInstaller .app bundles
    # contain hundreds of symlinks (Contents/Resources/*.dylib -> Frameworks/*);
    # shutil.copytree dereferences them by default, which breaks dyld and makes
    # the app in the DMG crash on launch (exit 139). ditto preserves the bundle
    # structure, symlinks, and signatures correctly.
    run(["ditto", str(app_path), str(temp_dmg / "PhysioScript.app")])

    # Create Applications symlink
    os.symlink("/Applications", temp_dmg / "Applications")

    # Create DMG
    cmd = [
        "hdiutil", "create",
        "-volname", "Physio Script",
        "-srcfolder", str(temp_dmg),
        "-ov",
        "-format", "UDZO",
        str(dmg_path),
    ]
    run(cmd)

    # Cleanup
    shutil.rmtree(temp_dmg)

    if dmg_path.exists():
        size_mb = dmg_path.stat().st_size / (1024 * 1024)
        print(f"  DMG created: {dmg_path}")
        print(f"  Size: {size_mb:.1f} MB")
    else:
        print("  WARNING: DMG creation may have failed")


def main():
    args = sys.argv[1:]
    do_clean = "--clean" in args
    do_dmg = "--dmg" in args

    print("=" * 50)
    print("  Physio Script - Build Tool")
    print("=" * 50)

    if do_clean:
        clean()

    check_prerequisites()
    app_path = build_app()

    if do_dmg:
        create_dmg(app_path)

    print("\n" + "=" * 50)
    print("  Build complete!")
    print("=" * 50)
    print(f"\nTo run: open {DIST_DIR / 'PhysioScript.app'}")
    print("Note: Ollama must be running separately on your machine.")


if __name__ == "__main__":
    main()
