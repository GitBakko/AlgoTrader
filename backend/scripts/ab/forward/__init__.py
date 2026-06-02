"""Forward Demo Lab — leak-immune forward experiments on a dedicated demo account.

See docs/strategy/FORWARD_LAB_SPEC.md. Vertical slice: H2 gap-fade. Strategies
implement ForwardStrategy; ExperimentExecutor places real orders on the
experiment account ONLY; ForwardLedger + ForwardScorer judge them forward.
"""
