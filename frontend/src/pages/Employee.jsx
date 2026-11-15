import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { affordability, api, bedsLabel, generateOptions, getOptions, money, plainTalk, selectOption, updateEmployee } from "../api";
import MapFrame from "../components/MapFrame";
import NearbyPlaces from "../components/NearbyPlaces";
import PriceSplit, { helpLine } from "../components/PriceSplit";

const BILL_FIELDS = [
  ["utilities", "Utilities", "180"],
  ["groceries", "Groceries", "550"],
  ["transport", "Getting around", "220"],
  ["childcare", "Childcare", "0"],
  ["other", "Other bills", "150"],
];

const EMPTY_BILLS = {
  utilities: "180",
  groceries: "550",
  transport: "220",
  childcare: "0",
  other: "150",
  savings: "400",
  take_home_ratio: "0.75",
};

function homeType(value) {
  if (!value) return "";
  const text = String(value).replaceAll("_", " ").toLowerCase();
  if (text.includes("single")) return "House";
  if (text.includes("apartment") || text.includes("condo")) return "Apartment";
  if (text.includes("town")) return "Townhouse";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export default function Employee() {
  const { employeeId } = useParams();
  const [roster, setRoster] = useState([]);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [notes, setNotes] = useState("");
  const [selecting, setSelecting] = useState(null);
  const [bills, setBills] = useState(EMPTY_BILLS);
  const [ranking, setRanking] = useState(null);
  const [calcBusy, setCalcBusy] = useState(false);
  const [hideOver, setHideOver] = useState(false);
  const [needs, setNeeds] = useState("");
  const [savingNeeds, setSavingNeeds] = useState(false);

  useEffect(() => {
    api("/employees").then(setRoster).catch(() => setRoster([]));
  }, []);

  useEffect(() => {
    if (!employeeId) {
      setData(null);
      return;
    }
    setError("");
    setRanking(null);
    getOptions(employeeId)
      .then((next) => {
        setData(next);
        setNeeds(next.employee?.other_notes || "");
      })
      .catch((err) => setError(err.message));
  }, [employeeId]);

  useEffect(() => {
    if (!loading) return undefined;
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.round((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [loading]);

  const billTotal = BILL_FIELDS.reduce((sum, [key]) => sum + (Number(bills[key]) || 0), 0);
  const savingsAmount = Number(bills.savings) || 0;
  const takeHome = data?.monthly_gross ? data.monthly_gross * Number(bills.take_home_ratio) : null;
  const leftAfterBills = takeHome == null ? null : takeHome - billTotal - savingsAmount;

  const rankedById = useMemo(() => {
    const map = new Map();
    (ranking?.options || []).forEach((row) => map.set(row.housing_option_id, row));
    return map;
  }, [ranking]);

  const options = useMemo(() => {
    const rows = data?.options || [];
    if (!ranking) return rows;
    return [...rows]
      .sort((a, b) => (rankedById.get(a.id)?.rank || 99) - (rankedById.get(b.id)?.rank || 99))
      .filter((row) => !hideOver || rankedById.get(row.id)?.fits_budget);
  }, [data, ranking, rankedById, hideOver]);

  async function onGenerate() {
    setLoading(true);
    setElapsed(0);
    setError("");
    setNotice("");
    try {
      const result = await generateOptions(employeeId);
      setData(result);
      setRanking(null);
      setNotice("Homes are ready.");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function onSelect(optionId) {
    setSelecting(optionId);
    setError("");
    try {
      await selectOption(employeeId, optionId, notes);
      setData(await getOptions(employeeId));
      setNotice("Your choice was saved.");
    } catch (err) {
      setError(err.message);
    } finally {
      setSelecting(null);
    }
  }

  async function onCalc(event) {
    event.preventDefault();
    setCalcBusy(true);
    setError("");
    try {
      const result = await affordability(employeeId, {
        other_monthly_expenses: billTotal,
        desired_savings: Number(bills.savings) || 0,
        take_home_ratio: Number(bills.take_home_ratio),
      });
      setRanking(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setCalcBusy(false);
    }
  }

  if (!employeeId) {
    return (
      <div>
        <p className="text-xs uppercase tracking-[0.18em] text-clay">Employee</p>
        <h1 className="font-display text-4xl">Choose a person</h1>
        <div className="mt-6 grid gap-3 sm:grid-cols-2">
          {roster.map((person) => (
            <Link key={person.id} to={`/employee/${person.employee_id_external}`} className="rounded-3xl border border-sand bg-white p-4 hover:border-clay">
              <p className="font-medium">{person.full_name}</p>
              <p className="text-sm text-ink/65">{person.preferred_city}</p>
            </Link>
          ))}
        </div>
      </div>
    );
  }

  const employee = data?.employee;
  const loadingLine = elapsed < 20 ? "Looking up rentals." : elapsed < 50 ? "Checking prices and nearby places." : "Finishing the matches.";
  const household = employee
    ? `${employee.family_size} ${employee.family_size === 1 ? "person" : "people"}${
        employee.num_children ? `, ${employee.num_children} ${employee.num_children === 1 ? "child" : "children"}` : ""
      }`
    : "";

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
      <aside className="lg:sticky lg:top-4 lg:self-start">
        <form onSubmit={onCalc} className="rounded-3xl border border-sand bg-white p-4">
          <h2 className="font-display text-2xl">Monthly bills</h2>
          <p className="mt-1 text-xs text-ink/60">These come out before rent. We’ll use what’s left to reorder the homes.</p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            {BILL_FIELDS.map(([key, label]) => (
              <label key={key} className="text-xs text-ink/60">
                {label}
                <input
                  type="number"
                  min="0"
                  className="mt-1 w-full rounded-xl border border-sand px-3 py-2 text-sm text-ink"
                  value={bills[key]}
                  onChange={(event) => setBills({ ...bills, [key]: event.target.value })}
                />
              </label>
            ))}
            <label className="text-xs text-ink/60">
              Amount to save
              <input
                type="number"
                min="0"
                className="mt-1 w-full rounded-xl border border-sand px-3 py-2 text-sm text-ink"
                value={bills.savings}
                onChange={(event) => setBills({ ...bills, savings: event.target.value })}
              />
            </label>
          </div>
          <label className="mt-3 block text-xs text-ink/60">
            <span className="flex items-center justify-between gap-3">
              Take-home pay
              <span className="font-medium text-ink">{Math.round(Number(bills.take_home_ratio) * 100)}%</span>
            </span>
            <input
              type="range"
              min="60"
              max="100"
              step="1"
              className="mt-2"
              value={Math.round(Number(bills.take_home_ratio) * 100)}
              onChange={(event) => setBills({ ...bills, take_home_ratio: String(Number(event.target.value) / 100) })}
            />
            <span className="mt-1 flex justify-between text-[11px] text-ink/45">
              <span>60%</span>
              <span>100%</span>
            </span>
          </label>
          <div className="mt-4 space-y-1 rounded-2xl bg-paper px-3 py-3 text-sm">
            <p className="flex justify-between gap-3">
              <span className="text-ink/60">Take-home pay</span>
              <span className="font-medium">{takeHome == null ? "—" : `${money(takeHome)} / mo`}</span>
            </p>
            <p className="flex justify-between gap-3">
              <span className="text-ink/60">Bills and savings</span>
              <span className="font-medium">{money(billTotal + savingsAmount)}</span>
            </p>
            <p className="flex justify-between gap-3 border-t border-sand pt-2">
              <span>Left after bills</span>
              <span className={`font-medium ${leftAfterBills != null && leftAfterBills < 0 ? "text-rose-600" : "text-emerald-700"}`}>
                {leftAfterBills == null ? "—" : `${money(leftAfterBills)} / mo`}
              </span>
            </p>
          </div>
          <button className="mt-3 w-full rounded-full bg-ink py-2 text-sm text-paper disabled:opacity-50" disabled={calcBusy || !data?.options?.length}>
            {calcBusy ? "Updating…" : "See which homes fit"}
          </button>
          {ranking && (
            <div className="mt-4 space-y-2 text-sm">
              <p>
                Left for housing <span className="font-medium">{money(ranking.housing_budget)}</span>
              </p>
              <p className="text-ink/70">{plainTalk(ranking.narrative)}</p>
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={hideOver} onChange={(event) => setHideOver(event.target.checked)} />
                Only show homes within this
              </label>
              <button
                type="button"
                className="text-xs underline"
                onClick={() => {
                  setRanking(null);
                  setHideOver(false);
                }}
              >
                Show the original order
              </button>
            </div>
          )}
        </form>
      </aside>

      <section>
        {employee && (
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-clay">{employee.preferred_city}</p>
              <h1 className="font-display text-4xl">{employee.full_name}</h1>
            </div>
            <button className="rounded-full border border-ink px-4 py-2 text-sm disabled:opacity-50" onClick={onGenerate} disabled={loading}>
              {loading ? "Searching…" : data.options?.length ? "Refresh homes" : "Find homes"}
            </button>
          </div>
        )}

        {employee && (
          <div className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["Household", household],
              ["Pay", `${money(employee.annual_salary)} a year`],
              ["Employer help", helpLine(employee)],
              ["A comfortable rent", `${money(data.housing_budget)} a month`],
            ].map(([label, value]) => (
              <div key={label} className="rounded-2xl border border-sand bg-white px-3 py-3">
                <p className="text-xs uppercase tracking-wider text-ink/45">{label}</p>
                <p className="mt-1 text-sm font-medium leading-snug">{value}</p>
              </div>
            ))}
          </div>
        )}
        {employee && (
          <form
            className="mt-3 rounded-2xl border border-sand bg-white p-4"
            onSubmit={async (event) => {
              event.preventDefault();
              setSavingNeeds(true);
              setError("");
              try {
                const updated = await updateEmployee(employeeId, { other_notes: needs });
                setData((current) => ({ ...current, employee: { ...current.employee, ...updated } }));
                setNotice("Requirements saved. Refresh homes to use them in the next match.");
              } catch (err) {
                setError(err.message);
              } finally {
                setSavingNeeds(false);
              }
            }}
          >
            <label className="block text-xs text-ink/60">
              What this household needs
              <textarea
                className="mt-1 w-full rounded-xl border border-sand px-3 py-2 text-sm text-ink"
                rows={2}
                value={needs}
                onChange={(event) => setNeeds(event.target.value)}
                placeholder="Two school-age children. Needs an elementary school nearby and space for homework."
              />
            </label>
            <button className="mt-2 rounded-full border border-ink px-3 py-1.5 text-xs" disabled={savingNeeds}>
              {savingNeeds ? "Saving…" : "Save requirements"}
            </button>
          </form>
        )}

        {error && <p className="mt-3 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-900">{error}</p>}
        {notice && <p className="mt-3 rounded-2xl bg-pine/10 px-4 py-3 text-sm text-pine">{notice}</p>}
        {loading && (
          <div className="mt-4 rounded-3xl border border-sand bg-white p-5">
            <p className="font-display text-2xl">Finding homes</p>
            <p className="mt-2 text-sm text-ink/70">{loadingLine}</p>
            <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-sand">
              <div className="h-full w-1/2 animate-pulse bg-clay" />
            </div>
          </div>
        )}

        <div className="mt-4 space-y-4">
          {options.map((option) => {
            const analysis = option.gemini_analysis || {};
            const rank = rankedById.get(option.id);
            const selected = data.selected_option_id === option.id;
            const place = option.listing_data || {};
            return (
              <article key={option.id} className={`overflow-hidden rounded-3xl border bg-white shadow-card ${selected ? "border-pine" : "border-sand"}`}>
                <div className="grid lg:grid-cols-[minmax(0,1fr)_280px]">
                  <div className="p-5">
                    <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wider text-ink/45">
                      {selected && <span className="text-pine">Your choice</span>}
                      {rank && <span>{rank.fits_budget ? "Within budget" : "Above budget"}</span>}
                    </div>
                    <h2 className="mt-1 font-display text-3xl leading-tight">{option.address}</h2>
                    <p className="mt-1 text-sm text-ink/65">
                      {bedsLabel(option.bedrooms)}
                      {option.bathrooms ? ` · ${option.bathrooms} ${Number(option.bathrooms) === 1 ? "bath" : "baths"}` : ""}
                      {option.sqft ? ` · ${Math.round(option.sqft).toLocaleString()} sq ft` : ""}
                      {homeType(place.home_type) ? ` · ${homeType(place.home_type)}` : ""}
                    </p>
                    <div className="mt-4">
                      <p className="text-xs uppercase tracking-wider text-ink/45">You pay each month</p>
                      <p className="font-display text-4xl">{money(option.net_price)}</p>
                    </div>
                    <div className="mt-3">
                      <PriceSplit listed={option.price} employerPays={option.employer_monthly_cover} youPay={option.net_price} />
                    </div>
                    {rank && (
                      <p className={`mt-3 text-sm ${rank.fits_budget ? "text-emerald-700" : "text-rose-600"}`}>{plainTalk(rank.note)}</p>
                    )}
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <ul className="space-y-2">
                        {(analysis.pros || []).map((item) => (
                          <li key={item} className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
                            {plainTalk(item)}
                          </li>
                        ))}
                      </ul>
                      <ul className="space-y-2">
                        {(analysis.cons || []).map((item) => (
                          <li key={item} className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-800">
                            {plainTalk(item)}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div className="mt-4 flex flex-wrap items-center gap-3">
                      <button
                        className="rounded-full bg-clay px-4 py-2 text-sm text-white disabled:opacity-50"
                        disabled={selecting === option.id}
                        onClick={() => onSelect(option.id)}
                      >
                        {selected ? "Chosen" : selecting === option.id ? "Saving…" : "Choose this home"}
                      </button>
                      <Link className="text-sm underline" to={`/options/${option.id}`}>
                        More about this home
                      </Link>
                      {option.source_url && (
                        <a className="text-sm underline" href={option.source_url} target="_blank" rel="noreferrer">
                          View the listing
                        </a>
                      )}
                    </div>
                  </div>
                  <div className="border-t border-sand p-3 lg:border-l lg:border-t-0">
                    <MapFrame address={option.address} lat={place.latitude} lng={place.longitude} className="h-56" />
                    <NearbyPlaces
                      amenities={option.amenities_data}
                      lat={place.latitude}
                      lng={place.longitude}
                      className="mt-3"
                    />
                  </div>
                </div>
              </article>
            );
          })}
          {!loading && employee && options.length === 0 && (
            <div className="rounded-3xl border border-dashed border-sand bg-white p-6">
              <p className="font-display text-2xl">No homes yet</p>
              <p className="mt-2 text-sm text-ink/70">Find homes in {employee.preferred_city} for {employee.full_name}.</p>
            </div>
          )}
        </div>

        {employee && (
          <label className="mt-4 block rounded-3xl border border-sand bg-white p-4 text-xs text-ink/60">
            Note to send with your choice
            <textarea
              className="mt-1 w-full rounded-xl border border-sand px-3 py-2 text-sm text-ink"
              rows={2}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Optional"
            />
          </label>
        )}
      </section>
    </div>
  );
}
