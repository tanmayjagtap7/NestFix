import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getEmployers } from "../api";
import StaffDesk from "../components/StaffDesk";

export default function Admin() {
  const [employers, setEmployers] = useState([]);
  const [selected, setSelected] = useState(null);
  const [error, setError] = useState("");

  function load(preferId) {
    return getEmployers().then((rows) => {
      setEmployers(rows);
      const next = rows.find((item) => item.id === preferId) || rows[0];
      setSelected(next ? next.id : null);
    });
  }

  useEffect(() => {
    load().catch((err) => setError(err.message));
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs uppercase tracking-[0.18em] text-clay">Admin</p>
        <h1 className="font-display text-4xl">Companies and people</h1>
        <p className="mt-2 max-w-xl text-sm text-ink/70">
          Add a company with its people and what it will pay, then open anyone’s homes.
        </p>
      </div>

      {error && <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-900">{error}</p>}

      <section className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="space-y-3">
          <Link to="/admin/new" className="block rounded-3xl bg-ink px-4 py-3 text-center text-sm text-paper">
            Add a company
          </Link>
          <div className="rounded-3xl border border-sand bg-white p-2">
            {employers.map((item) => (
              <button
                key={item.id}
                className={`block w-full rounded-2xl px-3 py-3 text-left text-sm ${selected === item.id ? "bg-ink text-paper" : "hover:bg-sand/70"}`}
                onClick={() => setSelected(item.id)}
              >
                <span className="block font-medium">{item.company_name}</span>
                <span className={`block text-xs ${selected === item.id ? "text-paper/70" : "text-ink/50"}`}>{item.contact_email}</span>
              </button>
            ))}
          </div>
        </div>
        <div>{selected ? <StaffDesk employerId={selected} /> : <p className="text-sm text-ink/60">Add a company to get started.</p>}</div>
      </section>
    </div>
  );
}
