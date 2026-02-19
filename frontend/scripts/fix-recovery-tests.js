#!/usr/bin/env node
/**
 * Script to fix recovery tests by replacing isRecovering/recoveryResult props
 * with Zustand store state setup.
 */

const fs = require('fs');
const path = require('path');

const testFilePath = path.join(
  __dirname,
  '../src/components/__tests__/UnavailabilityBanner.recovery.test.tsx'
);

let content = fs.readFileSync(testFilePath, 'utf8');

// Pattern 1: Replace all instances where recoveryResult prop is passed with completed phase
const recoveryResultPattern = /render\(\s*<UnavailabilityBanner\s+availabilityStatus="([^"]+)"\s+entityType="([^"]+)"\s+entityId="([^"]+)"\s+onRecover=\{mockRecover\}\s+recoveryResult=\{recoveryResult\}\s*\/>\s*\);/gs;

content = content.replace(recoveryResultPattern, (match, status, entityType, entityId) => {
  return `// Set up store with completed session and result
      useRecoveryStore.setState({
        sessions: new Map([
          ["${entityId}", {
            sessionId: "test-session",
            entityId: "${entityId}",
            entityType: "${entityType}",
            entityTitle: "Test ${entityType === 'video' ? 'Video' : 'Channel'}",
            phase: "completed",
            startedAt: Date.now() - 5000,
            completedAt: Date.now(),
            filterOptions: {},
            result: recoveryResult,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="${status}"
          entityType="${entityType}"
          entityId="${entityId}"
          onRecover={mockRecover}
        />
      );`;
});

// Pattern 2: Replace all instances where isRecovering={true} is passed with in-progress phase
const isRecoveringPattern = /render\(\s*<UnavailabilityBanner\s+availabilityStatus="([^"]+)"\s+entityType="([^"]+)"\s+entityId="([^"]+)"\s+onRecover=\{mockRecover\}\s+isRecovering=\{true\}\s*\/>\s*\);/gs;

content = content.replace(isRecoveringPattern, (match, status, entityType, entityId) => {
  return `// Set up store with in-progress session
      useRecoveryStore.setState({
        sessions: new Map([
          ["${entityId}", {
            sessionId: "test-session",
            entityId: "${entityId}",
            entityType: "${entityType}",
            entityTitle: "Test ${entityType === 'video' ? 'Video' : 'Channel'}",
            phase: "in-progress",
            startedAt: Date.now(),
            completedAt: null,
            filterOptions: {},
            result: null,
            error: null,
            abortController: null,
          }],
        ]),
      });

      render(
        <UnavailabilityBanner
          availabilityStatus="${status}"
          entityType="${entityType}"
          entityId="${entityId}"
          onRecover={mockRecover}
        />
      );`;
});

fs.writeFileSync(testFilePath, content, 'utf8');
console.log('✅ Fixed UnavailabilityBanner.recovery.test.tsx');
