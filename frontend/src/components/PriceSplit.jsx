import { money } from "../api";

export default function PriceSplit({ listed, employerPays, youPay, size = "md" }) {
  const big = size === "lg";
  return (
    <div className={`grid grid-cols-3 gap-2 rounded-2xl bg-paper ${big ? "px-4 py-4" : "px-3 py-3"}`}>
      <div>
        <p className="text-xs text-ink/50">Listed rent</p>
        <p className={big ? "font-display text-3xl" : "text-sm font-medium"}>{money(listed)}</p>
      </div>
      <div>
        <p className="text-xs text-ink/50">Employer pays</p>
        <p className={big ? "font-display text-3xl" : "text-sm font-medium"}>− {money(employerPays)}</p>
      </div>
      <div>
        <p className="text-xs text-ink/50">You pay</p>
        <p className={big ? "font-display text-3xl" : "text-sm font-medium"}>{money(youPay)}</p>
      </div>
    </div>
  );
}

export function monthlyHelp(person) {
  const amount = Number(person.contribution_amount) || 0;
  const months = Number(person.contribution_duration_months) || 12;
  if (person.contribution_type === "monthly_subsidy") return amount;
  if (person.contribution_type === "one_time_assistance") return months ? amount / months : amount;
  return null;
}

export function helpLine(person) {
  if (person.contribution_type === "percent_of_rent") {
    const amount = Number(person.contribution_amount) || 0;
    const shown = amount > 1 ? amount : amount * 100;
    return `${shown}% of the rent`;
  }
  const monthly = monthlyHelp(person);
  if (person.contribution_type === "one_time_assistance") {
    return `${new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(monthly)} a month, from one-time help`;
  }
  return `${new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(monthly || 0)} a month`;
}
