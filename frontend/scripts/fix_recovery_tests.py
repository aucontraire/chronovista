#!/usr/bin/env python3
"""
Script to fix recovery tests by replacing isRecovering/recoveryResult props
with Zustand store state setup.
"""

import re

# Read the file
with open('src/components/__tests__/UnavailabilityBanner.recovery.test.tsx', 'r') as f:
    content = f.read()

# Store setup template for completed sessions with result
store_setup_template = """// Set up store with completed session and result
      useRecoveryStore.setState({{
        sessions: new Map([
          ["{entity_id}", {{
            sessionId: "test-session",
            entityId: "{entity_id}",
            entityType: "{entity_type}",
            entityTitle: "Test {entity_title}",
            phase: "completed",
            startedAt: Date.now() - 5000,
            completedAt: Date.now(),
            filterOptions: {{}},
            result: recoveryResult,
            error: null,
            abortController: null,
          }}],
        ]),
      }});

      render(
        <UnavailabilityBanner
          availabilityStatus="{availability_status}"
          entityType="{entity_type}"
          entityId="{entity_id}"
          onRecover={{mockRecover}}
        />
      );"""

# Pattern to match render with recoveryResult prop
pattern = r'render\(\s*<UnavailabilityBanner\s+availabilityStatus="([^"]+)"\s+entityType="([^"]+)"\s+entityId="([^"]+)"\s+onRecover=\{mockRecover\}\s+recoveryResult=\{recoveryResult\}\s*\/>\s*\);'

def replace_recovery_result(match):
    availability_status = match.group(1)
    entity_type = match.group(2)
    entity_id = match.group(3)
    entity_title = "Video" if entity_type == "video" else "Channel"

    return store_setup_template.format(
        entity_id=entity_id,
        entity_type=entity_type,
        entity_title=entity_title,
        availability_status=availability_status
    )

# Replace all occurrences
content = re.sub(pattern, replace_recovery_result, content, flags=re.MULTILINE)

# Store setup template for in-progress sessions (isRecovering=true)
in_progress_template = """// Set up store with in-progress session
      useRecoveryStore.setState({{
        sessions: new Map([
          ["{entity_id}", {{
            sessionId: "test-session",
            entityId: "{entity_id}",
            entityType: "{entity_type}",
            entityTitle: "Test {entity_title}",
            phase: "in-progress",
            startedAt: Date.now(),
            completedAt: null,
            filterOptions: {{}},
            result: null,
            error: null,
            abortController: null,
          }}],
        ]),
      }});

      render(
        <UnavailabilityBanner
          availabilityStatus="{availability_status}"
          entityType="{entity_type}"
          entityId="{entity_id}"
          onRecover={{mockRecover}}
        />
      );"""

# Pattern to match render with isRecovering=true prop
is_recovering_pattern = r'render\(\s*<UnavailabilityBanner\s+availabilityStatus="([^"]+)"\s+entityType="([^"]+)"\s+entityId="([^"]+)"\s+onRecover=\{mockRecover\}\s+isRecovering=\{true\}\s*\/>\s*\);'

def replace_is_recovering(match):
    availability_status = match.group(1)
    entity_type = match.group(2)
    entity_id = match.group(3)
    entity_title = "Video" if entity_type == "video" else "Channel"

    return in_progress_template.format(
        entity_id=entity_id,
        entity_type=entity_type,
        entity_title=entity_title,
        availability_status=availability_status
    )

# Replace all occurrences
content = re.sub(is_recovering_pattern, replace_is_recovering, content, flags=re.MULTILINE)

# Write back the file
with open('src/components/__tests__/UnavailabilityBanner.recovery.test.tsx', 'w') as f:
    f.write(content)

print("✅ Fixed all recoveryResult and isRecovering props in UnavailabilityBanner.recovery.test.tsx")
