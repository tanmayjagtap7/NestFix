import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { api, getEmployers } from "./api";
import Home from "./pages/Home";
import Employer from "./pages/Employer";
import Employee from "./pages/Employee";
import Admin from "./pages/Admin";
import NewCompany from "./pages/NewCompany";
import OptionDetail from "./pages/OptionDetail";

function Mark() {
  return (
    <span className="nav-mark grid h-9 w-9 place-items-center rounded-xl">
      <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden="true">
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

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <circle cx="12" cy="12" r="3.4" fill="currentColor" />
      <g fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
        <path d="M12 2.6v2.1M12 19.3v2.1M2.6 12h2.1M19.3 12h2.1M5.2 5.2l1.5 1.5M17.3 17.3l1.5 1.5M18.8 5.2l-1.5 1.5M6.7 17.3l-1.5 1.5" />
      </g>
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <path fill="currentColor" d="M15.2 3.1a8.1 8.1 0 1 0 5.6 12.4A6.9 6.9 0 0 1 15.2 3.1Z" />
    </svg>
  );
}

function Menu({ label, active, items }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function onDoc(event) {
      if (ref.current && !ref.current.contains(event.target)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        className={`nav-link rounded-full px-3 py-1.5 ${active ? "is-active" : ""}`}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        {label}
      </button>
      {open && (
        <div className="nav-menu absolute right-0 z-20 mt-2 min-w-44 overflow-hidden rounded-2xl border py-1 shadow-card">
          {items.length === 0 && <p className="nav-name px-3 py-2 text-sm">None yet</p>}
          {items.map((item) => (
            <Link key={item.to} to={item.to} className="nav-item nav-name block px-3 py-2 text-sm font-medium" onClick={() => setOpen(false)}>
              {item.title}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

function Shell() {
  const location = useLocation();
  const [employers, setEmployers] = useState([]);
  const [people, setPeople] = useState([]);
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));

  function toggleTheme() {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("nestfix-theme", next ? "dark" : "light");
    setDark(next);
  }

  useEffect(() => {
    getEmployers().then(setEmployers).catch(() => setEmployers([]));
    api("/employees").then(setPeople).catch(() => setPeople([]));
  }, [location.pathname]);

  return (
    <div className="min-h-screen">
      <header className="site-nav sticky top-0 z-10 border-b">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-3.5">
          <Link to="/" className="flex items-center gap-3">
            <Mark />
            <span className="nav-word font-display text-2xl leading-none tracking-tight">NestFix</span>
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            <Menu
              label="Employer"
              active={location.pathname.startsWith("/employer")}
              items={employers.map((item) => ({
                to: `/employer/${item.id}`,
                title: item.company_name,
              }))}
            />
            <Menu
              label="Employee"
              active={location.pathname.startsWith("/employee")}
              items={people.map((item) => ({
                to: `/employee/${item.employee_id_external}`,
                title: item.full_name,
              }))}
            />
            <NavLink to="/admin" className={({ isActive }) => `nav-link rounded-full px-3 py-1.5 ${isActive ? "is-active" : ""}`}>
              Admin
            </NavLink>
            <button
              className="nav-link grid h-9 w-9 place-items-center rounded-full"
              onClick={toggleTheme}
              aria-label={dark ? "Switch to day" : "Switch to night"}
            >
              {dark ? <SunIcon /> : <MoonIcon />}
            </button>
          </nav>
        </div>
      </header>
      <main className={location.pathname === "/" ? "home-main" : "mx-auto max-w-6xl px-5 py-8"}>
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route path="/" element={<Home />} />
        <Route path="/employer" element={<Employer />} />
        <Route path="/employer/:employerId" element={<Employer />} />
        <Route path="/employee" element={<Employee />} />
        <Route path="/employee/:employeeId" element={<Employee />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/admin/new" element={<NewCompany />} />
        <Route path="/options/:optionId" element={<OptionDetail />} />
      </Route>
    </Routes>
  );
}
