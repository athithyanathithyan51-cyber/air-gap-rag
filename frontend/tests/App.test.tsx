import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../src/App";
import { TITLE } from "../src/constants";

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

function sse(events: unknown[]): Response {
  const text = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  const bytes = new TextEncoder().encode(text);
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      // split mid-frame to exercise the buffering parser
      c.enqueue(bytes.slice(0, 25));
      c.enqueue(bytes.slice(25));
      c.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

const STATUS = {
  state: "ISOLATED",
  break: null,
  last_check: null,
  current_reasons: [],
  policy: { mode: "strict", allow: ["docker0"] },
  blocks: 0,
  key_id: "k",
  limits: [],
};

const CITATION = {
  label: "S1",
  chunk_id: 7,
  document_id: 1,
  filename: "policy.pdf",
  doc_sha256: "d",
  page: 4,
  section: "Attendance",
  score: 0.8,
  chunk_sha256: "c",
};

function mockFetch(route: Handler) {
  const fn = vi.fn((input: RequestInfo | URL, init?: RequestInit) => Promise.resolve(route(String(input), init)));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("shows the login form when not signed in, then signs in", async () => {
    let signedIn = false;
    const fetchMock = mockFetch((url, init) => {
      if (url === "/api/auth/me") return signedIn ? json({ id: 1, username: "alice", role: "user" }) : json({ detail: "not signed in" }, 401);
      if (url === "/api/auth/refresh") return json({ detail: "no refresh token" }, 401);
      if (url === "/api/auth/login") {
        expect(JSON.parse(String(init?.body))).toEqual({ username: "alice", password: "secret-password" });
        signedIn = true;
        return json({ id: 1, username: "alice", role: "user" });
      }
      if (url === "/api/attestation/status") return json(STATUS);
      return json({}, 404);
    });
    render(<App />);
    expect(await screen.findByRole("heading", { name: TITLE })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("● ISOLATED")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Admin" })).not.toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([u]) => String(u).startsWith("/"))).toBe(true);
  });

  it("streams an answer with citations and verifies it", async () => {
    document.cookie = "airgap_csrf=tok123";
    let chatHeaders: Headers | undefined;
    mockFetch((url, init) => {
      if (url === "/api/auth/me") return json({ id: 2, username: "admin", role: "admin" });
      if (url === "/api/attestation/status") return json(STATUS);
      if (url === "/api/chat") {
        chatHeaders = new Headers(init?.headers);
        return sse([
          { type: "sources", sources: [CITATION] },
          { type: "token", text: "Students need 75% " },
          { type: "token", text: "attendance [S1]." },
          {
            type: "final",
            status: "answered",
            reason: "grounded",
            answer: "Students need 75% attendance [S1].",
            citations: [CITATION],
            support: 1,
            best_score: 0.8,
            attestation: { index: 3, block_hash: "h", isolated: true, monitor_state: "ISOLATED" },
          },
        ]);
      }
      if (url === "/api/documents/chunks/7")
        return json({ chunk_id: 7, document_id: 1, filename: "policy.pdf", page: 4, section: "Attendance", text: "Minimum attendance is 75%.", sha256: "c" });
      if (url === "/api/attestation/blocks/3")
        return json({
          block: {
            index: 3,
            ts_utc: "2026-10-11T00:00:00.000Z",
            counter: 3,
            block_hash: "h",
            prev_hash: "p",
            key_id: "k",
            monitor_state: "ISOLATED",
            net: { platform: "linux", interfaces: [{ name: "eth0", up: false, addrs: [], kind: "physical" }], default_route_v4: false, default_route_v6: false },
          },
          chain_valid_up_to_block: true,
          chain_report: { blocks: 4, valid: true, first_broken: null, broken_reason: null, first_not_isolated: null, not_isolated_count: 0, not_isolated_reasons: [], warnings: [], exit_code: 0 },
          isolated: true,
          isolation_reasons: [],
          limits: ["It is not proof that no packet was ever sent."],
        });
      return json({}, 404);
    });
    render(<App />);
    expect(await screen.findByRole("button", { name: "Admin" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Question"), { target: { value: "What attendance is required?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText("Students need 75% attendance [S1].")).toBeInTheDocument();
    expect(chatHeaders?.get("X-CSRF-Token")).toBe("tok123");

    fireEvent.click(screen.getByRole("button", { name: /\[S1\] policy\.pdf · p\. 4 · Attendance/ }));
    const panel = await screen.findByRole("complementary", { name: "Cited passage" });
    expect(await within(panel).findByText("Minimum attendance is 75%.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Verify this answer" }));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("valid")).toBeInTheDocument();
    expect(within(dialog).getByText("ISOLATED")).toBeInTheDocument();
    expect(within(dialog).getByText(/not proof that no packet/)).toBeInTheDocument();
  });

  it("shows a refusal with its reason", async () => {
    mockFetch((url) => {
      if (url === "/api/auth/me") return json({ id: 1, username: "alice", role: "user" });
      if (url === "/api/attestation/status") return json(STATUS);
      if (url === "/api/chat")
        return sse([
          { type: "sources", sources: [] },
          {
            type: "final",
            status: "refused",
            reason: "low_retrieval_score",
            answer: "I don't know. The ingested documents do not contain enough information to answer this.",
            citations: [],
            support: 0,
            best_score: 0.1,
            attestation: { index: 0, block_hash: "h", isolated: true, monitor_state: "ISOLATED" },
          },
        ]);
      return json({}, 404);
    });
    render(<App />);
    fireEvent.change(await screen.findByLabelText("Question"), { target: { value: "Who won the 1998 world cup?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(/^I don't know/)).toBeInTheDocument();
    expect(screen.getByText("No sufficiently relevant passage was found in the documents.")).toBeInTheDocument();
  });
});
