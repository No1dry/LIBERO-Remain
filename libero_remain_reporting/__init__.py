"""Pure binary presentation of source-verified LIBERO-Remain score records.

The mapper is a reporting boundary, not an evaluator or an untrusted JSON loader.
Use load_verified_results for disk input; method callers must first invoke their
accepted source/result verifier and pass its original records with provenance.
"""
from .report import REPORT_VERSION, map_verified_results, render_report, write_report


def load_verified_results(*args, **kwargs):
    from .loader import load_verified_results as load
    return load(*args, **kwargs)


__all__ = ["REPORT_VERSION", "map_verified_results", "load_verified_results", "render_report", "write_report"]
