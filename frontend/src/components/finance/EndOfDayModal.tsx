import React, { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { useAuth } from '../../context/AuthContext';
import { Modal } from '../ui/Modal';
import { Button } from '../ui/Button';
import { Banknote, CreditCard, CheckCircle2, AlertTriangle, ShieldCheck, Printer } from 'lucide-react';

interface EndOfDayModalProps {
  isOpen: boolean;
  onClose: () => void;
  onRegisterClosed?: () => void;
}

interface DayTransaction {
  id: string;
  receipt_number: string;
  student_name: string;
  class_name: string;
  amount: number;
  method: string;
  time: string;
  recorded_by: string;
}

interface DaySummary {
  total_cash: number;
  total_bank: number;
  total_momo: number;
  transaction_count: number;
  date: string;
  transactions?: DayTransaction[];
}

// Generates and opens a printable official End-of-Day report in a new window
function generateAndPrintReport(summary: DaySummary, bursarName: string, schoolName: string) {
  const grandTotal = summary.total_cash + summary.total_bank + summary.total_momo;
  const reportDate = new Date().toLocaleDateString('en-UG', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  });
  const reportTime = new Date().toLocaleTimeString('en-UG', {
    hour: '2-digit', minute: '2-digit',
  });

  const txRows = (summary.transactions || []).map(tx => `
    <tr>
      <td>${tx.time}</td>
      <td><strong>${tx.receipt_number}</strong></td>
      <td>${tx.student_name} (${tx.class_name})</td>
      <td><span class="method-badge">${tx.method.toUpperCase()}</span></td>
      <td>UGX ${tx.amount.toLocaleString()}</td>
    </tr>
  `).join('');

  const html = `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>End-of-Day Reconciliation Report — ${summary.date}</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Georgia', serif;
      color: #1a1a1a;
      background: #fff;
      padding: 40px;
      max-width: 680px;
      margin: 0 auto;
    }
    .header { text-align: center; border-bottom: 3px double #1a1a1a; padding-bottom: 16px; margin-bottom: 24px; }
    .school-name { font-size: 22px; font-weight: bold; letter-spacing: 1px; text-transform: uppercase; }
    .school-sub { font-size: 12px; color: #555; margin-top: 4px; }
    .report-title { font-size: 16px; font-weight: bold; text-transform: uppercase; letter-spacing: 2px; margin-top: 12px; color: #333; }
    .report-meta { font-size: 12px; color: #666; margin-top: 4px; }
    .ref-box { background: #f4f4f4; border: 1px solid #ccc; border-radius: 4px; padding: 8px 16px; display: inline-block; margin-top: 8px; font-size: 11px; font-family: monospace; }

    .section-title {
      font-size: 11px; font-weight: bold; text-transform: uppercase;
      letter-spacing: 1.5px; color: #555; margin: 24px 0 8px;
      border-bottom: 1px solid #ddd; padding-bottom: 4px;
    }
    .summary-table { width: 100%; border-collapse: collapse; font-size: 13px; margin-bottom: 12px; }
    .summary-table td, .summary-table th { padding: 8px 10px; border-bottom: 1px solid #eee; text-align: left; }
    .summary-table td:last-child, .summary-table th:last-child { text-align: right; }
    .summary-table tr.grand-total td {
      border-top: 2px solid #1a1a1a; border-bottom: 2px solid #1a1a1a;
      font-size: 14px; font-weight: bold; background: #f9f9f9;
    }
    .method-badge { font-size: 10px; background: #eee; padding: 2px 6px; border-radius: 10px; }

    .confirmation-box {
      margin-top: 24px; padding: 14px; border: 1.5px solid #1a1a1a; border-radius: 4px;
      font-size: 12px; line-height: 1.7;
    }
    .confirmation-box strong { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }

    .signatures { display: grid; grid-template-columns: 1fr 1fr; gap: 40px; margin-top: 36px; }
    .sig-block { border-top: 1px solid #1a1a1a; padding-top: 6px; font-size: 11px; color: #555; }
    .sig-block .sig-name { font-weight: bold; color: #1a1a1a; margin-top: 2px; }
    .sig-block .sig-role { font-size: 10px; color: #888; }

    .footer { margin-top: 32px; text-align: center; font-size: 10px; color: #aaa; border-top: 1px solid #eee; padding-top: 12px; }

    @media print {
      body { padding: 20px; }
      @page { size: A4; margin: 20mm; }
    }
  </style>
</head>
<body>
  <div class="header">
    <div class="school-name">${schoolName}</div>
    <div class="school-sub">Uganda &nbsp;|&nbsp; SchoolBridge ERP</div>
    <div class="report-title">Official End-of-Day Reconciliation Report</div>
    <div class="report-meta">${reportDate} &nbsp;&bull;&nbsp; Closed at ${reportTime}</div>
    <div class="ref-box">REF: EOD-${new Date().toISOString().slice(0, 10).replace(/-/g, '')}-${Math.floor(Math.random() * 9000) + 1000}</div>
  </div>

  <div class="section-title">Daily Collections Summary</div>
  <table class="summary-table">
    <tr>
      <td>Cash Payments <span class="method-badge">CASH</span></td>
      <td>UGX ${summary.total_cash.toLocaleString()}</td>
    </tr>
    <tr>
      <td>Bank Transfers <span class="method-badge">BANK</span></td>
      <td>UGX ${summary.total_bank.toLocaleString()}</td>
    </tr>
    <tr>
      <td>MTN MoMo &amp; Airtel Money <span class="method-badge">MOMO</span></td>
      <td>UGX ${summary.total_momo.toLocaleString()}</td>
    </tr>
    <tr class="grand-total">
      <td>GRAND TOTAL COLLECTED</td>
      <td>UGX ${grandTotal.toLocaleString()}</td>
    </tr>
  </table>

  ${txRows ? `
  <div class="section-title">Itemized Transactions Today (${summary.transaction_count})</div>
  <table class="summary-table">
    <thead>
      <tr style="font-size: 11px; color: #777; border-bottom: 1px solid #ccc;">
        <th>Time</th>
        <th>Receipt #</th>
        <th>Student</th>
        <th>Method</th>
        <th>Amount</th>
      </tr>
    </thead>
    <tbody>
      ${txRows}
    </tbody>
  </table>
  ` : ''}

  <div class="section-title">Transaction Statistics</div>
  <table class="summary-table">
    <tr>
      <td>Total Receipts Issued</td>
      <td>${summary.transaction_count} receipts</td>
    </tr>
    <tr>
      <td>Cash to be banked tomorrow</td>
      <td>UGX ${summary.total_cash.toLocaleString()}</td>
    </tr>
    <tr>
      <td>Report generated by</td>
      <td>${bursarName}</td>
    </tr>
  </table>

  <div class="confirmation-box">
    <strong>Bursar Confirmation Statement</strong><br /><br />
    I, <strong>${bursarName}</strong>, hereby confirm that I have counted the physical cash in the 
    school's cash drawer and that it corresponds to the amount of 
    <strong>UGX ${summary.total_cash.toLocaleString()}</strong> as recorded in the SchoolBridge digital ledger 
    for the period ending <strong>${reportDate}</strong>.<br /><br />
    All transactions recorded in this report have been verified and the register is now officially closed.
  </div>

  <div class="signatures">
    <div class="sig-block">
      <div style="height: 36px;"></div>
      <div class="sig-name">${bursarName}</div>
      <div class="sig-role">Bursar / Finance Officer</div>
      <div class="sig-role">Date: ___________________</div>
    </div>
    <div class="sig-block">
      <div style="height: 36px;"></div>
      <div class="sig-name">_______________________</div>
      <div class="sig-role">Director / Head of School</div>
      <div class="sig-role">Date: ___________________</div>
    </div>
  </div>

  <div class="footer">
    Generated by SchoolBridge ERP &nbsp;&bull;&nbsp; ${new Date().toISOString()} &nbsp;&bull;&nbsp; 
    This is an official financial document. Retain for audit purposes.
  </div>

  <script>
    window.onload = function() {
      setTimeout(function() { window.print(); }, 400);
    };
  </script>
</body>
</html>`;

  const win = window.open('', '_blank', 'width=780,height=900');
  if (win) {
    win.document.write(html);
    win.document.close();
  } else {
    alert('Please allow pop-ups for this site to generate the report. Go to browser settings → allow pop-ups for localhost.');
  }
}

