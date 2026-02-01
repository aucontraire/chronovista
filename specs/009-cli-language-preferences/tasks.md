# Tasks: CLI Language Preferences

**Input**: Design documents from `/specs/009-cli-language-preferences/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/cli-commands.md, quickstart.md
**Tests**: Required (>90% coverage per constitution check)
**Updated**: 2026-01-31

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the language_commands.py file structure and register with CLI

- [x] T001 Create language_commands.py skeleton with imports, constants, and Typer app in src/chronovista/cli/language_commands.py
- [x] T002 Add OutputFormat enum (TABLE, JSON, YAML) in src/chronovista/cli/language_commands.py
- [x] T003 Register language_app in main.py with `app.add_typer(language_app, name="languages")` in src/chronovista/cli/main.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Helper functions and utilities that ALL commands depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Implement parse_language_input() for comma-separated parsing with whitespace handling in src/chronovista/cli/language_commands.py
- [x] T005 [P] Implement validate_language_code() for LanguageCode enum validation in src/chronovista/cli/language_commands.py
- [x] T006 [P] Implement detect_system_locale() with fallback to English in src/chronovista/cli/language_commands.py
- [x] T007 [P] Implement suggest_similar_codes() with Levenshtein distance (threshold ≤2, max 3) in src/chronovista/cli/language_commands.py
- [x] T008 [P] Implement get_language_display_name() for human-readable names in src/chronovista/cli/language_commands.py
- [x] T009 Create async helper _get_preferences() for database access pattern in src/chronovista/cli/language_commands.py
- [x] T010 Create test file skeleton with fixtures in tests/unit/cli/test_language_commands.py

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - View Language Preferences (Priority: P1) 🎯 MVP

**Goal**: Users can see their current language preferences grouped by type with priorities

**Independent Test**: Run `chronovista languages list` and verify formatted output displays all preference types correctly

### Tests for User Story 1

- [x] T011 [P] [US1] Test list command with empty preferences shows guidance in tests/unit/cli/test_language_commands.py
- [x] T012 [P] [US1] Test list command with preferences shows grouped table in tests/unit/cli/test_language_commands.py
- [x] T013 [P] [US1] Test list --format json outputs valid JSON structure in tests/unit/cli/test_language_commands.py
- [x] T014 [P] [US1] Test list --format yaml outputs valid YAML structure in tests/unit/cli/test_language_commands.py
- [x] T015 [P] [US1] Test list --type fluent filters to fluent only in tests/unit/cli/test_language_commands.py
- [x] T016 [P] [US1] Test list --available shows all language codes in tests/unit/cli/test_language_commands.py

### Implementation for User Story 1

- [x] T017 [US1] Implement async _list_preferences() helper for fetching preferences in src/chronovista/cli/language_commands.py
- [x] T018 [US1] Implement _format_table_output() with Rich Table grouped by type in src/chronovista/cli/language_commands.py
- [x] T019 [US1] Implement _format_json_output() with grouped structure in src/chronovista/cli/language_commands.py
- [x] T020 [US1] Implement _format_yaml_output() matching JSON structure in src/chronovista/cli/language_commands.py
- [x] T021 [US1] Implement list command with --format and --type options in src/chronovista/cli/language_commands.py
- [x] T022 [US1] Implement list --available subcommand showing all LanguageCode values in src/chronovista/cli/language_commands.py
- [x] T023 [US1] Add empty state handling with guidance message in src/chronovista/cli/language_commands.py

**Checkpoint**: User Story 1 complete - `languages list` is fully functional

---

## Phase 4: User Story 2 & 3 - Interactive Setup with Locale Detection (Priority: P1)

**Goal**: Users can configure languages interactively with locale-detected defaults

**Independent Test**: Run `chronovista languages set` (no flags), verify locale detected, accept defaults, confirm preferences saved

### Tests for User Story 2 & 3

- [x] T024 [P] [US2] Test set interactive mode detects system locale in tests/unit/cli/test_language_commands.py
- [x] T025 [P] [US2] Test set interactive mode accepts defaults with Enter in tests/unit/cli/test_language_commands.py
- [x] T026 [P] [US2] Test set interactive mode allows customization with 'c' in tests/unit/cli/test_language_commands.py
- [x] T027 [P] [US3] Test set --from-locale uses system locale without prompts in tests/unit/cli/test_language_commands.py
- [x] T028 [P] [US2] Test full interactive prompt sequence (fluent → learning → curious → exclude) in tests/unit/cli/test_language_commands.py
- [x] T029 [P] [US2] Test learning language prompts for optional goal in tests/unit/cli/test_language_commands.py
- [x] T030 [P] [US2] Test Ctrl+C exits with code 130 and no partial saves in tests/unit/cli/test_language_commands.py

### Implementation for User Story 2 & 3

- [x] T031 [US3] Implement _show_first_run_defaults() with locale detection and English fallback in src/chronovista/cli/language_commands.py
- [x] T032 [US2] Implement _run_full_interactive_setup() with 4-type prompt sequence in src/chronovista/cli/language_commands.py
- [x] T033 [US2] Implement _prompt_learning_goals() for learning language goal input in src/chronovista/cli/language_commands.py
- [x] T034 [US2] Implement _show_confirmation_summary() with Rich Panel in src/chronovista/cli/language_commands.py
- [x] T035 [US2] Implement async _save_preferences() with atomic transaction in src/chronovista/cli/language_commands.py
- [x] T036 [US2] Implement KeyboardInterrupt handling for Ctrl+C with rollback in src/chronovista/cli/language_commands.py
- [x] T037 [US2] Implement set command entry point dispatching to interactive/non-interactive in src/chronovista/cli/language_commands.py

**Checkpoint**: User Stories 2 & 3 complete - interactive setup is fully functional

---

## Phase 5: User Story 4 - Non-Interactive Configuration (Priority: P2)

**Goal**: Users can configure languages via CLI flags for automation

**Independent Test**: Run `chronovista languages set --fluent en,es --learning it` and verify preferences saved

### Tests for User Story 4

- [x] T038 [P] [US4] Test set --fluent flag saves fluent preferences in tests/unit/cli/test_language_commands.py
- [x] T039 [P] [US4] Test set with multiple flags (--fluent, --learning, --curious, --exclude) in tests/unit/cli/test_language_commands.py
- [x] T040 [P] [US4] Test set --append adds to existing preferences in tests/unit/cli/test_language_commands.py
- [x] T041 [P] [US4] Test set with conflict (same language in multiple types) shows error in tests/unit/cli/test_language_commands.py
- [x] T042 [P] [US4] Test set with invalid language code shows suggestions in tests/unit/cli/test_language_commands.py

### Implementation for User Story 4

- [x] T043 [US4] Implement _validate_no_conflicts() for cross-type duplicate detection in src/chronovista/cli/language_commands.py
- [x] T044 [US4] Implement _process_flag_input() for parsing and validating flag values in src/chronovista/cli/language_commands.py
- [x] T045 [US4] Implement non-interactive mode in set command with all flags in src/chronovista/cli/language_commands.py
- [x] T046 [US4] Implement --append logic to merge with existing preferences in src/chronovista/cli/language_commands.py
- [x] T047 [US4] Add auto_download_transcripts defaults based on preference type in src/chronovista/cli/language_commands.py

**Checkpoint**: User Story 4 complete - non-interactive configuration is fully functional

---

## Phase 6: User Story 5 - Add Single Language (Priority: P2)

**Goal**: Users can add a single language preference incrementally

**Independent Test**: Run `chronovista languages add it --type learning --goal "B2 by December"` and verify in list

### Tests for User Story 5

- [x] T048 [P] [US5] Test add command adds language at end of priority list in tests/unit/cli/test_language_commands.py
- [x] T049 [P] [US5] Test add --priority inserts at specified position and shifts others in tests/unit/cli/test_language_commands.py
- [x] T050 [P] [US5] Test add --goal stores learning goal for learning type in tests/unit/cli/test_language_commands.py
- [x] T051 [P] [US5] Test add existing language shows error with guidance in tests/unit/cli/test_language_commands.py
- [x] T052 [P] [US5] Test add invalid code shows suggestions in tests/unit/cli/test_language_commands.py

### Implementation for User Story 5

- [x] T053 [US5] Implement async _check_language_exists() for duplicate detection in src/chronovista/cli/language_commands.py
- [x] T054 [US5] Implement _calculate_priority() for append vs insert logic in src/chronovista/cli/language_commands.py
- [x] T055 [US5] Implement async _shift_priorities() for priority renumbering in src/chronovista/cli/language_commands.py
- [x] T056 [US5] Implement add command with LANGUAGE, --type, --priority, --goal in src/chronovista/cli/language_commands.py
- [x] T057 [US5] Add success output with priority and auto-download status in src/chronovista/cli/language_commands.py

**Checkpoint**: User Story 5 complete - `languages add` is fully functional

---

## Phase 7: User Story 6 - Remove Language (Priority: P2)

**Goal**: Users can remove a language from their preferences

**Independent Test**: Run `chronovista languages remove it` and confirm removal, then verify with list

### Tests for User Story 6

- [x] T058 [P] [US6] Test remove command with confirmation in tests/unit/cli/test_language_commands.py
- [x] T059 [P] [US6] Test remove --yes skips confirmation in tests/unit/cli/test_language_commands.py
- [x] T060 [P] [US6] Test remove compacts priorities after removal in tests/unit/cli/test_language_commands.py
- [x] T061 [P] [US6] Test remove non-existent language shows message in tests/unit/cli/test_language_commands.py
- [x] T062 [P] [US6] Test remove cancelled by user returns exit code 1 in tests/unit/cli/test_language_commands.py

### Implementation for User Story 6

- [x] T063 [US6] Implement async _compact_priorities() for renumbering after removal in src/chronovista/cli/language_commands.py
- [x] T064 [US6] Implement remove command with LANGUAGE and --yes in src/chronovista/cli/language_commands.py
- [x] T065 [US6] Add confirmation prompt with language display name in src/chronovista/cli/language_commands.py
- [x] T066 [US6] Add not-found handling with friendly message in src/chronovista/cli/language_commands.py

**Checkpoint**: User Story 6 complete - `languages remove` is fully functional

---

## Phase 8: User Story 7 - Reset All Preferences (Priority: P3)

**Goal**: Users can clear all preferences and optionally reconfigure

**Independent Test**: Run `chronovista languages reset --yes` and verify list shows empty state

### Tests for User Story 7

- [x] T067 [P] [US7] Test reset command with confirmation in tests/unit/cli/test_language_commands.py
- [x] T068 [P] [US7] Test reset --yes skips confirmation in tests/unit/cli/test_language_commands.py
- [x] T069 [P] [US7] Test reset offers reconfiguration after clearing in tests/unit/cli/test_language_commands.py
- [x] T070 [P] [US7] Test reset --no-setup skips reconfiguration offer in tests/unit/cli/test_language_commands.py
- [x] T071 [P] [US7] Test reset cancelled by user returns exit code 1 in tests/unit/cli/test_language_commands.py

### Implementation for User Story 7

- [x] T072 [US7] Implement reset command with --yes and --no-setup in src/chronovista/cli/language_commands.py
- [x] T073 [US7] Add confirmation prompt showing count of preferences to delete in src/chronovista/cli/language_commands.py
- [x] T074 [US7] Add optional reconfiguration flow after reset in src/chronovista/cli/language_commands.py

**Checkpoint**: User Story 7 complete - `languages reset` is fully functional

---

## Phase 9: User Story 8 - Upgrade Path for Existing Users (Priority: P2)

**Goal**: Existing users are prompted about language configuration when running sync commands

**Independent Test**: Clear preferences, run `chronovista sync videos`, verify upgrade prompt appears once

### Tests for User Story 8

- [x] T075 [P] [US8] Test upgrade prompt appears when no preferences configured in tests/unit/cli/test_language_commands.py
- [x] T076 [P] [US8] Test upgrade prompt does NOT appear when preferences exist in tests/unit/cli/test_language_commands.py
- [x] T077 [P] [US8] Test upgrade prompt appears only once per session in tests/unit/cli/test_language_commands.py
- [x] T078 [P] [US8] Test accepting upgrade prompt enters first-run setup in tests/unit/cli/test_language_commands.py
- [x] T079 [P] [US8] Test declining upgrade prompt proceeds with defaults in tests/unit/cli/test_language_commands.py

### Implementation for User Story 8

- [x] T080 [US8] Create _upgrade_prompt_shown module-level flag for session state in src/chronovista/cli/language_commands.py
- [x] T081 [US8] Implement async check_and_prompt_language_preferences() callable from sync in src/chronovista/cli/language_commands.py
- [x] T082 [US8] Implement _show_upgrade_prompt() with [Y/n] format in src/chronovista/cli/language_commands.py
- [x] T083 [US8] Add upgrade prompt integration to sync commands in src/chronovista/cli/sync_commands.py
- [x] T084 [US8] Ensure prompt never blocks sync operation (always proceeds after prompt) in src/chronovista/cli/sync_commands.py

**Checkpoint**: User Story 8 complete - upgrade path is fully functional

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Final quality improvements and validation

- [x] T085 [P] Add comprehensive docstrings to all public functions in src/chronovista/cli/language_commands.py
- [x] T086 [P] Implement non-TTY detection for plain text output in src/chronovista/cli/language_commands.py
- [x] T087 [P] Add terminal width handling with text truncation in src/chronovista/cli/language_commands.py
- [x] T088 Run full test suite and verify >90% coverage for language_commands.py
- [x] T089 Run quickstart.md verification commands manually
- [x] T090 Run mypy type checking on language_commands.py

---

## Phase 11: User Story 9 - Multi-Language Fluent Download (Priority: P1)

**Goal**: Transcript sync downloads ALL fluent language transcripts automatically while respecting exclude/curious preferences

**Independent Test**: Set fluent preferences for en,es,fr → Run sync → Verify all three language transcripts downloaded

### Tests for User Story 9

- [x] T091 [P] [US9] Test transcript sync downloads ALL fluent language transcripts in tests/unit/services/test_preference_aware_transcript_filter.py
- [x] T092 [P] [US9] Test transcript sync skips excluded languages in tests/unit/services/test_preference_aware_transcript_filter.py
- [x] T093 [P] [US9] Test transcript sync skips curious languages (on-demand only) in tests/unit/services/test_preference_aware_transcript_filter.py
- [x] T094 [P] [US9] Test transcript sync with no preferences uses system defaults in tests/unit/services/test_preference_aware_transcript_filter.py
- [x] T095 [P] [US9] Test transcript sync reports download summary with language breakdown in tests/unit/services/test_preference_aware_transcript_filter.py

### Implementation for User Story 9

- [x] T096 [US9] Create PreferenceAwareTranscriptFilter service in src/chronovista/services/preference_aware_transcript_filter.py
- [x] T097 [US9] Implement filter_transcripts_by_preference() method that applies fluent/exclude/curious rules in src/chronovista/services/preference_aware_transcript_filter.py
- [x] T098 [US9] Implement get_download_languages() method returning list of languages to fetch in src/chronovista/services/preference_aware_transcript_filter.py
- [x] T099 [US9] Integrate PreferenceAwareTranscriptFilter into transcript sync flow in src/chronovista/cli/sync_commands.py
- [x] T100 [US9] Add download summary output showing languages downloaded/skipped to sync command in src/chronovista/cli/sync_commands.py

**Checkpoint**: User Story 9 complete - multi-language fluent downloads working

---

## Phase 12: User Story 10 - Learning Language Download (Priority: P2)

**Goal**: Learning languages download both original transcript AND translation to top fluent language when available

**Independent Test**: Set learning=it, fluent=en → Sync video with Italian transcript → Verify Italian + English translation downloaded

### Tests for User Story 10

- [x] T101 [P] [US10] Test learning language downloads original transcript in tests/unit/services/test_preference_aware_transcript_filter.py
- [x] T102 [P] [US10] Test learning language downloads translation to top fluent when available in tests/unit/services/test_preference_aware_transcript_filter.py
- [x] T103 [P] [US10] Test graceful handling when translation unavailable (INFO log per FR-016) in tests/unit/services/test_preference_aware_transcript_filter.py
- [x] T104 [P] [US10] Test translation target is determined by top fluent language priority in tests/unit/services/test_preference_aware_transcript_filter.py

### Implementation for User Story 10

- [x] T105 [US10] Implement get_top_fluent_language() returning highest priority fluent language in src/chronovista/services/preference_aware_transcript_filter.py
- [x] T106 [US10] Implement get_translation_pair() method returning (original, translation_target) tuple in src/chronovista/services/preference_aware_transcript_filter.py
- [x] T107 [US10] Add INFO logging for missing translations per FR-016 in src/chronovista/services/preference_aware_transcript_filter.py
- [x] T108 [US10] Update sync command output to show translation pairing info in src/chronovista/cli/sync_commands.py

**Checkpoint**: User Story 10 complete - learning language translation pairing working

---

## Phase 13: Integration Testing (Priority: P2)

**Goal**: End-to-end validation of complete download behavior integration

**Independent Test**: Run full workflow from preferences → sync → verify downloads

### E2E Tests for Download Behavior

- [x] T109 [P] E2E test: set preferences → sync → verify correct languages downloaded in tests/integration/test_language_download_integration.py
- [x] T110 [P] E2E test: exclude preference prevents download completely in tests/integration/test_language_download_integration.py
- [x] T111 [P] E2E test: curious preference only downloads on explicit --language flag in tests/integration/test_language_download_integration.py
- [x] T112 [P] E2E test: learning preference pairs with translation when available in tests/integration/test_language_download_integration.py
- [x] T113 [P] E2E test: fallback behavior when no preferences configured (system locale) in tests/integration/test_language_download_integration.py

**Checkpoint**: Phase 13 complete - all download behavior integration validated

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-9)**: All depend on Foundational phase completion
  - US1 (list) → Independent, no story dependencies
  - US2/US3 (interactive set) → Independent, no story dependencies
  - US4 (non-interactive set) → Independent, no story dependencies
  - US5 (add) → Independent, no story dependencies
  - US6 (remove) → Independent, no story dependencies
  - US7 (reset) → Depends on US2 (reuses interactive setup)
  - US8 (upgrade path) → Depends on US2/US3 (reuses first-run flow)
- **Polish (Phase 10)**: Depends on all user stories being complete
- **Download Behavior (Phase 11-12)**: Depends on Phase 2 + US8 (upgrade path integration)
  - US9 (multi-fluent download) → Depends on preferences being configurable (US2-US6)
  - US10 (learning download) → Depends on US9 (builds on filter service)
- **Integration Testing (Phase 13)**: Depends on US9 + US10 completion

### User Story Dependencies

```
Phase 2 (Foundational) ──┬──> US1 (list) - MVP
                         │
                         ├──> US2/US3 (interactive set) ──┬──> US7 (reset)
                         │                                 │
                         │                                 └──> US8 (upgrade path)
                         │
                         ├──> US4 (non-interactive set)
                         │
                         ├──> US5 (add)
                         │
                         ├──> US6 (remove)
                         │
                         └──> US9 (multi-fluent download) ──> US10 (learning download) ──> Phase 13 (E2E)
