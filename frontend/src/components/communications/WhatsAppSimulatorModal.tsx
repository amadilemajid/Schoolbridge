import React, { useState, useRef, useEffect, useCallback } from 'react';
import { apiClient } from '../../api/client';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import {
  Send,
  CheckCheck,
  Sparkles,
  RotateCcw,
  Languages,
  DollarSign,
  GraduationCap,
  CalendarCheck,
  Clock,
  Receipt,
  FileText,
  CreditCard,
  HelpCircle,
  X,
  Calendar,
  Banknote,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';

interface ChatMessage {
  id: string;
  sender: 'user' | 'bot';
  text: string;
  timestamp: string;
  status?: 'sent' | 'delivered' | 'read';
}

/** Live contact from /api/v1/messaging/simulator-contacts/ */
interface LiveContact {
  id: string;
  name: string;
  phone: string;
  student_name: string;
  class_name: string;
  balance: number;
  balance_display: string;
  is_primary: boolean;
}

/** Fallback (shown during load or if API fails) — clearly labelled as examples only */
const FALLBACK_CONTACTS: LiveContact[] = [
  { id: 'fallback-1', name: 'Loading... (demo only)', phone: '+256700000001', student_name: 'Demo Student', class_name: 'N/A', balance: 0, balance_display: 'UGX 0', is_primary: true },
];

// Today + 1 day as default for absence date
const getTomorrowStr = () => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().split('T')[0];
};

const QUICK_COMMANDS = [
  { label: 'BALANCE (1)', cmd: 'BALANCE', icon: DollarSign, color: 'hover:bg-emerald-500/20 text-emerald-400 border-emerald-500/30', isAbsent: false, isPay: false },
  { label: 'RESULTS (2)', cmd: 'RESULTS', icon: GraduationCap, color: 'hover:bg-blue-500/20 text-blue-400 border-blue-500/30', isAbsent: false, isPay: false },
  { label: 'ATTEND (3)', cmd: 'ATTEND', icon: CalendarCheck, color: 'hover:bg-teal-500/20 text-teal-400 border-teal-500/30', isAbsent: false, isPay: false },
  { label: 'TIMETABLE (5)', cmd: 'TIMETABLE', icon: Clock, color: 'hover:bg-indigo-500/20 text-indigo-400 border-indigo-500/30', isAbsent: false, isPay: false },
  { label: 'RECEIPT (4)', cmd: 'RECEIPT', icon: Receipt, color: 'hover:bg-amber-500/20 text-amber-400 border-amber-500/30', isAbsent: false, isPay: false },
  { label: 'ABSENT (7)', cmd: 'ABSENT', icon: FileText, color: 'hover:bg-rose-500/20 text-rose-400 border-rose-500/30', isAbsent: true, isPay: false },
  { label: 'PAY (8)', cmd: 'PAY', icon: Banknote, color: 'hover:bg-green-500/20 text-green-400 border-green-500/30', isAbsent: false, isPay: true },
  { label: 'PLAN (6)', cmd: 'PLAN', icon: CreditCard, color: 'hover:bg-purple-500/20 text-purple-400 border-purple-500/30', isAbsent: false, isPay: false },
  { label: 'LUGANDA', cmd: 'LUGANDA', icon: Languages, color: 'hover:bg-yellow-500/20 text-yellow-400 border-yellow-500/30', isAbsent: false, isPay: false },
  { label: 'ENGLISH', cmd: 'ENGLISH', icon: Languages, color: 'hover:bg-cyan-500/20 text-cyan-400 border-cyan-500/30', isAbsent: false, isPay: false },
  { label: 'MENU', cmd: 'MENU', icon: HelpCircle, color: 'hover:bg-slate-500/20 text-slate-300 border-slate-500/30', isAbsent: false, isPay: false },
];

/** Detects if user typed just "PAY" or shortcut "8" that needs the mini-form */
const isPayWithoutAmount = (text: string): boolean => {
  const upper = text.trim().toUpperCase();
  if (upper === '8') return true;
  if (upper.startsWith('8 ')) {
    const rest = upper.slice(2).trim();
    return !(/^\d+/.test(rest));
  }
  if (!upper.startsWith('PAY')) return false;
  const rest = upper.slice(3).trim();
  // If already has a numeric amount, pass through
  return !(/^\d+/.test(rest));
};