export const EndOfDayModal: React.FC<EndOfDayModalProps> = ({ isOpen, onClose, onRegisterClosed }) => {
  const { user, tenant } = useAuth();
  const [reportGenerated, setReportGenerated] = useState(false);
  const [showTxDetails, setShowTxDetails] = useState(false);
  const bursarName = user ? `${user.first_name} ${user.last_name}`.trim() || user.username : 'Bursar';
  const schoolName = tenant?.name || 'School';

  const { data: summary, isLoading } = useQuery({
    queryKey: ['end-of-day-summary'],
    queryFn: async () => {
      const res = await apiClient.get('/payments/payments/end-of-day-summary/');
      return res.data as DaySummary;
    },
    enabled: isOpen,
    refetchOnWindowFocus: false,
    staleTime: 0,
  });

  const { mutate: closeRegister, isPending } = useMutation({
    mutationFn: async () => {
      try {
        await apiClient.post('/payments/payments/close-register/');
      } catch {
        // close-register is best-effort; proceed regardless
      }
      return true;
    },
    onSuccess: () => {
      if (summary) {
        generateAndPrintReport(summary, bursarName, schoolName);
      }
      setReportGenerated(true);
      const today = new Date().toISOString().slice(0, 10);
      localStorage.setItem('schoolbridge_register_closed_date', today);
      if (onRegisterClosed) onRegisterClosed();
      setTimeout(() => {
        onClose();
        setReportGenerated(false);
      }, 2000);
    },
  });

  const grandTotal = summary ? summary.total_cash + summary.total_bank + summary.total_momo : 0;
  const txSum = (summary?.transactions || []).reduce((acc, t) => acc + t.amount, 0);
  const isReconciled = summary ? grandTotal === txSum : true;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="End of Day Reconciliation" maxWidth="lg">
      <div className="space-y-5">

        {/* Success State */}
        {reportGenerated ? (
          <div className="py-8 flex flex-col items-center gap-4 text-center">
            <div className="w-16 h-16 rounded-full bg-emerald-500/20 flex items-center justify-center">
              <CheckCircle2 className="w-8 h-8 text-emerald-400" />
            </div>
            <div>
              <p className="text-base font-bold text-white">Register Closed Successfully</p>
              <p className="text-xs text-slate-400 mt-1">
                Your report has opened in a new window. Use your browser's print dialog to save or print it.
              </p>
            </div>
          </div>
        ) : (
          <>
            {/* Verification Banner */}
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-xl flex gap-4 items-start">
              <div className="p-2 bg-emerald-500/20 rounded-lg text-emerald-400 shrink-0">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-emerald-400">Cash Drawer &amp; Ledger Reconciliation</h3>
                <p className="text-xs text-slate-400 mt-1">
                  Count physical cash in the school drawer and verify that all cash, bank, and MoMo collections match the digital ledger below.
                </p>
              </div>
            </div>

            {/* Summary Figures */}
            {isLoading ? (
              <div className="text-center py-6 text-sm text-slate-400 animate-pulse">Loading today's summary...</div>
            ) : summary ? (
              <div className="space-y-3">
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div className="p-3 bg-slate-800 rounded-xl border border-slate-700">
                    <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                      <Banknote className="w-3.5 h-3.5 text-emerald-400" /> Expected Cash in Drawer
                    </div>
                    <div className="text-base font-bold text-white">UGX {summary.total_cash.toLocaleString()}</div>
                  </div>

                  <div className="p-3 bg-slate-800 rounded-xl border border-slate-700">
                    <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                      <CreditCard className="w-3.5 h-3.5 text-indigo-400" /> Bank Transfers (Logged)
                    </div>
                    <div className="text-base font-bold text-white">UGX {summary.total_bank.toLocaleString()}</div>
                  </div>

                  <div className="p-3 bg-slate-800 rounded-xl border border-slate-700">
                    <div className="flex items-center gap-1.5 text-xs text-slate-400 mb-1">
                      <Banknote className="w-3.5 h-3.5 text-teal-400" /> MoMo Collections
                    </div>
                    <div className="text-base font-bold text-white">UGX {summary.total_momo.toLocaleString()}</div>
                  </div>
                </div>

                {/* Grand total & reconciliation audit line */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between p-3.5 bg-emerald-950/30 rounded-xl border border-emerald-500/30 gap-2">
                  <div>
                    <div className="text-xs font-semibold text-emerald-300">Grand Total Collected Today</div>
                    <div className="text-lg font-bold text-emerald-400">UGX {grandTotal.toLocaleString()}</div>
                  </div>

                  <div className="flex items-center gap-2">
                    {isReconciled ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-emerald-500/20 text-emerald-300 rounded-lg text-xs font-semibold">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> Discrepancy: UGX 0 (Fully Reconciled)
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-rose-500/20 text-rose-300 rounded-lg text-xs font-semibold">
                        <AlertTriangle className="w-3.5 h-3.5 text-rose-400" /> Discrepancy: UGX {Math.abs(grandTotal - txSum).toLocaleString()}
                      </span>
                    )}
                  </div>
                </div>

                {/* Individual Transactions Accordion / Toggle */}
                {summary.transactions && summary.transactions.length > 0 && (
                  <div className="bg-slate-900 border border-slate-700/60 rounded-xl overflow-hidden">
                    <button
                      type="button"
                      onClick={() => setShowTxDetails(v => !v)}
                      className="w-full px-4 py-2.5 bg-slate-800/60 hover:bg-slate-800 transition-colors flex items-center justify-between text-xs font-semibold text-slate-300"
                    >
                      <span>Itemized Transactions Breakdown ({summary.transactions.length} receipts)</span>
                      <span className="text-emerald-400">{showTxDetails ? 'Hide details ▲' : 'Show details ▼'}</span>
                    </button>

                    {showTxDetails && (
                      <div className="divide-y divide-slate-800 max-h-48 overflow-y-auto">
                        {summary.transactions.map((tx) => (
                          <div key={tx.id} className="px-4 py-2.5 flex items-center justify-between text-xs gap-3">
                            <div>
                              <div className="font-semibold text-slate-200">{tx.student_name} <span className="text-slate-500 text-[10px]">({tx.class_name})</span></div>
                              <div className="text-[10px] text-slate-400 font-mono">Receipt: {tx.receipt_number} &bull; {tx.time}</div>
                            </div>
                            <div className="text-right shrink-0">
                              <div className="font-bold text-white">UGX {tx.amount.toLocaleString()}</div>
                              <span className="inline-block text-[9px] uppercase px-1.5 py-0.5 rounded bg-slate-700 text-slate-300 font-semibold">{tx.method}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {summary.transaction_count === 0 && (
                  <div className="p-3 bg-slate-800/40 rounded-xl border border-slate-700/40 text-xs text-slate-400 text-center">
                    No transactions recorded today yet.
                  </div>
                )}
              </div>
            ) : null}

            {/* Confirmation Warning */}
            <div className="p-3 bg-amber-500/5 border border-amber-500/20 rounded-lg text-xs text-slate-400 flex gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <span>
                By closing the register, you confirm physical cash corresponds to the digital ledger.
                An official report will generate immediately for printing and sign-off.
              </span>
            </div>
          </>
        )}

        {/* Action Buttons */}
        {!reportGenerated && (
          <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
            <Button variant="ghost" onClick={onClose} disabled={isPending}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={() => closeRegister()}
              isLoading={isPending}
              leftIcon={<Printer className="w-4 h-4" />}
              disabled={!summary || summary.transaction_count === 0}
            >
              Close Register &amp; Generate Report
            </Button>
          </div>
        )}
      </div>
    </Modal>
  );
};
