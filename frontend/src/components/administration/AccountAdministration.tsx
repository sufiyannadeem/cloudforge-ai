"use client";

import { useCallback, useEffect, useState } from "react";

type User = { username: string; role: string; active: boolean; email: string | null };
type Data = {
  users: User[];
  projects: { id: string; name: string; created_by: string | null }[];
  memberships: { project_id: string; username: string; level: string }[];
  audit: { id: number; actor: string; action: string; username: string; project_id: string | null; level: string | null; created_at: string }[];
};
const endpoint = "/api/proxy/project/admin/accounts";

export default function AccountAdministration() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const response = await fetch(endpoint, { cache: "no-store" });
    if (!response.ok) throw new Error(response.status === 403 ? "Account administration access denied." : "Account administration unavailable.");
    return await response.json() as Data;
  }, []);
  useEffect(() => { load().then(setData).catch((e: Error) => setError(e.message)); }, [load]);

  async function change(form: HTMLFormElement) {
    setBusy(true); setError(""); setMessage("");
    const input = Object.fromEntries(new FormData(form));
    const csrf = document.cookie.split(";").map((part) => part.trim()).find((part) => part.startsWith("cf_csrf="))?.slice(8);
    try {
      const response = await fetch(endpoint, { method: "POST", headers: {
        "Content-Type": "application/json", "X-CSRF-Token": csrf ? decodeURIComponent(csrf) : "",
      }, body: JSON.stringify(input) });
      if (!response.ok) throw new Error(response.status === 409 ? "Change conflicts with the current account state or was already used." : response.status === 403 ? "Administrative permission denied." : "Administrative change rejected.");
      form.reset();
      setMessage("Administrative change saved.");
      setData(await load());
    } catch (e) { setError(e instanceof Error ? e.message : "Administration unavailable."); }
    finally { setBusy(false); }
  }

  const style = "rounded border border-[var(--cf-border)] bg-[var(--cf-surface)] p-2";
  return <div className="space-y-6">
    {error && <p role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {!data && !error && <p role="status">Loading accounts…</p>}
    <form aria-label="Manage account" className="flex flex-wrap gap-3" onSubmit={(event) => { event.preventDefault(); void change(event.currentTarget); }}>
      <label>Action <select name="action" className={style}><option value="create">Create user</option><option value="set-role">Change role</option><option value="set-email">Set email</option><option value="deactivate">Deactivate</option><option value="activate">Activate</option><option value="revoke">Revoke sessions</option></select></label>
      <label>Username <input required name="username" autoComplete="off" className={style}/></label>
      <label>Role <select name="role" className={style}><option value="developer">Developer</option><option value="sre">SRE</option><option value="platform-engineer">Platform Engineer</option></select></label>
      <label>Password for new user <input name="password" type="password" minLength={15} maxLength={1024} autoComplete="new-password" className={style}/></label>
      <label>Email <input name="email" type="email" className={style}/></label>
      <button disabled={busy} className={style}>Save account change</button>
    </form>
    <div className="overflow-x-auto"><table className="w-full text-left"><caption>Users</caption><thead><tr><th>Username</th><th>Email</th><th>Role</th><th>Status</th></tr></thead><tbody>{data?.users.map((user) => <tr key={user.username}><td>{user.username}</td><td>{user.email ?? "Not provided"}</td><td>{user.role}</td><td>{user.active ? "Active" : "Inactive"}</td></tr>)}</tbody></table></div>
    <form aria-label="Manage project membership" className="flex flex-wrap gap-3" onSubmit={(event) => { event.preventDefault(); void change(event.currentTarget); }}>
      <input type="hidden" name="action" value="membership"/>
      <label>Project <select required name="project_id" className={style}>{data?.projects.map((project) => <option key={project.id} value={project.id}>{project.name} · Owner {project.created_by ?? "Unverified"}</option>)}</select></label>
      <label>Member <select required name="username" className={style}>{data?.users.map((user) => <option key={user.username}>{user.username}</option>)}</select></label>
      <label>Access <select name="level" className={style}><option value="viewer">Viewer</option><option value="maintainer">Maintainer</option><option value="remove">Remove membership</option></select></label>
      <button disabled={busy || !data?.projects.length} className={style}>Save membership</button>
    </form>
    {data?.projects.length === 0 && <p>No projects available.</p>}
    <ul aria-label="Project memberships">{data?.memberships.map((member) => <li key={member.project_id + member.username}>{member.project_id} · {member.username} · {member.level}</li>)}</ul>
    <h2 className="text-lg font-semibold">Account audit history</h2>
    {data?.audit.length === 0 && <p>No administrative changes recorded.</p>}
    <ol>{data?.audit.map((entry) => <li key={entry.id}>{new Date(entry.created_at).toLocaleString()} · {entry.actor} · {entry.action} · {entry.username} {entry.project_id} {entry.level}</li>)}</ol>
  </div>;
}
