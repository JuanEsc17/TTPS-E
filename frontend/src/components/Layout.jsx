import { useState } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import LogoAdn from "./LogoAdn";

const MENU_POR_ROL = {
    paciente: [{ to: "/paciente/estudios", label: "Mis estudios" }],
    medico: [{ to: "/medico/estudios", label: "Estudios" }],
    gerente_medico: [{ to: "/gerencia/patologias", label: "Patologías" }],
    administrativo: [{ to: "/administracion/estudios", label: "Carga de datos ACTG" }],
    bioinformatico: [{ to: "/bioinformatica/cola", label: "Estudios en análisis" }],
    transportista: [{ to: "/transporte/orden-del-dia", label: "Orden diaria" }],
    admin_general: [{ to: "/admin/dashboard", label: "Panel general" }],
};

const ETIQUETA_ROL = {
    paciente: "Paciente",
    medico: "Médico tratante",
    gerente_medico: "Gerencia médica",
    administrativo: "Personal administrativo",
    bioinformatico: "Bioinformático",
    transportista: "Transportista",
    admin_general: "Admin general",
};

function obtenerIniciales(usuario) {
    const n = usuario?.nombre?.[0] || "";
    const a = usuario?.apellido?.[0] || "";
    return (n + a).toUpperCase() || "U";
}

export default function Layout({ sesion }) {
    const [menuAbierto, setMenuAbierto] = useState(false);
    const { pathname } = useLocation();

    if (!sesion?.access_token) {
        return <Navigate to="/login" replace />;
    }

    const { usuario } = sesion;
    const itemsMenu = MENU_POR_ROL[usuario?.rol] || [];
    const itemActivo = itemsMenu.find((i) => pathname.startsWith(i.to))?.label || "Inicio";

    const contenidoSidebar = (
        <div className="flex h-full flex-col justify-between p-4">
            <div>
                <div className="mb-6 px-1">
                    <LogoAdn />
                </div>

                <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    {ETIQUETA_ROL[usuario?.rol] || usuario?.rol}
                </p>

                <nav aria-label="Navegación principal" className="space-y-1">
                    {itemsMenu.map((item) => (
                        <NavLink
                            key={item.to}
                            to={item.to}
                            onClick={() => setMenuAbierto(false)}
                            className={({ isActive }) =>
                                `block rounded-lg px-3 py-2 text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0B4F8A] ${isActive
                                    ? "bg-[#EAF2FA] font-medium text-[#0B4F8A]"
                                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                                }`
                            }
                        >
                            {item.label}
                        </NavLink>
                    ))}
                </nav>
            </div>

            <p className="px-3 text-[11px] text-slate-400">Exoma Clínico · TTPS-E</p>
        </div>
    );

    return (
        <div className="flex min-h-screen bg-[#F4F7FA] text-slate-900">
            {/* Sidebar escritorio */}
            <aside className="hidden w-64 shrink-0 border-r border-slate-200 bg-white lg:block">
                {contenidoSidebar}
            </aside>

            {/* Drawer móvil */}
            {menuAbierto && (
                <div className="fixed inset-0 z-40 flex lg:hidden" role="dialog" aria-modal="true" aria-label="Menú lateral">
                    <div className="fixed inset-0 bg-slate-900/30" onClick={() => setMenuAbierto(false)} />
                    <aside className="relative z-50 w-64 bg-white shadow-xl">{contenidoSidebar}</aside>
                </div>
            )}

            <div className="flex min-w-0 flex-1 flex-col">
                <header className="border-b border-slate-200 bg-white">
                    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
                        <div className="flex items-center gap-3">
                            <button
                                type="button"
                                onClick={() => setMenuAbierto(true)}
                                aria-label="Abrir menú de navegación"
                                aria-expanded={menuAbierto}
                                className="rounded-lg border border-slate-200 p-2 text-slate-600 hover:bg-slate-50 lg:hidden"
                            >
                                <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M4 6h16M4 12h16M4 18h16" />
                                </svg>
                            </button>
                            <nav aria-label="Ruta actual" className="flex items-center gap-2 text-xs text-slate-500">
                                <span>Exoma clínico</span>
                                <span aria-hidden="true">→</span>
                                <span className="font-medium text-slate-700">{itemActivo}</span>
                            </nav>
                        </div>

                        <div className="hidden items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50/70 px-3 py-1 text-xs text-slate-600 md:flex">
                            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
                            Circuito clínico protegido
                        </div>

                        <div className="flex items-center gap-3">
                            <div className="text-right leading-tight">
                                <span className="block text-xs font-semibold text-slate-800">
                                    {usuario?.nombre} {usuario?.apellido}
                                </span>
                                <span className="block text-[11px] text-slate-500">
                                    {ETIQUETA_ROL[usuario?.rol] || usuario?.rol}
                                </span>
                            </div>
                            <div
                                className="flex h-9 w-9 items-center justify-center rounded-full bg-[#EAF2FA] text-xs font-semibold text-[#0B4F8A]"
                                aria-hidden="true"
                            >
                                {obtenerIniciales(usuario)}
                            </div>
                        </div>
                    </div>
                </header>

                <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-8">
                    <Outlet />
                </main>
            </div>
        </div>
    );
}