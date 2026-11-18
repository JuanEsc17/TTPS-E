import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// Centro geografico de La Plata y alrededores
const CENTRO_LA_PLATA = [-34.895, -57.955];

function crearIconoCentro({ seleccionado = false }) {
    const el = document.createElement("div");
    el.style.width = seleccionado ? "34px" : "28px";
    el.style.height = seleccionado ? "34px" : "28px";
    el.style.borderRadius = "9999px";
    el.style.backgroundColor = seleccionado ? "#0B4F8A" : "#FFFFFF";
    el.style.color = seleccionado ? "#FFFFFF" : "#0B4F8A";
    el.style.border = seleccionado ? "3px solid #FFFFFF" : "2.5px solid #0B4F8A";
    el.style.boxShadow = seleccionado
        ? "0 0 0 6px rgba(11, 79, 138, 0.22), 0 6px 14px rgba(15, 23, 42, 0.28)"
        : "0 3px 8px rgba(15, 23, 42, 0.18)";
    el.style.display = "flex";
    el.style.alignItems = "center";
    el.style.justifyContent = "center";
    el.style.fontSize = seleccionado ? "13px" : "11px";
    el.style.fontWeight = "700";
    el.style.transition = "transform 150ms ease";
    el.textContent = "C";

    const tamano = seleccionado ? 34 : 28;
    const mitad = tamano / 2;
    return L.divIcon({
        html: el.outerHTML,
        className: "",
        iconSize: [tamano, tamano],
        iconAnchor: [mitad, mitad],
        popupAnchor: [0, -mitad],
    });
}

function crearPopupCentro(centro, seleccionado) {
    const cont = document.createElement("div");
    cont.style.minWidth = "180px";

    const titulo = document.createElement("p");
    titulo.style.margin = "0";
    titulo.style.fontWeight = "700";
    titulo.style.fontSize = "12px";
    titulo.style.color = "#0f172a";
    titulo.textContent = centro.nombre;
    cont.appendChild(titulo);

    const dir = document.createElement("p");
    dir.style.margin = "3px 0 0";
    dir.style.fontSize = "11px";
    dir.style.color = "#475569";
    dir.textContent = centro.direccion;
    cont.appendChild(dir);

    const badge = document.createElement("p");
    badge.style.margin = "6px 0 0";
    badge.style.fontSize = "11px";
    badge.style.fontWeight = "600";
    badge.style.color = seleccionado ? "#047857" : "#0B4F8A";
    badge.textContent = seleccionado ? "✓ Centro seleccionado" : "Clic para seleccionar";
    cont.appendChild(badge);

    return cont;
}

export default function MapaCentrosLeaflet({
    centros,
    centroSeleccionadoId,
    onSeleccionarCentro,
}) {
    const contenedorRef = useRef(null);
    const mapaRef = useRef(null);
    const capaRef = useRef(null);
    const marcadoresRef = useRef(new Map());
    const ultimaClaveBoundsRef = useRef("");
    const onSeleccionarRef = useRef(onSeleccionarCentro);

    useEffect(() => {
        onSeleccionarRef.current = onSeleccionarCentro;
    }, [onSeleccionarCentro]);

    useEffect(() => {
        if (!contenedorRef.current || mapaRef.current) return;

        const mapa = L.map(contenedorRef.current, {
            center: CENTRO_LA_PLATA,
            zoom: 12,
            zoomControl: true,
        });

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: "&copy; OpenStreetMap",
            maxZoom: 19,
        }).addTo(mapa);

        const capa = L.layerGroup().addTo(mapa);
        mapaRef.current = mapa;
        capaRef.current = capa;

        return () => {
            mapa.remove();
            mapaRef.current = null;
            capaRef.current = null;
        };
    }, []);

    useEffect(() => {
        const mapa = mapaRef.current;
        const capa = capaRef.current;
        if (!mapa || !capa) return;

        capa.clearLayers();
        marcadoresRef.current.clear();

        const puntos = [];

        (centros || []).forEach((centro) => {
            if (typeof centro.latitud !== "number" || typeof centro.longitud !== "number") return;
            const coords = [centro.latitud, centro.longitud];
            const seleccionado = centro.id === centroSeleccionadoId;
            puntos.push(coords);

            const marcador = L.marker(coords, {
                icon: crearIconoCentro({ seleccionado }),
                zIndexOffset: seleccionado ? 1000 : 300,
            }).addTo(capa);

            marcador.bindPopup(crearPopupCentro(centro, seleccionado));
            marcador.on("click", () => {
                onSeleccionarRef.current?.(centro.id);
            });
            marcadoresRef.current.set(centro.id, marcador);
        });

        const claveBounds = JSON.stringify((centros || []).map((c) => c.id));

        if (puntos.length > 0 && ultimaClaveBoundsRef.current !== claveBounds) {
            ultimaClaveBoundsRef.current = claveBounds;
            if (puntos.length === 1) {
                mapa.setView(puntos[0], 13);
            } else {
                mapa.fitBounds(L.latLngBounds(puntos), { padding: [36, 36], maxZoom: 13 });
            }
        }
    }, [centros, centroSeleccionadoId]);

    useEffect(() => {
        const mapa = mapaRef.current;
        if (!mapa || !centroSeleccionadoId) return;
        const marcador = marcadoresRef.current.get(centroSeleccionadoId);
        if (marcador) {
            mapa.panTo(marcador.getLatLng(), { animate: true });
            marcador.openPopup();
        }
    }, [centroSeleccionadoId]);

    function handleCentrarTodos() {
        const mapa = mapaRef.current;
        if (!mapa || !centros?.length) return;
        const puntos = centros
            .filter((c) => typeof c.latitud === "number" && typeof c.longitud === "number")
            .map((c) => [c.latitud, c.longitud]);
        if (puntos.length === 1) {
            mapa.setView(puntos[0], 13, { animate: true });
        } else if (puntos.length > 1) {
            mapa.fitBounds(L.latLngBounds(puntos), { padding: [36, 36], maxZoom: 13, animate: true });
        }
    }

    return (
        <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-100">
            <div
                ref={contenedorRef}
                className="h-72 w-full sm:h-80"
                role="region"
                aria-label="Mapa interactivo de centros de extracción en La Plata y alrededores"
            />

            <button
                type="button"
                onClick={handleCentrarTodos}
                className="absolute top-3 right-3 z-[400] rounded-lg border border-slate-200/90 bg-white/95 px-2.5 py-1.5 text-[11px] font-semibold text-[#0B4F8A] shadow-xs backdrop-blur-xs transition hover:bg-[#EAF2FA]"
            >
                Ver todos los centros
            </button>

            <div className="pointer-events-none absolute bottom-3 left-3 z-[400] flex flex-wrap items-center gap-3 rounded-lg border border-white/80 bg-white/90 px-2.5 py-1.5 text-[11px] font-medium text-slate-700 shadow-xs backdrop-blur-xs">
                <span className="inline-flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-[#0B4F8A]" aria-hidden="true" />
                    Seleccionado
                </span>
                <span className="inline-flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full border-2 border-[#0B4F8A] bg-white" aria-hidden="true" />
                    Disponible
                </span>
            </div>
        </div>
    );
}
