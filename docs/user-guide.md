# User guide

1. **Sign in.** Open `http://127.0.0.1:8000/` and sign in with the account your admin gave you.
2. **Ask a question.** On the **Chat** tab, type a question about the organisation's documents and press **Ask**. The answer streams in as it is generated.
3. **Check the sources.** Each answer ends with citations such as `[S1] Lab-Manual.pdf · p. 12 · Experiment 3`.
   - Click a citation to read the exact passage the answer came from.
   - From the passage view, you can download the original document.
4. **"Not in the documents" answers.** The assistant tells you it could not find what you asked (naming your question, and the closest related document if there is one) when:
   - no relevant passage was found,
   - the model found no answer in the passages, or
   - the draft answer was not supported by its cited passages.

   Below the reply you will see which of these applied. This is deliberate: the assistant does not guess.
5. **Verify an answer.** Click **Verify this answer** to see:
   - whether the signed record chain is intact up to this answer,
   - whether the machine was network-isolated when the answer was produced, and
   - the recorded interface snapshot.
6. **Know the limits.** Read **Help & limits**. In short:
   - The record shows interface state at the moment of the answer. It is not proof that no packet was ever sent.
   - Someone with full control of the machine and the signing key could forge records.

**Tips**
- Ask specific questions ("What is the minimum attendance for the semester exam?"). These retrieve better than vague ones.
- The assistant only knows what is in the uploaded documents. It has no internet and no general web knowledge.
