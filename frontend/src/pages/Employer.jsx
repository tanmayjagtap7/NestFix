import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import StaffDesk from "../components/StaffDesk";
import { getEmployers } from "../api";

export default function Employer() {
  const { employerId } = useParams();
  const [resolved, setResolved] = useState(employerId || null);

  useEffect(() => {
    if (employerId) {
      setResolved(employerId);
      return;
    }
    getEmployers()
      .then((rows) => {
        if (rows[0]) setResolved(String(rows[0].id));
      })
      .catch(() => setResolved(null));
  }, [employerId]);

  if (!resolved) return <p className="text-sm text-ink/60">Loading the company…</p>;
  return <StaffDesk employerId={resolved} />;
}
