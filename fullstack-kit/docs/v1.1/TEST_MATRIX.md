# 测试矩阵

最终命令：`python -B -m unittest discover -s fullstack-kit/tests -v`。Windows、Python 3.14.6，未设置PYTHONUTF8。实际退出0，38项全部通过，无skip。完整日志：evidence/final-suite-release.log。

| 测试 | 类型 | 实测 |
|---|---|---|
| test_cards_v11.CardInputIntegration.test_invalid_inputs_have_located_errors_and_exit_two.test_invalid_inputs_have_located_errors_and_exit_two | 集成 | PASS |
| test_concurrency_v11.EvidenceConcurrencyIntegration.test_concurrent_same_check_serialized_no_partial_receipts.test_concurrent_same_check_serialized_no_partial_receipts | 集成 | PASS |
| test_concurrency_v11.EvidenceConcurrencyIntegration.test_damaged_index_fails_closed.test_damaged_index_fails_closed | 集成 | PASS |
| test_concurrency_v11.EvidenceConcurrencyIntegration.test_interrupted_execution_blocks_old_pass_and_recovers.test_interrupted_execution_blocks_old_pass_and_recovers | 集成 | PASS |
| test_delivery_v11.DeliveryIntegration.test_export_conflict_and_portable_verify.test_export_conflict_and_portable_verify | 端到端（工具fixture） | PASS |
| test_delivery_v11.DeliveryIntegration.test_repeat_verify_is_read_only.test_repeat_verify_is_read_only | 端到端（工具fixture） | PASS |
| test_evidence_v11.EvidenceRegression.test_command_rejection_supersedes_previous_pass.test_command_rejection_supersedes_previous_pass | 集成 | PASS |
| test_evidence_v11.EvidenceRegression.test_corrupt_latest_never_falls_back.test_corrupt_latest_never_falls_back | 集成 | PASS |
| test_evidence_v11.EvidenceRegression.test_legacy_receipt_rejected.test_legacy_receipt_rejected | 集成 | PASS |
| test_evidence_v11.EvidenceRegression.test_pass_fail_pass_latest_only.test_pass_fail_pass_latest_only | 集成 | PASS |
| test_evidence_v11.EvidenceRegression.test_source_change_invalidates.test_source_change_invalidates | 集成 | PASS |
| test_evidence_v11.EvidenceRegression.test_source_changes_during_execution_invalidates.test_source_changes_during_execution_invalidates | 集成 | PASS |
| test_executor_v11.ExecutorIntegration.test_node_absolute_local_script.test_node_absolute_local_script | 集成 | PASS |
| test_executor_v11.ExecutorIntegration.test_real_npm_test_build_and_cmd.test_real_npm_test_build_and_cmd | 集成 | PASS |
| test_executor_v11.ExecutorIntegration.test_timeout_kills_descendant.test_timeout_kills_descendant | 集成 | PASS |
| test_package.PackTests.test_bad_card_rejected.test_bad_card_rejected | 单元 | PASS |
| test_package.PackTests.test_document_placeholder_rejected.test_document_placeholder_rejected | 单元 | PASS |
| test_package.PackTests.test_gate_accepts_real_docs.test_gate_accepts_real_docs | 单元 | PASS |
| test_package.PackTests.test_gate_blocks_missing_docs.test_gate_blocks_missing_docs | 单元 | PASS |
| test_package.PackTests.test_init_idempotent.test_init_idempotent | 单元 | PASS |
| test_package.PackTests.test_pack_structure.test_pack_structure | 单元 | PASS |
| test_package.PackTests.test_prevent_traversal_evidence.test_prevent_traversal_evidence | 单元 | PASS |
| test_package.PackTests.test_qa_allowlist.test_qa_allowlist | 单元 | PASS |
| test_package.PackTests.test_run_records_and_tamper_detects.test_run_records_and_tamper_detects | 集成 | PASS |
| test_package.PackTests.test_source_cards.test_source_cards | 单元 | PASS |
| test_review_v11.IndependentReviewRegression.test_export_inside_source_rejected.test_export_inside_source_rejected | 集成 | PASS |
| test_review_v11.IndependentReviewRegression.test_private_key_output_redacted.test_private_key_output_redacted | 单元 | PASS |
| test_review_v11.IndependentReviewRegression.test_quoted_and_bearer_secret_output_redacted.test_quoted_and_bearer_secret_output_redacted | 单元 | PASS |
| test_review_v11.IndependentReviewRegression.test_required_command_cannot_be_substituted.test_required_command_cannot_be_substituted | 集成 | PASS |
| test_review_v11.IndependentReviewRegression.test_sanitized_json_remains_parseable.test_sanitized_json_remains_parseable | 单元 | PASS |
| test_review_v11.IndependentReviewRegression.test_work_directory_is_source.test_work_directory_is_source | 集成 | PASS |
| test_security_v11.SecurityIntegration.test_known_environment_secret_stdout_stderr_redacted.test_known_environment_secret_stdout_stderr_redacted | 集成 | PASS |
| test_security_v11.SecurityIntegration.test_secret_argument_not_persisted.test_secret_argument_not_persisted | 集成 | PASS |
| test_workflow_v11.WorkflowE2E.test_missing_phases_and_unapproved_transition.test_missing_phases_and_unapproved_transition | 端到端（工具fixture） | PASS |
| test_workflow_v11.WorkflowE2E.test_noninteractive_approval_denied.test_noninteractive_approval_denied | 端到端（工具fixture） | PASS |
| test_workflow_v11.WorkflowE2E.test_real_evidence_approval_and_source_invalidation.test_real_evidence_approval_and_source_invalidation | 端到端（工具fixture） | PASS |
| test_workflow_v11.WorkflowE2E.test_sequential_p0_to_p5_then_production_blocked.test_sequential_p0_to_p5_then_production_blocked | 端到端（工具fixture） | PASS |
| test_workflow_v11.WorkflowE2E.test_synthetic_never_qualifies_for_production.test_synthetic_never_qualifies_for_production | 端到端（工具fixture） | PASS |

## 其他实际检查

原审查harness原样重跑：35命令、28诊断断言、0 findings；旧失败测试仍真实失败，修复后的P4门禁退出2。npm通过、非法卡片退出2、秘密参数被拒绝、兼容验收入口退出0。该harness有固定历史结论文案，其生成报告不作为本版结论，采用JSON与日志实测。

结构检查与只读verify退出0。当前真实工作区workflow状态P0—P7均pending，没有把fixture状态写成真实项目完成。

## 未执行

macOS/Linux实际运行；另一台机器；真实业务/生产部署；所有者在交互终端完成真实批准；新Codex会话Skill自动发现。以上均未标PASS。