```

### Parallel Opportunities

**Phase 2 - All [P] tasks can run in parallel:**
```
T005, T006, T007, T008 can all run simultaneously (different helper functions)
```

**Phase 3 (US1) - All tests can run in parallel:**
```
T011, T012, T013, T014, T015, T016 can all run simultaneously
```

**After Foundational - User Stories can run in parallel:**
```
US1, US2/US3, US4, US5, US6 have no inter-dependencies
Only US7 and US8 depend on US2/US3 completion
```

**Phase 11 (US9) - All tests can run in parallel:**
```
T091, T092, T093, T094, T095 can all run simultaneously (different filter scenarios)
```

**Phase 12 (US10) - All tests can run in parallel:**
```
T101, T102, T103, T104 can all run simultaneously (different translation scenarios)
```

**Phase 13 (E2E) - All tests can run in parallel:**
```
T109, T110, T111, T112, T113 can all run simultaneously (independent E2E scenarios)
```

---

## Parallel Execution Examples

### Phase 2 - Foundational Helpers

```bash
# Launch all helper functions together:
Task: "Implement validate_language_code() in src/chronovista/cli/language_commands.py"
Task: "Implement detect_system_locale() in src/chronovista/cli/language_commands.py"
Task: "Implement suggest_similar_codes() in src/chronovista/cli/language_commands.py"
Task: "Implement get_language_display_name() in src/chronovista/cli/language_commands.py"
```

### User Story 1 - Tests

```bash
# Launch all US1 tests together:
Task: "Test list command with empty preferences in tests/unit/cli/test_language_commands.py"
Task: "Test list command with preferences in tests/unit/cli/test_language_commands.py"
Task: "Test list --format json in tests/unit/cli/test_language_commands.py"
Task: "Test list --format yaml in tests/unit/cli/test_language_commands.py"
Task: "Test list --type fluent in tests/unit/cli/test_language_commands.py"
Task: "Test list --available in tests/unit/cli/test_language_commands.py"
```

### User Story 9 - Tests (Multi-Fluent Download)

```bash
# Launch all US9 tests together:
Task: "Test transcript sync downloads ALL fluent languages in tests/unit/services/test_preference_aware_transcript_filter.py"
Task: "Test transcript sync skips excluded languages in tests/unit/services/test_preference_aware_transcript_filter.py"
Task: "Test transcript sync skips curious languages in tests/unit/services/test_preference_aware_transcript_filter.py"
Task: "Test transcript sync with no preferences uses defaults in tests/unit/services/test_preference_aware_transcript_filter.py"
Task: "Test transcript sync reports download summary in tests/unit/services/test_preference_aware_transcript_filter.py"
```

### User Story 10 - Tests (Learning Download)

```bash
# Launch all US10 tests together:
Task: "Test learning language downloads original transcript in tests/unit/services/test_preference_aware_transcript_filter.py"
Task: "Test learning language downloads translation when available in tests/unit/services/test_preference_aware_transcript_filter.py"
Task: "Test graceful handling when translation unavailable in tests/unit/services/test_preference_aware_transcript_filter.py"
Task: "Test translation target is top fluent language in tests/unit/services/test_preference_aware_transcript_filter.py"
```

### Phase 13 - E2E Integration Tests

```bash
# Launch all E2E tests together:
Task: "E2E test: set preferences → sync → verify downloads in tests/integration/test_language_download_integration.py"
Task: "E2E test: exclude preference prevents download in tests/integration/test_language_download_integration.py"
Task: "E2E test: curious preference only downloads on-demand in tests/integration/test_language_download_integration.py"
Task: "E2E test: learning preference pairs with translation in tests/integration/test_language_download_integration.py"
Task: "E2E test: fallback behavior when no preferences in tests/integration/test_language_download_integration.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003)
2. Complete Phase 2: Foundational (T004-T010)
3. Complete Phase 3: User Story 1 - list command (T011-T023)
4. **STOP and VALIDATE**: Test `chronovista languages list` independently
5. Deploy/demo if ready - users can at least VIEW preferences

