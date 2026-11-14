export default function LogoAdn({ compacto = false }) {
    return (
        <div className="flex items-center gap-3">
            <div
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#0B4F8A] text-white shadow-xs"
                aria-hidden="true"
            >
                <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M7 3c0 4.5 10 4.5 10 9s-10 4.5-10 9" />
                    <path d="M17 3c0 4.5-10 4.5-10 9s10 4.5 10 9" />
                    <line x1="8.5" y1="6.5" x2="15.5" y2="6.5" />
                    <line x1="8.5" y1="12" x2="15.5" y2="12" />
                    <line x1="8.5" y1="17.5" x2="15.5" y2="17.5" />
                </svg>
            </div>
            <div className="leading-tight">
                <span className="block text-sm font-bold text-slate-900">Exoma Clínico</span>
                {!compacto && (
                    <span className="block text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                        Coordinación de Laboratorio
                    </span>
                )}
            </div>
        </div>
    );
}