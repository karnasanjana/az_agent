'use client'

const steps = ['Connect', 'Extract', 'View Diagram'] as const

interface StepIndicatorProps {
  currentStep: 1 | 2 | 3
}

export function StepIndicator({ currentStep }: StepIndicatorProps) {
  return (
    <nav className="flex items-center justify-center gap-2 py-3">
      {steps.map((label, index) => {
        const stepNumber = index + 1
        const isCompleted = stepNumber < currentStep
        const isActive = stepNumber === currentStep
        const isFuture = stepNumber > currentStep

        return (
          <div key={label} className="flex items-center gap-2">
            {/* Connecting line before step (not before first) */}
            {index > 0 && (
              <div
                className={`w-8 h-0.5 transition-colors ${
                  isCompleted || isActive ? 'bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.5)]' : 'bg-slate-700'
                }`}
              />
            )}

            {/* Step circle + label */}
            <div className="flex items-center gap-1.5">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold transition-all ${
                  isCompleted
                    ? 'bg-indigo-900/50 text-indigo-400 border py-1.5 border-indigo-500/30'
                    : isActive
                      ? 'bg-gradient-to-tr from-indigo-500 to-purple-500 text-white shadow-[0_0_15px_rgba(99,102,241,0.5)]'
                      : 'bg-slate-800 text-slate-500 border border-slate-700'
                }`}
              >
                {isCompleted ? (
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                ) : (
                  stepNumber
                )}
              </div>
              <span
                className={`text-sm tracking-wide ${
                  isCompleted
                    ? 'text-indigo-400'
                    : isActive
                      ? 'text-indigo-300 font-semibold'
                      : isFuture
                        ? 'text-slate-500'
                        : ''
                }`}
              >
                {label}
              </span>
            </div>
          </div>
        )
      })}
    </nav>
  )
}
