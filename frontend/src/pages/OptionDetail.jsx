import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { bedsLabel, getEmployee, getOption, money, selectOption } from "../api";
import HomeQuestions from "../components/HomeQuestions";
import MapFrame from "../components/MapFrame";
import NearbyPlaces from "../components/NearbyPlaces";
import PriceSplit from "../components/PriceSplit";

export default function OptionDetail() {
  const { optionId } = useParams();
  const [option, setOption] = useState(null);
  const [employee, setEmployee] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    getOption(optionId)
      .then(async (row) => {
        setOption(row);
        const person = await getEmployee(row.employee_id);
        setEmployee(person);
      })
      .catch((err) => setError(err.message));
  }, [optionId]);

  async function onSelect() {
    try {
      await selectOption(option.employee_id, option.id, notes);
      setNotice("Selection saved for the employer.");
      const person = await getEmployee(option.employee_id);
      setEmployee(person);
    } catch (err) {
      setError(err.message);
    }
  }

  if (error) return <p className="rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-900">{error}</p>;
  if (!option) return <p>Loading listing…</p>;
  const analysis = option.gemini_analysis || {};
  const amenities = option.amenities_data || {};
  const selected = employee?.selected_option_id === option.id;

  return (
    <article className="mx-auto max-w-3xl">
      <Link className="text-sm underline" to={employee ? `/employee/${employee.employee_id_external}` : "/employee"}>
        Back to options
      </Link>
      <h1 className="mt-4 font-display text-5xl leading-tight">{option.address}</h1>
      <p className="mt-2 text-ink/70">
        {bedsLabel(option.bedrooms)}
        {option.bathrooms ? ` · ${option.bathrooms} bath` : ""}
        {option.sqft ? ` · ${Math.round(option.sqft).toLocaleString()} sq ft` : ""}
      </p>
      <p className="mt-4 text-xs uppercase tracking-wider text-ink/45">You pay each month</p>
      <p className="font-display text-5xl">{money(option.net_price)}</p>
      <div className="mt-4">
        <PriceSplit listed={option.price} employerPays={option.employer_monthly_cover} youPay={option.net_price} size="lg" />
      </div>
      <div className="mt-4 overflow-hidden rounded-3xl border border-sand">
        <MapFrame
          address={option.address}
          lat={option.listing_data?.latitude}
          lng={option.listing_data?.longitude}
          className="h-72"
        />
        <NearbyPlaces
          detailed
          amenities={amenities}
          lat={option.listing_data?.latitude}
          lng={option.listing_data?.longitude}
          className="px-4 py-4"
        />
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <ul className="space-y-2">
          {(analysis.pros || []).map((item) => (
            <li key={item} className="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{item}</li>
          ))}
        </ul>
        <ul className="space-y-2">
          {(analysis.cons || []).map((item) => (
            <li key={item} className="rounded-xl bg-rose-50 px-3 py-2 text-sm text-rose-800">{item}</li>
          ))}
        </ul>
      </div>
      <div className="mt-6 overflow-hidden rounded-3xl border border-sand">
        <HomeQuestions optionId={option.id} />
      </div>
      {notice && <p className="mt-4 rounded-2xl bg-pine/10 px-4 py-3 text-sm text-pine">{notice}</p>}
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <input
          className="min-w-[220px] flex-1 rounded-full border border-sand bg-white px-4 py-2 text-sm"
          placeholder="Note for your employer"
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
        />
        <button className="rounded-full bg-clay px-4 py-2 text-sm text-white" onClick={onSelect}>
          {selected ? "Update selection" : "Select this home"}
        </button>
        {option.source_url && (
          <a className="text-sm underline" href={option.source_url} target="_blank" rel="noreferrer">
            Open listing source
          </a>
        )}
      </div>
    </article>
  );
}
