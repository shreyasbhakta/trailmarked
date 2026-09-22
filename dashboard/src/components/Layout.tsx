import { NavLink, Outlet } from "react-router-dom";

const navItems = [
  { to: "/", label: "Registry" },
  { to: "/discovery", label: "Discovery" },
  { to: "/replay", label: "Replay" },
  { to: "/escalations", label: "Escalations" },
];

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-[var(--border)] bg-[var(--bg-panel)] px-6 py-3 flex items-center gap-8">
        <div className="text-[15px] font-semibold tracking-tight">Trailmarked</div>
        <nav className="flex gap-5 text-sm">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `pb-1 border-b-2 transition-colors ${
                  isActive ? "border-[var(--accent)] text-white" : "border-transparent text-[var(--text-dim)] hover:text-white"
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="flex-1 px-6 py-6">
        <Outlet />
      </main>
    </div>
  );
}
