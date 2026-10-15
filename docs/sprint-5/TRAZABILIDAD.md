# Trazabilidad escenario → caso → test (Sprint 5)

Generada leyendo los identificadores `CP-…` de los tests. Los casos `CP-xxx-nn` son del backend, `CP-xxx-Mnn` de la app móvil y `CP-xxx-Pnn` del panel.


## US-015

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| E1 | CP-015-01 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestTriggeredByTheClose.test_the_close_enqueues_the_comparison_after_the_photo_is_blurred` |
| E1 | CP-015-02 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestTriggeredByTheClose.test_nothing_is_enqueued_if_the_close_is_rolled_back` |
| E1 | CP-015-03 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestTriggeredByTheClose.test_it_compares_with_the_category_and_the_declared_work` |
| E2 | CP-015-04 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVerdicts.test_a_consistent_verdict_is_shown_with_its_explanation` |
| E2 | CP-015-P02 | panel | `urbanchech_frontend/src/features/reports/components/ResolutionComparisonCard.test.tsx` | `pone las dos fotos lado a lado` |
| E3 | CP-015-05 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVerdicts.test_a_doubtful_verdict_flags_the_report_in_the_list` |
| E3 | CP-015-06 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVerdicts.test_the_list_can_be_filtered_by_closures_to_review` |
| E3 | CP-015-07 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVerdicts.test_the_flag_goes_away_once_the_report_is_confirmed` |
| E3 | CP-015-08 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVerdicts.test_a_pending_comparison_does_not_flag_anything` |
| E3 | CP-015-P06 | panel | `urbanchech_frontend/src/features/reports/components/ReportsTable.test.tsx` | `señala el cierre que la comparación automática marcó como dudoso` |
| E3 | CP-015-P07 | panel | `urbanchech_frontend/src/features/reports/components/ReportFilters.test.tsx` | `el botón activa el filtro` |
| E4 | CP-015-09 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestNoEffectOnTheReport.test_no_verdict_changes_the_state_or_the_deadline` |
| E4 | CP-015-10 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestNoEffectOnTheReport.test_the_automatic_confirmation_runs_as_usual` |
| E4 | CP-015-P03 | panel | `urbanchech_frontend/src/features/reports/components/ResolutionComparisonCard.test.tsx` | `se presenta como sugerencia y no como determinación` |
| E5 | CP-015-11 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestServiceFailure.test_retries_are_exhausted_and_it_is_unavailable` |
| E5 | CP-015-12 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestServiceFailure.test_a_transient_failure_can_recover` |
| E5 | CP-015-13 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestServiceFailure.test_a_definitive_failure_is_not_retried` |
| E5 | CP-015-14 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestServiceFailure.test_an_unexpected_error_does_not_leave_it_pending` |
| E5 | CP-015-15 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestServiceFailure.test_a_broker_down_does_not_break_the_close` |
| E5 | CP-015-16 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestServiceFailure.test_without_configuration_the_close_works_the_same` |
| E6 | CP-015-17 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestWithoutImage.test_an_image_deleted_before_running_leaves_no_material` |
| E6 | CP-015-18 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestWithoutImage.test_without_image_at_closing_it_is_not_even_enqueued` |
| E7 | CP-015-19 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestSecondClose.test_both_verdicts_are_kept` |
| E7 | CP-015-P08 | panel | `urbanchech_frontend/src/features/reports/components/ResolutionThread.test.tsx` | `después de una objeción se ven los veredictos de los dos cierres` |
| E8 | CP-015-20 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestRestrictedVisibility.test_the_citizen_surface_does_not_carry_it` |
| E8 | CP-015-21 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestRestrictedVisibility.test_the_operator_does_not_see_it` |
| E9 | CP-015-22 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVerdicts.test_a_consistent_verdict_is_shown_with_its_explanation` |
| E10 | CP-015-23 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestOnlyBlurredImagesLeave.test_what_is_sent_is_what_was_stored` |
| E2 y E9 | CP-015-P01 | panel | `urbanchech_frontend/src/features/reports/components/ResolutionComparisonCard.test.tsx` | `muestra el veredicto consistente con la explicación del modelo` |
| Cliente | CP-015-29 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVisionClient.test_a_valid_answer_is_parsed` |
| Cliente | CP-015-30 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVisionClient.test_the_request_carries_both_images_and_the_work_as_data` |
| Cliente | CP-015-31 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVisionClient.test_an_answer_outside_the_schema_is_rejected` |
| Cliente | CP-015-32 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVisionClient.test_a_body_that_is_not_json_is_rejected` |
| Cliente | CP-015-33 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVisionClient.test_rate_limits_and_server_errors_are_transient` |
| Cliente | CP-015-34 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVisionClient.test_client_errors_are_definitive` |
| Cliente | CP-015-35 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVisionClient.test_network_failures_are_transient` |
| Cliente | CP-015-36 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestVisionClient.test_an_unreadable_image_is_definitive` |
| Proveedor | CP-015-24 | backend | `urbancheck/reports/tests/test_vision_provider.py` | `TestTheNullProvider.test_it_is_the_default` |
| Proveedor | CP-015-25 | backend | `urbancheck/reports/tests/test_vision_provider.py` | `TestTheNullProvider.test_it_never_compares` |
| Proveedor | CP-015-26 | backend | `urbancheck/reports/tests/test_vision_provider.py` | `TestTheNullProvider.test_a_closure_is_registered_as_unavailable_and_nothing_is_sent` |
| Proveedor | CP-015-27 | backend | `urbancheck/reports/tests/test_vision_provider.py` | `TestTheChosenProvider.test_the_openai_compatible_adapter_needs_its_key` |
| Proveedor | CP-015-28 | backend | `urbancheck/reports/tests/test_vision_provider.py` | `TestTheChosenProvider.test_an_unknown_provider_fails_loudly` |
| Reintento | CP-015-37 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestRetryCommand.test_it_compares_what_was_left_unavailable` |
| Reintento | CP-015-38 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestRetryCommand.test_a_transient_failure_is_retried_without_celery` |
| Reintento | CP-015-39 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestRetryCommand.test_a_stale_pending_one_is_picked_up` |
| Reintento | CP-015-40 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestRetryCommand.test_without_key_it_refuses` |
| Reintento | CP-015-41 | backend | `urbancheck/reports/tests/test_comparison.py` | `TestRetryCommand.test_it_does_not_touch_completed_or_missing_material` |

## US-021

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| E1 | CP-021-01 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestFilingAComplaint.test_it_is_registered_for_every_reason` |
| E1 | CP-021-02 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestFilingAComplaint.test_the_comment_is_optional` |
| E1 | CP-021-03 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestFilingAComplaint.test_a_comment_that_is_too_long_is_rejected` |
| E1 | CP-021-04 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestFilingAComplaint.test_a_content_complaint_is_confirmed_as_going_to_the_municipality` |
| E1 | CP-021-05 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestFilingAComplaint.test_a_personal_data_complaint_is_confirmed_with_the_rn12_deadline` |
| E1 | CP-021-06 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestFilingAComplaint.test_a_content_complaint_points_at_the_report_not_at_an_image` |
| E1 | CP-021-07 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestFilingAComplaint.test_work_accounts_use_their_personal_account` |
| E1 | CP-021-08 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestFilingAComplaint.test_the_operator_is_rejected` |
| E1 | CP-021-09 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestFilingAComplaint.test_a_report_that_does_not_exist_answers_404` |
| E1 | CP-021-10 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestNotifications.test_the_reporter_gets_the_receipt_as_a_notice` |
| E1 | CP-021-M04 | app | `urbancheck_mobile/src/reports/__tests__/ComplaintModal.test.tsx` | `con el motivo solo, denuncia sin comentario` |
| E1 | CP-021-M05 | app | `urbancheck_mobile/src/reports/__tests__/ComplaintModal.test.tsx` | `manda el comentario cuando se escribe uno` |
| E2 | CP-021-11 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestReasonCatalog.test_it_offers_the_three_reasons` |
| E2 | CP-021-12 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestReasonCatalog.test_each_reason_carries_its_recipient` |
| E2 | CP-021-13 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestReasonCatalog.test_every_reason_has_a_recipient` |
| E2 | CP-021-14 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestReasonCatalog.test_it_requires_a_session` |
| E2 | CP-021-M01 | app | `urbancheck_mobile/src/reports/__tests__/ComplaintModal.test.tsx` | `ofrece los tres motivos que manda el servidor` |
| E3 | CP-021-15 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestRouting.test_content_complaints_go_to_the_municipal_agent` |
| E3 | CP-021-16 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestRouting.test_personal_data_complaints_go_to_the_platform_admin` |
| E3 | CP-021-17 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestRouting.test_the_municipal_queue_is_the_one_of_the_reports_jurisdiction` |
| E3 | CP-021-18 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestRouting.test_a_personal_data_complaint_enters_the_us043_circuit` |
| E3 | CP-021-M06 | app | `urbancheck_mobile/src/reports/__tests__/ComplaintModal.test.tsx` | `una denuncia de contenido confirma la revisión del municipio` |
| E3 | CP-021-M07 | app | `urbancheck_mobile/src/reports/__tests__/ComplaintModal.test.tsx` | `CP-043-M01 (US-043 E1) · una de dato personal confirma el plazo de 24 ` |
| E4 | CP-021-19 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestReasonIsRequired.test_a_complaint_without_a_reason_is_rejected` |
| E4 | CP-021-20 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestReasonIsRequired.test_a_reason_outside_the_catalog_is_rejected` |
| E4 | CP-021-M02 | app | `urbancheck_mobile/src/reports/__tests__/ComplaintModal.test.tsx` | `sin motivo no manda nada y dice que es obligatorio` |
| E4 | CP-021-M03 | app | `urbancheck_mobile/src/reports/__tests__/ComplaintModal.test.tsx` | `al elegir un motivo se va el aviso de que faltaba` |
| E5 | CP-021-21 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestNoAutomaticHiding.test_it_stays_in_the_feed` |
| E5 | CP-021-22 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestNoAutomaticHiding.test_it_stays_on_the_map` |
| E5 | CP-021-23 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestNoAutomaticHiding.test_it_can_still_be_opened_by_id` |
| E5 | CP-021-24 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestNoAutomaticHiding.test_its_status_does_not_change` |
| E5 | CP-021-25 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestNoAutomaticHiding.test_it_is_not_marked_as_under_review` |
| E5 | CP-021-26 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestNoAutomaticHiding.test_the_visibility_function_ignores_content_complaints` |
| E5 | CP-021-M11 | app | `urbancheck_mobile/src/reports/__tests__/PrivacyReview.test.tsx` | `una denuncia de contenido deja al vecino en el reporte` |
| E6 | CP-021-27 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestDuplicateComplaint.test_the_same_reason_twice_creates_no_new_record` |
| E6 | CP-021-28 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestDuplicateComplaint.test_the_same_user_can_file_a_different_reason` |
| E6 | CP-021-29 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestDuplicateComplaint.test_another_user_can_file_the_same_reason` |
| E6 | CP-021-30 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestDuplicateComplaint.test_the_same_user_can_file_the_same_reason_on_another_report` |
| E6 | CP-021-31 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestDuplicateComplaint.test_a_resolved_content_complaint_still_blocks_a_new_one` |
| E6 | CP-021-32 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestDuplicateComplaint.test_the_database_enforces_it` |
| E6 | CP-021-33 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestNotifications.test_a_duplicate_does_not_notify_again` |
| E6 | CP-021-M08 | app | `urbancheck_mobile/src/reports/__tests__/ComplaintModal.test.tsx` | `si ya lo denunció por ese motivo, lo dice sin registrar otra` |
| E7 | CP-021-34 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestOwnReport.test_the_author_cannot_file_a_complaint_on_their_own_report` |
| E7 | CP-021-M09 | app | `urbancheck_mobile/src/reports/__tests__/PrivacyReview.test.tsx` | `el autor no tiene la acción sobre su propio reporte` |
| E8 | CP-021-35 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestFinalStatus.test_a_cancelled_or_archived_report_cannot_be_reported` |
| E8 | CP-021-36 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestFinalStatus.test_a_report_withdrawn_for_personal_data_cannot_be_reported` |
| E8 | CP-021-37 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestFinalStatus.test_a_published_report_can_be_reported` |
| E9 | CP-021-38 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestAnonymity.test_no_public_serializer_carries_the_complaint` |
| E9 | CP-021-39 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestAnonymity.test_the_author_is_not_told_how_many_complaints_there_are` |
| E9 | CP-021-40 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestAnonymity.test_the_authors_notice_names_nobody` |
| E9 | CP-021-41 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestAnonymity.test_the_notifications_api_does_not_expose_the_reporter` |
| E9 | CP-021-42 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestAnonymity.test_the_receipt_does_not_carry_the_reporter` |
| E9 | CP-021-43 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestNotifications.test_the_author_learns_the_report_was_reported` |
| E9 | CP-021-44 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestNotifications.test_the_author_is_told_once_however_many_complaints_arrive` |
| E9 | CP-021-45 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestNotifications.test_the_author_is_told_again_once_the_previous_ones_were_resolved` |
| E9 | CP-021-46 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestNotifications.test_a_personal_data_complaint_tells_the_author_through_us043` |
| E9 | CP-021-47 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestNotifications.test_a_rejected_complaint_notifies_nobody` |
| E10 | CP-021-48 | backend | `urbancheck/reports/tests/test_complaints.py` | `TestAuthentication.test_an_anonymous_visitor_is_denied` |

