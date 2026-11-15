import { useEffect, useState } from "react";
import { askAboutHome, getQuestions, plainTalk } from "../api";

const SUGGESTIONS = ["What would I pay each month?", "How far is the nearest school?", "Is there a grocery store nearby?"];

export default function HomeQuestions({ optionId }) {
  const [rows, setRows] = useState([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getQuestions(optionId).then(setRows).catch(() => setRows([]));
  }, [optionId]);

  async function ask(text) {
    const cleaned = text.trim();
    if (!cleaned || busy) return;
    setBusy(true);
    setError("");
    try {
      const saved = await askAboutHome(optionId, cleaned);
      setRows((current) => [...current, saved]);
      setQuestion("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="px-4 py-4">
      <h3 className="font-display text-2xl">Ask about this home</h3>
      <p className="mt-1 text-xs text-ink/60">Rent and schools already on the home answer right away. A new place, like a store or park, can take about a minute.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {SUGGESTIONS.map((item) => (
          <button
            key={item}
            type="button"
            className="rounded-full border border-sand px-3 py-1 text-xs disabled:opacity-50"
            disabled={busy}
            onClick={() => ask(item)}
          >
            {item}
          </button>
        ))}
      </div>
      <form
        className="mt-3 flex flex-wrap gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          ask(question);
        }}
      >
        <input
          className="min-w-[200px] flex-1 rounded-full border border-sand px-4 py-2 text-sm text-ink"
          placeholder="Ask something else about this home"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <button className="rounded-full bg-ink px-4 py-2 text-sm text-paper disabled:opacity-50" disabled={busy || question.trim().length < 3}>
          {busy ? "Looking it up…" : "Ask"}
        </button>
      </form>
      {error && <p className="mt-3 rounded-2xl bg-red-50 px-3 py-2 text-sm text-red-900">{error}</p>}
      {rows.length > 0 && (
        <ul className="mt-4 space-y-3">
          {rows.map((row) => (
            <li key={row.id} className="rounded-2xl bg-paper px-3 py-3">
              <p className="text-sm font-medium">{row.question}</p>
              <p className="mt-1 text-sm leading-relaxed text-ink/80">{plainTalk(row.answer)}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
