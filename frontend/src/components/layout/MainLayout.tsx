import React, { useState, useEffect } from 'react';
import { Outlet, Link, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { 
  School, 
  LayoutDashboard, 
  Users, 
  CreditCard, 
  GraduationCap, 
  CalendarCheck, 
  MessageSquare, 
  BarChart3, 
  Settings, 
  LogOut, 
  Menu, 
  X,
  Search,
  Globe,
  ChevronDown,
  ChevronRight,
  WifiOff,
  Activity,
} from 'lucide-react';

export const MainLayout: React.FC = () => {
  const { user, tenant, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [expandedNav, setExpandedNav] = useState<Record<string, boolean>>({ Attendance: true, Academics: true });
  const [language, setLanguage] = useState<'en' | 'lg'>('en');
  const location = useLocation();

  // Network connection state (online / offline / low-bandwidth)
  const [isOnline, setIsOnline] = useState<boolean>(typeof navigator !== 'undefined' ? navigator.onLine : true);
  const [isLowBandwidth, setIsLowBandwidth] = useState<boolean>(false);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    const navConn = (navigator as any).connection || (navigator as any).mozConnection || (navigator as any).webkitConnection;
    if (navConn) {
      const updateConn = () => {
        const slowTypes = ['slow-2g', '2g'];
        const isSlow = slowTypes.includes(navConn.effectiveType) || navConn.saveData || (navConn.rtt && navConn.rtt > 1500);
        setIsLowBandwidth(Boolean(isSlow));
      };
      updateConn();
      navConn.addEventListener('change', updateConn);
      return () => {
        window.removeEventListener('online', handleOnline);
        window.removeEventListener('offline', handleOffline);
        navConn.removeEventListener('change', updateConn);
      };
    }

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  const toggleExpand = (name: string) => {
    setExpandedNav(prev => ({ ...prev, [name]: !prev[name] }));
  };

  const isTeacher = user?.role === 'teacher';
  const isDirector = user?.role === 'director' || user?.role === 'super_admin';
  const isBursar = user?.role === 'bursar';

  const rawNavigation = [
    { name: 'Dashboard', href: '/', icon: LayoutDashboard },
    { name: 'Students', href: '/students', icon: Users },
    
    // Director Finance (Management)
    ...(isDirector ? [{
      name: 'Finance (Management)',
      href: '/finance',
      icon: CreditCard,
      subItems: [
        { name: 'Finance Dashboard', href: '/finance' },
        { name: 'Fee Structures', href: '/finance?tab=structures' },
        { name: 'Defaulters & Reminders', href: '/finance?filter=defaulter' },
        { name: 'Waiver Approvals', href: '/finance?action=waivers' },
        { name: 'MoMo Reconciliation', href: '/finance/reconciliation' },
        { name: 'End-of-Day Review', href: '/finance?action=end_of_day' },
      ]
    }] : []),

    // Bursar Finance (Operations)
    ...(isBursar ? [{
      name: 'Finance (Operations)',
      href: '/finance',
      icon: CreditCard,
      subItems: [
        { name: 'Student Fee Accounts', href: '/finance' },
        { name: 'Fee Structures', href: '/finance?tab=structures' },
        { name: 'Defaulters & Reminders', href: '/finance?filter=defaulter' },
        { name: 'Record Payment', href: '/finance?action=record_payment' },
        { name: 'Instalment Plans', href: '/finance?filter=plan' },
        { name: 'Waivers & Discounts', href: '/finance?action=waiver_request' },
        { name: 'MoMo Reconciliation', href: '/finance/reconciliation' },
        { name: 'End of Day Closing', href: '/finance?action=end_of_day' },
      ]
    }] : []),

    // Other non-teacher roles with finance permission (e.g. school admin)
    ...(!isDirector && !isBursar && !isTeacher ? [{
      name: 'Finance',
      href: '/finance',
      icon: CreditCard,
    }] : []),

    { 
      name: 'Academics', 
      href: '/academics', 
      icon: GraduationCap,
      subItems: [
        { name: 'Marks Entry', href: '/academics' },
        { name: 'Timetable', href: '/academics/timetable' },
      ]
    },
    { 
      name: 'Attendance', 
      href: '/attendance', 
      icon: CalendarCheck,
      subItems: [
        { name: 'Attendance Register', href: '/attendance' },
        { name: 'View Class Attendances', href: '/attendance/class' },
        { name: 'View Student Attendances', href: '/attendance/student' },
      ]
    },
    { name: 'Messaging', href: '/communications', icon: MessageSquare },
    { name: 'Reports', href: '/reports', icon: BarChart3 },
    { name: 'Settings', href: '/settings', icon: Settings },
  ];

  const navigation = rawNavigation;

  return (
    <div className="min-h-screen bg-slate-900 flex flex-col font-body">
      {/* Top Navbar */}
      <header className="h-16 bg-slate-800/80 backdrop-blur-md border-b border-slate-700/60 sticky top-0 z-40 px-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="lg:hidden p-2 text-slate-300 hover:text-white rounded-lg hover:bg-slate-700/50"
            aria-label="Toggle menu"
          >
            {sidebarOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>

          <Link to="/" className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-600 to-teal-500 flex items-center justify-center shadow-lg shadow-emerald-900/30">
              <School className="w-5 h-5 text-white" />
            </div>
            <span className="font-heading font-bold text-lg text-white tracking-tight hidden sm:inline">
              School<span className="text-emerald-400">Bridge</span>
            </span>
          </Link>

          {tenant && (
            <div className="ml-4 pl-4 border-l border-slate-700 flex items-center gap-2">
              <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-700 text-emerald-400 border border-slate-600">
                {tenant.name}
              </span>
            </div>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3">
          {/* Network Connection Indicator */}
          {!isOnline ? (
            <div
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-rose-500/15 border border-rose-500/30 text-rose-300 text-xs font-semibold animate-pulse"
              title="Offline mode: working with cached data"
            >
              <WifiOff className="w-3.5 h-3.5 text-rose-400" />
              <span className="hidden sm:inline">Offline Mode</span>
            </div>
          ) : isLowBandwidth ? (
            <div
              className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/15 border border-amber-500/30 text-amber-300 text-xs font-semibold"
              title="Low bandwidth connection (2G / slow network detected). Light mode active."
            >
              <Activity className="w-3.5 h-3.5 text-amber-400" />
              <span className="hidden sm:inline">Low Bandwidth</span>
            </div>
          ) : (
            <div
              className="hidden lg:flex items-center gap-1.5 px-2 py-1 text-[11px] font-medium text-slate-400"
              title="Connected to SchoolBridge cloud"
            >
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span>Online</span>
            </div>
          )}

          {/* Quick Search Shortcut */}
          <button
            className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-slate-400 text-xs hover:text-slate-200 transition-colors"
            onClick={() => {
              const event = new KeyboardEvent('keydown', { key: 'k', ctrlKey: true });
              window.dispatchEvent(event);
            }}
          >
            <Search className="w-3.5 h-3.5" />
            <span>Search or Ctrl+K</span>
          </button>

          {/* Language Switcher */}
          <button
            onClick={() => setLanguage(l => l === 'en' ? 'lg' : 'en')}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-700 text-slate-300 text-xs font-semibold hover:border-emerald-500 transition-all"
            title="Switch Language (English / Luganda)"
          >
            <Globe className="w-3.5 h-3.5 text-emerald-400" />
            <span>{language.toUpperCase()}</span>
          </button>

          {/* User Profile */}
          {user && (
            <div className="flex items-center gap-3 pl-2 border-l border-slate-700">
              <div className="hidden sm:flex flex-col text-right">
                <span className="text-xs font-semibold text-slate-200">{user.first_name} {user.last_name}</span>
                <span className="text-[10px] text-emerald-400 uppercase tracking-wider">{user.role}</span>
              </div>
              <button
                onClick={logout}
                className="p-2 text-slate-400 hover:text-rose-400 hover:bg-slate-700/50 rounded-lg transition-colors"
                title="Logout"
              >
                <LogOut className="w-5 h-5" />
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Offline Alert Banner */}
      {!isOnline && (
        <div className="bg-rose-950/80 border-b border-rose-500/30 px-4 py-2 text-center text-xs text-rose-200 flex items-center justify-center gap-2">
          <WifiOff className="w-4 h-4 text-rose-400 shrink-0" />
          <span>
            <strong>Network offline.</strong> SchoolBridge is operating in offline mode. Records will sync when connection is restored.
          </span>
        </div>
      )}

      <div className="flex flex-1 relative">
        {/* Sidebar Navigation */}
        <aside
          className={`
            fixed lg:sticky top-16 z-30 h-[calc(100vh-4rem)] w-64 bg-slate-850 border-r border-slate-700/60 transition-all duration-300 ease-in-out
            ${sidebarOpen ? 'left-0' : '-left-64 lg:left-0'}
          `}
        >
          <nav className="p-4 space-y-1 overflow-y-auto max-h-[calc(100vh-5rem)]">
            {navigation.map((item) => {
              const isPathActive = location.pathname === item.href || (item.subItems && item.subItems.some(sub => location.pathname === sub.href));
              const Icon = item.icon;
              const hasSub = !!item.subItems;
              const isExpanded = expandedNav[item.name] ?? isPathActive;

              return (
                <div key={item.name} className="space-y-1">
                  {hasSub ? (
                    <button
                      onClick={() => toggleExpand(item.name)}
                      className={`
                        w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all
                        ${isPathActive
                          ? 'bg-emerald-600/15 text-emerald-400 border border-emerald-500/20 font-semibold'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                        }
                      `}
                    >
                      <div className="flex items-center gap-3">
                        <Icon className={`w-5 h-5 ${isPathActive ? 'text-emerald-400' : 'text-slate-400'}`} />
                        <span>{item.name}</span>
                      </div>
                      {isExpanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-500" />}
                    </button>
                  ) : (
                    <Link
                      to={item.href}
                      onClick={() => setSidebarOpen(false)}
                      className={`
                        flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium transition-all
                        ${isPathActive
                          ? 'bg-emerald-600/15 text-emerald-400 border border-emerald-500/20 font-semibold'
                          : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                        }
                      `}
                    >
                      <Icon className={`w-5 h-5 ${isPathActive ? 'text-emerald-400' : 'text-slate-400'}`} />
                      <span>{item.name}</span>
                    </Link>
                  )}

                  {/* Sub Items Dropdown */}
                  {hasSub && isExpanded && (
                    <div className="pl-9 pr-2 space-y-1 border-l-2 border-slate-700/60 ml-5 my-1">
                      {item.subItems.map((sub) => {
                        const isSubActive = location.pathname === sub.href;
                        return (
                          <Link
                            key={sub.name}
                            to={sub.href}
                            onClick={() => setSidebarOpen(false)}
                            className={`
                              block py-1.5 px-3 rounded-lg text-xs font-medium transition-colors
                              ${isSubActive
                                ? 'bg-emerald-500/20 text-emerald-300 font-bold'
                                : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800'
                              }
                            `}
                          >
                            {sub.name}
                          </Link>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </nav>
        </aside>

        {/* Main Content Viewport */}
        <main className="flex-1 p-4 lg:p-8 max-w-7xl mx-auto w-full">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