## US-026

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| E1 | CP-026-01 | backend | `urbancheck/reports/tests/test_duplicates.py` | `test_same_category_within_the_radius` |
| E1 | CP-026-02 | backend | `urbancheck/reports/tests/test_duplicates.py` | `test_the_default_radius_is_30_meters` |
| E2 | CP-026-03 | backend | `urbancheck/reports/tests/test_duplicates.py` | `test_same_place_another_category` |
| E3 | CP-026-04 | backend | `urbancheck/reports/tests/test_duplicates.py` | `test_same_category_outside_the_radius` |
| E4 | CP-026-05 | backend | `urbancheck/reports/tests/test_duplicates.py` | `test_a_closed_report_does_not_count` |
| E4 | CP-026-06 | backend | `urbancheck/reports/tests/test_duplicates.py` | `test_every_active_status_counts` |
| E4 | CP-026-07 | backend | `urbancheck/reports/tests/test_duplicates.py` | `test_every_status_is_either_active_or_closed` |
| E5 | CP-026-08 | backend | `urbancheck/reports/tests/test_duplicates.py` | `test_the_closest_one_wins` |
| E6 | CP-026-09 | backend | `urbancheck/reports/tests/test_duplicates.py` | `test_the_radius_is_read_from_configuration` |
| E7 | CP-026-10 | backend | `urbancheck/reports/tests/test_duplicates.py` | `test_another_municipality_does_not_count` |
| E8 | CP-026-11 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestNothingIsStored.test_no_report_and_no_file` |
| E8 | CP-026-12 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestNothingIsStored.test_the_photo_never_enters_the_queue` |
| E9 | CP-026-13 | backend | `urbancheck/reports/tests/test_duplicates.py` | `test_the_lookup_uses_the_index` |
| E9 | CP-026-14 | backend | `urbancheck/reports/tests/test_duplicates.py` | `test_the_index_covers_exactly_the_active_statuses` |
| E9 | CP-026-15 | backend | `urbancheck/reports/tests/test_duplicates.py` | `test_the_volume_benchmark_measures_and_leaves_nothing_behind` |

