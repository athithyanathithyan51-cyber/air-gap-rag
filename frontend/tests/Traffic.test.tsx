import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Traffic from "../src/components/Traffic";
import { api, type CaptureDetail } from "../src/api";

const ME = { id: 1, username: "admin", role: "admin" } as const;

const DETAIL: CaptureDetail = {
  name: "20261028T103446Z",
  verdict: "PASS - zero packets on physical network adapters",
  summary: {
    packets: 2,
    bytes: 132,
    first: 1_700_000_000,
    last: 1_700_000_060,
    truncated: false,
    protocols: [{ name: "HTTPS", count: 2 }],
    talkers: [{ address: "10.0.0.5", count: 2 }],
  },
  offset: 0,
  limit: 100,
  packets: [
    { number: 1, time: 1_700_000_000.5, length: 66, src: "10.0.0.5", dst: "93.184.216.34", protocol: "HTTPS", ports: "50000 -> 443", info: "SYN" },
    { number: 2, time: 1_700_000_001, length: 66, src: "93.184.216.34", dst: "10.0.0.5", protocol: "HTTPS", ports: "443 -> 50000", info: "SYN ACK" },
  ],
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Traffic", () => {
  it("shows the verdict, the summary and the packet rows of the newest capture", async () => {
    vi.spyOn(api, "captures").mockResolvedValue([{ name: DETAIL.name, verdict: DETAIL.verdict, has_packets: true, size_bytes: 132 }]);
    vi.spyOn(api, "capture").mockResolvedValue(DETAIL);
    render(<Traffic me={ME} />);

    expect(await screen.findByText(DETAIL.verdict as string)).toBeInTheDocument();
    expect(screen.getAllByText("93.184.216.34")).toHaveLength(2);
    expect(screen.getByText(/50000 -> 443/)).toBeInTheDocument();
    expect(screen.getByText(/SYN ACK/)).toBeInTheDocument();
  });

  it("explains how to record a capture when none exist", async () => {
    vi.spyOn(api, "captures").mockResolvedValue([]);
    render(<Traffic me={ME} />);

    expect(await screen.findByText("No capture yet")).toBeInTheDocument();
    expect(screen.getByText(/capture-windows\.ps1/)).toBeInTheDocument();
  });

  it("shows the error when the capture list cannot be loaded", async () => {
    vi.spyOn(api, "captures").mockRejectedValue(new Error("admin role required"));
    render(<Traffic me={ME} />);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("admin role required"));
  });
});
