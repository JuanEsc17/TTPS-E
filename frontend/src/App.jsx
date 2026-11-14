import { useState } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { guardarSesion, leerSesion } from "./api/auth";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";

const RUTAS_INICIO = [
  { path: "/paciente/estudios", titulo: "Mis estudios (Paciente)" },
  { path: "/medico/estudios", titulo: "Estudios médicos" },
  { path: "/gerencia/patologias", titulo: "Gestión de patologías" },
  { path: "/administracion/estudios", titulo: "Panel administrativo" },
  { path: "/bioinformatica/cola", titulo: "Cola de bioinformática" },
  { path: "/transporte/orden-del-dia", titulo: "Orden del día" },
  { path: "/admin/dashboard", titulo: "Administración general" },
];

function PanelPlaceholder({ titulo }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6">
      <h1 className="text-lg font-semibold text-slate-900">{titulo}</h1>
      <p className="mt-1 text-sm text-slate-600">
        Sesión iniciada correctamente desde un dispositivo conocido.
      </p>
    </div>
  );
}

function FlujoPendiente({ titulo, descripcion }) {
  const { state } = useLocation();
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-lg font-semibold text-slate-900">{titulo}</h1>
        <p className="mt-2 text-sm text-slate-600">{descripcion}</p>
        {state?.usuario?.email && (
          <p className="mt-2 text-xs text-slate-500">Cuenta: {state.usuario.email}</p>
        )}
        <Link to="/login" className="mt-4 inline-block text-sm font-medium text-sky-600 hover:underline">
          Volver al login
        </Link>
      </div>
    </div>
  );
}

export default function App() {
  const [sesion, setSesion] = useState(() => leerSesion());

  function manejarSesion(nuevaSesion) {
    guardarSesion(nuevaSesion);
    setSesion(nuevaSesion);
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage sesion={sesion} onSesion={manejarSesion} />} />
        <Route
          path="/cambiar-password-inicial"
          element={
            <FlujoPendiente
              titulo="Cambio de contraseña inicial requerido"
              descripcion="Acá va la pantalla del Escenario 20 para establecer tu contraseña definitiva."
            />
          }
        />
        <Route
          path="/verificar-dispositivo"
          element={
            <FlujoPendiente
              titulo="Verificación de máquina nueva"
              descripcion="Enviamos un código de 6 dígitos a tu correo. Acá va la pantalla del Escenario 26."
            />
          }
        />

        <Route element={<Layout sesion={sesion} />}>
          {RUTAS_INICIO.map((r) => (
            <Route key={r.path} path={r.path} element={<PanelPlaceholder titulo={r.titulo} />} />
          ))}
        </Route>

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}