# v1.2 independent review

This reviewer did not implement R01, R02 or R03. All fixtures are synthetic tooling diagnostics on Windows. Evidence folder: work/independent12-e7d1ad7bacd241b1bf8a8f0984b6aa92.

* R01: the original absolute helper reference in .fullstack/checks was initially exploitable (result.json). After revision, rerun-*/result.json shows stale evidence false and actual changed test exit 1. Temporarily replacing a copied input during execution and restoring it can still fool local hashes. With both required checks executed, check_gate and workflow.requirements each returned UNVERIFIED_EXECUTION_INPUTS (workflow_probe.txt). Treat local receipts as consistency records only. An independent reviewer must verify the actual input closure before signing.
* R02: in an isolated snapshot, all four policy tests passed (matrix/signatures-stable.txt). They exercised actual OpenSSH signing, rejection of missing/wrong evidence, a signed P4 positive, a signed P6 positive, rejection after a rerun, and help-only build denial. Stored signers and verification executable resolve to system paths. Test signers were temporary. No production key was used.
* R03: both parser integration tests passed (matrix/r03.txt); malformed check ID was separately verified exit 2, fixed-parser contained zero files.
* Operational limitation: an execution image shares OS permissions with the parent. Attestation requires an independent trusted verifier; a signature alone cannot measure file reads. Permission to deploy and business acceptance remain unevaluated.

Scoped verdict: no open bypass reproduced of the revised gates. End-to-end release status depends on the complete suite and required artifacts.
