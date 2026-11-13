# Trazabilidad escenario → caso → test (Sprint 6)

Los casos `CP-xxx-nn` son del backend, `CP-xxx-Mnn` de la app móvil y `CP-xxx-Pnn` del panel.

## US-051

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| E1 | CP-051-01 | backend | `urbancheck/users/tests/api/test_onboarding.py` | `TestNewCitizen.test_a_new_citizen_has_no_mark` |
| E1 | CP-051-02 | backend | `urbancheck/users/tests/api/test_onboarding.py` | `TestNewCitizen.test_a_citizen_who_signs_up_gets_a_null_mark_in_the_response` |
| E1 | CP-051-03 | backend | `urbancheck/users/tests/api/test_onboarding.py` | `TestNewCitizen.test_the_mark_travels_in_the_login_payload_even_when_null` |
| E1 | CP-051-04 | backend | `urbancheck/users/tests/api/test_onboarding.py` | `TestNewCitizen.test_the_mark_travels_in_the_profile` |
| — | CP-051-05 | backend | `urbancheck/users/tests/api/test_onboarding.py` | `TestNewCitizen.test_the_mark_cannot_be_written_through_the_profile` |
| E1 | CP-051-M14 | móvil | `src/onboarding/__tests__/onboardingGuard.test.tsx` | `un vecino nuevo ve el tutorial antes que el feed` |
| E1 | CP-051-M01 | móvil | `src/onboarding/__tests__/OnboardingTour.test.tsx` | `tiene los cuatro pasos de la historia, en orden` |
| E2 | CP-051-M02 | móvil | `src/onboarding/__tests__/OnboardingTour.test.tsx` | `avanza y retrocede con los botones e indica el paso` |
| E2 | CP-051-M03 | móvil | `src/onboarding/__tests__/OnboardingTour.test.tsx` | `deslizar también cambia de paso` |
| E3 | CP-051-M04 | móvil | `src/onboarding/__tests__/OnboardingTour.test.tsx` | `en el último paso Empezar reemplaza a Omitir y cierra` |
| E3, E4 | CP-051-06 | backend | `urbancheck/users/tests/api/test_onboarding.py` | `TestMarkingAsSeen.test_finishing_or_skipping_marks_the_account` |
| E3, E4 | CP-051-M08 | móvil | `src/onboarding/__tests__/mark.test.ts` | `devuelve el perfil que confirma el servidor` |
| E4 | CP-051-M05 | móvil | `src/onboarding/__tests__/OnboardingTour.test.tsx` | `Omitir desde cualquier paso sale igual que terminar` |
| E5, E10 | CP-051-07 | backend | `urbancheck/users/tests/api/test_onboarding.py` | `TestMarkingAsSeen.test_a_second_call_does_not_overwrite_the_original_date` |
| E5, E9 | CP-051-M15 | móvil | `src/onboarding/__tests__/onboardingGuard.test.tsx` | `con la marca puesta entra directo a la app` |
| E6 | — | móvil | manual | Cerrar la app a mitad del recorrido: no se marcó nada, vuelve desde el paso 1 |
| E7 | CP-051-M06 | móvil | `src/onboarding/__tests__/OnboardingTour.test.tsx` | `al volver a verlo no hay Omitir, se cierra` |
| E7 | CP-051-M10 | móvil | `src/reports/__tests__/ProfileScreen.test.tsx` | `el vecino puede volver a ver el tutorial` |
| — | CP-051-08 | backend | `urbancheck/users/tests/api/test_onboarding.py` | `TestMarkingAsSeen.test_it_requires_a_session` |
| E8 | CP-051-09 | backend | `urbancheck/users/tests/api/test_onboarding.py` | `TestMarkingAsSeen.test_other_roles_are_rejected` |
| E8 | CP-051-M11 | móvil | `src/reports/__tests__/ProfileScreen.test.tsx` | `una cuenta de trabajo no tiene la opción` |
| E8 | CP-051-M16 | móvil | `src/onboarding/__tests__/onboardingGuard.test.tsx` | `una cuenta %s nunca ve el tutorial` |
| E9 | CP-051-10 | backend | `urbancheck/users/tests/api/test_onboarding.py` | `TestExistingAccountsMigration.test_existing_accounts_are_marked_as_seen` |
| E9 | CP-051-11 | backend | `urbancheck/users/tests/api/test_onboarding.py` | `TestExistingAccountsMigration.test_it_keeps_a_date_that_was_already_there` |
| E10 | CP-051-M09 | móvil | `src/onboarding/__tests__/mark.test.ts` | `con error de red no bloquea y anota el reintento` |
| E10 | CP-051-M12 | móvil | `src/onboarding/__tests__/mark.test.ts` | `en el siguiente ingreso reintenta y limpia la anotación` |
| E10 | CP-051-M13 | móvil | `src/onboarding/__tests__/mark.test.ts` | `si el reintento vuelve a fallar, igual no muestra el tutorial` |

