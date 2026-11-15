import { Link } from "react-router-dom";

function Mark() {
  return (
    <span className="home-mark" aria-hidden="true">
      <svg viewBox="0 0 32 32" className="h-8 w-8">
        <path
          fill="#4338ca"
          fillRule="evenodd"
          d="M16 4.2 23.8 11.6h-2.1v7.6H10.3v-7.6H8.2L16 4.2Zm-1.6 8.4h3.2V16h-3.2v-3.4Z"
        />
        <path
          fill="none"
          stroke="#0f766e"
          strokeWidth="2.6"
          strokeLinecap="round"
          d="M6.6 21.8c1.3 5 4.6 7.2 9.4 7.2s8.1-2.2 9.4-7.2"
        />
      </svg>
    </span>
  );
}

const TRADES = [
  {
    place: "Central San Diego",
    title: "Living near work",
    rows: [
      ["Typical home price", "~$850,000", "bad"],
      ["Typical 2-bed rent", "~$3,200/mo", "bad"],
      ["Commute to work", "~15 min", "good"],
    ],
    pill: "Housing costs too high",
    tone: "bad",
  },
  {
    place: "Inland and outlying areas",
    title: "Moving farther away",
    rows: [
      ["Typical home price", "~$550,000", "good"],
      ["Typical 2-bed rent", "~$2,100/mo", "good"],
      ["Commute to work", "~75 min", "bad"],
    ],
    pill: "Much longer commute",
    tone: "warn",
  },
];

export default function Home() {
  return (
    <div className="home-story">
      <header className="home-brand">
        <div className="home-lockup">
          <Mark />
          <p className="home-word">NestFix</p>
        </div>
        <p className="home-line">Helping Employees Find Home.</p>
        <p className="home-line home-line-mint">Helping Employers Keep Talent.</p>
        <p className="home-quote">Because retaining great employees starts with helping them build a better future.</p>
      </header>

      <section className="home-tradeoff">
        <p className="home-kicker">The trade-off</p>
        <h1>Close to work, or within budget?</h1>
        <div className="home-trade-grid">
          {TRADES.map((card) => (
            <article key={card.title} className="home-trade-card">
              <p className="home-place">{card.place}</p>
              <h2>{card.title}</h2>
              <dl>
                {card.rows.map(([label, value, tone]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd className={tone === "good" ? "is-good" : "is-bad"}>{value}</dd>
                  </div>
                ))}
              </dl>
              <p className={`home-pill is-${card.tone}`}>{card.pill}</p>
            </article>
          ))}
        </div>
        <p className="home-fine">Rounded, illustrative figures. Not market data.</p>
      </section>

      <section className="home-answer">
        <p className="home-kicker">What if employers helped</p>
        <h2>The company pays part. The person can live closer.</h2>
        <p className="home-lead">
          NestFix finds rentals in that person’s city, subtracts what the employer will cover, and shows the monthly number left.
        </p>
        <article className="home-example">
          <div>
            <p className="home-place">Maya Chen · Austin</p>
            <h3>5808 Ann Jene Ct</h3>
            <p className="home-meta">3 bed · 3 bath · 2,556 sq ft</p>
          </div>
          <dl>
            <div>
              <dt>Listed rent</dt>
              <dd>$2,800</dd>
            </div>
            <div>
              <dt>Harborlight pays</dt>
              <dd className="is-good">$600</dd>
            </div>
            <div>
              <dt>Maya pays</dt>
              <dd>$2,200</dd>
            </div>
          </dl>
          <div className="home-bar" aria-hidden="true">
            <span />
            <span />
          </div>
        </article>
        <div className="home-actions">
          <Link to="/employer/1" className="home-go">
            Open the employer desk
          </Link>
          <Link to="/employee/HL-1042" className="home-go home-go-quiet">
            Review homes as Maya
          </Link>
          <Link to="/admin" className="home-go home-go-quiet">
            Open admin
          </Link>
        </div>
      </section>
    </div>
  );
}
