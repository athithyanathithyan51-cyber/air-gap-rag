export default function Help() {
  return (
    <div className="h-full overflow-y-auto p-4">
      <article className="mx-auto max-w-3xl space-y-4 rounded-lg bg-white p-6 text-sm leading-relaxed shadow-sm">
        <h2 className="text-lg font-semibold">How answers work</h2>
        <ul className="ml-5 list-disc space-y-1">
          <li>The assistant runs entirely on this machine: a local language model, a local search index, no internet.</li>
          <li>It answers only from the documents an admin has added, and cites the document, page or section for each claim.</li>
          <li>
            If no passage is relevant enough, or the draft answer is not supported by its cited passages, you get &ldquo;I
            don&apos;t know&rdquo; instead of a guess.
          </li>
          <li>Document text is treated as data, never as instructions to the assistant.</li>
        </ul>

        <h2 className="text-lg font-semibold">Isolation records (&ldquo;Verify this answer&rdquo;)</h2>
        <p>
          Every answer, including &ldquo;I don&apos;t know&rdquo;, is written to a signed, hash-chained record together with a
          snapshot of the machine&apos;s network interfaces and default routes. This is a{" "}
          <strong>tamper-evident record of network-interface state at the moment of each answer</strong>.
        </p>
        <h3 className="font-semibold">Limits: please read</h3>
        <ul className="ml-5 list-disc space-y-1">
          <li>
            It is <strong>not proof that no packet was ever sent</strong>. Packet captures taken during operation are the
            separate evidence for &ldquo;no network traffic&rdquo;.
          </li>
          <li>
            It is <strong>tamper-evident, not tamper-proof</strong>: someone with administrator access to this machine and the
            signing key could create a new, consistent-looking chain.
          </li>
          <li>A snapshot shows the interface state at one moment; an interface could go up and down between checks.</li>
          <li>Changing the system clock changes timestamps. The monotonic counter and hash links still preserve order.</li>
          <li>On Windows or macOS with Docker Desktop, the record describes Docker&apos;s virtual machine, not the physical computer.</li>
        </ul>
        <p>
          If the monitor detects a network interface coming up, every later answer is marked <em>NOT ISOLATED</em> until an
          admin acknowledges the event after the machine is isolated again.
        </p>
      </article>
    </div>
  );
}
