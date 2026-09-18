import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AuthProvider } from "./lib/auth";
import { LangProvider } from "./lib/i18n";
import { Shell } from "./components/layout/Shell";
import { RequireRole } from "./components/layout/RequireRole";

import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { ComplaintDetailPage } from "./pages/ComplaintDetailPage";
import { ReportForm } from "./pages/citizen/ReportForm";
import { MyComplaints } from "./pages/citizen/MyComplaints";
import { OfficerQueue } from "./pages/officer/OfficerQueue";
import { FieldTasks } from "./pages/field/FieldTasks";
import { PublicDashboard } from "./pages/public/PublicDashboard";
import { JurisdictionAdmin } from "./pages/admin/JurisdictionAdmin";
import { DemoConsole } from "./pages/admin/DemoConsole";

export default function App() {
  return (
    <AuthProvider>
      <LangProvider>
        <BrowserRouter>
          <Shell>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<Login />} />
              <Route path="/public" element={<PublicDashboard />} />

              <Route
                path="/citizen/report"
                element={
                  <RequireRole roles={["CITIZEN"]}>
                    <ReportForm />
                  </RequireRole>
                }
              />
              <Route
                path="/citizen/complaints"
                element={
                  <RequireRole roles={["CITIZEN"]}>
                    <MyComplaints />
                  </RequireRole>
                }
              />
              <Route
                path="/citizen/complaints/:id"
                element={
                  <RequireRole roles={["CITIZEN"]}>
                    <ComplaintDetailPage />
                  </RequireRole>
                }
              />

              <Route
                path="/officer/queue"
                element={
                  <RequireRole roles={["OFFICER", "ADMIN"]}>
                    <OfficerQueue />
                  </RequireRole>
                }
              />
              <Route
                path="/officer/complaints/:id"
                element={
                  <RequireRole roles={["OFFICER", "ADMIN", "FIELD_WORKER"]}>
                    <ComplaintDetailPage />
                  </RequireRole>
                }
              />

              <Route
                path="/field/tasks"
                element={
                  <RequireRole roles={["FIELD_WORKER", "ADMIN"]}>
                    <FieldTasks />
                  </RequireRole>
                }
              />

              <Route
                path="/admin/jurisdictions"
                element={
                  <RequireRole roles={["ADMIN"]}>
                    <JurisdictionAdmin />
                  </RequireRole>
                }
              />
              <Route
                path="/admin/demo"
                element={
                  <RequireRole roles={["ADMIN", "OFFICER"]}>
                    <DemoConsole />
                  </RequireRole>
                }
              />

              <Route path="*" element={<Landing />} />
            </Routes>
          </Shell>
        </BrowserRouter>
      </LangProvider>
    </AuthProvider>
  );
}
