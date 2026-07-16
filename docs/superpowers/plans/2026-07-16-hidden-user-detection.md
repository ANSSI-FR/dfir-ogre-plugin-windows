# Hidden User Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct `SpecialAccounts\UserList` parsing so the user-profile output distinguishes explicitly hidden, explicitly visible, and unspecified accounts.

**Architecture:** Move collection of `UserList` values into a focused helper that returns an explicit `Dict[str, bool]`. Keep profile parsing and output unchanged except that matching entries emit both `True` and `False`; absent entries remain omitted and therefore serialize as `null`.

**Tech Stack:** Python 3.10+, `dfir-ogre-common` registry/output APIs, standard-library `unittest`, and `unittest.mock`.

## Global Constraints

- DWORD `0` must emit `is_hidden: true`.
- A nonzero DWORD must emit `is_hidden: false`.
- No matching `UserList` value must preserve `is_hidden: null`.
- Registry value names and profile directory names must match case-insensitively.
- Preserve the existing emitted `user_name` format and all unrelated profile fields.
- Do not add or modify a binary registry-hive fixture.
- Do not change dependencies or `uv.lock`.

---

### Task 1: Correct the tri-state registry-value semantics

**Files:**
- Modify: `tests/hive/test_user_profile.py:1-69`
- Modify: `src/dfir_ogre_plugin_windows/registry/user_profile.py:22-89`

**Interfaces:**
- Consumes: `Registry.glob_keys(path)`, registry values exposing `name()` and `data()`, and the existing `RegUserProfile.parse()` output contract.
- Produces: `_get_hidden_users(reg: Registry) -> Dict[str, bool]`, mapping explicit `UserList` entries to their hidden state.

- [ ] **Step 1: Add a parser-level regression harness and failing tri-state test**

Update the test imports:

```python
from unittest.mock import Mock, patch

from dfir_ogre_common import Metadata, OutputConfiguration, Registry, RunConfiguration
```

Add these methods to `UserProfile`:

```python
    def _parse_with_user_list(self, user_list_values):
        plugin_file = os.path.join(CONF_FOLDER, "user_profile.xml")
        input_file = os.path.join(DATA_FOLDER, "hive", "SOFTWARE.dat")
        real_registry = Registry.load(input_file, "\\HKLM\\Software")

        values = []
        for name, data in user_list_values:
            registry_value = Mock()
            registry_value.name.return_value = name
            registry_value.data.return_value = data
            values.append(registry_value)

        user_list_key = Mock()
        user_list_key.values.return_value = values
        user_list_path = (
            "HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon"
            "\\SpecialAccounts\\UserList"
        )

        class RegistryWithUserList:
            def glob_keys(self, path):
                if path == user_list_path:
                    return [user_list_key]
                return real_registry.glob_keys(path)

        base_output_name = "user_profile_hidden_states"
        output_file = os.path.join(
            TEMP_FOLDER, base_output_name + ".user_profile.jsonl"
        )
        if os.path.exists(output_file):
            os.remove(output_file)

        output_config = OutputConfiguration(
            base_output_name,
            TEMP_FOLDER,
            with_timeline=True,
            include_empty=True,
        )
        run_config = RunConfiguration([output_config])

        with patch(
            "dfir_ogre_plugin_windows.registry.user_profile.Registry"
        ) as registry_type:
            registry_type.load.return_value = RegistryWithUserList()
            report = RegUserProfile().parse(
                input_file,
                plugin_file,
                run_config,
                Metadata("test"),
            )

        self.assertIsNone(report.last_error)
        with open(output_file, encoding="utf-8") as output:
            return {
                record["data"]["user_name"]: record["data"]
                for record in (json.loads(line) for line in output)
            }

    def test_user_profile_hidden_state_semantics(self):
        records = self._parse_with_user_list(
            [("admin", 0), ("nobody", 1)]
        )

        self.assertIs(records["admin"]["is_hidden"], True)
        self.assertIs(records["nobody"]["is_hidden"], False)
        self.assertIsNone(records["systemprofile"]["is_hidden"])
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.hive.test_user_profile.UserProfile.test_user_profile_hidden_state_semantics -v
```

Expected: `FAIL`; the `admin` record has `is_hidden == None` instead of `True`, demonstrating that DWORD `0` is not currently recognized as hidden.

- [ ] **Step 3: Implement the minimal tri-state fix**

