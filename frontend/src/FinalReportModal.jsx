const Ring = ({ label, value, color }) => {
  const radius = 26
  const circumference = 2 * Math.PI * radius
  const normalized = Math.min(Math.max(value, 0), 10)
  const progress = (normalized / 10) * circumference
  const strokeDasharray = `${progress} ${circumference - progress}`

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width="72" height="72" viewBox="0 0 72 72" className="drop-shadow">
        <circle
          cx="36"
          cy="36"
          r={radius}
          stroke="rgba(255,255,255,0.15)"
          strokeWidth="8"
          fill="none"
        />
        <circle
          cx="36"
          cy="36"
          r={radius}
          stroke={color}
          strokeWidth="8"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={strokeDasharray}
          transform="rotate(-90 36 36)"
        />
        <text
          x="36"
          y="40"
          textAnchor="middle"
          className="fill-slate-100 text-sm font-semibold"
        >
          {normalized}
        </text>
      </svg>
      <span className="text-xs uppercase tracking-[0.2em] text-slate-300">{label}</span>
    </div>
  )
}

const FinalReportModal = ({ report, metrics, onClose, onRestart, onPrint }) => {
  const verdictTone =
    report.overall_verdict === 'Strong Hire'
      ? 'bg-emerald-500/20 text-emerald-100 border-emerald-400/40'
      : report.overall_verdict === 'Hire'
        ? 'bg-indigo-500/20 text-indigo-100 border-indigo-400/40'
        : 'bg-rose-500/20 text-rose-100 border-rose-400/40'

  const rings = [
    {
      label: 'Technical',
      value: metrics.average_technical_accuracy,
      color: '#34d399',
    },
    {
      label: 'Communication',
      value: metrics.average_communication_clarity,
      color: '#60a5fa',
    },
    {
      label: 'Confidence',
      value: Math.round((metrics.average_confidence_score / 3) * 10),
      color: '#fbbf24',
    },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/90 p-6">
      <div className="relative w-full max-w-4xl rounded-[32px] border border-white/10 bg-slate-900/90 p-10 shadow-2xl backdrop-blur">
        <div className="absolute left-6 top-6 h-14 w-14 rounded-full border border-white/10 bg-white/5" />
        <div className="absolute right-6 top-6 h-10 w-10 rounded-full border border-white/10 bg-white/5" />

        <div className="flex items-start justify-between gap-6">
          <div>
            <p className="text-xs uppercase tracking-[0.4em] text-slate-400">Final Certificate</p>
            <h3 className="mt-4 text-3xl font-semibold text-white">Interview Summary</h3>
            <p className="mt-2 text-sm text-slate-300">
              Performance summary and recommended next steps.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-full border border-white/10 px-4 py-2 text-xs uppercase tracking-[0.3em] text-slate-300 hover:bg-white/10"
          >
            Close
          </button>
        </div>

        <div className="mt-8 grid gap-8 lg:grid-cols-[1.1fr_0.9fr]">
          <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Overall Verdict</p>
                <div
                  className={`mt-3 inline-flex items-center rounded-full border px-5 py-2 text-lg font-semibold ${verdictTone}`}
                >
                  {report.overall_verdict}
                </div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3 text-center">
                <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Culture Fit</p>
                <p className="mt-1 text-2xl font-semibold text-white">
                  {report.culture_fit_score || 0}/10
                </p>
              </div>
            </div>

            <div className="mt-8">
              <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Score Rings</p>
              <div className="mt-4 flex flex-wrap gap-6">
                {rings.map((ring) => (
                  <Ring key={ring.label} {...ring} />
                ))}
              </div>
            </div>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
            <p className="text-xs uppercase tracking-[0.3em] text-slate-400">Feedback</p>
            <div className="mt-4 space-y-6">
              <div>
                <h4 className="text-sm font-semibold uppercase tracking-[0.2em] text-emerald-300">
                  Strengths
                </h4>
                <ul className="mt-3 space-y-2 text-sm text-slate-200">
                  {report.key_strengths.map((item) => (
                    <li key={item} className="rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h4 className="text-sm font-semibold uppercase tracking-[0.2em] text-amber-300">
                  Critical Gaps
                </h4>
                <ul className="mt-3 space-y-2 text-sm text-slate-200">
                  {report.critical_gaps.map((item) => (
                    <li key={item} className="rounded-xl border border-white/10 bg-white/5 px-3 py-2">
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>

        <div className="mt-8 flex flex-wrap items-center justify-end gap-3">
          <button
            type="button"
            onClick={onRestart}
            className="rounded-full border border-white/10 px-5 py-2 text-sm text-slate-200 transition hover:bg-white/10"
          >
            Restart
          </button>
          <button
            type="button"
            onClick={onPrint}
            className="rounded-full bg-indigo-500 px-6 py-2 text-sm font-semibold text-white transition hover:bg-indigo-400"
          >
            Print to PDF
          </button>
        </div>
      </div>
    </div>
  )
}

export default FinalReportModal
