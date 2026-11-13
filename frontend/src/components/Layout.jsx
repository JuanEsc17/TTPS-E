import { Navigate, Outlet } from "react-router-dom";
import LogoAdn from "./LogoAdn";

export default function Layout({ sesion }) {
    if (!sesion?.access_token) {
        return <Navigate to="/login" replace />;
    }

    const { usuario } = sesion;

    return (
        <div className="min-h-screen bg-slate-50 text-slate-800">
            <header className="border-b border-slate-200 bg-white">
                <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-4 py-3">
                    <LogoAdn />
                    <div className="flex items-center gap-3 text-sm">
                        <span className="rounded-full bg-sky-100 px-2.5 py-0.5 text-xs font-medium text-sky-800">
                            {usuario?.rol}
                        </span>
                        <span className="font-medium text-slate-700">
                            {usuario?.nombre} {usuario?.apellido}
                        </span>
                    </div>
                </div>
            </header>

            <main className="mx-auto max-w-5xl px-4 py-6">
                <Outlet />
            </main>
        </div>
    );
}