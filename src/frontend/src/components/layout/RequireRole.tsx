import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../../lib/auth";
import type { Role } from "../../lib/types";
import { Spinner } from "../ui/Primitives";

export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Spinner label="Checking your session..." />;
  if (!user) return <Navigate to="/login" replace />;
  if (!roles.includes(user.role)) {
    return (
      <div className="max-w-md mx-auto text-center py-16">
        <p className="font-[family-name:var(--font-display)] text-xl mb-2">Not permitted</p>
        <p className="text-sm text-[var(--color-ink-soft)]">
          Your account ({user.role.toLowerCase().replace("_", " ")}) doesn't have access to this page.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
