"""flowpipe - LangGraph orchestrator for the flow plugin.

Drives /flow:build -> tests -> /flow:check -> (/flow:qa) -> triage -> /flow:fix
loops with hash-enforced re-verification, then a double human gate around
/flow:ship. Shape and plan are done natively in the TUI beforehand; the
orchestrator starts from the .work/<slug>/ artifacts they produced.
"""
__version__ = "3.2.0"
