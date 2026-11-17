import { useState } from "react";
import { NavLink, Navigate, Outlet, useLocation } from "react-router-dom";
import FondoAdn from "./FondoAdn";
import LogoAdn from "./LogoAdn";

const MENU_POR_ROL = {
    paciente: [
        { to: "/paciente/estudios", label: "Mis estudios" },
        { to: "/chatbot", label: "Asistente de patologías" },
    ],
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

export default function Layout({ sesion, onCerrarSesion }) {
    const [menuAbierto, setMenuAbierto] = useState(false);
    const [cerrando, setCerrando] = useState(false);
    const { pathname } = useLocation();

    if (!sesion?.access_token) {
        return <Navigate to="/login" replace />;
    }

    async function handleCerrarSesion() {
        setCerrando(true);
        setMenuAbierto(false);
        try {
            await onCerrarSesion?.();
        } finally {
            setCerrando(false);
        }
    }

    const { usuario } = sesion;
    const itemsMenu = MENU_POR_ROL[usuario?.rol] || [];
    const itemActivo =
        pathname === "/cambiar-password"
            ? "Cambiar contraseña"
            : itemsMenu.find((i) => pathname.startsWith(i.to))?.label || "Inicio";

    const contenidoSidebar = (
        <div className="relative flex h-full flex-col justify-between overflow-hidden bg-gradient-to-b from-[#062846] via-[#093D6B] to-[#0B4F8A] p-4 text-white">
            {/* Helice decorativa sutil en la parte inferior del sidebar */}
            <svg
                aria-hidden="true"
                viewBox="0 0 120 240"
                className="pointer-events-none absolute -right-4 bottom-10 h-52 w-24 opacity-10"
                fill="none"
            >
                <path d="M25 10 C95 50, 95 90, 25 130 C-25 160, 95 200, 25 230" stroke="white" strokeWidth="5" strokeLinecap="round" />
                <path d="M95 10 C25 50, 25 90, 95 130 C145 160, 25 200, 95 230" stroke="#67E8F9" strokeWidth="5" strokeLinecap="round" />
                <line x1="35" y1="35" x2="85" y2="35" stroke="white" strokeWidth="3" />
                <line x1="35" y1="95" x2="85" y2="95" stroke="white" strokeWidth="3" />
                <line x1="35" y1="165" x2="85" y2="165" stroke="white" strokeWidth="3" />
            </svg>

            <div className="relative">
                <div className="mb-6 rounded-xl bg-white/95 p-2.5 shadow-xs">
                    <LogoAdn />
                </div>

                <p className="mb-2 px-3 text-[11px] font-semibold uppercase tracking-wider text-cyan-200/80">
                    {ETIQUETA_ROL[usuario?.rol] || usuario?.rol}
                </p>

                <nav aria-label="Navegación principal" className="space-y-1">
                    {itemsMenu.map((item) => (
                        <NavLink
                            key={item.to}
                            to={item.to}
                            onClick={() => setMenuAbierto(false)}
                            className={({ isActive }) =>
                                `flex items-center gap-2 rounded-xl px-3 py-2.5 text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300 ${isActive
                                    ? "border border-white/20 bg-white/15 font-semibold text-white shadow-xs"
                                    : "text-cyan-100/80 hover:bg-white/10 hover:text-white"
                                }`
                            }
                        >
                            <span className="h-1.5 w-1.5 rounded-full bg-cyan-300" aria-hidden="true" />
                            {item.label}
                        </NavLink>
                    ))}
                </nav>
            </div>

            <div className="relative space-y-2 border-t border-white/15 pt-3">
                <NavLink
                    to="/cambiar-password"
                    onClick={() => setMenuAbierto(false)}
                    className={({ isActive }) =>
                        `flex items-center gap-2 rounded-xl px-3 py-2 text-sm transition focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300 ${isActive
                            ? "border border-white/20 bg-white/15 font-semibold text-white shadow-xs"
                            : "text-cyan-100/80 hover:bg-white/10 hover:text-white"
                        }`
                    }
                >
                    <span className="h-1.5 w-1.5 rounded-full bg-cyan-300" aria-hidden="true" />
                    Cambiar contraseña
                </NavLink>
                <button
                    type="button"
                    onClick={handleCerrarSesion}
                    disabled={cerrando}
                    className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm font-medium text-cyan-100/85 transition hover:bg-red-500/20 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-cyan-300 disabled:opacity-50"
                >
                    <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                        <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                        <polyline points="16 17 21 12 16 7" />
                        <line x1="21" y1="12" x2="9" y2="12" />
                    </svg>
                    {cerrando ? "Cerrando sesión..." : "Cerrar sesión"}
                </button>
                <p className="px-3 text-[11px] text-cyan-200/60">Exoma Clínico · Genómica</p>
            </div>
        </div>
    );

    return (
        <div className="relative flex min-h-screen text-slate-900">
            <FondoAdn />

            {/* Sidebar escritorio */}
            <aside className="hidden w-64 shrink-0 shadow-lg shadow-[#062846]/10 lg:block">
                {contenidoSidebar}
            </aside>

            {/* Drawer móvil */}
            {menuAbierto && (
                <div className="fixed inset-0 z-40 flex lg:hidden" role="dialog" aria-modal="true" aria-label="Menú lateral">
                    <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs" onClick={() => setMenuAbierto(false)} />
                    <aside className="relative z-50 w-64 shadow-xl">{contenidoSidebar}</aside>
                </div>
            )}

            <div className="flex min-w-0 flex-1 flex-col">
                <header className="mx-auto w-full max-w-6xl px-4 pt-4 sm:px-8">
                    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/70 bg-white/70 px-4 py-2.5 shadow-xs backdrop-blur-md">
                        <div className="flex items-center gap-3">
                            <button
                                type="button"
                                onClick={() => setMenuAbierto(true)}
                                aria-label="Abrir menú de navegación"
                                aria-expanded={menuAbierto}
                                className="rounded-lg border border-slate-200/80 bg-white/80 p-2 text-slate-600 hover:bg-white lg:hidden"
                            >
                                <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M4 6h16M4 12h16M4 18h16" />
                                </svg>
                            </button>
                            <nav aria-label="Ruta actual" className="flex items-center gap-2 text-xs text-slate-500">
                                <span className="font-semibold text-[#0B4F8A]">Secuenciación de Exoma</span>
                                <span aria-hidden="true">→</span>
                                <span className="font-semibold text-slate-800">{itemActivo}</span>
                            </nav>
                        </div>

                        <div className="hidden items-center gap-1.5 rounded-full border border-cyan-200/80 bg-cyan-50/70 px-3 py-1 text-xs font-medium text-[#0B4F8A] md:flex">
                            <span className="h-1.5 w-1.5 rounded-full bg-[#0891B2]" aria-hidden="true" />
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
                                className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-[#0B4F8A] to-[#0891B2] text-xs font-semibold text-white shadow-xs"
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