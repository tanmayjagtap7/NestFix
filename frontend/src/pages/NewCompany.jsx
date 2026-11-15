import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createEmployer, money, uploadJson } from "../api";
import { monthlyHelp } from "../components/PriceSplit";

const EMPTY_PERSON = {
  employee_id: "",
  full_name: "",
  email: "",
  annual_salary: "",
  family_size: "1",
  num_children: "0",
  preferred_city: "",
  max_commute_minutes: "30",
  min_bedrooms: "",
  other_notes: "",
  contribution_type: "monthly_subsidy",
  contribution_amount: "",
  contribution_duration_months: "12",
};

const HEADER_ALIASES = {
  employee_id: "employee_id",
  employeeid: "employee_id",
  full_name: "full_name",
  name: "full_name",
  email: "email",
  annual_salary: "annual_salary",
  salary: "annual_salary",
  family_size: "family_size",
  num_children: "num_children",
  children: "num_children",
  preferred_city: "preferred_city",
  city: "preferred_city",
  work_location: "preferred_city",
  max_commute_minutes: "max_commute_minutes",
  min_bedrooms: "min_bedrooms",
  other_notes: "other_notes",
  notes: "other_notes",
  contribution_type: "contribution_type",
  contribution_amount: "contribution_amount",
  contribution_duration_months: "contribution_duration_months",
};

function blankPerson() {
  return { ...EMPTY_PERSON, key: `${Date.now()}-${Math.random()}` };
}

function parseCsv(text) {
  const rows = [];
  let row = [];
  let cell = "";
  let quoted = false;
  const source = String(text || "").replace(/^\uFEFF/, "");
  for (let index = 0; index < source.length; index += 1) {
    const char = source[index];
    if (quoted) {
      if (char === '"') {
        if (source[index + 1] === '"') {
          cell += '"';
          index += 1;
        } else quoted = false;
      } else cell += char;
    } else if (char === '"') quoted = true;
    else if (char === ",") {
      row.push(cell);
      cell = "";
    } else if (char === "\n" || char === "\r") {
      if (char === "\r" && source[index + 1] === "\n") index += 1;
      row.push(cell);
      cell = "";
      if (row.some((value) => value.trim())) rows.push(row);
      row = [];
    } else cell += char;
  }
  if (cell || row.length) {
    row.push(cell);
    if (row.some((value) => value.trim())) rows.push(row);
  }
  if (rows.length < 2) throw new Error("The file needs a header row and at least one person.");
  const headers = rows[0].map((value) => HEADER_ALIASES[value.trim().toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "")] || "");
  return rows.slice(1).map((values) => {
    const person = blankPerson();
    headers.forEach((field, index) => {
      if (field) person[field] = (values[index] || "").trim();
    });
    return person;
  });
}

function toPayload(person) {
  return {
    employee_id: person.employee_id.trim(),
    full_name: person.full_name.trim(),
    email: person.email.trim(),
    annual_salary: Number(person.annual_salary),
    family_size: Number(person.family_size),
    num_children: Number(person.num_children) || 0,
    preferred_city: person.preferred_city.trim(),
    max_commute_minutes: person.max_commute_minutes ? Number(person.max_commute_minutes) : null,
    min_bedrooms: person.min_bedrooms ? Number(person.min_bedrooms) : null,
    other_notes: person.other_notes.trim() || null,
    contribution_type: person.contribution_type,
    contribution_amount: Number(person.contribution_amount),
    contribution_duration_months: person.contribution_duration_months ? Number(person.contribution_duration_months) : null,
  };
}