Add this helper below `logger` in `user_profile.py`:

```python
def _get_hidden_users(reg: Registry) -> Dict[str, bool]:
    hidden_users: Dict[str, bool] = {}
    for reg_key in reg.glob_keys(
        "HKLM\\Software\\Microsoft\\Windows NT\\CurrentVersion\\Winlogon"
        "\\SpecialAccounts\\UserList"
    ):
        for user_visibility in reg_key.values():
            hidden_users[user_visibility.name()] = user_visibility.data() == 0
    return hidden_users
```

Replace the inline `hidden_users` collection in `RegUserProfile.parse()` with:

```python
        hidden_users = _get_hidden_users(reg)
```

Replace the truthiness-only output condition in `parse_key()` with:

```python
                if profile in hidden_users:
                    tuple.add("is_hidden", value(hidden_users[profile]))
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.hive.test_user_profile.UserProfile.test_user_profile_hidden_state_semantics -v
```

Expected: `PASS`; `0`, `1`, and absence serialize as `true`, `false`, and `null` respectively.

- [ ] **Step 5: Run the complete user-profile test module**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest tests.hive.test_user_profile -v
```

Expected: all tests in `tests.hive.test_user_profile` pass.

- [ ] **Step 6: Commit the semantic correction**

```bash
git add src/dfir_ogre_plugin_windows/registry/user_profile.py \
  tests/hive/test_user_profile.py
git commit -m "Fix hidden user registry value semantics"
```

---

### Task 2: Match account names case-insensitively and verify the full suite

**Files:**
- Modify: `tests/hive/test_user_profile.py`
- Modify: `src/dfir_ogre_plugin_windows/registry/user_profile.py`

**Interfaces:**
- Consumes: `_get_hidden_users(reg: Registry) -> Dict[str, bool]` from Task 1 and the existing lowercase `user_name` output.
- Produces: Case-normalized lookup keys without changing the emitted `user_name` value.

- [ ] **Step 1: Add a failing mixed-case username test**

Add this method to `UserProfile`:

```python
    def test_user_profile_matches_user_list_names_case_insensitively(self):
        records = self._parse_with_user_list(
            [("AdMiN", 0), ("NoBoDy", 1)]
        )

        self.assertIs(records["admin"]["is_hidden"], True)
        self.assertIs(records["nobody"]["is_hidden"], False)
```

- [ ] **Step 2: Run the mixed-case test and verify RED**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.hive.test_user_profile.UserProfile.test_user_profile_matches_user_list_names_case_insensitively -v
```

Expected: `FAIL`; the lowercase profile names do not match the mixed-case registry value names.

- [ ] **Step 3: Normalize comparison keys without changing output**

In `_get_hidden_users()`, change the mapping assignment to:

```python
            hidden_users[user_visibility.name().casefold()] = (
                user_visibility.data() == 0
            )
```

In `parse_key()`, use a normalized lookup key while leaving `profile` unchanged:

```python
                profile_lookup = profile.casefold()
                if profile_lookup in hidden_users:
                    tuple.add("is_hidden", value(hidden_users[profile_lookup]))
```

- [ ] **Step 4: Run both hidden-user regression tests and verify GREEN**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest \
  tests.hive.test_user_profile.UserProfile.test_user_profile_hidden_state_semantics \
  tests.hive.test_user_profile.UserProfile.test_user_profile_matches_user_list_names_case_insensitively -v
```

Expected: both tests pass.

- [ ] **Step 5: Run all verification checks**

Run:

```bash
PYTHONPATH=src ../../.venv/bin/python -m unittest discover -q
PYTHONPATH=src ../../.venv/bin/python -m compileall -q src tests
git diff --check
```

Expected: the full suite passes with 147 tests, compilation succeeds, and `git diff --check` emits no output.

- [ ] **Step 6: Review the final diff for scope**

Run:

```bash
git diff -- src/dfir_ogre_plugin_windows/registry/user_profile.py \
  tests/hive/test_user_profile.py
```

Expected: only the helper, tri-state membership output, case-normalized comparison, and regression tests are present; no unrelated parser behavior changes.

- [ ] **Step 7: Commit case-insensitive matching**

```bash
git add src/dfir_ogre_plugin_windows/registry/user_profile.py \
  tests/hive/test_user_profile.py
git commit -m "Match hidden user names case-insensitively"
```
