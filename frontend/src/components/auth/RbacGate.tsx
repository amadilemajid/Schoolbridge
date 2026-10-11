import React from 'react';
import { Navigate } from 'react-router-dom';
import { useRbac } from '../../hooks/useRbac';
import { ShieldX } from 'lucide-react';

interface RbacGateProps {
  /** Permission string, e.g. 'view:finance' or 'student:create' */
  permission?: string;
  /** Array of permissions — user needs at least one */
  anyOf?: string[];
  /** Array of permissions — user needs all */
  allOf?: string[];
  /** Where to redirect on denial. If omitted, renders inline denial UI */
  redirectTo?: string;
  children: React.ReactNode;
  /** Custom denied fallback element */
  fallback?: React.ReactNode;
}

/**
 * RbacGate — wraps any JSX subtree and shows it only when the current
 * user holds the required permission(s). Used both for page-level route
 * protection and for hiding individual buttons/sections inside pages.
 */
export const RbacGate: React.FC<RbacGateProps> = ({
  permission,
  anyOf,
  allOf,
  redirectTo,
  children,
  fallback,
}) => {
  const { can, canAny, canAll } = useRbac();

  const hasAccess = (() => {
    if (permission) return can(permission);
    if (anyOf && anyOf.length > 0) return canAny(...anyOf);
    if (allOf && allOf.length > 0) return canAll(...allOf);
    return true;
  })();

  if (hasAccess) return <>{children}</>;

  if (redirectTo) return <Navigate to={redirectTo} replace />;

  if (fallback !== undefined) return <>{fallback}</>;

  // Default inline denial block — subtle, not full-page
  return (
    <div className="flex items-center gap-2.5 p-3.5 bg-slate-800/60 border border-slate-700/60 rounded-xl text-xs text-slate-500">
      <ShieldX className="w-4 h-4 text-slate-600 shrink-0" />
      <span>You don't have permission to access this feature.</span>
    </div>
  );
};
