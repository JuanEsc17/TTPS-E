import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

function crearIconoMarcador({ texto, fondo, borde, anillo, escala = 1 }) {
    const el = document.createElement("div");
    el.style.width = "30px";
    el.style.height = "30px";
    el.style.borderRadius = "9999px";
    el.style.backgroundColor = fondo;
    el.style.color = "#ffffff";
    el.style.border = `2.5px solid ${borde}`;
    el.style.boxShadow = anillo
        ? `0 0 0 5px ${anillo}, 0 4px 10px rgba(15, 23, 42, 0.25)`
        : "0 3px 8px rgba(15, 23, 42, 0.25)";
    el.style.display = "flex";
    el.style.alignItems = "center";
    el.style.justifyContent = "center";
    el.style.fontSize = texto.length > 2 ? "10px" : "12px";
    el.style.fontWeight = "700";
    el.style.transform = `scale(${escala})`;
    el.style.transition = "transform 150ms ease";
    el.textContent = texto;

    return L.divIcon({
        html: el.outerHTML,
        className: "",
        iconSize: [30, 30],
        iconAnchor: [15, 15],
        popupAnchor: [0, -16],
    });
}

function crearPopupDom(titulo, subtitulo, estado) {
    const cont = document.createElement("div");
    cont.style.minWidth = "170px";

    const strong = document.createElement("p");
    strong.style.margin = "0";
    strong.style.fontWeight = "700";
    strong.style.fontSize = "12px";
    strong.style.color = "#0f172a";
    strong.textContent = titulo;
    cont.appendChild(strong);

    if (subtitulo) {
        const dir = document.createElement("p");
        dir.style.margin = "2px 0 0";
        dir.style.fontSize = "11px";
        dir.style.color = "#475569";
        dir.textContent = subtitulo;
        cont.appendChild(dir);
    }

    if (estado) {
        const est = document.createElement("p");
        est.style.margin = "6px 0 0";
        est.style.fontSize = "11px";
        est.style.fontWeight = "600";
        est.style.color = "#0B4F8A";
        est.textContent = estado;
        cont.appendChild(est);
    }

    return cont;
}

