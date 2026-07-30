'use client'

import { useState } from 'react'
import ConnectionForm from '@/components/connection-form'
import BigQueryForm from '@/components/bigquery-form'
import DataverseForm from '@/components/dataverse-form'
import PostgresForm from '@/components/postgres-form'
import { StepIndicator } from '@/components/step-indicator'

type DbType = 'sqlserver' | 'postgres' | 'bigquery' | 'dataverse' | null

export default function Home() {
  // Restore Dataverse tab after Microsoft OAuth redirect
  const [dbType, setDbType] = useState<DbType>(() => {
    if (typeof window !== 'undefined' && sessionStorage.getItem('dv_pending_env_url')) {
      return 'dataverse'
    }
    return null
  })

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
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 via-purple-400 to-indigo-400 bg-300% animate-gradient">Connect to your Data</span>
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
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* SQL Server Card */}
            <button
              onClick={() => setDbType('sqlserver')}
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
            <button onClick={() => setDbType('postgres')} className={`p-6 rounded-2xl text-center glass-panel w-full ${dbType === 'postgres' ? 'border-blue-500/50 bg-blue-900/20 ring-1 ring-blue-500/30' : ''}`}>
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
              onClick={() => setDbType('bigquery')}
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
              onClick={() => setDbType('dataverse')}
              className={`p-6 rounded-2xl text-center glass-panel w-full ${
                dbType === 'dataverse'
                  ? 'border-purple-500/50 bg-purple-900/20 shadow-[0_0_20px_rgba(168,85,247,0.15)] ring-1 ring-purple-500/30'
                  : ''
              }`}
            >
              <div className={`w-14 h-14 mx-auto mb-4 rounded-2xl flex items-center justify-center transition-colors ${
                dbType === 'dataverse' ? 'bg-purple-500/20 shadow-[0_0_15px_rgba(168,85,247,0.3)]' : 'bg-slate-800 border border-slate-700'
              }`}>
                <svg
                  className={`w-7 h-7 ${dbType === 'dataverse' ? 'text-purple-400' : 'text-slate-300'}`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                    d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"
                  />
                </svg>
              </div>
              <span className={`block font-semibold text-base mb-1 ${dbType === 'dataverse' ? 'text-purple-300' : 'text-slate-200'}`}>
                Dataverse
              </span>
              <p className={`text-xs ${dbType === 'dataverse' ? 'text-purple-400/80' : 'text-slate-500'}`}>
                Power Platform
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
        </div>

        {/* Feature cards — fill empty space when no form is shown */}
        {!dbType && (
          <div className="max-w-4xl mx-auto mt-8 w-full animate-fadeIn">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="glass-panel rounded-2xl p-6 text-center group">
                <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center group-hover:border-violet-500/50 group-hover:shadow-[0_0_15px_rgba(139,92,246,0.3)] transition-all">
                  <svg className="w-6 h-6 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6z" />
                  </svg>
                </div>
                <h3 className="text-base font-semibold text-slate-200 mb-2">Auto Schema Extraction</h3>
                <p className="text-sm text-slate-400 leading-relaxed">Extract tables, columns, and relationships automatically with high precision</p>
              </div>

              <div className="glass-panel rounded-2xl p-6 text-center group">
                <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center group-hover:border-indigo-500/50 group-hover:shadow-[0_0_15px_rgba(99,102,241,0.3)] transition-all">
                  <svg className="w-6 h-6 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
                  </svg>
                </div>
                <h3 className="text-base font-semibold text-slate-200 mb-2">Talk to your Data</h3>
                <p className="text-sm text-slate-400 leading-relaxed">Ask questions or optimize architectural schema using AI assistance</p>
              </div>

              <div className="glass-panel rounded-2xl p-6 text-center group">
                <div className="w-12 h-12 mx-auto mb-4 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center group-hover:border-emerald-500/50 group-hover:shadow-[0_0_15px_rgba(16,185,129,0.3)] transition-all">
                  <svg className="w-6 h-6 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                  </svg>
                </div>
                <h3 className="text-base font-semibold text-slate-200 mb-2">Export & Share</h3>
                <p className="text-sm text-slate-400 leading-relaxed">Save diagrams instantly or generate SQL DDL pipelines on the fly</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
