import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Accueil", icon: "🏠" },
  { to: "/library", label: "Bibliothèque", icon: "📚" },
  { to: "/rules", label: "Règles", icon: "🧹" },
  { to: "/pending", label: "À nettoyer", icon: "🗑️" },
  { to: "/settings", label: "Paramètres", icon: "⚙️" },
];

export default function Sidebar() {
  return (
    <aside className="w-56 shrink-0 border-r border-slate-800 bg-slate-950/60 p-4 flex flex-col gap-1">
      <div className="px-2 pb-4">
        <h1 className="text-xl font-bold bg-gradient-to-r from-brand-500 to-purple-500 bg-clip-text text-transparent">
          JellyClean
        </h1>
        <p className="text-[10px] text-slate-600 uppercase tracking-wider mt-0.5">
          v0.1 · Phase 1
        </p>
      </div>
      {links.map((l) => (
        <NavLink
          key={l.to}
          to={l.to}
          end={l.to === "/"}
          className={({ isActive }) =>
            `flex items-center gap-2 px-3 py-2 rounded-md text-sm transition ${
              isActive
                ? "bg-slate-800/80 text-white"
                : "text-slate-400 hover:bg-slate-800/40 hover:text-slate-200"
            }`
          }
        >
          <span>{l.icon}</span>
          <span>{l.label}</span>
        </NavLink>
      ))}
    </aside>
  );
}