export default function MapaRutaLeaflet({
    paradas,
    labCentral,
    ubicacionTransportista,
    paradaSeleccionadaId,
    onSeleccionarParada,
    modoFijarUbicacion = false,
    onFijarUbicacion,
}) {
    const contenedorRef = useRef(null);
    const mapaRef = useRef(null);
    const capaRef = useRef(null);
    const marcadoresPorIdRef = useRef(new Map());
    const ultimaClaveAjusteRef = useRef("");
    const modoFijarRef = useRef(modoFijarUbicacion);
    const onFijarRef = useRef(onFijarUbicacion);

    useEffect(() => {
        modoFijarRef.current = modoFijarUbicacion;
    }, [modoFijarUbicacion]);

    useEffect(() => {
        onFijarRef.current = onFijarUbicacion;
    }, [onFijarUbicacion]);

    useEffect(() => {
        if (!contenedorRef.current || mapaRef.current) return;

        const mapa = L.map(contenedorRef.current, {
            center: [labCentral.latitud, labCentral.longitud],
            zoom: 11,
            zoomControl: true,
        });

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: "&copy; OpenStreetMap",
            maxZoom: 19,
        }).addTo(mapa);

        mapa.on("click", (e) => {
            if (modoFijarRef.current && onFijarRef.current) {
                onFijarRef.current({
                    latitud: e.latlng.lat,
                    longitud: e.latlng.lng,
                });
            }
        });

        const capa = L.layerGroup().addTo(mapa);
        mapaRef.current = mapa;
        capaRef.current = capa;

        return () => {
            mapa.remove();
            mapaRef.current = null;
            capaRef.current = null;
        };
    }, [labCentral.latitud, labCentral.longitud]);

    useEffect(() => {
        const cont = contenedorRef.current;
        if (!cont) return;
        cont.style.cursor = modoFijarUbicacion ? "crosshair" : "";
    }, [modoFijarUbicacion]);

    useEffect(() => {
        const mapa = mapaRef.current;
        const capa = capaRef.current;
        if (!mapa || !capa) return;

        capa.clearLayers();
        marcadoresPorIdRef.current.clear();

        const paradasValidas = paradas.filter(
            (p) => Number.isFinite(Number(p.latitud)) && Number.isFinite(Number(p.longitud))
        );

        const tieneTransportista =
            ubicacionTransportista &&
            Number.isFinite(Number(ubicacionTransportista.latitud)) &&
            Number.isFinite(Number(ubicacionTransportista.longitud));

        const coordsTransportista = tieneTransportista
            ? [Number(ubicacionTransportista.latitud), Number(ubicacionTransportista.longitud)]
            : null;
        const labCoords = [labCentral.latitud, labCentral.longitud];

        // Ruta: Transportista (origen) -> Parada 1 -> ... -> Parada N -> Laboratorio Central (destino final)
        const nodosRuta = [
            ...(coordsTransportista
                ? [{ tipo: "transportista", coords: coordsTransportista, completado: true }]
                : []),
            ...paradasValidas.map((p) => ({
                tipo: "parada",
                parada: p,
                coords: [Number(p.latitud), Number(p.longitud)],
                completado: Boolean(p.retirada_en),
            })),
            {
                tipo: "lab",
                coords: labCoords,
                completado:
                    paradasValidas.length > 0 &&
                    paradasValidas.every((p) => Boolean(p.llegada_lab_central)),
            },
        ];

        for (let i = 0; i < nodosRuta.length - 1; i += 1) {
            const origen = nodosRuta[i];
            const destino = nodosRuta[i + 1];
            const tramoCompletado = origen.completado && destino.completado;

            L.polyline([origen.coords, destino.coords], {
                color: tramoCompletado ? "#0891B2" : "#0B4F8A",
                weight: tramoCompletado ? 4 : 3,
                opacity: tramoCompletado ? 0.9 : 0.65,
                dashArray: tramoCompletado ? undefined : "7, 7",
            }).addTo(capa);
        }

        const puntosBounds = [labCoords];

        // Marcador del Transportista (origen)
        if (coordsTransportista) {
            puntosBounds.push(coordsTransportista);
            const iconoTransp = crearIconoMarcador({
                texto: "T",
                fondo: "#D97706",
                borde: "#ffffff",
                anillo: "rgba(217, 119, 6, 0.25)",
            });
            L.marker(coordsTransportista, { icon: iconoTransp, zIndexOffset: 600 })
                .bindPopup(
                    crearPopupDom(
                        "Tu ubicación (Transportista)",
                        `${coordsTransportista[0].toFixed(4)}, ${coordsTransportista[1].toFixed(4)}`,
                        "Punto de partida del recorrido"
                    )
                )
                .addTo(capa);
        }

        // Marcadores numerados de cada parada
        for (const p of paradasValidas) {
            const coords = [Number(p.latitud), Number(p.longitud)];
            puntosBounds.push(coords);

            const entregada = Boolean(p.llegada_lab_central);
            const recogida = Boolean(p.retirada_en);
            const seleccionada = p.parada_id === paradaSeleccionadaId;

            let fondo = "#0B4F8A";
            let estadoTexto = "Pendiente de retiro";
            if (entregada) {
                fondo = "#059669";
                estadoTexto = "Entregada en Laboratorio Central";
            } else if (recogida) {
                fondo = "#0891B2";
                estadoTexto = "Retirada · En camino al Laboratorio Central";
            }

            const icono = crearIconoMarcador({
                texto: String(p.posicion),
                fondo,
                borde: "#ffffff",
                anillo: seleccionada ? "rgba(11, 79, 138, 0.35)" : "rgba(11, 79, 138, 0.14)",
                escala: seleccionada ? 1.18 : 1,
            });

            const marcador = L.marker(coords, {
                icon: icono,
                zIndexOffset: seleccionada ? 500 : 100,
            })
                .bindPopup(
                    crearPopupDom(
                        `${p.posicion}. ${p.nombre_centro || `Centro #${p.centro_id}`}`,
                        p.direccion,
                        estadoTexto
                    )
                )
                .on("click", () => {
                    onSeleccionarParada?.(p.parada_id);
                })
                .addTo(capa);

            marcadoresPorIdRef.current.set(p.parada_id, marcador);
        }

        // Marcador del Laboratorio Central (destino final)
        const iconoLab = crearIconoMarcador({
            texto: "Lab",
            fondo: "#0f172a",
            borde: "#ffffff",
            anillo: "rgba(15, 23, 42, 0.18)",
        });
        L.marker(labCoords, { icon: iconoLab })
            .bindPopup(
                crearPopupDom(
                    labCentral.nombre,
                    labCentral.direccion,
                    "Destino final de entrega de muestras"
                )
            )
            .addTo(capa);

        const claveAjuste = [
            paradasValidas.map((p) => `${p.parada_id}:${p.latitud}:${p.longitud}`).join("|"),
            coordsTransportista ? `${coordsTransportista[0]}:${coordsTransportista[1]}` : "sin-gps",
        ].join("@");
        if (claveAjuste !== ultimaClaveAjusteRef.current && puntosBounds.length > 0) {
            ultimaClaveAjusteRef.current = claveAjuste;
            if (puntosBounds.length === 1) {
                mapa.setView(puntosBounds[0], 13);
            } else {
                mapa.fitBounds(puntosBounds, { padding: [36, 36], maxZoom: 14 });
            }
        }
    }, [paradas, labCentral, ubicacionTransportista, paradaSeleccionadaId, onSeleccionarParada]);

    useEffect(() => {
        const mapa = mapaRef.current;
        if (!mapa || !paradaSeleccionadaId) return;
        const marcador = marcadoresPorIdRef.current.get(paradaSeleccionadaId);
        if (marcador) {
            mapa.panInside(marcador.getLatLng(), { padding: [40, 40] });
        }
    }, [paradaSeleccionadaId]);

    return (
        <div className="overflow-hidden rounded-xl border border-slate-200/90 bg-slate-100">
            <div
                ref={contenedorRef}
                className="relative z-0 h-80 w-full sm:h-96"
                aria-label="Mapa geográfico del recorrido de extracción"
            />
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-slate-50/90 px-3.5 py-2 text-[11px] text-slate-600">
                <div className="flex flex-wrap items-center gap-3">
                    <span className="inline-flex items-center gap-1.5">
                        <span className="h-2.5 w-2.5 rounded-full bg-amber-600" aria-hidden="true" />
                        Transportista (origen)
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                        <span className="h-2.5 w-2.5 rounded-full bg-[#0B4F8A]" aria-hidden="true" />
                        Pendiente
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                        <span className="h-2.5 w-2.5 rounded-full bg-[#0891B2]" aria-hidden="true" />
                        Retirada
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                        <span className="h-2.5 w-2.5 rounded-full bg-emerald-600" aria-hidden="true" />
                        En Lab Central
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                        <span className="h-2.5 w-2.5 rounded-full bg-slate-900" aria-hidden="true" />
                        Lab Central (destino)
                    </span>
                </div>
                <span className="text-[10px] text-slate-500">Ruta fija · Solo lectura</span>
            </div>
        </div>
    );
}
