'use client'

import { useState } from 'react'
import ConnectionForm from '@/components/connection-form'
import BigQueryForm from '@/components/bigquery-form'
import DataverseForm from '@/components/dataverse-form'
import PostgresForm from '@/components/postgres-form'
import SharePointForm from '@/components/sharepoint-form'
import GcsForm from '@/components/gcs-form'
import { StepIndicator } from '@/components/step-indicator'

type DbType = 'sqlserver' | 'postgres' | 'bigquery' | 'dataverse' | 'sharepoint' | 'gcs' | null

export default function Home() {
  // Restore the right tab after a Microsoft OAuth redirect so the form re-mounts
  // and handles the returned token.
  const [dbType, setDbType] = useState<DbType>(() => {
    if (typeof window !== 'undefined') {
      if (sessionStorage.getItem('dv_pending_env_url')) return 'dataverse'
      if (sessionStorage.getItem('sp_pending_site_url')) return 'sharepoint'
    }
    return null
  })

  // Picking a source starts a NEW connection — drop any prior extraction so the
  // Dictionary (and this flow) never show stale data from a previous session.
  const chooseSource = (t: Exclude<DbType, null>) => {
    sessionStorage.removeItem('extracted_schema')
    sessionStorage.removeItem('current_diagram_id')
    sessionStorage.removeItem('current_diagram_name')
    setDbType(t)
  }

  return (
    <main className="min-h-screen bg-gradient-surface flex flex-col relative overflow-hidden">
      {/* Abstract Glowing Orbs in the background */}
      <div className="absolute top-0 inset-x-0 h-[500px] w-full pointer-events-none overflow-hidden -z-10">
        <div className="absolute top-[-20%] left-[10%] w-[400px] h-[400px] bg-indigo-600/5 rounded-full blur-[100px] mix-blend-screen animate-pulse duration-1000"></div>
        <div className="absolute top-[20%] right-[10%] w-[300px] h-[300px] bg-indigo-400/5 rounded-full blur-[100px] mix-blend-screen animate-pulse duration-[3000ms]"></div>
      </div>

      {/* Main content — vertically centered */}
      <div className="flex-1 flex flex-col justify-center container mx-auto px-4 py-12 z-10">
        {/* Hero section */}
        <div className="text-center mb-10">
          <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight mb-4">
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-indigo-400 to-indigo-400 bg-300% animate-gradient">Connect to your Data</span>
          </h1>
          <p className="max-w-2xl mx-auto text-lg text-slate-400">
            Choose a data source to generate interactive ER diagrams and optimize your architecture
          </p>
        </div>

        <StepIndicator currentStep={1} />

        {/* Database Type Selector */}
        <div className="max-w-3xl mx-auto mb-10 w-full">
          <p className="text-sm font-semibold text-slate-500 text-center mb-6 uppercase tracking-widest">
            Select Data Source
          </p>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {/* SQL Server Card */}
            <button
              onClick={() => chooseSource('sqlserver')}
              className={`p-6 rounded-2xl text-center glass-panel w-full ${
                dbType === 'sqlserver'
                  ? 'border-indigo-500/50 bg-indigo-900/20 shadow-[0_0_20px_rgba(99,102,241,0.15)] ring-1 ring-indigo-500/30'
                  : ''
              }`}
            >
              <div className={`w-14 h-14 mx-auto mb-4 rounded-2xl flex items-center justify-center transition-colors ${
                dbType === 'sqlserver' ? 'bg-indigo-500/20 shadow-[0_0_15px_rgba(99,102,241,0.3)]' : 'bg-slate-800 border border-slate-700'
              }`}>
                <svg
                  className={`w-7 h-7 ${dbType === 'sqlserver' ? 'text-indigo-400' : 'text-slate-300'}`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01"
                  />
                </svg>
              </div>
              <span className={`block font-semibold text-base mb-1 ${dbType === 'sqlserver' ? 'text-indigo-300' : 'text-slate-200'}`}>
                SQL Server
              </span>
              <p className={`text-xs ${dbType === 'sqlserver' ? 'text-indigo-400/80' : 'text-slate-500'}`}>
                Azure SQL, MSSQL, On-prem
              </p>
            </button>

            {/* PostgreSQL Card */}
            <button onClick={() => chooseSource('postgres')} className={`p-6 rounded-2xl text-center glass-panel w-full ${dbType === 'postgres' ? 'border-blue-500/50 bg-blue-900/20 ring-1 ring-blue-500/30' : ''}`}>
              <div className={`w-14 h-14 mx-auto mb-4 rounded-2xl flex items-center justify-center ${dbType === 'postgres' ? 'bg-blue-500/20' : 'bg-slate-800 border border-slate-700'}`}>
                <svg className={`w-7 h-7 ${dbType === 'postgres' ? 'text-blue-400' : 'text-slate-300'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 7v10c0 2.2 3.6 4 8 4s8-1.8 8-4V7M4 7c0 2.2 3.6 4 8 4s8-1.8 8-4M4 7c0-2.2 3.6-4 8-4s8 1.8 8 4" />
                </svg>
              </div>
              <span className={`block font-semibold text-base mb-1 ${dbType === 'postgres' ? 'text-blue-300' : 'text-slate-200'}`}>PostgreSQL</span>
              <p className={`text-xs ${dbType === 'postgres' ? 'text-blue-400/80' : 'text-slate-500'}`}>Local, cloud, managed</p>
            </button>

            {/* BigQuery Card */}
            <button
              onClick={() => chooseSource('bigquery')}
              className={`p-6 rounded-2xl text-center glass-panel w-full ${
                dbType === 'bigquery'
                  ? 'border-blue-500/50 bg-blue-900/20 shadow-[0_0_20px_rgba(59,130,246,0.15)] ring-1 ring-blue-500/30'
                  : ''
              }`}
            >
              <div className={`w-14 h-14 mx-auto mb-4 rounded-2xl flex items-center justify-center transition-colors ${
                dbType === 'bigquery' ? 'bg-blue-500/20 shadow-[0_0_15px_rgba(59,130,246,0.3)]' : 'bg-slate-800 border border-slate-700'
              }`}>
                <svg
                  className={`w-7 h-7 ${dbType === 'bigquery' ? 'text-blue-400' : 'text-slate-300'}`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z"
                  />
                </svg>
              </div>
              <span className={`block font-semibold text-base mb-1 ${dbType === 'bigquery' ? 'text-blue-300' : 'text-slate-200'}`}>
                BigQuery
              </span>
              <p className={`text-xs ${dbType === 'bigquery' ? 'text-blue-400/80' : 'text-slate-500'}`}>
                Google Cloud Platform
              </p>
            </button>

            {/* Dataverse Card */}
            <button
              onClick={() => chooseSource('dataverse')}
              className={`p-6 rounded-2xl text-center glass-panel w-full ${
                dbType === 'dataverse'
                  ? 'border-indigo-500/50 bg-indigo-900/20 shadow-[0_0_20px_rgba(68,147,248,0.15)] ring-1 ring-indigo-500/30'
                  : ''
              }`}
            >
              <div className={`w-14 h-14 mx-auto mb-4 rounded-2xl flex items-center justify-center transition-colors ${
                dbType === 'dataverse' ? 'bg-indigo-500/20 shadow-[0_0_15px_rgba(68,147,248,0.3)]' : 'bg-slate-800 border border-slate-700'
              }`}>
                <svg
                  className={`w-7 h-7 ${dbType === 'dataverse' ? 'text-indigo-400' : 'text-slate-300'}`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"
                  />
                </svg>
              </div>
              <span className={`block font-semibold text-base mb-1 ${dbType === 'dataverse' ? 'text-indigo-300' : 'text-slate-200'}`}>
                Dataverse
              </span>
              <p className={`text-xs ${dbType === 'dataverse' ? 'text-indigo-400/80' : 'text-slate-500'}`}>
                Power Platform
              </p>
            </button>

            {/* SharePoint Card */}
            <button
              onClick={() => chooseSource('sharepoint')}
              className={`p-6 rounded-2xl text-center glass-panel w-full ${
                dbType === 'sharepoint'
                  ? 'border-teal-500/50 bg-teal-900/20 shadow-[0_0_20px_rgba(20,184,166,0.15)] ring-1 ring-teal-500/30'
                  : ''
              }`}
            >
              <div className={`w-14 h-14 mx-auto mb-4 rounded-2xl flex items-center justify-center transition-colors ${
                dbType === 'sharepoint' ? 'bg-teal-500/20 shadow-[0_0_15px_rgba(20,184,166,0.3)]' : 'bg-slate-800 border border-slate-700'
              }`}>
                <svg
                  className={`w-7 h-7 ${dbType === 'sharepoint' ? 'text-teal-400' : 'text-slate-300'}`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M3.75 9.776c.112-.017.227-.026.344-.026h15.812c.117 0 .232.009.344.026m-16.5 0a2.25 2.25 0 00-1.883 2.542l.857 6a2.25 2.25 0 002.227 1.932H19.05a2.25 2.25 0 002.227-1.932l.857-6a2.25 2.25 0 00-1.883-2.542m-16.5 0V6A2.25 2.25 0 016 3.75h3.879a1.5 1.5 0 011.06.44l2.122 2.12a1.5 1.5 0 001.06.44H18A2.25 2.25 0 0120.25 9v.776"
                  />
                </svg>
              </div>
              <span className={`block font-semibold text-base mb-1 ${dbType === 'sharepoint' ? 'text-teal-300' : 'text-slate-200'}`}>
                SharePoint
              </span>
              <p className={`text-xs ${dbType === 'sharepoint' ? 'text-teal-400/80' : 'text-slate-500'}`}>
                Lists via Microsoft Graph
              </p>
            </button>

            {/* GCS Bucket Card */}
            <button
              onClick={() => chooseSource('gcs')}
              className={`p-6 rounded-2xl text-center glass-panel w-full ${
                dbType === 'gcs'
                  ? 'border-amber-500/50 bg-amber-900/20 shadow-[0_0_20px_rgba(245,158,11,0.15)] ring-1 ring-amber-500/30'
                  : ''
              }`}
            >
              <div className={`w-14 h-14 mx-auto mb-4 rounded-2xl flex items-center justify-center transition-colors ${
                dbType === 'gcs' ? 'bg-amber-500/20 shadow-[0_0_15px_rgba(245,158,11,0.3)]' : 'bg-slate-800 border border-slate-700'
              }`}>
                <svg
                  className={`w-7 h-7 ${dbType === 'gcs' ? 'text-amber-400' : 'text-slate-300'}`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M2.25 13.5h3.86a2.25 2.25 0 012.012 1.244l.256.512a2.25 2.25 0 002.013 1.244h3.218a2.25 2.25 0 002.013-1.244l.256-.512a2.25 2.25 0 012.013-1.244h3.859m-19.5.338V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 00-2.15-1.588H6.911a2.25 2.25 0 00-2.15 1.588L2.35 13.177a2.25 2.25 0 00-.1.661z"
                  />
                </svg>
              </div>
              <span className={`block font-semibold text-base mb-1 ${dbType === 'gcs' ? 'text-amber-300' : 'text-slate-200'}`}>
                GCS Bucket
              </span>
              <p className={`text-xs ${dbType === 'gcs' ? 'text-amber-400/80' : 'text-slate-500'}`}>
                Files in Cloud Storage
              </p>
            </button>
          </div>
        </div>

        {/* Show the appropriate form */}
        <div className="w-full">
          {dbType === 'sqlserver' && <ConnectionForm />}
          {dbType === 'postgres' && <PostgresForm />}
          {dbType === 'bigquery' && <BigQueryForm />}
          {dbType === 'dataverse' && <DataverseForm />}
          {dbType === 'sharepoint' && <SharePointForm />}
          {dbType === 'gcs' && <GcsForm />}
        </div>
      </div>
    </main>
  )
}
