import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App, { TITLE } from "../src/App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("shows server status from /health", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok", version: "0.1.0" }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(screen.getByRole("heading", { name: TITLE })).toBeInTheDocument();
    expect(await screen.findByText("ok")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/health", expect.objectContaining({ credentials: "same-origin" }));
  });

  it("reports an unreachable server", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 503 })));
    render(<App />);
    expect(await screen.findByText(/Server unreachable: HTTP 503/)).toBeInTheDocument();
  });
});
