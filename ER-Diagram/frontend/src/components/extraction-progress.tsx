'use client'

import { useEffect, useState, useRef } from 'react'
import { getApiBaseUrl } from '@/app/actions'
import type { ExtractionProgress, DatabaseSchema } from '@/types/schema'

interface ExtractionProgressProps {
  streamId: string
  onComplete: (schema: DatabaseSchema) => void
  onError: (error: string) => void
}

export default function ExtractionProgressComponent({
  streamId,
  onComplete,
  onError,
}: ExtractionProgressProps) {
  const [progress, setProgress] = useState<ExtractionProgress | null>(null)
  const [showStillWorking, setShowStillWorking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const startTimeRef = useRef<number>(Date.now())
  const resultReceivedRef = useRef<boolean>(false)

  useEffect(() => {
    // Record start time
    startTimeRef.current = Date.now()

    // Set up "Still working..." timer (30 seconds)
    const stillWorkingTimer = setTimeout(() => {
      setShowStillWorking(true)
    }, 30000)

    // Create EventSource connection
    let eventSource: EventSource | null = null
    getApiBaseUrl().then((apiBase) => {
      const es = new EventSource(
        `${apiBase}/api/schema/stream/${streamId}`
      )
      eventSource = es

      es.addEventListener('progress', (event) => {
        try {
          const data: ExtractionProgress = JSON.parse(event.data)
          setProgress(data)
        } catch {
          console.error('Failed to parse progress event:', event.data)
        }
      })

      es.addEventListener('complete', () => {
        setProgress({
          percentage: 100,
          current_table: null,
          message: 'Extraction complete',
          status: 'complete',
        })
      })

      es.addEventListener('result', (event) => {
        try {
          const schema: DatabaseSchema = JSON.parse(event.data)
          resultReceivedRef.current = true
          clearTimeout(stillWorkingTimer)
          es.close()
          sessionStorage.setItem('extracted_schema', JSON.stringify(schema))
          onComplete(schema)
        } catch (err) {
          console.error('Failed to parse result event:', err, event.data?.substring(0, 200))
          setError('Failed to parse extraction results')
          onError('Failed to parse extraction results')
          es.close()
        }
      })

      es.addEventListener('error', (event) => {
        const messageEvent = event as MessageEvent
        if (messageEvent.data) {
          try {
            const errorData = JSON.parse(messageEvent.data)
            const errorMessage = errorData.message || 'Extraction failed'
            setError(errorMessage)
            setProgress({
              percentage: 0,
              current_table: null,
              message: errorMessage,
              status: 'error',
            })
            onError(errorMessage)
          } catch {
            setError('Extraction failed')
            onError('Extraction failed')
          }
        } else {
          setError('Connection to server lost')
          onError('Connection to server lost')
        }
        clearTimeout(stillWorkingTimer)
        es.close()
      })

      es.onerror = () => {
        if (resultReceivedRef.current) return
        setTimeout(() => {
          if (resultReceivedRef.current) return
          setError('Connection to server lost')
          onError('Connection to server lost')
          clearTimeout(stillWorkingTimer)
          es.close()
        }, 1000)
      }
    })

    // Cleanup
    return () => {
      clearTimeout(stillWorkingTimer)
      eventSource?.close()
    }
  }, [streamId, onComplete, onError])

  // Calculate display percentage
  const percentage = progress?.percentage ?? 0
  const displayMessage = progress?.current_table
    ? `Processing ${progress.current_table}...`
    : progress?.message || 'Starting extraction...'

  return (
    <div className="w-full max-w-md mx-auto p-6 bg-white rounded-lg shadow-md">
      {/* Progress bar container */}
      <div className="mb-4">
        <div className="flex justify-between text-sm text-gray-600 mb-2">
          <span>Extracting schema...</span>
          <span>{percentage}%</span>
        </div>
        <div className="w-full h-4 bg-gray-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-500 transition-all duration-300 ease-out"
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>

      {/* Status message */}
      <div className="text-center">
        {/* Normal progress */}
        {progress?.status === 'progress' && (
          <p className="text-gray-700">{displayMessage}</p>
        )}

        {/* Complete state */}
        {progress?.status === 'complete' && (
          <p className="text-green-600 font-medium">Extraction complete!</p>
        )}

        {/* Warning state */}
        {progress?.status === 'warning' && (
          <div className="p-3 bg-yellow-100 text-yellow-800 rounded-md">
            {progress.message}
          </div>
        )}

        {/* Error state */}
        {(progress?.status === 'error' || error) && (
          <div className="p-3 bg-red-100 text-red-700 rounded-md">
            {error || progress?.message || 'An error occurred'}
          </div>
        )}

        {/* Still working message after 30 seconds */}
        {showStillWorking && progress?.status === 'progress' && (
          <p className="mt-2 text-sm text-gray-500">
            Still working... Large databases may take a while.
          </p>
        )}

        {/* Initial state - no progress yet */}
        {!progress && !error && (
          <p className="text-gray-600">Connecting to server...</p>
        )}
      </div>
    </div>
  )
}