## US-049

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| E1 | CP-049-01 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestInbox.test_it_lists_pending_content_complaints_of_my_municipality` |
| E1 | CP-049-03 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestInbox.test_oldest_first` |
| E1, E2 | CP-049-P02 | panel | `urbanchech_frontend/src/features/moderation/ModerationInboxPage.test.tsx` | `una tarjeta por reporte con todas sus denuncias` |
| E2 | CP-049-02 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestInbox.test_several_complaints_make_one_entry` |
| E2, E3 | CP-049-08 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestDiscard.test_all_complaints_are_resolved_in_one_decision` |
| E3 | CP-049-07 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestDiscard.test_the_report_is_cancelled_and_hidden` |
| E3 | CP-049-09 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestDiscard.test_the_history_records_the_agent_and_the_origin` |
| E3 | CP-049-10 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestDiscard.test_the_author_is_notified_with_the_reason` |
| E3, E5 | CP-049-P03 | panel | `urbanchech_frontend/src/features/moderation/ModerationInboxPage.test.tsx` | `descartar avisa que el motivo es público y lo exige` |
| E4 | CP-049-17 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestDismiss.test_the_report_keeps_its_status_and_visibility` |
| E4 | CP-049-18 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestDismiss.test_the_same_people_cannot_file_it_again` |
| E4 | CP-049-P04 | panel | `urbanchech_frontend/src/features/moderation/ModerationInboxPage.test.tsx` | `desestimar no avisa de publicación y manda el motivo` |
| E5 | CP-049-19 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestReasonIsMandatoryAndPublic.test_without_a_reason_it_is_rejected` |
| E5 | CP-049-20 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestReasonIsMandatoryAndPublic.test_any_citizen_reads_the_reason` |
| E5, E6 | CP-049-23 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestReasonIsMandatoryAndPublic.test_the_author_sees_the_full_detail_and_can_appeal` |
| E5 | CP-049-M01 | móvil | `src/reports/__tests__/ModerationDetail.test.tsx` | `un tercero ve solo el aviso con el motivo` |
| E5, E6 | CP-049-M02 | móvil | `src/reports/__tests__/ModerationDetail.test.tsx` | `el autor ve el motivo y puede apelar` |
| E5 | CP-049-P07 | panel | `urbanchech_frontend/src/features/moderation/components/ReportModerationCard.test.tsx` | `muestra el motivo público del descarte y las denuncias resueltas` |
| E6 | CP-049-24 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAppeal.test_the_author_appeals_and_the_report_stays_cancelled` |
| E6 | CP-049-25 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAppeal.test_it_shows_up_in_the_admin_review` |
| E11 | CP-049-37 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestJurisdictionAndRoles.test_other_roles_cannot_review_appeals` |
| E8 | CP-049-43 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestJurisdictionAndRoles.test_only_the_admin_reverts_ex_officio` |
| E6 | CP-049-M03 | móvil | `src/reports/__tests__/ModerationDetail.test.tsx` | `con la apelación pendiente no se ofrece otra` |
| E6 | CP-049-M05 | móvil | `src/reports/__tests__/ModerationDetail.test.tsx` | `avisa que es una sola y exige el motivo` |
| E6 | CP-049-M06 | móvil | `src/reports/__tests__/ModerationDetail.test.tsx` | `manda el motivo al endpoint de moderación y vuelve` |
| E6 | CP-049-P10 | panel | `urbanchech_frontend/src/features/moderation/ModerationAppealsPage.test.tsx` | `muestra el motivo del municipio junto al del vecino` |
| E7 | CP-049-26 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAppeal.test_only_once` |
| E7 | CP-049-29 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAdminResolution.test_accepting_restores_the_previous_status` |
| E7 | CP-049-30 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAdminResolution.test_rejecting_keeps_it_cancelled_without_a_second_appeal` |
| E7 | CP-049-M04 | móvil | `src/reports/__tests__/ModerationDetail.test.tsx` | `si la rechazaron, lo dice con la respuesta` |
| E7 | CP-049-P11 | panel | `urbanchech_frontend/src/features/moderation/ModerationAppealsPage.test.tsx` | `hacer lugar pide motivo y lo manda` |
| E7 | CP-049-P12 | panel | `urbanchech_frontend/src/features/moderation/ModerationAppealsPage.test.tsx` | `rechazar es destructivo y avisa que no hay segunda apelación` |
| E8 | CP-049-32 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAdminResolution.test_ex_officio_reversal` |
| E8 | CP-049-P08 | panel | `urbanchech_frontend/src/features/moderation/components/ReportModerationCard.test.tsx` | `el admin revierte de oficio, con motivo, al estado previo` |
| E9 | CP-049-05 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestInbox.test_other_municipalities_do_not_show_up` |
| E9 | CP-049-35 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestJurisdictionAndRoles.test_another_municipality_gets_a_404` |
| E10 | CP-049-04 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestInbox.test_personal_data_complaints_never_show_up` |
| E11 | CP-049-36 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestJurisdictionAndRoles.test_other_roles_cannot_moderate` |
| E11 | CP-049-P01 | panel | `urbanchech_frontend/src/routes/loginRedirect.test.tsx` | `la bandeja es del agente y las apelaciones de los dos` |
| E12 | CP-049-38 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestListingFlag.test_the_panel_list_flags_pending_complaints` |
| E12 | CP-049-P09 | panel | `urbanchech_frontend/src/features/moderation/components/ReportModerationCard.test.tsx` | `con denuncias pendientes, el agente va a la bandeja` |
| E12 | CP-049-P13 | panel | `urbanchech_frontend/src/features/reports/components/ReportsTable.test.tsx` | `señala los reportes con denuncias por contenido pendientes` |
| — | CP-049-06 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestInbox.test_the_counter_counts_reports` |
| — | CP-049-11 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestDiscard.test_the_complainants_are_told` |
| — | CP-049-12 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestDiscard.test_the_previous_status_is_kept_for_the_reversal` |
| DoD | CP-049-13 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestDiscard.test_it_all_happens_in_one_transaction` |
| — | CP-049-14 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestDiscard.test_the_second_decision_gets_a_conflict` |
| — | CP-049-15 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestDiscard.test_without_pending_complaints_there_is_nothing_to_discard` |
| — | CP-049-16 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestDiscard.test_it_is_not_offered_as_a_panel_button` |
| DoD | CP-049-21 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestReasonIsMandatoryAndPublic.test_the_complainants_never_come_out` |
| — | CP-049-22 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestReasonIsMandatoryAndPublic.test_comments_and_likes_stay_closed` |
| — | CP-049-27 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAppeal.test_only_the_author` |
| — | CP-049-28 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAppeal.test_it_is_not_part_of_the_closure_thread` |
| — | CP-049-31 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAdminResolution.test_an_appeal_is_resolved_once` |
| — | CP-049-33 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAdminResolution.test_reverting_twice_is_a_conflict` |
| — | CP-049-34 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAdminResolution.test_the_restore_guard_refuses_another_target` |
| — | CP-049-39 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestListingFlag.test_the_panel_detail_lists_complaints_and_their_state` |
| — | CP-049-40 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestValidatorRejectionOrigin.test_a_rejection_is_a_field_decision` |
| — | CP-049-41 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestValidatorRejectionOrigin.test_the_migration_fixes_the_rejections_left_as_manual` |
| — | CP-049-42 | backend | `urbancheck/reports/tests/test_moderation.py` | `test_closure_appeals_still_reach_the_thread` |
| — | CP-049-P05 | panel | `urbanchech_frontend/src/features/moderation/ModerationInboxPage.test.tsx` | `si otra pestaña resolvió antes, lo dice` |
| — | CP-049-P06 | panel | `urbanchech_frontend/src/features/moderation/ModerationInboxPage.test.tsx` | `sin denuncias muestra el estado vacío` |
| E6, E7 (decisión del usuario) | CP-049-44 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAgentReviewsAppealsOfTheirCity.test_the_agent_sees_only_the_appeals_of_their_city` |
| E7 (decisión del usuario) | CP-049-45 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAgentReviewsAppealsOfTheirCity.test_the_agent_accepts_and_the_report_is_restored` |
| E7 (decisión del usuario) | CP-049-46 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAgentReviewsAppealsOfTheirCity.test_the_agent_rejects_and_there_is_no_second_appeal` |
| E9 | CP-049-47 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAgentReviewsAppealsOfTheirCity.test_another_city_gets_a_404` |
| — | CP-049-48 | backend | `urbancheck/reports/tests/test_moderation.py` | `TestAgentReviewsAppealsOfTheirCity.test_the_admin_can_narrow_to_one_municipality` |

