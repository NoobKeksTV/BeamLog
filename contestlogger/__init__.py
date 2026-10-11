"""BeamLog – lokaler, webbasierter Contest-Logger für UKW-Contests."""

__version__ = "1.0.3"
__copyright__ = "© 2026 Lars Hölker"
__app_name__ = "BeamLog"
__license__ = "GNU AGPLv3"
__source_url__ = "https://github.com/NoobKeksTV/BeamLog"


def env(key: str, default: str = "") -> str:
    """Einstellung aus der Umgebung: BEAMLOG_<KEY>, ersatzweise der alte Name CONTESTLOGGER_<KEY> (bis 0.9)."""
    import os
    return os.environ.get(f"BEAMLOG_{key}") or os.environ.get(f"CONTESTLOGGER_{key}") or default
