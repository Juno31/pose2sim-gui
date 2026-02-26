"""
app/pose2sim_api.py - Single import point for pose2sim.
Imports lazily so the real traceback is always visible when something goes wrong.
"""

import sys
import traceback


def _import_pose2sim():
    """Import pose2sim and return the Pose2Sim class, with a clear error on failure."""
    try:
        from Pose2Sim import Pose2Sim
        return Pose2Sim
    except ImportError:
        # pose2sim itself is missing
        print("\n" + "━" * 52, file=sys.stderr)
        print("  pose2sim is not installed in this environment.", file=sys.stderr)
        print("  Run:  pip install pose2sim", file=sys.stderr)
        print("━" * 52 + "\n", file=sys.stderr)
        traceback.print_exc()
        raise
    except Exception:
        # pose2sim is installed but fails to load (broken dependency etc.)
        # Print the FULL traceback so the real cause is visible
        print("\n" + "━" * 52, file=sys.stderr)
        print("  pose2sim is installed but failed to import.", file=sys.stderr)
        print("  Full traceback below — this is the real error:", file=sys.stderr)
        print("━" * 52 + "\n", file=sys.stderr)
        traceback.print_exc()
        raise


# Lazy singleton — imported once on first use, not at module load time
_Pose2Sim = None


class Pose2Sim:
    """
    Thin proxy around pose2sim.Pose2Sim.
    Import is deferred until the first method call so startup never fails
    due to a pose2sim import error — the error surfaces only when you run a step.
    """

    @staticmethod
    def calibration(**kwargs):
        global _Pose2Sim
        if _Pose2Sim is None:
            _Pose2Sim = _import_pose2sim()
        return _Pose2Sim.calibration(**kwargs)

    @staticmethod
    def poseEstimation(**kwargs):
        global _Pose2Sim
        if _Pose2Sim is None:
            _Pose2Sim = _import_pose2sim()
        return _Pose2Sim.poseEstimation(**kwargs)

    @staticmethod
    def synchronization(**kwargs):
        global _Pose2Sim
        if _Pose2Sim is None:
            _Pose2Sim = _import_pose2sim()
        return _Pose2Sim.synchronization(**kwargs)

    @staticmethod
    def triangulation(**kwargs):
        global _Pose2Sim
        if _Pose2Sim is None:
            _Pose2Sim = _import_pose2sim()
        return _Pose2Sim.triangulation(**kwargs)

    @staticmethod
    def filtering(**kwargs):
        global _Pose2Sim
        if _Pose2Sim is None:
            _Pose2Sim = _import_pose2sim()
        return _Pose2Sim.filtering(**kwargs)

    @staticmethod
    def markerAugmentation(**kwargs):
        global _Pose2Sim
        if _Pose2Sim is None:
            _Pose2Sim = _import_pose2sim()
        return _Pose2Sim.markerAugmentation(**kwargs)
