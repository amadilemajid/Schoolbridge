import { useAuth } from '../context/AuthContext';

export type AppRole = 'super_admin' | 'director' | 'bursar' | 'teacher' | 'school_admin' | 'system_admin';

// Role hierarchy: higher index = more permissions
const ROLE_HIERARCHY: AppRole[] = [
  'teacher',
  'school_admin',
  'bursar',
  'director',
  'super_admin',
  'system_admin',
];

// Define which roles can perform which actions
const ROLE_PERMISSIONS: Record<string, AppRole[]> = {
  // Navigation routes
  'view:dashboard':      ['director', 'super_admin', 'school_admin', 'teacher', 'bursar'],
  'view:students':       ['director', 'super_admin', 'school_admin', 'teacher', 'bursar'],
  'view:attendance':     ['director', 'super_admin', 'school_admin', 'teacher'],
  'view:academics':      ['director', 'super_admin', 'school_admin', 'teacher'],
  'view:finance':        ['director', 'super_admin', 'school_admin', 'bursar'],
  'view:communications': ['director', 'super_admin', 'school_admin', 'teacher', 'bursar'],
  'view:reports':        ['director', 'super_admin', 'school_admin', 'bursar'],
  'view:settings':       ['director', 'super_admin', 'school_admin'],

  // Student actions
  'student:create':      ['director', 'super_admin', 'school_admin', 'bursar'],
  'student:edit':        ['director', 'super_admin', 'school_admin', 'bursar'],
  'student:delete':      ['director', 'super_admin'],
  'student:csv_import':  ['director', 'super_admin', 'school_admin', 'bursar'],

  // Attendance actions
  'attendance:mark':     ['teacher', 'school_admin', 'director', 'super_admin'],

  // Academics actions
  'marks:enter':         ['teacher', 'school_admin', 'director', 'super_admin'],
  'marks:approve':       ['director', 'super_admin', 'school_admin'],

  // Finance actions
  'payment:record':      ['bursar', 'director', 'super_admin', 'school_admin'],
  'payment:plan':        ['bursar', 'director', 'super_admin'],
  'payment:link':        ['bursar', 'director', 'super_admin'],
  'finance:reconcile':   ['bursar', 'director', 'super_admin'],

  // Communications actions
  'campaign:launch':     ['director', 'super_admin', 'school_admin', 'teacher', 'bursar'],
  'messaging:pause':     ['director', 'super_admin'],

  // Reports
  'reports:export':      ['director', 'super_admin', 'school_admin', 'bursar'],
  'reports:uneb':        ['director', 'super_admin', 'school_admin'],

  // Settings
  'settings:school':     ['director', 'super_admin', 'school_admin'],
  'settings:users':      ['director', 'super_admin'],
  'settings:audit':      ['director', 'super_admin'],
};

export const useRbac = () => {
  const { user } = useAuth();

  const can = (permission: string): boolean => {
    if (!user) return false;
    if (user.role === 'system_admin' || user.role === 'super_admin') return true;
    const allowed = ROLE_PERMISSIONS[permission];
    if (!allowed) return false;
    return allowed.includes(user.role);
  };

  const canAny = (...permissions: string[]): boolean =>
    permissions.some((p) => can(p));

  const canAll = (...permissions: string[]): boolean =>
    permissions.every((p) => can(p));

  const isAtLeast = (minRole: AppRole): boolean => {
    if (!user) return false;
    return (
      ROLE_HIERARCHY.indexOf(user.role as AppRole) >=
      ROLE_HIERARCHY.indexOf(minRole)
    );
  };

  const role = user?.role as AppRole | undefined;
  const isDirector = role === 'director' || role === 'super_admin' || role === 'system_admin';
  const isBursar = role === 'bursar';
  const isTeacher = role === 'teacher';
  const isAdmin = role === 'school_admin' || role === 'super_admin' || role === 'system_admin';

  return { can, canAny, canAll, isAtLeast, role, isDirector, isBursar, isTeacher, isAdmin };
};
