export default function LogoAdn() {
    return (
        <div className="flex items-center gap-2.5">
            <svg
                viewBox="0 0 32 32"
                className="h-8 w-8 text-sky-600"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                aria-hidden="true"
            >
                <path d="M9 4c0 6 14 6 14 12S9 22 9 28" />
                <path d="M23 4c0 6-14 6-14 12s14 6 14 12" />
                <line x1="11" y1="8" x2="21" y2="8" />
                <line x1="11" y1="16" x2="21" y2="16" />
                <line x1="11" y1="24" x2="21" y2="24" />
            </svg>
            <div className="leading-tight">
                <span className="block text-sm font-bold text-slate-900">Exoma Lab</span>
                <span className="block text-[11px] text-slate-500">Seguimiento Clínico</span>
            </div>
        </div>
    );
}