/** Detects if user typed just "ABSENT" or shortcut "7" that needs the mini-form */
const isAbsentWithoutDate = (text: string): boolean => {
  const upper = text.trim().toUpperCase();
  if (upper === '7') return true;
  if (upper.startsWith('7 ')) {
    const rest = upper.slice(2).trim();
    return !(/^\d{4}-\d{2}-\d{2}/.test(rest));
  }
  if (!upper.startsWith('ABSENT')) return false;
  const rest = upper.slice(6).trim();
  return !(/^\d{4}-\d{2}-\d{2}/.test(rest));
};

/** Inline ABSENT form shown above the chat input */
const AbsentForm: React.FC<{
  studentName: string;
  onSend: (cmd: string) => void;
  onCancel: () => void;
}> = ({ studentName, onSend, onCancel }) => {
  const [absDate, setAbsDate] = useState(getTomorrowStr());
  const [reason, setReason] = useState('Sick');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!absDate) return;
    const cmd = reason.trim() ? `ABSENT ${absDate} ${reason.trim()}` : `ABSENT ${absDate}`;
    onSend(cmd);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="mx-3 mb-2 bg-rose-950/40 border border-rose-500/30 rounded-xl p-3 animate-in slide-in-from-bottom-2"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-rose-300">
          <Calendar className="w-3.5 h-3.5" />
          <span>Pre-Excuse Absence — {studentName}</span>
        </div>
        <button
          type="button"
          onClick={onCancel}
          className="text-rose-400/70 hover:text-rose-300 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-2">
        <div>
          <label className="text-[10px] text-rose-300/70 block mb-1">Absence Date *</label>
          <input
            type="date"
            value={absDate}
            onChange={(e) => setAbsDate(e.target.value)}
            required
            className="w-full bg-slate-950 border border-rose-500/40 rounded-lg px-2.5 py-1.5 text-xs text-white focus:outline-none focus:border-rose-400"
          />
        </div>
        <div>
          <label className="text-[10px] text-rose-300/70 block mb-1">Reason (optional)</label>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Sick, Funeral..."
            className="w-full bg-slate-950 border border-rose-500/40 rounded-lg px-2.5 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-rose-400"
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={!absDate}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs font-semibold bg-rose-600 hover:bg-rose-500 disabled:opacity-40 text-white rounded-lg transition-colors"
        >
          <Send className="w-3 h-3" />
          Send ABSENT {absDate ? absDate : ''}{reason ? ` ${reason}` : ''}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-3 py-1.5 text-xs text-slate-400 hover:text-white transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  );
};

/** Inline PAY form shown above the chat input */
const PayForm: React.FC<{
  studentName: string;
  onSend: (cmd: string) => void;
  onCancel: () => void;
}> = ({ studentName, onSend, onCancel }) => {
  const [amount, setAmount] = useState('');
  const [studentId, setStudentId] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount) return;
    const cmd = studentId.trim() ? `PAY ${amount} ${studentId.trim()}` : `PAY ${amount}`;
    onSend(cmd);
  };

  const formatted = amount ? `UGX ${Number(amount).toLocaleString()}` : '';

  return (
    <form
      onSubmit={handleSubmit}
      className="mx-3 mb-2 bg-green-950/40 border border-green-500/30 rounded-xl p-3"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-green-300">
          <Banknote className="w-3.5 h-3.5" />
          <span>MoMo Pay Request — {studentName}</span>
        </div>
        <button type="button" onClick={onCancel} className="text-green-400/70 hover:text-green-300 transition-colors">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2 mb-2">
        <div>
          <label className="text-[10px] text-green-300/70 block mb-1">Amount (UGX) *</label>
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="e.g. 200000"
            min="1000"
            max="5000000"
            required
            className="w-full bg-slate-950 border border-green-500/40 rounded-lg px-2.5 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-green-400"
          />
          {formatted && <div className="text-[10px] text-green-400 mt-0.5">{formatted}</div>}
        </div>
        <div>
          <label className="text-[10px] text-green-300/70 block mb-1">Student name (if siblings)</label>
          <input
            type="text"
            value={studentId}
            onChange={(e) => setStudentId(e.target.value)}
            placeholder="e.g. Emmanuel"
            className="w-full bg-slate-950 border border-green-500/40 rounded-lg px-2.5 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-green-400"
          />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={!amount}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs font-semibold bg-green-700 hover:bg-green-600 disabled:opacity-40 text-white rounded-lg transition-colors"
        >
          <Send className="w-3 h-3" />
          Send PAY {amount ? formatted : ''}{studentId ? ` ${studentId}` : ''}
        </button>
        <button type="button" onClick={onCancel} className="px-3 py-1.5 text-xs text-slate-400 hover:text-white transition-colors">
          Cancel
        </button>
      </div>
    </form>
  );
};