export default function NewCompany() {
  const navigate = useNavigate();
  const [company, setCompany] = useState({ company_name: "", contact_email: "" });
  const [people, setPeople] = useState([blankPerson()]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const commitment = useMemo(() => {
    let dollars = 0;
    let percentPeople = 0;
    people.forEach((person) => {
      if (person.contribution_amount === "") return;
      const monthly = monthlyHelp(person);
      if (monthly == null) percentPeople += 1;
      else dollars += monthly;
    });
    return { dollars, percentPeople };
  }, [people]);

  function updatePerson(key, patch) {
    setPeople((rows) => rows.map((person) => (person.key === key ? { ...person, ...patch } : person)));
  }

  function onCsv(file) {
    if (!file) return;
    setError("");
    file
      .text()
      .then((text) => {
        const parsed = parseCsv(text);
        if (!parsed.length) throw new Error("No people were found in that file.");
        setPeople(parsed);
      })
      .catch((err) => setError(err.message));
  }

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    const filled = people.filter((person) => person.full_name.trim() || person.email.trim() || person.employee_id.trim());
    if (!filled.length) {
      setError("Add at least one person.");
      return;
    }
    setSaving(true);
    let created = null;
    try {
      created = await createEmployer(company);
      await uploadJson({ employer_id: created.id, employees: filled.map(toPayload) });
      navigate(`/employer/${created.id}`);
    } catch (err) {
      setError(created ? `The company was saved, but the people were not. ${err.message}` : err.message);
      if (created) navigate(`/employer/${created.id}`);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-clay">Admin</p>
          <h1 className="font-display text-4xl">New company</h1>
          <p className="mt-2 max-w-xl text-sm text-ink/70">
            Company, contact, and the people they will help, including what the company is ready to pay. One save.
          </p>
        </div>
        <Link className="text-sm underline" to="/admin">
          Back to companies
        </Link>
      </div>

      {error && <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-900">{error}</p>}

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="rounded-3xl border border-sand bg-white p-5">
          <h2 className="font-display text-2xl">Company</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="text-xs text-ink/60">
              Company name
              <input
                required
                className="mt-1 w-full rounded-xl border border-sand px-3 py-2 text-sm text-ink"
                value={company.company_name}
                onChange={(event) => setCompany({ ...company, company_name: event.target.value })}
              />
            </label>
            <label className="text-xs text-ink/60">
              Contact email
              <input
                required
                type="email"
                className="mt-1 w-full rounded-xl border border-sand px-3 py-2 text-sm text-ink"
                value={company.contact_email}
                onChange={(event) => setCompany({ ...company, contact_email: event.target.value })}
              />
            </label>
          </div>
        </div>
        <div className="rounded-3xl bg-pine p-5 text-paper">
          <p className="text-xs uppercase tracking-[0.16em] text-paper/70">Ready to pay</p>
          <p className="mt-2 font-display text-4xl">
            {money(commitment.dollars)}
            <span className="text-2xl"> / month</span>
          </p>
          <p className="mt-2 text-sm text-paper/80">
            From the people below.
            {commitment.percentPeople
              ? ` ${commitment.percentPeople} ${commitment.percentPeople === 1 ? "person gets" : "people get"} a share of the rent on top of that.`
              : ""}
          </p>
        </div>
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-2xl">People</h2>
          <div className="flex flex-wrap items-center gap-3">
            <label className="cursor-pointer text-sm underline">
              Fill from a CSV
              <input type="file" accept=".csv,text/csv" className="hidden" onChange={(event) => onCsv(event.target.files?.[0])} />
            </label>
            <a className="text-sm underline" href="/sample_employees.csv">
              Sample file
            </a>
            <button type="button" className="rounded-full border border-ink px-3 py-1.5 text-sm" onClick={() => setPeople((rows) => [...rows, blankPerson()])}>
              Add a person
            </button>
          </div>
        </div>
        {people.map((person, index) => (
          <article key={person.key} className="rounded-3xl border border-sand bg-white p-5">
            <div className="flex items-center justify-between gap-3">
              <h3 className="font-medium">Person {index + 1}</h3>
              {people.length > 1 && (
                <button
                  type="button"
                  className="text-xs underline"
                  onClick={() => setPeople((rows) => rows.filter((item) => item.key !== person.key))}
                >
                  Remove
                </button>
              )}
            </div>
            <div className="mt-3 grid gap-3 md:grid-cols-3">
              {[
                ["employee_id", "Employee ID"],
                ["full_name", "Full name"],
                ["email", "Email"],
                ["annual_salary", "Yearly pay"],
                ["family_size", "People in the household"],
                ["num_children", "Children"],
                ["preferred_city", "City"],
                ["max_commute_minutes", "Max commute, minutes"],
                ["min_bedrooms", "Bedrooms needed"],
                ["contribution_amount", "Help amount"],
                ["contribution_duration_months", "How many months"],
              ].map(([field, label]) => (
                <label key={field} className="text-xs text-ink/60">
                  {label}
                  <input
                    className="mt-1 w-full rounded-xl border border-sand px-3 py-2 text-sm text-ink"
                    type={field === "email" ? "email" : "text"}
                    required={["employee_id", "full_name", "email", "annual_salary", "preferred_city", "contribution_amount"].includes(field)}
                    value={person[field]}
                    onChange={(event) => updatePerson(person.key, { [field]: event.target.value })}
                  />
                </label>
              ))}
              <label className="text-xs text-ink/60">
                Kind of help
                <select
                  className="mt-1 w-full rounded-xl border border-sand px-3 py-2 text-sm text-ink"
                  value={person.contribution_type}
                  onChange={(event) => updatePerson(person.key, { contribution_type: event.target.value })}
                >
                  <option value="monthly_subsidy">A set amount each month</option>
                  <option value="one_time_assistance">One-time help</option>
                  <option value="percent_of_rent">A percent of the rent</option>
                </select>
              </label>
              <label className="text-xs text-ink/60 md:col-span-2">
                Anything else we should know
                <input
                  className="mt-1 w-full rounded-xl border border-sand px-3 py-2 text-sm text-ink"
                  value={person.other_notes}
                  onChange={(event) => updatePerson(person.key, { other_notes: event.target.value })}
                />
              </label>
            </div>
          </article>
        ))}
      </section>

      <button className="rounded-full bg-ink px-5 py-2.5 text-sm text-paper disabled:opacity-50" disabled={saving}>
        {saving ? "Saving…" : "Save company and people"}
      </button>
    </form>
  );
}