## US-023

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| E1 | CP-023-01 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestDistributions.test_by_category_with_count_and_percentage` |
| E1, E2 | CP-023-P02 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `cada barra muestra el valor absoluto y el porcentaje` |
| E2 | CP-023-02 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestDistributions.test_by_status_lists_the_seven_states` |
| E3 | CP-023-06 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestPeriods.test_a_custom_range_counts_only_what_was_created_in_it` |
| E3, E4 | CP-023-P07 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `el selector ofrece los cuatro períodos y aplica uno fijo al elegirlo` |
| E4 | CP-023-05 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestPeriods.test_the_available_windows` |
| E5 | CP-023-04 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestPeriods.test_default_is_the_last_30_days` |
| E5 | CP-023-P01 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `sin elegir nada pide los últimos 30 días y lo dice` |
| E6 | CP-023-08 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestPeriods.test_an_invalid_range_is_rejected_with_the_reason` |
| E6 | CP-023-P04 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `un rango en la URL que es inválido cae al default` |
| E7 | CP-023-09 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestPeriods.test_an_empty_period_has_no_percentages` |
| E7 | CP-023-P05 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `un período sin reportes muestra el vacío y ningún gráfico` |
| E8 | CP-023-10 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestJurisdiction.test_another_municipality_never_counts` |
| E8 | CP-023-11 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestJurisdiction.test_no_parameter_can_widen_it` |
| E9 | CP-023-12 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestJurisdiction.test_the_admin_sees_one_municipality_from_its_page` |
| E9 | CP-023-P06 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `el admin pregunta por la municipalidad de la ficha` |
| E10 | CP-023-14 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestJurisdiction.test_other_roles_get_a_403` |
| E11 | CP-023-P03 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `la URL conserva el período elegido` |
| — | CP-023-03 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestDistributions.test_empty_buckets_come_back_in_zero` |
| — | CP-023-07 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestPeriods.test_the_last_day_counts_until_midnight_local_time` |
| — | CP-023-13 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestJurisdiction.test_the_admin_has_no_global_panel_statistics` |
| DoD | CP-023-15 | backend | `urbancheck/reports/tests/test_statistics.py` | `test_the_aggregation_runs_in_the_database` |
| — | CP-023-16 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestSeedStatistics.test_it_creates_dated_reports_with_valid_chains` |
| — | CP-023-17 | backend | `urbancheck/reports/tests/test_statistics.py` | `TestSeedStatistics.test_it_is_idempotent` |
| — | CP-023-P08 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `rechaza el inicio posterior al fin` |
| — | CP-023-P09 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `rechaza las fechas futuras` |
| — | CP-023-P10 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `pide las dos fechas` |

## US-050

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| E1 | CP-050-01 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestValidationTime.test_average_from_creation_to_reported` |
| E1 | CP-050-03 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestValidationTime.test_only_reports_validated_within_the_period` |
| E1-E4, E11 | CP-050-P01 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `los tres tiempos, en orden, con su muestra` |
| E2 | CP-050-02 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestValidationTime.test_split_by_origin` |
| E3 | CP-050-04 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestAssignmentTime.test_from_reported_to_in_process` |
| E4 | CP-050-05 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestResolutionTime.test_from_in_process_to_the_operator_close` |
| E5 | CP-050-07 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestOpenReports.test_open_reports_do_not_count_in_averages` |
| E5 | CP-050-P03 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `los abiertos se muestran aparte, con el más viejo` |
| E6 | CP-050-08 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestClosuresAndCancellations.test_appealed_closures_over_all_closures` |
| E6 | CP-050-P04 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `los cierres apelados se destacan sobre el umbral` |
| E7 | CP-050-09 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestClosuresAndCancellations.test_cancellations_split_by_origin` |
| E7, E8 | CP-050-P05 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `cancelaciones por origen y archivados por separado` |
| E8 | CP-050-10 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestClosuresAndCancellations.test_archived_by_inactivity_is_its_own_indicator` |
| E9 | CP-050-12 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestEmptyAndShared.test_they_travel_with_the_distributions_and_the_same_period` |
| E9 | CP-050-P06 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `se muestran aunque el período no tenga reportes creados` |
| E10 | CP-050-11 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestEmptyAndShared.test_without_closed_cases_the_averages_are_not_available` |
| E10 | CP-050-P02 | panel | `urbanchech_frontend/src/features/statistics/StatisticsView.test.tsx` | `sin casos dice que no hay, no muestra cero` |
| E12 | CP-050-13 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestJurisdictionAndRoles.test_another_municipality_never_counts` |
| E12 | CP-050-14 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestJurisdictionAndRoles.test_the_admin_sees_the_municipality_of_its_page` |
| E12 | CP-050-15 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestJurisdictionAndRoles.test_other_roles_get_a_403` |
| notas | CP-050-06 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `TestResolutionTime.test_a_reopened_report_takes_first_start_and_last_close` |
| DoD | CP-050-16 | backend | `urbancheck/reports/tests/test_management_indicators.py` | `test_everything_runs_in_the_database` |

## US-030

| Escenario | Caso | Repo | Archivo | Test |
| --- | --- | --- | --- | --- |
| E1 | CP-030-01 | backend | `urbancheck/reports/tests/test_share.py` | `TestTheLink.test_every_report_has_its_own_random_token` |
| E1 | CP-030-02 | backend | `urbancheck/reports/tests/test_share.py` | `TestTheLink.test_the_detail_offers_the_link` |
| E2 | CP-030-05 | backend | `urbancheck/reports/tests/test_share.py` | `TestThePublicPage.test_anyone_without_the_app_sees_the_details` |
| E2 | CP-030-14 | backend | `urbancheck/reports/tests/test_share.py` | `test_the_app_opens_the_link_when_installed` |
| E2 | CP-030-M06 | móvil | `src/reports/__tests__/ShareReport.test.tsx` | `con sesión va directo al detalle` |
| E2 | CP-030-P01 | panel | `urbanchech_frontend/src/features/public-report/PublicReportPage.test.tsx` | `muestra el reporte con sus detalles, buscado por el token` |
| E2 | CP-030-P02 | panel | `urbanchech_frontend/src/features/public-report/PublicReportPage.test.tsx` | `ofrece abrirlo en la app con el mismo token` |
| E2 | CP-030-P05 | panel | `urbanchech_frontend/src/features/public-report/PublicReportPage.test.tsx` | `se abre sin sesión: no pasa por el login` |
| E3 | CP-030-07 | backend | `urbancheck/reports/tests/test_share.py` | `TestThePublicPage.test_an_archived_or_cancelled_report_is_no_longer_available` |
| E3 | CP-030-08 | backend | `urbancheck/reports/tests/test_share.py` | `TestThePublicPage.test_a_deleted_report_is_no_longer_available` |
| E3 | CP-030-M07 | móvil | `src/reports/__tests__/ShareReport.test.tsx` | `si ya no está disponible, lo dice` |
| E3 | CP-030-P03 | panel | `urbanchech_frontend/src/features/public-report/PublicReportPage.test.tsx` | `un reporte archivado o eliminado ya no está disponible` |
| — | CP-030-03 | backend | `urbancheck/reports/tests/test_share.py` | `TestTheLink.test_a_report_nobody_else_sees_offers_no_link` |
| — | CP-030-04 | backend | `urbancheck/reports/tests/test_share.py` | `TestTheLink.test_the_migration_gives_each_existing_report_a_different_token` |
| — | CP-030-06 | backend | `urbancheck/reports/tests/test_share.py` | `TestThePublicPage.test_it_never_exposes_people` |
| — | CP-030-09 | backend | `urbancheck/reports/tests/test_share.py` | `TestThePublicPage.test_a_report_hidden_for_privacy_is_not_available` |
| — | CP-030-10 | backend | `urbancheck/reports/tests/test_share.py` | `TestThePublicPage.test_an_unprocessed_photo_is_not_available` |
| — | CP-030-11 | backend | `urbancheck/reports/tests/test_share.py` | `TestThePublicPage.test_a_discarded_report_shows_the_public_reason` |
| — | CP-030-12 | backend | `urbancheck/reports/tests/test_share.py` | `TestThePublicPage.test_an_unknown_token_is_a_404` |
| — | CP-030-13 | backend | `urbancheck/reports/tests/test_share.py` | `TestThePublicPage.test_the_id_does_not_open_it` |
| — | CP-030-M01 | móvil | `src/reports/__tests__/ShareReport.test.tsx` | `ofrece WhatsApp, Instagram y copiar el enlace` |
| — | CP-030-M02 | móvil | `src/reports/__tests__/ShareReport.test.tsx` | `WhatsApp lleva el mensaje con el enlace` |
| — | CP-030-M03 | móvil | `src/reports/__tests__/ShareReport.test.tsx` | `sin WhatsApp instalado cae en WhatsApp Web` |
| — | CP-030-M04 | móvil | `src/reports/__tests__/ShareReport.test.tsx` | `Instagram abre la hoja del sistema con el enlace` |
| — | CP-030-M05 | móvil | `src/reports/__tests__/ShareReport.test.tsx` | `copiar deja el enlace en el portapapeles y lo confirma` |
| — | CP-030-M09 | móvil | `src/reports/__tests__/ShareReport.test.tsx` | `sin sesión pide iniciarla` |
| — | CP-030-M10 | móvil | `src/reports/__tests__/ModerationDetail.test.tsx` | `aparece solo si el reporte tiene enlace público` |
| — | CP-030-M11 | móvil | `src/reports/__tests__/ModerationDetail.test.tsx` | `un reporte que nadie más ve no ofrece compartir` |
