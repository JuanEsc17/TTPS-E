import { useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { guardarSesion, leerSesion, limpiarSesion, logoutRequest } from "./api/auth";
import Layout from "./components/Layout";
import LoginPage from "./pages/LoginPage";
import CambiarPasswordInicialPage from "./pages/CambiarPasswordInicialPage";
import VerificarDispositivoPage from "./pages/VerificarDispositivoPage";
import RegistroMedicoPage from "./pages/RegistroMedicoPage";
import PacientesMedicoPage from "./pages/PacientesMedicoPage";
import AltaPacientePage from "./pages/AltaPacientePage";
import FamiliaresPacientePage from "./pages/FamiliaresPacientePage";
import CambiarPasswordPage from "./pages/CambiarPasswordPage";
import ChatbotPage from "./pages/ChatbotPage";
import OrdenDelDiaPage from "./pages/OrdenDelDiaPage";
import PatologiasPage from "./pages/PatologiasPage";
import DatosCrudosAdminPage from "./pages/DatosCrudosAdminPage";
import BioinformaticaPage from "./pages/BioinformaticaPage";

const RUTAS_INICIO = [
  { path: "/paciente/estudios", titulo: "Mis estudios (Paciente)" },
  { path: "/medico/estudios", titulo: "Estudios médicos" },
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

  async function manejarCerrarSesion() {
    try {
      await logoutRequest(sesion?.access_token)
    } finally {
      limpiarSesion()
      setSesion(null)
    }
  }

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage sesion={sesion} onSesion={manejarSesion} />} />
        <Route path="/registro-medico" element={<RegistroMedicoPage sesion={sesion} />} />
        <Route
          path="/cambiar-password-inicial"
          element={<CambiarPasswordInicialPage sesion={sesion} onSesion={manejarSesion} />}
        />
        <Route
          path="/verificar-dispositivo"
          element={<VerificarDispositivoPage sesion={sesion} onSesion={manejarSesion} />}
        />

        <Route element={<Layout sesion={sesion} onCerrarSesion={manejarCerrarSesion} />}>
          <Route path="/medico/pacientes" element={<PacientesMedicoPage sesion={sesion} />} />
          <Route path="/medico/pacientes/nuevo" element={<AltaPacientePage sesion={sesion} />} />
          <Route path="/medico/pacientes/:pacienteId/familiares" element={<FamiliaresPacientePage sesion={sesion} />} />
          {RUTAS_INICIO.map((r) => (
            <Route key={r.path} path={r.path} element={<PanelPlaceholder titulo={r.titulo} />} />
          ))}
          <Route
            path="/cambiar-password"
            element={<CambiarPasswordPage sesion={sesion} onSesion={manejarSesion} />}
          />
          <Route
            path="/gerencia/patologias"
            element={<PatologiasPage sesion={sesion} />}
          />
          <Route
            path="/administracion/estudios"
            element={<DatosCrudosAdminPage sesion={sesion} />}
          />
          <Route
            path="/bioinformatica/cola"
            element={<BioinformaticaPage sesion={sesion} />}
          />
          <Route
            path="/chatbot"
            element={<ChatbotPage sesion={sesion} />}
          />
          <Route
            path="/transporte/orden-del-dia"
            element={<OrdenDelDiaPage sesion={sesion} />}
          />
        </Route>

        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  );
}