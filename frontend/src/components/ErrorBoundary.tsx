import { Component, type ErrorInfo, type ReactNode } from "react";

type State = { error: Error | null };

// Shows the error instead of a blank page if rendering throws.
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("render_failed", error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 p-4 font-sans">
        <div className="w-full max-w-lg rounded-lg border border-red-200 bg-white p-6 shadow-sm">
          <h1 className="text-lg font-bold text-red-800">Something went wrong</h1>
          <p className="mt-2 text-sm text-slate-600">The page hit an error while drawing. Reloading usually fixes it.</p>
          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded bg-slate-100 p-2 text-xs text-slate-700">
            {error.message}
          </pre>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 rounded bg-blue-700 px-4 py-2 font-medium text-white hover:bg-blue-800"
          >
            Reload
          </button>
        </div>
      </main>
    );
  }
}