export const WhatsAppSimulatorModal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
}> = ({ isOpen, onClose }) => {
  const [selectedPhone, setSelectedPhone] = useState('');
  const [customPhone, setCustomPhone] = useState('');
  const [inputMessage, setInputMessage] = useState('');
  const [showAbsentForm, setShowAbsentForm] = useState(false);
  const [showPayForm, setShowPayForm] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      sender: 'bot',
      text: '👋 Welcome to the SchoolBridge WhatsApp Simulator!\n\nLoading real parent contacts from the database...\nSelect a contact and click any quick command to test real-time simulated WhatsApp replies.',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    },
  ]);
  const [isSending, setIsSending] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // Live contacts state — fetched from /api/v1/messaging/simulator-contacts/
  const [contacts, setContacts] = useState<LiveContact[]>(FALLBACK_CONTACTS);
  const [contactsLoading, setContactsLoading] = useState(false);
  const [contactsError, setContactsError] = useState<string | null>(null);
  const [schoolId, setSchoolId] = useState<string | null>(null);

  const fetchContacts = useCallback(async () => {
    setContactsLoading(true);
    setContactsError(null);
    try {
      const res = await apiClient.get('/messaging/simulator-contacts/?limit=20');
      const data = res.data;
      if (data?.contacts?.length > 0) {
        setContacts(data.contacts);
        setSchoolId(data.school_id || null);
        // Auto-select the first real contact
        setSelectedPhone(data.contacts[0].phone);
      } else {
        setContactsError('No registered guardians found for this school.');
      }
    } catch (err: any) {
      const msg = err.response?.data?.detail || err.message || 'Failed to load contacts.';
      setContactsError(msg);
    } finally {
      setContactsLoading(false);
    }
  }, []);

  // Fetch contacts when modal opens
  useEffect(() => {
    if (isOpen) {
      fetchContacts();
    }
  }, [isOpen, fetchContacts]);

  const activePhone = customPhone.trim() || selectedPhone;
  const activeContact = contacts.find((c) => c.phone === activePhone);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isSending]);

  // Watch the input and auto-show forms for commands that need extra data
  useEffect(() => {
    const upper = inputMessage.trim().toUpperCase();
    if (isAbsentWithoutDate(inputMessage)) {
      setShowAbsentForm(true);
      setShowPayForm(false);
    } else if (isPayWithoutAmount(inputMessage)) {
      setShowPayForm(true);
      setShowAbsentForm(false);
    } else {
      // Hide forms when user clears back to non-matching input
      if (!upper.startsWith('ABSENT') && upper !== '7' && !upper.startsWith('7 ')) setShowAbsentForm(false);
      if (!upper.startsWith('PAY') && upper !== '8' && !upper.startsWith('8 ')) setShowPayForm(false);
    }
  }, [inputMessage]);

  const sendToAPI = async (text: string) => {
    if (!text || isSending) return;

    const userMsgId = Date.now().toString();
    const currentTime = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    setMessages((prev) => [
      ...prev,
      { id: userMsgId, sender: 'user', text, timestamp: currentTime, status: 'sent' },
    ]);
    setInputMessage('');
    setShowAbsentForm(false);
    setShowPayForm(false);
    setIsSending(true);

    try {
      const payload: Record<string, unknown> = {
        phone: activePhone,
        message: text,
      };
      // Pass school_id for strict tenant isolation when we have it from the contacts endpoint
      if (schoolId) payload.school_id = schoolId;
      const res = await apiClient.post('/messaging/simulate/', payload);

      const replyText = res.data?.reply || 'No response returned from command processor.';

      setTimeout(() => {
        setMessages((prev) => [
          ...prev.map((m) => (m.id === userMsgId ? { ...m, status: 'read' as const } : m)),
          {
            id: (Date.now() + 1).toString(),
            sender: 'bot',
            text: replyText,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ]);
        setIsSending(false);
      }, 300);
    } catch (err: any) {
      const errorMsg = err.response?.data?.error || err.message || 'Error communicating with simulator API.';
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: 'bot',
          text: `⚠️ Simulation Error: ${errorMsg}`,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        },
      ]);
      setIsSending(false);
    }
  };

  const handleSendMessage = (textToSend?: string) => {
    const text = (textToSend || inputMessage).trim();
    if (!text) return;

    // Intercept bare ABSENT — show the date/reason form
    if (isAbsentWithoutDate(text)) {
      setShowAbsentForm(true);
      setShowPayForm(false);
      return;
    }

    // Intercept bare PAY — show the amount form
    if (isPayWithoutAmount(text)) {
      setShowPayForm(true);
      setShowAbsentForm(false);
      return;
    }

    sendToAPI(text);
  };

  const handleClearChat = () => {
    setShowAbsentForm(false);
    setShowPayForm(false);
    setMessages([
      {
        id: Date.now().toString(),
        sender: 'bot',
        text: '🧹 Chat cleared. Ready for new simulated WhatsApp commands.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      },
    ]);
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="WhatsApp Inbound Command Simulator"
      description="Simulate parent WhatsApp self-service commands in real-time"
      maxWidth="2xl"
    >
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 min-h-[580px]">
        {/* Left Side: Sender Config & Quick Commands */}
        <div className="lg:col-span-5 space-y-4 flex flex-col justify-between">
          <div className="space-y-4">
            {/* Contact Selector — Live from DB */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 space-y-3">
              <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center justify-between">
                <span>Select Test Parent</span>
                <div className="flex items-center gap-1.5">
                  {contactsLoading && (
                    <RefreshCw className="w-3 h-3 text-emerald-400 animate-spin" />
                  )}
                  <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                    {contactsLoading ? 'Loading…' : 'Live DB'}
                  </span>
                  <button
                    onClick={fetchContacts}
                    disabled={contactsLoading}
                    title="Refresh contacts"
                    className="text-slate-500 hover:text-emerald-400 disabled:opacity-40 transition-colors"
                  >
                    <RefreshCw className="w-3 h-3" />
                  </button>
                </div>
              </div>

              {contactsError && (
                <div className="flex items-start gap-1.5 text-[10px] text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded-lg px-2.5 py-1.5">
                  <AlertCircle className="w-3 h-3 mt-0.5 shrink-0" />
                  <span>{contactsError}</span>
                </div>
              )}

              {contactsLoading ? (
                <div className="space-y-1.5">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="h-6 bg-slate-800/60 rounded-md animate-pulse" />
                  ))}
                </div>
              ) : (
                <select
                  value={selectedPhone}
                  onChange={(e) => {
                    setSelectedPhone(e.target.value);
                    setCustomPhone('');
                  }}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 transition-colors"
                >
                  {contacts.map((c) => (
                    <option key={c.id} value={c.phone}>
                      {c.name} — {c.phone} ({c.student_name} · {c.class_name})
                    </option>
                  ))}
                </select>
              )}

              {activeContact && !customPhone && !contactsLoading && (
                <div className="bg-slate-950/60 border border-slate-800/80 rounded-lg p-2.5 text-xs text-slate-300 space-y-1">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Parent:</span>
                    <span className="font-medium text-white">{activeContact.name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Child:</span>
                    <span className="font-medium text-emerald-400">{activeContact.student_name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Class:</span>
                    <span className="font-medium text-slate-200">{activeContact.class_name}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Balance:</span>
                    <span className={`font-semibold ${activeContact.balance > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
                      {activeContact.balance_display}
                    </span>
                  </div>
                </div>
              )}

              {/* Custom Phone Override */}
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Or enter custom phone number:</label>
                <input
                  type="text"
                  placeholder="e.g. 0772123456 or +256772123456"
                  value={customPhone}
                  onChange={(e) => setCustomPhone(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
                />
              </div>
            </div>

            {/* Quick Command Pills */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-3.5 space-y-2.5">
              <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                <span>1-Tap Command Triggers</span>
              </div>
              <div className="grid grid-cols-2 gap-1.5">
                {QUICK_COMMANDS.map((item) => {
                  const Icon = item.icon;
                  return (
                    <button
                      key={item.label}
                      onClick={() => {
                        if (item.isAbsent) {
                          setShowAbsentForm(true);
                          setShowPayForm(false);
                          setInputMessage('');
                        } else if (item.isPay) {
                          setShowPayForm(true);
                          setShowAbsentForm(false);
                          setInputMessage('');
                        } else {
                          handleSendMessage(item.cmd);
                        }
                      }}
                      disabled={isSending}
                      className={`flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg border bg-slate-950/70 transition-all text-left ${item.color} disabled:opacity-50`}
                    >
                      <Icon className="w-3.5 h-3.5 shrink-0" />
                      <span className="truncate">{item.label}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Reset Action */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-800">
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
              onClick={handleClearChat}
            >
              Clear Conversation
            </Button>
            <span className="text-[11px] text-slate-400 font-mono">From: {activePhone}</span>
          </div>
        </div>

        {/* Right Side: Simulated Phone Chat Interface */}
        <div className="lg:col-span-7 flex flex-col bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-2xl">
          {/* WhatsApp Chat Header */}
          <div className="bg-[#075E54] text-white px-4 py-3 flex items-center justify-between shadow-md">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-full bg-emerald-700 border border-emerald-400/40 flex items-center justify-center font-bold text-sm">
                SB
              </div>
              <div>
                <div className="font-semibold text-sm leading-tight flex items-center gap-1.5">
                  <span>SchoolBridge Bot</span>
                  <span className="inline-block w-2 h-2 rounded-full bg-emerald-300"></span>
                </div>
                <div className="text-[11px] text-emerald-100/80">Simulating Official Meta WABA</div>
              </div>
            </div>
            <div className="text-right text-[11px] text-emerald-100/90 font-mono">
              {activePhone}
            </div>
          </div>

          {/* Chat Messages Feed */}
          <div className="flex-1 p-4 overflow-y-auto space-y-3 bg-[radial-gradient(#1e293b_1px,transparent_1px)] [background-size:16px_16px] bg-slate-950/90 max-h-[400px] min-h-[340px]">
            {messages.map((msg) => {
              const isUser = msg.sender === 'user';
              return (
                <div
                  key={msg.id}
                  className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-xs shadow-lg ${
                      isUser
                        ? 'bg-[#005c4b] text-emerald-50 rounded-tr-none'
                        : 'bg-slate-900 text-slate-200 border border-slate-800 rounded-tl-none'
                    }`}
                  >
                    <div className="whitespace-pre-wrap leading-relaxed font-sans">{msg.text}</div>
                    <div
                      className={`flex items-center justify-end gap-1 mt-1 text-[10px] ${
                        isUser ? 'text-emerald-200/70' : 'text-slate-400'
                      }`}
                    >
                      <span>{msg.timestamp}</span>
                      {isUser && (
                        <CheckCheck className={`w-3.5 h-3.5 ${msg.status === 'read' ? 'text-sky-400' : 'text-emerald-200/60'}`} />
                      )}
                    </div>
                  </div>
                </div>
              );
            })}

            {isSending && (
              <div className="flex justify-start">
                <div className="bg-slate-900 border border-slate-800 rounded-2xl rounded-tl-none px-4 py-2.5 text-xs text-slate-400 flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full bg-emerald-400 animate-bounce"></div>
                  <div className="w-2 h-2 rounded-full bg-emerald-400 animate-bounce [animation-delay:0.2s]"></div>
                  <div className="w-2 h-2 rounded-full bg-emerald-400 animate-bounce [animation-delay:0.4s]"></div>
                  <span className="text-[11px] text-slate-400 ml-1">Processing command router...</span>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* ABSENT Mini-Form — slides up above input bar when triggered */}
          {showAbsentForm && (
            <AbsentForm
              studentName={activeContact?.student_name || 'Student'}
              onSend={(cmd) => sendToAPI(cmd)}
              onCancel={() => setShowAbsentForm(false)}
            />
          )}

          {/* PAY Mini-Form — slides up above input bar when triggered */}
          {showPayForm && (
            <PayForm
              studentName={activeContact?.student_name || 'Student'}
              onSend={(cmd) => sendToAPI(cmd)}
              onCancel={() => setShowPayForm(false)}
            />
          )}

          {/* Chat Input Bar */}
          <div className="p-3 bg-slate-900 border-t border-slate-800 flex items-center gap-2">
            <input
              type="text"
              placeholder="Type WhatsApp command (e.g. BALANCE, RESULTS, 1, 2)..."
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSendMessage();
              }}
              disabled={isSending}
              className="flex-1 bg-slate-950 border border-slate-700 rounded-xl px-3.5 py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition-colors"
            />
            <button
              onClick={() => handleSendMessage()}
              disabled={!inputMessage.trim() || isSending}
              className="p-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white transition-colors shadow-md"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
};
