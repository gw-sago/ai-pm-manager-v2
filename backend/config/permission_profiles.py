"""
AI PM Framework - Permission Profiles Configuration

Manages permission profiles for Worker task execution:
- Load profile definitions from JSON file
- Provide profile-based tool access control
- Support fallback to hardcoded defaults
"""

import json
import logging
from pathlib import Path
from typing import Optional

# Set up logging
logger = logging.getLogger(__name__)

# Default profile definitions (fallback when JSON file is missing)
DEFAULT_PROFILES = {
    "profiles": {
        "research": {
            "description": "調査・分析タスク用",
            "allowed_tools": [
                "Read",
                "Grep",
                "Glob",
                "WebSearch",
                "WebFetch",
                "TodoWrite",
                "Task",
            ],
        },
        "development": {
            "description": "実装・開発タスク用",
            "allowed_tools": [
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
                "Bash",
                "TodoWrite",
                "Task",
                "NotebookEdit",
            ],
        },
        "document": {
            "description": "ドキュメント作成タスク用",
            "allowed_tools": [
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
                "TodoWrite",
            ],
        },
        "full": {
            "description": "フルアクセス（全ツール許可）",
            "allowed_tools": [
                "Read",
                "Write",
                "Edit",
                "Glob",
                "Grep",
                "Bash",
                "WebSearch",
                "WebFetch",
                "TodoWrite",
                "Task",
                "NotebookEdit",
            ],
        },
    },
    "default_profile": "development",
    "version": "1.0.0",
}


def _get_profiles_file_path() -> Path:
    """
    Get the path to permission_profiles.json

    Returns:
        Path object to the JSON file
    """
    # This file is in backend/config/
    config_dir = Path(__file__).parent
    return config_dir / "permission_profiles.json"


def load_profiles() -> dict:
    """
    Load permission profiles from JSON file

    Returns:
        Dictionary containing profiles configuration
        Falls back to DEFAULT_PROFILES if file doesn't exist or is invalid
    """
    profiles_file = _get_profiles_file_path()

    if not profiles_file.exists():
        logger.warning(
            f"Permission profiles file not found: {profiles_file}. Using defaults."
        )
        return DEFAULT_PROFILES

    try:
        with open(profiles_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Basic validation
        if not isinstance(data, dict) or "profiles" not in data:
            logger.error(
                f"Invalid profiles file format: {profiles_file}. Using defaults."
            )
            return DEFAULT_PROFILES

        logger.info(
            f"Loaded {len(data.get('profiles', {}))} permission profiles from {profiles_file}"
        )
        return data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse profiles JSON: {e}. Using defaults.")
        return DEFAULT_PROFILES
    except Exception as e:
        logger.error(f"Error loading profiles file: {e}. Using defaults.")
        return DEFAULT_PROFILES


def get_profile(name: str) -> Optional[dict]:
    """
    Get a specific permission profile by name

    Args:
        name: Profile name (e.g., "research", "development")

    Returns:
        Profile dictionary if found, None otherwise
    """
    profiles_data = load_profiles()
    profiles = profiles_data.get("profiles", {})
    return profiles.get(name)


def get_profile_tools(name: str) -> list[str]:
    """
    Get the list of allowed tools for a profile

    Args:
        name: Profile name

    Returns:
        List of allowed tool names, empty list if profile not found
    """
    profile = get_profile(name)
    if profile is None:
        logger.warning(f"Profile '{name}' not found. Returning empty tool list.")
        return []

    return profile.get("allowed_tools", [])


def get_default_profile() -> str:
    """
    Get the default profile name

    Returns:
        Default profile name (e.g., "development")
    """
    profiles_data = load_profiles()
    return profiles_data.get("default_profile", "development")


def list_profiles() -> list[str]:
    """
    List all available profile names

    Returns:
        List of profile names
    """
    profiles_data = load_profiles()
    profiles = profiles_data.get("profiles", {})
    return list(profiles.keys())


def validate_profile(profile: dict) -> bool:
    """
    Validate a profile definition structure

    Args:
        profile: Profile dictionary to validate

    Returns:
        True if valid, False otherwise
    """
    if not isinstance(profile, dict):
        logger.error("Profile must be a dictionary")
        return False

    # Check required fields
    if "allowed_tools" not in profile:
        logger.error("Profile missing 'allowed_tools' field")
        return False

    # Validate allowed_tools is a list
    allowed_tools = profile.get("allowed_tools")
    if not isinstance(allowed_tools, list):
        logger.error("'allowed_tools' must be a list")
        return False

    # Validate all tools are strings
    if not all(isinstance(tool, str) for tool in allowed_tools):
        logger.error("All tools in 'allowed_tools' must be strings")
        return False

    # Optional: description should be string if present
    if "description" in profile and not isinstance(profile["description"], str):
        logger.error("'description' must be a string")
        return False

    return True


def get_profile_description(name: str) -> Optional[str]:
    """
    Get the description of a profile

    Args:
        name: Profile name

    Returns:
        Profile description if found, None otherwise
    """
    profile = get_profile(name)
    if profile is None:
        return None

    return profile.get("description")


def validate_all_profiles() -> bool:
    """
    Validate all profiles in the configuration

    Returns:
        True if all profiles are valid, False otherwise
    """
    profiles_data = load_profiles()
    profiles = profiles_data.get("profiles", {})

    all_valid = True
    for name, profile in profiles.items():
        if not validate_profile(profile):
            logger.error(f"Invalid profile: {name}")
            all_valid = False

    return all_valid
