import { Fragment, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { downloadChoices, generateOptions, getEmployees, getEmployers, getSummary, money, updateEmployee, updateEmployer, uploadCsv, uploadJson } from "../api";
import { helpLine, monthlyHelp } from "./PriceSplit";

const EMPTY_FORM = {
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

export default function StaffDesk({ employerId }) {
  const [employer, setEmployer] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [workLocation, setWorkLocation] = useState("");
  const [savingPlace, setSavingPlace] = useState(false);

  async function refresh(id) {
    const [companies, staff, report] = await Promise.all([getEmployers(), getEmployees(id), getSummary(id)]);
    const company = companies.find((item) => item.id === Number(id)) || null;
    setEmployer(company);
    setWorkLocation(company?.work_location || "");
    setEmployees(staff);
    setSummary(report);
  }

  useEffect(() => {
    if (!employerId) return;
    refresh(employerId).catch((err) => setError(err.message));
  }, [employerId]);

  const commitment = useMemo(() => {
    let dollars = 0;
    let percentPeople = 0;
    employees.forEach((person) => {
      const monthly = monthlyHelp(person);
      if (monthly == null) percentPeople += 1;
      else dollars += monthly;
    });
    return { dollars, percentPeople };
  }, [employees]);

  async function onCsv(file) {
    if (!file || !employerId) return;
    setError("");
    try {
      const result = await uploadCsv(employerId, file);
      setNotice(`Saved ${result.created} new people and updated ${result.updated}.`);
      await refresh(employerId);
    } catch (err) {
      setError(err.message);
    }
  }

  async function onAddEmployee(event) {
    event.preventDefault();
    setError("");
    try {
      await uploadJson({
        employer_id: Number(employerId),
        employees: [
          {
            ...form,
            annual_salary: Number(form.annual_salary),
            family_size: Number(form.family_size),
            num_children: Number(form.num_children),
            max_commute_minutes: form.max_commute_minutes ? Number(form.max_commute_minutes) : null,
            min_bedrooms: form.min_bedrooms ? Number(form.min_bedrooms) : null,
            contribution_amount: Number(form.contribution_amount),
            contribution_duration_months: form.contribution_duration_months
              ? Number(form.contribution_duration_months)
              : null,
          },
        ],
      });
      setForm(EMPTY_FORM);
      setShowForm(false);
      setNotice("Person saved.");
      await refresh(employerId);
    } catch (err) {
      setError(err.message);
    }
  }

  async function onSaveBudget(event) {
    event.preventDefault();
    if (!editing) return;
    setError("");
    try {
      const previous = employees.find((person) => person.employee_id_external === editing.id);
      await updateEmployee(editing.id, {
        preferred_city: editing.preferred_city.trim(),
        contribution_type: editing.contribution_type,
        contribution_amount: Number(editing.contribution_amount),
        contribution_duration_months: editing.contribution_duration_months
          ? Number(editing.contribution_duration_months)
          : null,
      });
      const cityChanged = previous && previous.preferred_city.trim() !== editing.preferred_city.trim();
      setEditing(null);
      setNotice(cityChanged ? "City saved. Refresh homes to search the new city." : "Details saved.");
      await refresh(employerId);
    } catch (err) {
      setError(err.message);
    }
  }

  async function onGenerate(person) {
    setBusyId(person.id);
    setError("");
    setNotice(`Finding homes for ${person.full_name}.`);
    try {
      const result = await generateOptions(person.id);
      setNotice(`${result.options_created} homes ready for ${person.full_name}.`);
      await refresh(employerId);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.18em] text-clay">Employer</p>
          <h1 className="font-display text-4xl">{employer?.company_name || "Company"}</h1>
          <p className="text-sm text-ink/60">{employer?.contact_email}</p>
          <form
            className="mt-3 flex flex-wrap items-end gap-2"
            onSubmit={async (event) => {
              event.preventDefault();
              if (!employer) return;
              setSavingPlace(true);
              setError("");
              setNotice("");
              try {
                const updated = await updateEmployer(employer.id, { work_location: workLocation.trim() });
                setEmployer(updated);
                setWorkLocation(updated.work_location || "");
                setNotice(
                  updated.work_latitude
                    ? "Workplace saved. Homes are suggested closer to it."
                    : "That address was saved, but it could not be placed on a map."
                );
              } catch (err) {
                setError(err.message);
              } finally {
                setSavingPlace(false);
              }
            }}
          >
            <label className="text-xs text-ink/60">
              Workplace
              <input
                required
                className="mt-1 w-80 max-w-full rounded-xl border border-sand bg-white px-3 py-2 text-sm text-ink"
                value={workLocation}
                onChange={(event) => setWorkLocation(event.target.value)}
              />
            </label>
            <button className="rounded-full border border-ink px-4 py-2 text-sm" disabled={savingPlace}>
              {savingPlace ? "Saving…" : "Save workplace"}
            </button>
          </form>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <div className="rounded-3xl bg-pine p-5 text-paper md:col-span-2">
          <p className="text-xs uppercase tracking-[0.16em] text-paper/70">Ready to pay</p>
          <p className="mt-2 font-display text-4xl">{money(commitment.dollars)}<span className="text-2xl"> / month</span></p>
          <p className="mt-2 text-sm text-paper/80">
            Fixed help across the team.
            {commitment.percentPeople
              ? ` ${commitment.percentPeople} ${commitment.percentPeople === 1 ? "person gets" : "people get"} a share of the rent on top of that.`
              : ""}
          </p>
        </div>
        {[
          ["People", summary?.total_employees ?? employees.length],
          ["Have homes", summary?.options_ready_count ?? 0],
          ["Have chosen", summary?.selections_count ?? 0],
        ].map(([label, value]) => (
          <div key={label} className="rounded-3xl border border-sand bg-white px-4 py-4">
            <p className="text-xs uppercase tracking-wider text-ink/45">{label}</p>
            <p className="font-display text-4xl">{value}</p>
          </div>
        ))}
      </div>

      {(error || notice) && (
        <p className={`rounded-2xl px-4 py-3 text-sm ${error ? "bg-red-50 text-red-900" : "bg-pine/10 text-pine"}`}>
          {error || notice}
        </p>
      )}

      <section
        className="rounded-3xl border border-dashed border-clay/40 bg-white p-5"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          onCsv(event.dataTransfer.files?.[0]);
        }}
      >
        <h2 className="font-display text-2xl">Add people from a spreadsheet</h2>
        <p className="mt-2 max-w-xl text-sm text-ink/70">
          Drop a CSV here, or start from the sample. Each row is one person, their city, and how much you will contribute.
        </p>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <label className="cursor-pointer rounded-full bg-clay px-4 py-2 text-sm text-white">
            Choose file
            <input type="file" accept=".csv,text/csv" className="hidden" onChange={(event) => onCsv(event.target.files?.[0])} />
          </label>
          <a className="text-sm underline" href="/sample_employees.csv">
            Download a sample file
          </a>
        </div>
      </section>

      <section className="overflow-hidden rounded-3xl border border-sand bg-white">
        <div className="flex items-center justify-between gap-3 border-b border-sand px-5 py-4">
          <h2 className="font-display text-2xl">People</h2>
          <button className="rounded-full border border-ink px-3 py-1.5 text-sm" onClick={() => setShowForm((value) => !value)}>
            {showForm ? "Close" : "Add a person"}
          </button>
        </div>
        {showForm && (
          <form onSubmit={onAddEmployee} className="grid gap-3 border-b border-sand px-5 py-4 md:grid-cols-3">
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
            ].map(([key, label]) => (
              <label key={key} className="text-xs text-ink/60">
                {label}
                <input
                  className="mt-1 w-full rounded-xl border border-sand px-3 py-2 text-sm text-ink"
                  value={form[key]}
                  onChange={(event) => setForm({ ...form, [key]: event.target.value })}
                  required={["employee_id", "full_name", "email", "annual_salary", "preferred_city", "contribution_amount"].includes(key)}
                />
              </label>
            ))}
            <label className="text-xs text-ink/60">
              Kind of help
              <select
                className="mt-1 w-full rounded-xl border border-sand px-3 py-2 text-sm text-ink"
                value={form.contribution_type}
                onChange={(event) => setForm({ ...form, contribution_type: event.target.value })}
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
                value={form.other_notes}
                onChange={(event) => setForm({ ...form, other_notes: event.target.value })}
              />
            </label>
            <button className="rounded-full bg-ink px-4 py-2 text-sm text-paper md:col-span-3">Save</button>
          </form>
        )}
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-ink/45">
              <tr>
                <th className="px-5 py-3 font-medium">Person</th>
                <th className="px-3 py-3 font-medium">City</th>
                <th className="px-3 py-3 font-medium">You pay</th>
                <th className="px-3 py-3 font-medium">Homes</th>
                <th className="px-5 py-3 font-medium"> </th>
              </tr>
            </thead>
            <tbody>
              {employees.map((person) => (
                <Fragment key={person.id}>
                <tr className="border-t border-sand">
                  <td className="px-5 py-3">
                    <p className="font-medium">{person.full_name}</p>
                    <p className="text-xs text-ink/55">{person.email}</p>
                  </td>
                  <td className="px-3 py-3">{person.preferred_city}</td>
                  <td className="px-3 py-3">{helpLine(person)}</td>
                  <td className="px-3 py-3">
                    {person.selected_address ? (
                      <p className="text-pine">{person.selected_address}</p>
                    ) : person.options_count ? (
                      `${person.options_count} ready`
                    ) : (
                      "Not searched yet"
                    )}
                  </td>
                  <td className="w-44 px-4 py-3">
                    <div className="flex flex-col items-stretch gap-1.5">
                      <button
                        className="whitespace-nowrap rounded-full bg-pine px-3 py-1.5 text-xs text-white disabled:opacity-50"
                        disabled={busyId === person.id}
                        onClick={() => onGenerate(person)}
                      >
                        {busyId === person.id ? "Searching…" : person.options_count ? "Refresh homes" : "Find homes"}
                      </button>
                      <button
                        className="whitespace-nowrap text-xs underline"
                        onClick={() =>
                          setEditing({
                            id: person.employee_id_external,
                            preferred_city: person.preferred_city || "",
                            contribution_type: person.contribution_type,
                            contribution_amount: person.contribution_amount,
                            contribution_duration_months: person.contribution_duration_months || "",
                          })
                        }
                      >
                        Edit
                      </button>
                      <Link className="whitespace-nowrap text-center text-xs underline" to={`/employee/${person.employee_id_external}`}>
                        See their homes
                      </Link>
                    </div>
                  </td>
                </tr>
                {editing?.id === person.employee_id_external && (
                  <tr className="border-t border-sand bg-paper">
                    <td colSpan={5} className="px-5 py-3">
                      <form onSubmit={onSaveBudget} className="flex flex-wrap items-end gap-2">
                        <label className="text-xs text-ink/60">
                          City
                          <input
                            required
                            className="mt-1 block w-44 rounded-xl border border-sand bg-white px-3 py-2 text-sm text-ink"
                            value={editing.preferred_city}
                            onChange={(event) => setEditing({ ...editing, preferred_city: event.target.value })}
                          />
                        </label>
                        <label className="text-xs text-ink/60">
                          Kind of help
                          <select
                            className="mt-1 block rounded-xl border border-sand bg-white px-3 py-2 text-sm text-ink"
                            value={editing.contribution_type}
                            onChange={(event) => setEditing({ ...editing, contribution_type: event.target.value })}
                          >
                            <option value="monthly_subsidy">A set amount each month</option>
                            <option value="one_time_assistance">One-time help</option>
                            <option value="percent_of_rent">A percent of the rent</option>
                          </select>
                        </label>
                        <label className="text-xs text-ink/60">
                          Amount
                          <input
                            type="number"
                            min="0"
                            required
                            className="mt-1 block w-28 rounded-xl border border-sand bg-white px-3 py-2 text-sm text-ink"
                            value={editing.contribution_amount}
                            onChange={(event) => setEditing({ ...editing, contribution_amount: event.target.value })}
                          />
                        </label>
                        <label className="text-xs text-ink/60">
                          Months
                          <input
                            type="number"
                            min="1"
                            className="mt-1 block w-24 rounded-xl border border-sand bg-white px-3 py-2 text-sm text-ink"
                            value={editing.contribution_duration_months}
                            onChange={(event) => setEditing({ ...editing, contribution_duration_months: event.target.value })}
                          />
                        </label>
                        <button className="rounded-full bg-ink px-3 py-2 text-xs text-paper">Save</button>
                        <button type="button" className="text-xs underline" onClick={() => setEditing(null)}>
                          Cancel
                        </button>
                      </form>
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-3xl border border-sand bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-2xl">Choices</h2>
          <button
            type="button"
            className="rounded-full border border-ink px-3 py-1.5 text-sm"
            onClick={() => downloadChoices(employer?.company_name, summary?.selections || [])}
          >
            Download choices
          </button>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wider text-ink/45">
              <tr>
                <th className="py-2 font-medium">Person</th>
                <th className="py-2 font-medium">Home</th>
                <th className="py-2 font-medium">Listed rent</th>
                <th className="py-2 font-medium">Company pays</th>
                <th className="py-2 font-medium">Employee pays</th>
              </tr>
            </thead>
            <tbody>
              {(summary?.selections || []).map((row) => (
                <tr key={row.employee_id} className="border-t border-sand">
                  <td className="py-3">
                    <p>{row.full_name}</p>
                    <p className="text-xs text-ink/55">{row.preferred_city}</p>
                  </td>
                  <td className="py-3">
                    {row.status === "selected" ? (
                      <Link className="underline" to={`/options/${row.housing_option_id}`}>
                        {row.address}
                      </Link>
                    ) : (
                      <span className="text-ink/45">Hasn’t chosen yet</span>
                    )}
                    {row.employee_notes ? <p className="mt-1 text-xs text-ink/60">{row.employee_notes}</p> : null}
                  </td>
                  <td className="py-3">{money(row.sticker_price)}</td>
                  <td className="py-3">{money(row.employer_monthly_cover)}</td>
                  <td className="py-3 font-medium">{money(row.net_price)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