### Incremental Delivery

1. **Foundation** → Setup + Foundational (T001-T010)
2. **MVP** → US1 (list) → Users can view preferences → Demo
3. **Core Setup** → US2/US3 (interactive set) → Users can configure → Demo
4. **Automation** → US4 (non-interactive set) → Scripting support → Demo
5. **Granular Control** → US5 + US6 (add/remove) → Incremental changes → Demo
6. **Full Feature** → US7 + US8 (reset + upgrade) → Complete CLI feature → Demo
7. **Download Integration** → US9 (multi-fluent) → Preferences affect sync → Demo
8. **Translation Support** → US10 (learning) → Learning language pairs → Demo
9. **Validation** → Phase 13 (E2E) → Full integration validated → Release

### Task Count Summary

| Phase | Tasks | Parallel Opportunities |
|-------|-------|------------------------|
| Phase 1: Setup | 3 | 0 |
| Phase 2: Foundational | 7 | 4 |
| Phase 3: US1 (list) | 13 | 6 tests |
| Phase 4: US2/US3 (interactive) | 14 | 7 tests |
| Phase 5: US4 (flags) | 10 | 5 tests |
| Phase 6: US5 (add) | 10 | 5 tests |
| Phase 7: US6 (remove) | 9 | 5 tests |
| Phase 8: US7 (reset) | 8 | 5 tests |
| Phase 9: US8 (upgrade) | 10 | 5 tests |
| Phase 10: Polish | 6 | 3 |
| Phase 11: US9 (multi-fluent download) | 10 | 5 tests |
| Phase 12: US10 (learning download) | 8 | 4 tests |
| Phase 13: E2E Integration | 5 | 5 tests |
| **TOTAL** | **113** | **59** |

---

## Notes

- [P] tasks = different functions/sections, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Tests are written FIRST per spec requirement (>90% coverage)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- All async database operations use existing Container + db_manager pattern
- Exit codes per contracts/cli-commands.md
