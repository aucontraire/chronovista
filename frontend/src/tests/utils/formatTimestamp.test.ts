/**
 * Unit tests for formatTimestamp utility function.
 *
 * Tests the FR-018 requirement: Format timestamps as MM:SS or H:MM:SS based on duration.
 *
 * @module tests/utils/formatTimestamp
 */

import { describe, it, expect } from "vitest";
import { formatTimestamp } from "../../utils/formatTimestamp";

describe("formatTimestamp", () => {
  describe("MM:SS format (times under 1 hour)", () => {
    it("formats 0 seconds as 0:00", () => {
      expect(formatTimestamp(0)).toBe("0:00");
    });

    it("formats seconds without minutes as M:SS", () => {
      expect(formatTimestamp(5)).toBe("0:05");
      expect(formatTimestamp(45)).toBe("0:45");
    });

    it("formats minutes and seconds as MM:SS", () => {
      expect(formatTimestamp(65)).toBe("1:05");
      expect(formatTimestamp(125)).toBe("2:05");
      expect(formatTimestamp(725)).toBe("12:05");
    });

    it("pads seconds to 2 digits", () => {
      expect(formatTimestamp(60)).toBe("1:00");
      expect(formatTimestamp(61)).toBe("1:01");
      expect(formatTimestamp(609)).toBe("10:09");
    });

    it("formats maximum time under 1 hour (59:59)", () => {
      expect(formatTimestamp(3599)).toBe("59:59");
    });

    it("does not pad minutes for times under 1 hour", () => {
      expect(formatTimestamp(180)).toBe("3:00");
      expect(formatTimestamp(540)).toBe("9:00");
    });
  });

  describe("H:MM:SS format (times 1 hour or longer)", () => {
    it("formats exactly 1 hour as 1:00:00", () => {
      expect(formatTimestamp(3600)).toBe("1:00:00");
    });

    it("formats hours with minutes and seconds as H:MM:SS", () => {
      expect(formatTimestamp(3661)).toBe("1:01:01");
      expect(formatTimestamp(3725)).toBe("1:02:05");
      expect(formatTimestamp(4500)).toBe("1:15:00");
    });

    it("pads minutes to 2 digits for times >= 1 hour", () => {
      expect(formatTimestamp(3660)).toBe("1:01:00");
      expect(formatTimestamp(3780)).toBe("1:03:00");
      expect(formatTimestamp(7380)).toBe("2:03:00");
    });

    it("pads seconds to 2 digits for times >= 1 hour", () => {
      expect(formatTimestamp(3601)).toBe("1:00:01");
      expect(formatTimestamp(3609)).toBe("1:00:09");
    });

    it("formats multiple hours", () => {
      expect(formatTimestamp(7200)).toBe("2:00:00");
      expect(formatTimestamp(10800)).toBe("3:00:00");
      expect(formatTimestamp(36000)).toBe("10:00:00");
    });

    it("formats very long durations (>10 hours)", () => {
      expect(formatTimestamp(43199)).toBe("11:59:59");
      expect(formatTimestamp(86399)).toBe("23:59:59");
    });
  });

  describe("edge cases", () => {
    it("handles negative numbers (treats as 0)", () => {
      expect(formatTimestamp(-1)).toBe("0:00");
      expect(formatTimestamp(-100)).toBe("0:00");
    });

    it("truncates decimal values", () => {
      expect(formatTimestamp(65.7)).toBe("1:05");
      expect(formatTimestamp(125.999)).toBe("2:05");
      expect(formatTimestamp(3661.5)).toBe("1:01:01");
    });

    it("handles floating point precision issues", () => {
      expect(formatTimestamp(0.1)).toBe("0:00");
      expect(formatTimestamp(0.9)).toBe("0:00");
      expect(formatTimestamp(59.99)).toBe("0:59");
    });

    it("handles very large numbers", () => {
      expect(formatTimestamp(999999)).toBe("277:46:39");
    });
  });

  describe("common video duration scenarios", () => {
    it("formats typical short video durations", () => {
      expect(formatTimestamp(30)).toBe("0:30");
      expect(formatTimestamp(90)).toBe("1:30");
      expect(formatTimestamp(300)).toBe("5:00");
      expect(formatTimestamp(600)).toBe("10:00");
    });

    it("formats typical medium video durations", () => {
      expect(formatTimestamp(1200)).toBe("20:00");
      expect(formatTimestamp(1800)).toBe("30:00");
      expect(formatTimestamp(2700)).toBe("45:00");
    });

    it("formats typical long video durations", () => {
      expect(formatTimestamp(3600)).toBe("1:00:00");
      expect(formatTimestamp(5400)).toBe("1:30:00");
      expect(formatTimestamp(7200)).toBe("2:00:00");
    });
  });
});
