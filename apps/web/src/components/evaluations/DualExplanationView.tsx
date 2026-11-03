'use client';

import React, { useState } from 'react';
import { Zap, BookOpen, ChevronDown, ChevronUp, Sparkles } from 'lucide-react';

export function parseDualExplanation(raw?: string | null): { quick: string; detailed: string } {
  if (!raw) return { quick: '', detailed: '' };
  const clean = raw.trim();

  // Match explicit headers like "Quick Summary:" and "Detailed Breakdown:"
  const qMatch = clean.match(
    /(?:^|\n)\s*(?:\*\*)?(?:Quick (?:Summary|Explanation|Take)|Brief Summary):\s*(?:\*\*)?\s*([\s\S]*?)(?=\n\s*(?:\*\*)?(?:Detailed|Deep|Full (?:Breakdown|Analysis|Explanation))|$)/i
  );
  const dMatch = clean.match(
    /(?:^|\n)\s*(?:\*\*)?(?:Detailed|Deep|Full) (?:Breakdown|Analysis|Explanation):\s*(?:\*\*)?\s*([\s\S]*)/i
  );

  if (qMatch && dMatch && qMatch[1].trim() && dMatch[1].trim()) {
    return { quick: qMatch[1].trim(), detailed: dMatch[1].trim() };
  }

  // Derive quick summary (first 1-2 sentences) and detailed explanation
  const sentences = clean.split(/(?<=[.!?])\s+/).filter(Boolean);
  if (sentences.length > 1) {
    const quick =
      sentences[0].length < 45 && sentences.length > 2
        ? `${sentences[0]} ${sentences[1]}`
        : sentences[0];
    return { quick, detailed: clean };
  }

  return { quick: clean, detailed: clean };
}

interface DualExplanationViewProps {
  quickExplanation?: string | null;
  detailedExplanation?: string | null;
  rawText?: string | null;
  defaultExpanded?: boolean;
  className?: string;
  compact?: boolean;
}

export function DualExplanationView({
  quickExplanation,
  detailedExplanation,
  rawText,
  defaultExpanded = true,
  className = '',
  compact = false,
}: DualExplanationViewProps) {
  const [isDetailedOpen, setIsDetailedOpen] = useState(defaultExpanded);

  let quick = quickExplanation?.trim() || '';
  let detailed = detailedExplanation?.trim() || '';

  if ((!quick || !detailed) && rawText) {
    const parsed = parseDualExplanation(rawText);
    if (!quick) quick = parsed.quick;
    if (!detailed) detailed = parsed.detailed;
  }

  if (!quick && !detailed) {
    return null;
  }

  // If both are virtually identical or single short sentence, render single simple view
  const isIdentical = quick === detailed || detailed.length <= quick.length + 10;

  if (isIdentical) {
    return (
      <div className={`rounded-lg bg-[#F8FAFC] border border-[#E2E8F0] p-3 text-xs text-[#334155] leading-relaxed ${className}`}>
        <div className="flex items-center gap-1.5 font-semibold text-[#0F172A] mb-1">
          <Sparkles className="w-3.5 h-3.5 text-[#2563EB]" />
          <span>Simple Explanation</span>
        </div>
        <p className="whitespace-pre-line text-[#475569]">{quick || detailed}</p>
      </div>
    );
  }

  return (
    <div className={`space-y-2.5 ${className}`}>
      {/* 1. Quick Small Explanation */}
      {quick && (
        <div className={`rounded-lg bg-blue-50/70 border border-blue-200/80 ${compact ? 'p-2.5' : 'p-3'} text-xs text-[#1E3A8A] leading-relaxed shadow-2xs`}>
          <div className="flex items-center gap-1.5 font-bold uppercase tracking-wider text-[10px] text-blue-700 mb-1">
            <Zap className="w-3 h-3 text-blue-600 fill-blue-500" />
            <span>Quick Summary (Simple Take)</span>
          </div>
          <p className="font-medium text-blue-950 leading-normal">{quick}</p>
        </div>
      )}

      {/* 2. Deep & Detailed Explanation */}
      {detailed && (
        <div className="rounded-lg bg-slate-50 border border-slate-200 overflow-hidden shadow-2xs">
          <button
            type="button"
            onClick={() => setIsDetailedOpen(!isDetailedOpen)}
            className="w-full flex items-center justify-between p-2.5 text-left bg-slate-100/70 hover:bg-slate-100 transition-colors text-xs font-semibold text-slate-800"
          >
            <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-700">
              <BookOpen className="w-3.5 h-3.5 text-slate-600" />
              <span>In-Depth Detailed Breakdown</span>
            </div>
            <div className="flex items-center gap-1 text-[11px] font-medium text-slate-500">
              <span>{isDetailedOpen ? 'Hide Details' : 'Show Full Analysis'}</span>
              {isDetailedOpen ? (
                <ChevronUp className="w-3.5 h-3.5 text-slate-500" />
              ) : (
                <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
              )}
            </div>
          </button>

          {isDetailedOpen && (
            <div className={`p-3 text-xs text-slate-700 leading-relaxed whitespace-pre-line border-t border-slate-200 bg-white`}>
              {detailed}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