## US-032

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| E1 | CP-032-01 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestBlocked.test_it_carries_the_existing_report` |
| E1 | CP-032-02 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestBlocked.test_the_closest_one_wins` |
| E1 | CP-032-03 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestBlocked.test_an_address_is_geocoded_before_looking` |
| E1 | CP-032-04 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestBlocked.test_every_open_status_blocks` |
| E1 | CP-032-05 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestBlocked.test_the_radius_is_read_from_configuration` |
| E1 | CP-032-M01 | app | `urbancheck_mobile/src/reports/__tests__/ExistingReportModal.test.tsx` | `shows the existing report card` |
| E1 | CP-032-M02 | app | `urbancheck_mobile/src/reports/__tests__/ExistingReportModal.test.tsx` | `never calls it a duplicate` |
| E1 | CP-032-M07 | app | `urbancheck_mobile/src/reports/__tests__/CreateReportScreen.test.tsx` | `shows the existing report instead of an error` |
| E2 | CP-032-06 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestJoining.test_the_like_counts_toward_collective_validation` |
| E2 | CP-032-M03 | app | `urbancheck_mobile/src/reports/__tests__/ExistingReportModal.test.tsx` | `offers to join and joins` |
| E2 | CP-032-M08 | app | `urbancheck_mobile/src/reports/__tests__/CreateReportScreen.test.tsx` | `joins with a like and opens the existing report` |
| E3 | CP-032-M04 | app | `urbancheck_mobile/src/reports/__tests__/ExistingReportModal.test.tsx` | `goes back to the form without joining` |
| E3 | CP-032-M09 | app | `urbancheck_mobile/src/reports/__tests__/CreateReportScreen.test.tsx` | `goes back keeping what was loaded, without liking` |
| E4 | CP-032-07 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestWhoIsAsking.test_someone_who_already_supports_it` |
| E4 | CP-032-M05 | app | `urbancheck_mobile/src/reports/__tests__/ExistingReportModal.test.tsx` | `does not offer to join to someone already supporting it` |
| E5 | CP-032-08 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestWhoIsAsking.test_the_author` |
| E5 | CP-032-M06 | app | `urbancheck_mobile/src/reports/__tests__/ExistingReportModal.test.tsx` | `takes the author to their own report without offering to join` |
| E5 | CP-032-M10 | app | `urbancheck_mobile/src/reports/__tests__/CreateReportScreen.test.tsx` | `takes the author to their report without liking` |
| E6 | CP-032-09 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestNotADuplicate.test_outside_the_radius` |
| E6 | CP-032-10 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestNotADuplicate.test_another_category` |
| E6 | CP-032-11 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestNotADuplicate.test_a_closed_report` |
| E6 | CP-032-12 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestNotADuplicate.test_another_municipality` |
| E6 | CP-032-13 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestNotADuplicate.test_the_created_report_enters_the_queue_as_usual` |
| E6 | CP-032-14 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestNotADuplicate.test_invalid_data_still_gets_every_error` |
| E7 | CP-032-15 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestNothingIsStored.test_no_report_and_no_file` |
| E7 | CP-032-16 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestNothingIsStored.test_the_photo_never_enters_the_queue` |
| E8 | CP-032-17 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestBlocked.test_it_answers_409_with_its_own_code` |
| E9 | CP-032-18 | backend | `urbancheck/reports/tests/test_duplicate_reports.py` | `TestForcedClient.test_a_forcing_flag_is_ignored` |

## US-041

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| E1 | CP-041-01 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestFaces.test_a_single_face_is_blurred` |
| E1 | CP-041-02 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestFaces.test_the_blurred_face_is_no_longer_a_face` |
| E1 | CP-041-03 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestMixedAndClean.test_the_rest_of_the_image_is_left_alone` |
| E2 | CP-041-04 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestPlates.test_a_single_plate_is_blurred` |
| E3 | CP-041-05 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestFaces.test_every_face_is_blurred_not_only_the_largest` |
| E3 | CP-041-06 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestPlates.test_every_plate_is_blurred` |
| E3 | CP-041-07 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestMixedAndClean.test_faces_and_plates_in_the_same_image` |
| E4 | CP-041-08 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestMixedAndClean.test_a_clean_image_comes_back_unaltered` |
| E5 | CP-041-09 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestIrreversibleBlur.test_the_region_loses_all_detail` |
| E5 | CP-041-10 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestIrreversibleBlur.test_it_is_not_block_pixelation` |
| E5 | CP-041-11 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestIrreversibleBlur.test_the_box_is_expanded_with_a_safety_margin` |
| E5 | CP-041-12 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestIrreversibleBlur.test_nothing_outside_the_expanded_box_changes` |
| E6 | CP-041-13 | backend | `urbancheck/anonymization/tests/test_upload.py` | `TestOnlyTheAnonymizedVersionIsStored.test_creating_a_report` |
| E6 | CP-041-14 | backend | `urbancheck/anonymization/tests/test_upload.py` | `TestOnlyTheAnonymizedVersionIsStored.test_replacing_the_photo` |
| E6 | CP-041-15 | backend | `urbancheck/anonymization/tests/test_upload.py` | `TestOnlyTheAnonymizedVersionIsStored.test_the_operator_closing` |
| E6 | CP-041-16 | backend | `urbancheck/anonymization/tests/test_upload.py` | `TestOnlyTheAnonymizedVersionIsStored.test_the_citizen_appealing` |
| E6 | CP-041-17 | backend | `urbancheck/anonymization/tests/test_upload.py` | `TestOnlyTheAnonymizedVersionIsStored.test_a_large_photo_never_touches_a_temporary_file` |
| E6 | CP-041-18 | backend | `urbancheck/anonymization/tests/test_upload.py` | `TestOnlyTheAnonymizedVersionIsStored.test_nothing_is_stored_if_anonymization_fails` |
| E6 | CP-041-19 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestSuccess.test_processing_publishes_it_and_discards_the_original` |
| E6 | CP-041-20 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestLogging.test_the_log_never_names_the_file` |
| E7 | CP-041-21 | backend | `urbancheck/anonymization/tests/test_upload.py` | `TestNoWayToTheOriginal.test_the_api_serves_the_stored_version` |
| E7 | CP-041-22 | backend | `urbancheck/anonymization/tests/test_upload.py` | `TestNoWayToTheOriginal.test_every_photo_the_api_accepts_goes_through_the_queue` |
| E7 | CP-041-23 | backend | `urbancheck/anonymization/tests/test_upload.py` | `TestNoWayToTheOriginal.test_the_admin_cannot_upload_a_photo_or_force_its_state` |
| E7 | CP-041-24 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestTheOriginalIsNotReachable.test_the_pending_photo_has_no_url` |
| E7 | CP-041-25 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestTheOriginalIsNotReachable.test_the_pending_photo_lives_outside_the_served_media_root` |
| E8 | CP-041-26 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestPerformance.test_a_twelve_megapixel_photo_takes_less_than_ten_seconds` |
| E8 | CP-041-27 | backend | `urbancheck/anonymization/tests/test_benchmark.py` | `TestMeasureCommand.test_it_reports_time_cpu_and_memory` |
| E9 | CP-041-28 | backend | `urbancheck/anonymization/tests/test_benchmark.py` | `TestBenchmarkCommand.test_it_reports_rate_false_negatives_and_times` |
| E9 | CP-041-29 | backend | `urbancheck/anonymization/tests/test_benchmark.py` | `TestBenchmarkCommand.test_it_reads_the_unversioned_folder_from_configuration` |
| E9 | CP-041-30 | backend | `urbancheck/anonymization/tests/test_benchmark.py` | `TestBenchmarkCommand.test_without_a_set_it_says_what_is_missing` |
| E9 | CP-041-31 | backend | `urbancheck/anonymization/tests/test_benchmark.py` | `TestBenchmarkCommand.test_the_reference_set_is_not_versioned` |
| E10 | CP-041-32 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestFormat.test_jpeg_keeps_format_resolution_and_name` |
| E10 | CP-041-33 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestFormat.test_png_and_webp_keep_their_format` |
| E10 | CP-041-34 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestFormat.test_transparency_survives` |
| E10 | CP-041-35 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestFormat.test_an_unusual_format_comes_out_as_jpeg` |
| E10 | CP-041-36 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestFormat.test_the_exif_orientation_is_applied` |
| Fallos | CP-041-40 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestFailures.test_a_file_that_is_not_an_image_is_rejected` |
| Fallos | CP-041-41 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestFailures.test_a_detector_failure_is_not_published_silently` |
| Metadatos | CP-041-37 | backend | `urbancheck/anonymization/tests/test_service.py` | `TestFormat.test_exif_metadata_is_dropped` |
| Modelos | CP-041-38 | backend | `urbancheck/anonymization/tests/test_benchmark.py` | `TestModelIntegrity.test_the_shipped_weights_match_their_published_checksums` |
| Modelos | CP-041-39 | backend | `urbancheck/anonymization/tests/test_benchmark.py` | `TestModelIntegrity.test_a_tampered_model_is_refused` |

## US-042

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| E1 | CP-042-01 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestSuccess.test_the_endpoint_answers_before_processing` |
| E1 | CP-042-02 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestSuccess.test_processing_publishes_it_and_discards_the_original` |
| E1 | CP-042-03 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestVisibleOnceProcessed.test_it_shows_up_everywhere_when_the_photo_is_ready` |
| E2 | CP-042-04 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestInvisibleWhileProcessing.test_it_is_not_in_the_feed` |
| E2 | CP-042-05 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestInvisibleWhileProcessing.test_it_is_not_on_the_map` |
| E2 | CP-042-06 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestInvisibleWhileProcessing.test_it_is_not_found_by_search` |
| E2 | CP-042-07 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestInvisibleWhileProcessing.test_it_cannot_be_opened_by_id` |
| E2 | CP-042-08 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestInvisibleWhileProcessing.test_it_does_not_count_on_the_public_profile` |
| E3 | CP-042-09 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestTheAuthorSeesTheirOwn.test_it_is_in_their_own_history` |
| E3 | CP-042-10 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestTheAuthorSeesTheirOwn.test_they_can_open_it` |
| E3 | CP-042-11 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestTheAuthorSeesTheirOwn.test_they_can_still_delete_it` |
| E3 | CP-042-M01 | app | `urbancheck_mobile/src/reports/__tests__/CreateReportScreen.test.tsx` | `says the image is being processed instead of claiming it is published` |
| E3 | CP-042-M03 | app | `urbancheck_mobile/src/reports/__tests__/ProfileScreen.test.tsx` | `distingue el que se está procesando del que ya está publicado` |
| E4 | CP-042-12 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestRetries.test_a_detector_failure_is_retried_with_growing_backoff` |
| E4 | CP-042-13 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestRetries.test_the_maximum_comes_from_configuration` |
| E4 | CP-042-14 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestRetries.test_a_broken_file_is_not_retried_even_once` |
| E5 | CP-042-15 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestDefinitiveFailure.test_it_is_marked_and_dated` |
| E5 | CP-042-16 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestDefinitiveFailure.test_nothing_is_published_and_the_original_is_gone` |
| E5 | CP-042-17 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestDefinitiveFailure.test_the_author_is_told_they_can_upload_it_again` |
| E5 | CP-042-18 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestDefinitiveFailure.test_it_is_logged_with_its_code_and_without_the_filename` |
| E5 | CP-042-19 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestDefinitiveFailure.test_the_author_can_upload_another_photo_and_it_is_queued_again` |
| E5 | CP-042-M04 | app | `urbancheck_mobile/src/reports/__tests__/ProfileScreen.test.tsx` | `dice que el que falló no llegó a publicarse` |
| E6 | CP-042-20 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestThePanelSeesItButCannotPublishIt.test_the_panel_lists_it_with_its_state` |
| E6 | CP-042-21 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestThePanelSeesItButCannotPublishIt.test_the_panel_cannot_manage_it` |
| E6 | CP-042-22 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestThePanelSeesItButCannotPublishIt.test_it_offers_no_action_that_the_server_would_reject` |
| E6 | CP-042-23 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestNoPathPublishesAnUnprocessedPhoto.test_saving_a_photo_without_processing_it_is_rejected` |
| E6 | CP-042-24 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestNoPathPublishesAnUnprocessedPhoto.test_not_even_a_bulk_update_can_publish_it` |
| E6 | CP-042-P01 | panel | `urbanchech_frontend/src/features/reports/ReportDetailPage.test.tsx` | `dice que un reporte sin difuminar todavía no es público (US-042)` |
| E7 | CP-042-25 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestItDoesNotCountForCollectiveValidation.test_a_neighbour_cannot_like_it` |
| E7 | CP-042-26 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestItDoesNotCountForCollectiveValidation.test_not_even_the_author_can_like_it` |
| E7 | CP-042-27 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestItDoesNotCountForCollectiveValidation.test_it_is_not_in_the_validation_inbox` |
| E7 | CP-042-28 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestItDoesNotCountForCollectiveValidation.test_the_validator_cannot_open_it_either` |
| E7 | CP-042-M02 | app | `urbancheck_mobile/src/reports/__tests__/CreateReportScreen.test.tsx` | `does not offer to join a report that is still being processed` |
| E8 | CP-042-29 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestTheOperatorClosing.test_the_evidence_is_registered_without_its_photo` |
| E8 | CP-042-30 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestTheOperatorClosing.test_the_citizen_does_not_see_the_photo_while_it_processes` |
| E8 | CP-042-31 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestTheOperatorClosing.test_a_failed_close_photo_leaves_the_close_standing` |
| E9 | CP-042-32 | backend | `urbancheck/anonymization/tests/test_retroactive.py` | `TestAnonymizeExistingPhotos.test_without_apply_it_only_counts` |
| E9 | CP-042-33 | backend | `urbancheck/anonymization/tests/test_retroactive.py` | `TestAnonymizeExistingPhotos.test_it_replaces_the_published_photo_with_the_anonymized_one` |
| E9 | CP-042-34 | backend | `urbancheck/anonymization/tests/test_retroactive.py` | `TestAnonymizeExistingPhotos.test_running_it_twice_changes_nothing` |
| E9 | CP-042-35 | backend | `urbancheck/anonymization/tests/test_retroactive.py` | `TestAnonymizeExistingPhotos.test_photos_that_already_went_through_the_service_are_left_alone` |
| E9 | CP-042-36 | backend | `urbancheck/anonymization/tests/test_retroactive.py` | `TestAnonymizeExistingPhotos.test_a_photo_that_cannot_be_processed_is_withdrawn` |
| Apelación | CP-042-37 | backend | `urbancheck/anonymization/tests/test_upload.py` | `TestOnlyTheAnonymizedVersionIsStored.test_the_citizen_appealing` |
| Robustez | CP-042-38 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestSuccess.test_running_it_twice_changes_nothing` |
| Robustez | CP-042-39 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestNothingStaysQueuedForever.test_a_stale_photo_is_requeued` |
| Robustez | CP-042-40 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestNothingStaysQueuedForever.test_a_recent_one_is_left_alone` |
| Robustez | CP-042-41 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `TestADeletedReportIsNotAnError.test_the_task_tolerates_a_report_that_no_longer_exists` |
| Robustez | CP-042-42 | backend | `urbancheck/anonymization/tests/test_deferred_publication.py` | `test_the_pipeline_never_leaves_a_photo_pending_forever` |
| Robustez | CP-042-43 | backend | `urbancheck/reports/tests/test_photo_processing_visibility.py` | `TestThePanelSeesItButCannotPublishIt.test_a_failed_report_can_still_be_archived_or_cancelled` |

## US-043

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| E1 | CP-043-01 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_it_registers_the_reason_the_image_and_the_reception_time` |
| E1 | CP-043-02 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_the_confirmation_promises_the_24_hour_review` |
| E1 | CP-043-03 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_the_photo_of_a_resolution_evidence_can_be_reported` |
| E1 | CP-043-04 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_the_report_photo_and_an_evidence_photo_are_different_images` |
| E1 | CP-043-05 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_an_evidence_of_another_report_is_rejected` |
| E1 | CP-043-06 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_an_image_already_removed_cannot_be_reported` |
| E1 | CP-043-07 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_work_accounts_use_their_personal_account` |
| E1 | CP-043-08 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_the_operator_is_rejected` |
| E1 | CP-043-09 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_it_requires_a_session` |
| E1 | CP-043-10 | backend | `urbancheck/reports/tests/test_privacy_appeal_and_admin.py` | `TestTheAppealPhoto.test_anyone_can_ask_to_review_it` |
| E1 | CP-043-11 | backend | `urbancheck/reports/tests/test_privacy_appeal_and_admin.py` | `TestTheAppealPhoto.test_an_appeal_of_another_report_is_rejected` |
| E1 | CP-043-12 | backend | `urbancheck/reports/tests/test_privacy_appeal_and_admin.py` | `TestTheAppealPhoto.test_one_image_per_request` |
| E1 | CP-043-M04 | app | `urbancheck_mobile/src/reports/__tests__/PrivacyReview.test.tsx` | `con el motivo elegido, denuncia y confirma la revisión en el plazo` |
| E1 | CP-043-M07 | app | `urbancheck_mobile/src/reports/__tests__/PrivacyReview.test.tsx` | `la foto de una objeción se denuncia indicando cuál` |
| E1 | CP-043-P07 | panel | `urbanchech_frontend/src/features/privacy/PrivacyRequestsPage.test.tsx` | `la foto de una objeción se nombra como tal (US-043, escenario 1)` |
| E2 | CP-043-13 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestImmediateHiding.test_one_request_hides_it_from_the_feed` |
| E2 | CP-043-14 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestImmediateHiding.test_it_is_hidden_from_the_map` |
| E2 | CP-043-15 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestImmediateHiding.test_it_is_hidden_from_the_authors_public_profile` |
| E2 | CP-043-16 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestImmediateHiding.test_third_parties_cannot_open_it_by_id` |
| E2 | CP-043-17 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestImmediateHiding.test_the_author_still_sees_it_marked_as_under_review` |
| E2 | CP-043-18 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestImmediateHiding.test_an_evidence_photo_request_hides_the_whole_report` |
| E2 | CP-043-19 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestImmediateHiding.test_a_report_without_requests_is_not_under_review` |
| E2 | CP-043-20 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestVisibilityFunction.test_only_a_pending_request_hides` |
| E2 | CP-043-21 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestVisibilityFunction.test_it_keeps_excluding_inactive_reports` |
| E2 | CP-043-22 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestVisibilityFunction.test_the_author_is_the_only_one_who_sees_a_held_report` |
| E2 | CP-043-M02 | app | `urbancheck_mobile/src/reports/__tests__/PrivacyReview.test.tsx` | `una de dato personal lo saca: el reporte acaba de ocultarse` |
| E2 | CP-043-M09 | app | `urbancheck_mobile/src/reports/__tests__/PrivacyReview.test.tsx` | `el autor ve su reporte marcado como en revisión, sin volver a denuncia` |
| E2 | CP-043-M11 | app | `urbancheck_mobile/src/reports/__tests__/PrivacyReview.test.tsx` | `si el reporte se ocultó mientras estaba abierto, deja de mostrarlo` |
| E3 | CP-043-23 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_any_citizen_can_file_it_not_only_the_author` |
| E3 | CP-043-24 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_the_author_can_file_it_too` |
| E3 | CP-043-M03 | app | `urbancheck_mobile/src/reports/__tests__/PrivacyReview.test.tsx` | `el autor puede pedir la revisión de su propia foto` |
| E4 | CP-043-25 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestAdminInbox.test_it_lists_requests_from_every_municipality` |
| E4 | CP-043-26 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestAdminInbox.test_each_row_carries_image_report_reception_and_remaining_time` |
| E4 | CP-043-27 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestAdminInbox.test_they_are_ordered_by_age` |
| E4 | CP-043-28 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestAdminInbox.test_resolved_requests_leave_the_pending_list` |
| E4 | CP-043-29 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestAdminInbox.test_it_can_be_narrowed_to_one_municipality` |
| E4 | CP-043-P06 | panel | `urbanchech_frontend/src/features/privacy/PrivacyRequestsPage.test.tsx` | `lista las pendientes con la imagen, el reporte y su municipio` |
| E4 | CP-043-P13 | panel | `urbanchech_frontend/src/features/privacy/PrivacyRequestsPage.test.tsx` | `sin pendientes lo dice en vez de dibujar una tabla vacía` |
| E5 | CP-043-30 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRemovingTheImage.test_the_file_is_deleted_from_disk` |
| E5 | CP-043-31 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRemovingTheImage.test_the_report_keeps_everything_else` |
| E5 | CP-043-32 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRemovingTheImage.test_the_whole_report_is_withdrawn_for_good` |
| E5 | CP-043-33 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRemovingTheImage.test_the_author_still_sees_it_as_withdrawn_and_cannot_edit_it` |
| E5 | CP-043-34 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRemovingTheImage.test_a_withdrawn_report_does_not_block_reporting_the_problem_again` |
| E5 | CP-043-35 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRemovingTheImage.test_a_withdrawn_report_leaves_the_validator_inbox` |
| E5 | CP-043-36 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRemovingTheImage.test_the_author_is_notified_with_the_reason` |
| E5 | CP-043-37 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRemovingTheImage.test_every_pending_request_on_that_image_is_closed` |
| E5 | CP-043-38 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRemovingTheImage.test_a_resolved_request_cannot_be_decided_again` |
| E5 | CP-043-39 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRemovingTheImage.test_a_photo_replaced_meanwhile_is_kept_and_the_reported_one_deleted` |
| E5 | CP-043-40 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRemovingTheImage.test_a_failed_deletion_leaves_the_request_pending` |
| E5 | CP-043-41 | backend | `urbancheck/reports/tests/test_privacy_appeal_and_admin.py` | `TestTheDjangoAdminInbox.test_removing_from_the_admin_goes_through_the_service` |
| E5 | CP-043-42 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestNotifications.test_a_removal_tells_every_reporter_the_result` |
| E5 | CP-043-43 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestNotifications.test_removing_the_report_photo_tells_the_author_it_was_withdrawn` |
| E5 | CP-043-M10 | app | `urbancheck_mobile/src/reports/__tests__/PrivacyReview.test.tsx` | `una foto retirada se muestra como retirada y no se puede denunciar` |
| E5 | CP-043-P04 | panel | `urbanchech_frontend/src/features/reports/ReportDetailPage.test.tsx` | `una foto retirada gana sobre el difuminado: ya no importa en qué quedó` |
| E5 | CP-043-P05 | panel | `urbanchech_frontend/src/features/reports/ReportDetailPage.test.tsx` | `una foto retirada se muestra como retirada, no como un hueco` |
| E5 | CP-043-P09 | panel | `urbanchech_frontend/src/features/privacy/PrivacyRequestsPage.test.tsx` | `eliminar pide confirmación y avisa que es irreversible` |
| E5 | CP-043-P11 | panel | `urbanchech_frontend/src/features/privacy/PrivacyRequestsPage.test.tsx` | `cancelar la confirmación no resuelve nada` |
| E6 | CP-043-44 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestDismissing.test_the_image_stays_and_the_report_is_visible_again` |
| E6 | CP-043-45 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestDismissing.test_the_decision_is_registered_with_the_admin_and_the_date` |
| E6 | CP-043-46 | backend | `urbancheck/reports/tests/test_privacy_appeal_and_admin.py` | `TestTheDjangoAdminInbox.test_dismissing_from_the_admin_restores_the_report` |
| E6 | CP-043-47 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestNotifications.test_a_dismissal_tells_the_author_it_is_public_again` |
| E6 | CP-043-48 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestNotifications.test_a_dismissal_tells_every_reporter_the_result` |
| E6 | CP-043-M12 | app | `urbancheck_mobile/src/reports/__tests__/PrivacyReview.test.tsx` | `cuando se desestima la denuncia, el cartel del autor se va solo` |
| E6 | CP-043-P10 | panel | `urbanchech_frontend/src/features/privacy/PrivacyRequestsPage.test.tsx` | `desestimar va por su propio endpoint, también con confirmación` |
| E7 | CP-043-49 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestAdminInbox.test_an_overdue_request_is_flagged_and_goes_first` |
| E7 | CP-043-50 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestAdminInbox.test_the_deadline_counts_from_reception_not_from_resolution_activity` |
| E7 | CP-043-51 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestAdminInbox.test_the_deadline_follows_the_configuration` |
| E7 | CP-043-52 | backend | `urbancheck/reports/tests/test_privacy_appeal_and_admin.py` | `TestTheDjangoAdminInbox.test_the_inbox_flags_overdue_requests` |
| E8 | CP-043-53 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestTraceability.test_the_resolved_log_has_every_field` |
| E8 | CP-043-54 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestTraceability.test_a_late_resolution_is_recorded_as_such` |
| E8 | CP-043-55 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRemovingTheImage.test_it_is_registered_with_the_admin_and_the_date` |
| E8 | CP-043-P12 | panel | `urbanchech_frontend/src/features/privacy/PrivacyRequestsPage.test.tsx` | `el registro muestra la decisión, quién y si fue en plazo` |
| E9 | CP-043-56 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_a_second_request_by_the_same_user_is_rejected_without_a_new_record` |
| E9 | CP-043-57 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_another_user_can_add_theirs_on_the_same_image` |
| E9 | CP-043-58 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRequestingReview.test_the_same_user_can_file_again_after_a_decision` |
| E9 | CP-043-M05 | app | `urbancheck_mobile/src/reports/__tests__/PrivacyReview.test.tsx` | `una segunda denuncia sobre la misma imagen dice que ya está en curso` |
| E10 | CP-043-59 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestAdminInbox.test_the_municipal_agent_gets_403_listing` |
| E10 | CP-043-60 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestAdminInbox.test_the_municipal_agent_gets_403_resolving_by_id` |
| E10 | CP-043-61 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestAdminInbox.test_a_citizen_gets_403` |
| E10 | CP-043-62 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestAdminInbox.test_the_municipal_review_queue_never_contains_them` |
| E10 | CP-043-63 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestImmediateHiding.test_the_panel_still_shows_it_flagged` |
| E10 | CP-043-64 | backend | `urbancheck/reports/tests/test_privacy_appeal_and_admin.py` | `TestTheDjangoAdminInbox.test_only_the_platform_admin_can_resolve` |
| E10 | CP-043-65 | backend | `urbancheck/reports/tests/test_privacy_appeal_and_admin.py` | `TestTheDjangoAdminInbox.test_content_complaints_are_not_touched` |
| E10 | CP-043-P03 | panel | `urbanchech_frontend/src/features/reports/ReportDetailPage.test.tsx` | `avisa que el reporte está oculto mientras se revisa la imagen` |
| E11 | CP-043-66 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestRemovingTheImage.test_an_operator_evidence_photo_is_withdrawn_and_the_status_kept` |
| E11 | CP-043-67 | backend | `urbancheck/reports/tests/test_privacy_appeal_and_admin.py` | `TestTheAppealPhoto.test_removing_it_keeps_the_report_and_the_appeal` |
| E11 | CP-043-68 | backend | `urbancheck/reports/tests/test_privacy_appeal_and_admin.py` | `TestTheAppealPhoto.test_the_citizen_payload_says_the_photo_was_withdrawn` |
| E11 | CP-043-69 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestNotifications.test_the_removal_notice_does_not_claim_it_is_public_while_still_hidden` |
| E11 | CP-043-70 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestNotifications.test_removing_an_evidence_photo_says_it_is_public_when_it_is` |
| E11 | CP-043-M06 | app | `urbancheck_mobile/src/reports/__tests__/PrivacyReview.test.tsx` | `la foto de un cierre se denuncia indicando cuál` |
| E11 | CP-043-M08 | app | `urbancheck_mobile/src/reports/__tests__/PrivacyReview.test.tsx` | `la foto retirada de una objeción se muestra como retirada` |
| E11 | CP-043-P01 | panel | `urbanchech_frontend/src/features/reports/components/ResolutionThread.test.tsx` | `una foto de cierre retirada deja el aviso y conserva el parte (US-043)` |
| E11 | CP-043-P02 | panel | `urbanchech_frontend/src/features/reports/components/ResolutionThread.test.tsx` | `una foto de objeción retirada deja el aviso y conserva el motivo (US-0` |
| E4 y E7 | CP-043-P08 | panel | `urbanchech_frontend/src/features/privacy/PrivacyRequestsPage.test.tsx` | `respeta el orden del servidor y señala la que está fuera de plazo` |
| Avisos | CP-043-71 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestNotifications.test_the_author_learns_the_report_was_hidden` |
| Avisos | CP-043-72 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestNotifications.test_the_author_is_told_once_however_many_neighbours_report_it` |
| Avisos | CP-043-73 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestNotifications.test_an_author_reporting_their_own_photo_gets_no_hidden_notice` |
| Avisos | CP-043-74 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestNotifications.test_an_author_who_reported_gets_only_the_author_notice` |
| Avisos | CP-043-75 | backend | `urbancheck/reports/tests/test_privacy_requests.py` | `TestNotifications.test_no_restored_notice_while_another_image_keeps_it_hidden` |

## US-046

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| E7 | CP-046-07 | backend | `urbancheck/anonymization/tests/test_upload.py` | `TestOnlyTheAnonymizedVersionIsStored.test_the_operator_closing` |

## Seguridad SEC01

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| - | CP-SEC01-01 | backend | `urbancheck/common/tests/test_security_log.py` | `TestSharedCache.test_the_cache_is_redis_in_every_deployed_environment` |

## Seguridad SEC02

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| - | CP-SEC02-01 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestFailedLogins.test_the_sixth_failed_attempt_on_an_account_answers_429` |
| - | CP-SEC02-02 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestFailedLogins.test_the_right_password_is_also_held_back_while_locked` |
| - | CP-SEC02-03 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestFailedLogins.test_the_lock_is_per_account` |
| - | CP-SEC02-04 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestFailedLogins.test_the_wrong_credentials_message_stays_generic` |
| - | CP-SEC02-05 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestPasswordReset.test_the_fourth_request_in_an_hour_answers_429` |
| - | CP-SEC02-06 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestEmailConfirmation.test_resending_the_confirmation_is_limited` |
| - | CP-SEC02-07 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestSignup.test_signups_are_limited_per_ip` |

## Seguridad SEC03

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| - | CP-SEC03-01 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestComplaintThrottle.test_the_eleventh_complaint_of_the_day_answers_429` |
| - | CP-SEC03-02 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestComplaintThrottle.test_the_limit_is_per_user` |
| - | CP-SEC03-03 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestPrivacyRequestThrottle.test_the_sixth_request_of_the_day_answers_429_and_hides_nothing` |
| - | CP-SEC03-04 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestPrivacyRequestThrottle.test_the_complaint_endpoint_cannot_dodge_the_limit` |
| - | CP-SEC03-05 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestCommentThrottle.test_the_sixty_first_comment_in_an_hour_answers_429` |
| - | CP-SEC03-06 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestCommentThrottle.test_reading_comments_is_not_limited` |
| - | CP-SEC03-07 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestReportCreationThrottle.test_the_twenty_first_report_in_an_hour_answers_429` |
| - | CP-SEC03-08 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestReportCreationThrottle.test_the_rate_is_read_from_configuration` |

## Seguridad SEC04

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| - | CP-SEC04-01 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestTrustedProxies.test_two_clients_behind_the_proxy_do_not_share_a_counter` |
| - | CP-SEC04-02 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestTrustedProxies.test_the_proxy_counts_from_the_right` |
| - | CP-SEC04-03 | backend | `urbancheck/common/tests/test_rate_limits.py` | `TestTrustedProxies.test_without_proxies_the_header_is_ignored` |

## Seguridad SEC05

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| - | CP-SEC05-M01 | app | `urbancheck_mobile/src/auth/__tests__/RateLimitedAuthScreens.test.tsx` | `login: el bloqueo dice que hay que esperar, no que la contraseña está ` |
| - | CP-SEC05-M02 | app | `urbancheck_mobile/src/auth/__tests__/RateLimitedAuthScreens.test.tsx` | `registro: el tope por IP se explica igual` |
| - | CP-SEC05-M03 | app | `urbancheck_mobile/src/auth/__tests__/RateLimitedAuthScreens.test.tsx` | `recuperación: el tope por cuenta no se confunde con un email inválido` |
| - | CP-SEC05-M04 | app | `urbancheck_mobile/src/auth/__tests__/RateLimitedAuthScreens.test.tsx` | `restablecer la contraseña: el tope se explica` |
| - | CP-SEC05-M05 | app | `urbancheck_mobile/src/auth/__tests__/RateLimitedAuthScreens.test.tsx` | `cambiar la contraseña: el tope se explica en la pantalla` |
| - | CP-SEC05-M06 | app | `urbancheck_mobile/src/api/__tests__/errors.test.ts` | `usa el mensaje en castellano del servidor, con el tiempo de espera` |
| - | CP-SEC05-M07 | app | `urbancheck_mobile/src/api/__tests__/errors.test.ts` | `al bloqueo de allauth, en inglés, le pone un texto propio` |
| - | CP-SEC05-M08 | app | `urbancheck_mobile/src/api/__tests__/errors.test.ts` | `no se confunde con un error de campo` |
| - | CP-SEC05-M09 | app | `urbancheck_mobile/src/api/__tests__/errors.test.ts` | `isRateLimited reconoce solo el 429` |
| - | CP-SEC05-P01 | panel | `urbanchech_frontend/src/api/client.test.ts` | `un 429 de allauth se explica en castellano y sin campos` |
| - | CP-SEC05-P02 | panel | `urbanchech_frontend/src/api/client.test.ts` | `un 429 de la API conserva su detail, que ya trae el tiempo de espera` |
| - | CP-SEC05-P03 | panel | `urbanchech_frontend/src/api/client.test.ts` | `un 429 sin cuerpo JSON también se explica` |
| - | CP-SEC05-P04 | panel | `urbanchech_frontend/src/routes/pages/LoginPage.test.tsx` | `el bloqueo por intentos dice que hay que esperar` |
| - | CP-SEC05-P05 | panel | `urbanchech_frontend/src/routes/pages/LoginPage.test.tsx` | `una contraseña equivocada sigue diciendo lo de siempre, sin más detall` |

## Seguridad SEC09

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| - | CP-SEC09-01 | backend | `urbancheck/anonymization/tests/test_retroactive.py` | `TestProfilePhoto.test_the_api_stores_it_without_metadata` |
| - | CP-SEC09-02 | backend | `urbancheck/anonymization/tests/test_retroactive.py` | `TestProfilePhoto.test_any_other_path_stores_it_without_metadata_too` |
| - | CP-SEC09-03 | backend | `urbancheck/anonymization/tests/test_retroactive.py` | `TestProfilePhoto.test_the_orientation_is_applied_before_dropping_it` |
| - | CP-SEC09-04 | backend | `urbancheck/anonymization/tests/test_retroactive.py` | `TestProfilePhoto.test_it_is_not_blurred` |

## Seguridad SEC10

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| - | CP-SEC10-01 | backend | `urbancheck/anonymization/tests/test_retroactive.py` | `TestStripImageMetadata.test_without_apply_it_only_counts` |
| - | CP-SEC10-02 | backend | `urbancheck/anonymization/tests/test_retroactive.py` | `TestStripImageMetadata.test_it_rewrites_stored_avatars_without_metadata` |
| - | CP-SEC10-03 | backend | `urbancheck/anonymization/tests/test_retroactive.py` | `TestStripImageMetadata.test_an_unreadable_file_is_left_alone` |

## Seguridad SEC14

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| - | CP-SEC14-01 | backend | `urbancheck/common/tests/test_security_log.py` | `TestPasswordHashing.test_a_login_upgrades_the_hash_to_argon2id` |
| - | CP-SEC14-02 | backend | `urbancheck/common/tests/test_security_log.py` | `TestPasswordHashing.test_argon2_comes_first_and_pbkdf2_stays_for_migration` |

## Seguridad SEC16

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| - | CP-SEC16-01 | backend | `urbancheck/common/tests/test_production_settings.py` | `TestProductionSettings.test_debug_is_off_and_hosts_are_bounded` |
| - | CP-SEC16-02 | backend | `urbancheck/common/tests/test_production_settings.py` | `TestProductionSettings.test_https_is_enforced` |
| - | CP-SEC16-03 | backend | `urbancheck/common/tests/test_production_settings.py` | `TestProductionSettings.test_cors_is_closed_by_default` |
| - | CP-SEC16-04 | backend | `urbancheck/common/tests/test_production_settings.py` | `TestProductionSettings.test_the_admin_lives_off_the_default_path` |
| - | CP-SEC16-05 | backend | `urbancheck/common/tests/test_production_settings.py` | `TestProductionSettings.test_the_default_admin_path_is_refused` |
| - | CP-SEC16-06 | backend | `urbancheck/common/tests/test_production_settings.py` | `TestProductionSettings.test_the_security_log_and_the_shared_cache_survive` |

## Seguridad SEC17

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| - | CP-SEC17-01 | backend | `urbancheck/common/tests/test_production_settings.py` | `test_check_deploy_has_no_warnings` |

## Seguridad SEC18

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| - | CP-SEC18-01 | backend | `urbancheck/common/tests/test_security_log.py` | `TestLogins.test_a_successful_login_is_logged_with_user_ip_and_path` |
| - | CP-SEC18-02 | backend | `urbancheck/common/tests/test_security_log.py` | `TestLogins.test_a_failed_login_is_logged_without_the_password` |
| - | CP-SEC18-03 | backend | `urbancheck/common/tests/test_security_log.py` | `TestLogins.test_a_lockout_is_logged` |
| - | CP-SEC18-04 | backend | `urbancheck/common/tests/test_security_log.py` | `TestPasswords.test_a_password_change_is_logged` |
| - | CP-SEC18-05 | backend | `urbancheck/common/tests/test_security_log.py` | `TestWorkAccounts.test_creating_an_agent_from_the_panel_is_logged` |
| - | CP-SEC18-06 | backend | `urbancheck/common/tests/test_security_log.py` | `TestWorkAccounts.test_a_citizen_signup_is_not_a_work_account` |
| - | CP-SEC18-07 | backend | `urbancheck/common/tests/test_security_log.py` | `TestWorkAccounts.test_creating_a_municipality_is_logged` |
| - | CP-SEC18-08 | backend | `urbancheck/common/tests/test_security_log.py` | `TestComplaints.test_a_complaint_is_logged_with_user_and_ip` |
| - | CP-SEC18-09 | backend | `urbancheck/common/tests/test_security_log.py` | `TestComplaints.test_a_privacy_request_is_logged_with_user_and_ip` |
| - | CP-SEC18-10 | backend | `urbancheck/common/tests/test_security_log.py` | `TestRejectedResponses.test_a_401_is_logged` |
| - | CP-SEC18-11 | backend | `urbancheck/common/tests/test_security_log.py` | `TestRejectedResponses.test_a_403_is_logged_with_the_user` |
| - | CP-SEC18-12 | backend | `urbancheck/common/tests/test_security_log.py` | `TestRejectedResponses.test_a_429_is_logged` |
| - | CP-SEC18-13 | backend | `urbancheck/common/tests/test_security_log.py` | `TestFormat.test_a_value_cannot_forge_a_second_line` |
| - | CP-SEC18-14 | backend | `urbancheck/common/tests/test_security_log.py` | `TestPasswords.test_a_password_reset_is_logged` |

## Seguridad SEC19

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| - | CP-SEC19-01 | backend | `urbancheck/common/tests/test_env_example.py` | `test_every_variable_the_code_reads_is_documented` |
| - | CP-SEC19-02 | backend | `urbancheck/common/tests/test_env_example.py` | `test_the_example_carries_no_secret` |

## Función única de visibilidad (6.1)

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| - | CP-VIS-00 | backend | `urbancheck/reports/tests/test_visibility_sweep.py` | `test_a_visible_report_shows_up_everywhere` |
| - | CP-VIS-01 | backend | `urbancheck/reports/tests/test_visibility_sweep.py` | `test_an_invisible_report_shows_up_nowhere` |
| - | CP-VIS-02 | backend | `urbancheck/reports/tests/test_privacy_appeal_and_admin.py` | `TestThePanelDoesNotShowTheImageUnderReview.test_the_report_photo_is_withheld_while_under_review` |
| - | CP-VIS-03 | backend | `urbancheck/reports/tests/test_privacy_appeal_and_admin.py` | `TestThePanelDoesNotShowTheImageUnderReview.test_only_the_reported_image_is_withheld` |
| - | CP-VIS-04 | backend | `urbancheck/reports/tests/test_privacy_appeal_and_admin.py` | `TestThePanelDoesNotShowTheImageUnderReview.test_once_dismissed_the_photo_is_back` |
| - | CP-VIS-05 | backend | `urbancheck/reports/tests/test_visibility_sweep.py` | `test_the_author_still_sees_their_own` |
| - | CP-VIS-06 | backend | `urbancheck/reports/tests/test_visibility_sweep.py` | `test_the_panel_never_serves_an_image_that_is_not_public` |
