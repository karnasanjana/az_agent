'use client'

import { useState, useCallback } from 'react'
import type { ClarificationQuestion } from '@/types/chat'

// --- Single question component (no auto-send) ---

interface QuestionCardProps {
  question: ClarificationQuestion
  onAnswer: (questionId: string, answer: string) => void
  disabled?: boolean
}

function QuestionCard({ question, onAnswer, disabled = false }: QuestionCardProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [customText, setCustomText] = useState('')

  const isAnswered = selectedId !== null

  const handleOptionClick = (optionId: string, label: string) => {
    if (isAnswered || disabled) return
    setSelectedId(optionId)
    onAnswer(question.id, label)
  }

  const handleCustomSubmit = () => {
    if (!customText.trim() || isAnswered || disabled) return
    setSelectedId('custom')
    onAnswer(question.id, customText.trim())
  }

  return (
    <div className="mt-2">
      <p className="text-xs font-medium text-gray-700 mb-1.5">{question.text}</p>

      {/* Option buttons */}
      <div className="flex flex-wrap gap-1.5">
        {question.options.map((opt) => {
          const isSelected = selectedId === opt.id
          return (
            <button
              key={opt.id}
              onClick={() => handleOptionClick(opt.id, opt.label)}
              disabled={isAnswered || disabled}
              className={`px-2.5 py-1 text-xs rounded-full border transition-all ${
                isSelected
                  ? 'bg-blue-100 border-blue-400 text-blue-800 font-medium'
                  : isAnswered
                  ? 'bg-gray-50 border-gray-200 text-gray-400 cursor-not-allowed'
                  : 'bg-white border-gray-300 text-gray-700 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 cursor-pointer'
              }`}
            >
              {opt.label}
            </button>
          )
        })}
      </div>

      {/* Custom text input */}
      {question.allow_custom_input && !isAnswered && !disabled && (
        <div className="flex gap-1.5 mt-1.5">
          <input
            type="text"
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleCustomSubmit()}
            placeholder="Type your own answer..."
            className="flex-1 px-2.5 py-1 text-xs border border-gray-300 rounded-full focus:outline-none focus:ring-1 focus:ring-blue-400 focus:border-blue-400"
          />
          <button
            onClick={handleCustomSubmit}
            disabled={!customText.trim()}
            className="px-2.5 py-1 text-xs bg-blue-600 text-white rounded-full hover:bg-blue-700 disabled:bg-gray-300 transition-colors"
          >
            Send
          </button>
        </div>
      )}

      {/* Show custom answer after submission */}
      {selectedId === 'custom' && (
        <div className="mt-1.5">
          <span className="px-2.5 py-1 text-xs rounded-full border bg-blue-100 border-blue-400 text-blue-800 font-medium inline-block">
            {customText}
          </span>
        </div>
      )}
    </div>
  )
}

// --- Container that collects all answers and submits together ---

interface ClarificationGroupProps {
  questions: ClarificationQuestion[]
  onSubmitAll: (combinedAnswer: string) => void
  disabled?: boolean
}

export default function ClarificationGroup({
  questions,
  onSubmitAll,
  disabled = false,
}: ClarificationGroupProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [submitted, setSubmitted] = useState(false)

  const totalQuestions = questions.length
  const answeredCount = Object.keys(answers).length
  const allAnswered = answeredCount === totalQuestions

  const handleAnswer = useCallback((questionId: string, answer: string) => {
    setAnswers((prev) => ({ ...prev, [questionId]: answer }))
  }, [])

  const handleSubmit = useCallback(() => {
    if (!allAnswered || submitted || disabled) return
    setSubmitted(true)

    // Combine all answers into a single message
    const parts = questions.map((q) => {
      const answer = answers[q.id]
      return `${q.text} → ${answer}`
    })
    onSubmitAll(parts.join('\n'))
  }, [allAnswered, submitted, disabled, questions, answers, onSubmitAll])

  return (
    <div className="mt-3">
      {questions.map((question) => (
        <QuestionCard
          key={question.id}
          question={question}
          onAnswer={handleAnswer}
          disabled={submitted || disabled}
        />
      ))}

      {/* Submit button - appears when all questions are answered */}
      {allAnswered && !submitted && !disabled && (
        <button
          onClick={handleSubmit}
          className="mt-3 w-full py-1.5 text-xs font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          Submit Answers
        </button>
      )}

      {/* Progress indicator */}
      {!allAnswered && !submitted && !disabled && totalQuestions > 1 && (
        <p className="mt-2 text-[10px] text-gray-400">
          {answeredCount} of {totalQuestions} answered
        </p>
      )}
    </div>
  )
}
