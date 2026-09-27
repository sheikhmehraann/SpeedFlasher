"""Termux platform module for SpeedFlasher."""
from .platform import TermuxPlatform
from .installer import TermuxInstaller

__all__ = ["TermuxPlatform", "TermuxInstaller"]
