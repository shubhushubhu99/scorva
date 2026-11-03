'use client';

import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  Scale,
  GitBranch,
  Github,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  ExternalLink,
  Bot,
  ShieldCheck,
  FileText,
  Save,
  Send,
  Lock,
  Calendar,
  Sparkles,
  RefreshCw,
  RotateCcw,
  Sliders,
  ChevronDown,
  ChevronUp,
  Info,
  Code,
  Cpu,
  Zap,
  Layers,
  HelpCircle,
  TrendingUp,
  Terminal,
  Database,
  Server,
  ShieldAlert,
  AlertTriangle,
  Bug,
  Wrench,
} from 'lucide-react';
import { api, ApiClientError } from '@/lib/api-client';
import {
  JudgeSubmissionReviewResponse,
  OllamaRepoInspectionResponse,
  SaveJudgeReviewRequest,
  SubmitJudgeReviewRequest,
} from '@/types/api';
import { DualExplanationView } from '@/components/evaluations/DualExplanationView';

export default function JudgeProjectReviewPage() {
  const params = useParams();
  const router = useRouter();
  const hackathonId = params.hackathonId as string;
  const submissionId = params.submissionId as string;

  const [reviewData, setReviewData] = useState<JudgeSubmissionReviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Form State
  const [criterionScores, setCriterionScores] = useState<
    Record<string, { score: number; notes: string }>
  >({});
  const [overallFeedback, setOverallFeedback] = useState('');
  const [decision, setDecision] = useState<string>('accepted');
  const [version, setVersion] = useState<number | undefined>(undefined);

  // UI state
  const [isSavingDraft, setIsSavingDraft] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isConfirmModalOpen, setIsConfirmModalOpen] = useState(false);
  const [isRevertModalOpen, setIsRevertModalOpen] = useState(false);
  const [revertTargetStatus, setRevertTargetStatus] = useState<'draft' | 'awaiting'>('draft');
  const [revertReason, setRevertReason] = useState('');
  const [isReverting, setIsReverting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{
    type: 'success' | 'error';
    text: string;
  } | null>(null);
  const [copiedSha, setCopiedSha] = useState(false);
  const [showParticipantPitch, setShowParticipantPitch] = useState(false);

  // Ollama Repository Inspection State
  const [inspection, setInspection] = useState<OllamaRepoInspectionResponse | null>(null);
  const [isInspecting, setIsInspecting] = useState(false);
  const [inspectionError, setInspectionError] = useState<string | null>(null);
  const [activeInspectTab, setActiveInspectTab] = useState<
    'overview' | 'innovation' | 'tech_stack' | 'complexity' | 'judge_factors' | 'highlights' | 'questions'
  >('overview');
  const [copiedQuestionIndex, setCopiedQuestionIndex] = useState<number | null>(null);
  const [inspectProgressStep, setInspectProgressStep] = useState(0);

  // Fetch cached inspection on mount
  const fetchCachedInspection = async () => {
    try {
      const res = await api.getJudgeSubmissionInspection(hackathonId, submissionId);
      if (res) {
        setInspection(res);
      }
    } catch {
      // Ignored if not yet inspected
    }
  };

  const handleRunOllamaInspection = async (forceRefresh: boolean = false) => {
    setIsInspecting(true);
    setInspectionError(null);
    setInspectProgressStep(1);

    const stepInterval = setInterval(() => {
      setInspectProgressStep((prev) => (prev < 4 ? prev + 1 : prev));
    }, 4000);

    try {
      const res = await api.inspectJudgeSubmissionRepo(hackathonId, submissionId, forceRefresh);
      setInspection(res);
      setStatusMessage({
        type: 'success',
        text: `Repository inspection completed successfully (${res.model_name})!`,
      });
      setTimeout(() => setStatusMessage(null), 5000);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setInspectionError(err.message);
      } else {
        setInspectionError('Failed to execute repository inspection. Please retry or check AI runtime status.');
      }
    } finally {
      clearInterval(stepInterval);
      setIsInspecting(false);
      setInspectProgressStep(0);
    }
  };

  const handleApplyInspectionToRubric = () => {
    if (!inspection || !reviewData) return;

    const nextScores = { ...criterionScores };
    reviewData.rubric_criteria.forEach((crit) => {
      const titleLower = crit.title.toLowerCase();
      let suggestedScore: number | null = null;
      let suggestedNotes = '';

      if (titleLower.includes('innovation') || titleLower.includes('originality') || titleLower.includes('creativ')) {
        suggestedScore = inspection.innovation.score;
        suggestedNotes = `Ollama: ${inspection.innovation.summary}`;
      } else if (titleLower.includes('complexity') || titleLower.includes('architecture') || titleLower.includes('technical')) {
        suggestedScore = inspection.complexity.score;
        suggestedNotes = `Ollama (${inspection.complexity.level}): ${inspection.complexity.architecture_depth || ''}`;
      } else if (titleLower.includes('quality') || titleLower.includes('cleanliness') || titleLower.includes('code')) {
        suggestedScore = inspection.judge_factors.code_quality_score;
        suggestedNotes = `Ollama: ${inspection.judge_factors.code_quality_summary || ''}`;
      } else if (titleLower.includes('execution') || titleLower.includes('completeness')) {
        suggestedScore = inspection.judge_factors.completeness_score;
        suggestedNotes = `Ollama: ${inspection.judge_factors.completeness_summary || ''}`;
      } else if (titleLower.includes('impact') || titleLower.includes('usability')) {
        suggestedScore = inspection.judge_factors.potential_impact_score;
        suggestedNotes = `Ollama: ${inspection.judge_factors.potential_impact_summary || ''}`;
      }

      if (suggestedScore !== null) {
        const max = Number(crit.max_score) || 10;
        const normalized = Math.min(max, Math.max(0, suggestedScore * (max / 10)));
        nextScores[crit.id] = {
          score: Math.round(normalized * 10) / 10,
          notes: suggestedNotes || nextScores[crit.id]?.notes || '',
        };
      }
    });

    setCriterionScores(nextScores);
    if (!overallFeedback) {
      const defectsSummary = inspection.codebase_defects && inspection.codebase_defects.length > 0
        ? `\n\nIdentified Codebase Defects & Negative Points:\n${inspection.codebase_defects.map(d => `- ${d}`).join('\n')}`
        : (inspection.potential_red_flags?.length ? `\n\nIdentified Codebase Risks:\n${inspection.potential_red_flags.map(r => `- ${r}`).join('\n')}` : '');
      const improvementsSummary = inspection.recommended_improvements && inspection.recommended_improvements.length > 0
        ? `\n\nRecommended Technical Improvements:\n${inspection.recommended_improvements.map(i => `- ${i}`).join('\n')}`
        : '';

      setOverallFeedback(
        `Project Summary:\n${inspection.what_is_building}${defectsSummary}${improvementsSummary}\n\nSuggested Discussion:\n${inspection.suggested_judge_questions.slice(0, 2).map(q => `- ${q}`).join('\n')}`
      );
    }
    setStatusMessage({
      type: 'success',
      text: 'Ollama inspection findings and scores applied to your rubric form!',
    });
    setTimeout(() => setStatusMessage(null), 5000);
  };

  const handleCopyQuestion = (text: string, idx: number) => {
    navigator.clipboard.writeText(text);
    setCopiedQuestionIndex(idx);
    setTimeout(() => setCopiedQuestionIndex(null), 2500);
  };

  // Fetch submission review payload
  const fetchReview = async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const data = await api.getJudgeSubmissionReview(hackathonId, submissionId);
      setReviewData(data);

      // Populate form state from existing review or AI suggestions
      const scoresMap: Record<string, { score: number; notes: string }> = {};

      // Build criteria map from rubric criteria
      data.rubric_criteria.forEach((crit) => {
        // Find existing score if review exists
        const existingScore = data.review?.criterion_scores?.find(
          (cs) => cs.criterion_id === crit.id
        );

        if (existingScore && existingScore.score !== null && existingScore.score !== undefined) {
          scoresMap[crit.id] = {
            score: Number(existingScore.score),
            notes: existingScore.judge_notes || '',
          };
        } else {
          // If no judge score yet, leave at default midpoint or min
          const min = Number(crit.min_score) || 0;
          scoresMap[crit.id] = {
            score: min,
            notes: '',
          };
        }
      });

      setCriterionScores(scoresMap);
      setOverallFeedback(data.review?.overall_feedback || '');
      setDecision(data.review?.decision || 'accepted');
      setVersion(data.review?.version);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setLoadError(err.message);
      } else {
        setLoadError('Failed to load submission review details.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (hackathonId && submissionId) {
      fetchReview();
      fetchCachedInspection();
    }
  }, [hackathonId, submissionId]);

  // Live total score calculation
  const calculatedTotalScore = useMemo(() => {
    if (!reviewData || reviewData.rubric_criteria.length === 0) return 0;

    let weightedSum = 0;
    let totalWeight = 0;

    reviewData.rubric_criteria.forEach((crit) => {
      const weight = Number(crit.weight) || 1;
      const scoreObj = criterionScores[crit.id];
      const score = scoreObj ? scoreObj.score : 0;
      weightedSum += score * weight;
      totalWeight += weight;
    });

    if (totalWeight <= 0) return 0;
    return Number((weightedSum / totalWeight).toFixed(2));
  }, [reviewData, criterionScores]);

  // Copy commit sha
  const handleCopySha = (sha: string) => {
    navigator.clipboard.writeText(sha);
    setCopiedSha(true);
    setTimeout(() => setCopiedSha(false), 2000);
  };

  // Score change handler
  const handleScoreChange = (criterionId: string, newScore: number) => {
    if (!reviewData?.can_edit) return;
    setCriterionScores((prev) => ({
      ...prev,
      [criterionId]: {
        score: newScore,
        notes: prev[criterionId]?.notes || '',
      },
    }));
  };

  // Notes change handler
  const handleNotesChange = (criterionId: string, notes: string) => {
    if (!reviewData?.can_edit) return;
    setCriterionScores((prev) => ({
      ...prev,
      [criterionId]: {
        score: prev[criterionId]?.score || 0,
        notes,
      },
    }));
  };

  // Adopt AI suggested score for a criterion
  const handleAdoptAiScore = (criterionId: string, aiScore: number) => {
    if (!reviewData?.can_edit) return;
    handleScoreChange(criterionId, aiScore);
  };

  // Save Draft
  const handleSaveDraft = async () => {
    if (!reviewData || !reviewData.can_edit) return;
    setIsSavingDraft(true);
    setStatusMessage(null);

    const payload: SaveJudgeReviewRequest = {
      overall_feedback: overallFeedback || undefined,
      decision: decision || 'accepted',
      version: version,
      criterion_scores: Object.entries(criterionScores).map(([critId, val]) => ({
        criterion_id: critId,
        score: val.score,
        judge_notes: val.notes || undefined,
      })),
    };

    try {
      const updatedReview = await api.saveJudgeSubmissionReviewDraft(
        hackathonId,
        submissionId,
        payload
      );
      setVersion(updatedReview.version);
      setStatusMessage({
        type: 'success',
        text: 'Draft review saved successfully. Your progress is preserved.',
      });
      // Refresh review details
      const refreshed = await api.getJudgeSubmissionReview(hackathonId, submissionId);
      setReviewData(refreshed);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setStatusMessage({ type: 'error', text: err.message });
      } else {
        setStatusMessage({
          type: 'error',
          text: 'Failed to save review draft. Please check your network connection.',
        });
      }
    } finally {
      setIsSavingDraft(false);
    }
  };

  // Submit Final Review
  const handleSubmitFinal = async () => {
    if (!reviewData || !reviewData.can_edit) return;

    if (!overallFeedback.trim()) {
      setStatusMessage({
        type: 'error',
        text: 'Overall feedback is required before final submission.',
      });
      setIsConfirmModalOpen(false);
      return;
    }

    setIsSubmitting(true);
    setStatusMessage(null);

    const payload: SubmitJudgeReviewRequest = {
      overall_feedback: overallFeedback.trim(),
      decision: decision || 'accepted',
      version: version,
      criterion_scores: Object.entries(criterionScores).map(([critId, val]) => ({
        criterion_id: critId,
        score: val.score,
        judge_notes: val.notes || undefined,
      })),
    };

    try {
      await api.submitJudgeReview(hackathonId, submissionId, payload);
      setIsConfirmModalOpen(false);
      setStatusMessage({
        type: 'success',
        text: 'Review successfully submitted! Your scores and feedback are now recorded.',
      });
      // Refresh to lock the view
      const refreshed = await api.getJudgeSubmissionReview(hackathonId, submissionId);
      setReviewData(refreshed);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setStatusMessage({ type: 'error', text: err.message });
      } else {
        setStatusMessage({
          type: 'error',
          text: 'Failed to submit review. Please try again.',
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // Revert Submitted Review (Re-evaluate or Reset to Awaiting)
  const handleRevertReview = async () => {
    setIsReverting(true);
    setStatusMessage(null);

    try {
      await api.revertJudgeReview(hackathonId, submissionId, {
        target_status: revertTargetStatus,
        reason: revertReason.trim() || undefined,
      });

      setIsRevertModalOpen(false);
      setRevertReason('');
      setStatusMessage({
        type: 'success',
        text:
          revertTargetStatus === 'draft'
            ? 'Review unlocked! The submission is now back in Draft mode for re-evaluation.'
            : 'Review has been reset back to Awaiting Review.',
      });
      await fetchReview();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setStatusMessage({ type: 'error', text: err.message });
      } else {
        setStatusMessage({
          type: 'error',
          text: 'Failed to revert review. Please try again.',
        });
      }
    } finally {
      setIsReverting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="bg-white border border-[#E2E8F0] rounded-xl p-16 flex flex-col items-center justify-center gap-3">
        <RefreshCw className="w-8 h-8 text-[#2563EB] animate-spin" />
        <p className="text-sm font-medium text-[#64748B]">
          Loading submission review workspace...
        </p>
      </div>
    );
  }

  if (loadError || !reviewData) {
    return (
      <div className="bg-white border border-[#E2E8F0] rounded-xl p-8 max-w-2xl mx-auto text-center space-y-4">
        <AlertCircle className="w-10 h-10 text-red-500 mx-auto" />
        <h2 className="text-lg font-bold text-[#111827]">
          Unable to Load Submission
        </h2>
        <p className="text-xs text-[#64748B]">
          {loadError || 'The requested project could not be found or you do not have permission.'}
        </p>
        <div className="pt-2">
          <Link
            href="/judge/projects"
            className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-[#2563EB] rounded-lg hover:bg-blue-700 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Return to My Projects</span>
          </Link>
        </div>
      </div>
    );
  }

  const isSubmitted = reviewData.review?.status === 'submitted' || !reviewData.can_edit;

  return (
    <div className="space-y-8 pb-16">
      {/* Top Breadcrumb & Status Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-[#E2E8F0]">
        <div className="flex items-center gap-3">
          <Link
            href="/judge/projects"
            className="p-2 text-[#64748B] hover:text-[#111827] hover:bg-white rounded-lg border border-[#E2E8F0] transition-colors"
            title="Back to assigned projects"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2 text-xs text-[#64748B]">
              <span>Judge Workspace</span>
              <span>/</span>
              <span>{reviewData.hackathon_title || 'Hackathon Event'}</span>
            </div>
            <h1 className="text-xl font-bold tracking-tight text-[#111827] mt-0.5">
              {reviewData.submission_title}
            </h1>
          </div>
        </div>

        {/* Status Badge */}
        <div>
          {isSubmitted ? (
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs font-bold text-emerald-800">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>Review Submitted ({Number(reviewData.review?.score).toFixed(1)} / 100)</span>
            </div>
          ) : reviewData.review?.status === 'draft' ? (
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-blue-50 border border-blue-200 text-xs font-semibold text-[#2563EB]">
              <FileText className="w-4 h-4 text-[#2563EB]" />
              <span>Draft In Progress</span>
            </div>
          ) : (
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-50 border border-amber-200 text-xs font-semibold text-amber-800">
              <Scale className="w-4 h-4 text-amber-600" />
              <span>Awaiting Evaluation</span>
            </div>
          )}
        </div>
      </div>

      {/* Status banner alerts */}
      {statusMessage && (
        <div
          className={`p-4 rounded-xl border flex items-start gap-3 text-xs ${
            statusMessage.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
              : 'bg-red-50 border-red-200 text-red-900'
          }`}
        >
          {statusMessage.type === 'success' ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
          ) : (
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
          )}
          <span className="font-medium">{statusMessage.text}</span>
        </div>
      )}

      {/* Submitted Review Banner (Locked State) */}
      {isSubmitted && (
        <div className="p-4 rounded-xl bg-slate-100 border border-[#CBD5E1] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs text-[#334155]">
          <div className="flex items-center gap-2.5">
            <Lock className="w-4 h-4 text-[#64748B] shrink-0" />
            <span>
              This review was finalized and submitted on{' '}
              <strong>
                {reviewData.review?.submitted_at
                  ? new Date(reviewData.review.submitted_at).toLocaleDateString()
                  : 'earlier'}
              </strong>
              . If you need to revise scores or start fresh, you can revert this review.
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
            <span className="font-bold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-md border border-emerald-200">
              Completed
            </span>
            <button
              type="button"
              onClick={() => {
                setRevertTargetStatus('draft');
                setRevertReason('');
                setIsRevertModalOpen(true);
              }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-[#1E40AF] bg-[#EFF6FF] hover:bg-[#DBEAFE] border border-[#BFDBFE] transition-colors shadow-xs"
              title="Reopen review to re-evaluate scores or reset to awaiting"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Revert / Re-evaluate</span>
            </button>
          </div>
        </div>
      )}

      {/* ========================================================
          SECTION A: PROJECT OVERVIEW & AI ANALYSIS
      ======================================================== */}
      <section className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-xs space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#E2E8F0] pb-3">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#2563EB]" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-[#111827]">
              Section A: Project Overview & Codebase Analysis
            </h2>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            {inspection ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold text-emerald-800 bg-emerald-50 rounded-full border border-emerald-200">
                <Sparkles className="w-3 h-3 text-emerald-600" />
                AI Codebase Verified ({inspection.model_name})
              </span>
            ) : isInspecting ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold text-blue-800 bg-blue-50 rounded-full border border-blue-200 animate-pulse">
                <RefreshCw className="w-3 h-3 text-blue-600 animate-spin" />
                Analyzing Repository with Ollama...
              </span>
            ) : (
              <button
                type="button"
                onClick={() => handleRunOllamaInspection(false)}
                className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 rounded-lg border border-blue-200 transition-colors shadow-2xs"
              >
                <Zap className="w-3 h-3 text-blue-600" />
                <span>Run Ollama Analysis</span>
              </button>
            )}
            <span className="text-xs text-[#64748B]">
              Team: <strong className="text-[#111827]">{reviewData.team_name}</strong>
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            {/* If Ollama inspection has completed */}
            {inspection ? (
              <>
                {/* 1. AI Quick Summary (Executive TL;DR) */}
                <div className="p-4 rounded-xl bg-gradient-to-r from-blue-50/90 via-indigo-50/50 to-slate-50 border border-blue-200 shadow-xs space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-blue-900 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-blue-600" />
                      AI Quick Summary (TL;DR)
                    </span>
                    <span className="text-[11px] font-semibold text-blue-700 bg-white/90 px-2 py-0.5 rounded border border-blue-200">
                      Executive Snapshot
                    </span>
                  </div>
                  <p className="text-sm font-medium text-slate-900 leading-relaxed">
                    {inspection.quick_summary || (
                      inspection.what_is_building
                        ? inspection.what_is_building.split(/(?<=[.?!])\s+/).slice(0, 2).join(' ')
                        : 'No summary available.'
                    )}
                  </p>
                </div>

                {/* 2. AI Exact Overview (Codebase Verified) */}
                <div className="p-4 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-[#334155] flex items-center gap-1.5">
                      <Bot className="w-3.5 h-3.5 text-[#2563EB]" />
                      AI Exact Overview (What Is Being Built)
                    </span>
                    <span className="text-[11px] font-medium text-[#64748B]">
                      Extracted directly from repository code & AST
                    </span>
                  </div>
                  <p className="text-sm text-[#1E293B] leading-relaxed whitespace-pre-line">
                    {inspection.exact_overview || inspection.what_is_building}
                  </p>
                </div>
              </>
            ) : isInspecting ? (
              /* Inspecting in Progress Skeleton */
              <div className="p-6 rounded-xl bg-blue-50/40 border border-blue-200 text-center space-y-3">
                <div className="inline-flex p-3 rounded-full bg-blue-100 text-blue-600 animate-spin">
                  <RefreshCw className="w-6 h-6" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-blue-950">
                    Ollama is analyzing the repository code...
                  </h4>
                  <p className="text-xs text-blue-700 mt-1 max-w-md mx-auto">
                    Synthesizing an exact technical overview, executive quick summary, innovation metrics, and architecture depth.
                  </p>
                </div>
              </div>
            ) : (
              /* Prompt to inspect with Ollama */
              <div className="p-5 rounded-xl bg-gradient-to-r from-blue-50/80 to-indigo-50/80 border border-blue-200 space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="space-y-1">
                    <h4 className="text-sm font-bold text-blue-950 flex items-center gap-1.5">
                      <Sparkles className="w-4 h-4 text-blue-600" />
                      Generate AI Exact Overview & Quick Summary
                    </h4>
                    <p className="text-xs text-blue-800 leading-relaxed max-w-xl">
                      Participants often submit brief or promotional pitches. Let Ollama inspect the actual repository code to produce an objective executive quick summary and verify exactly what has been engineered.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRunOllamaInspection(false)}
                    className="inline-flex items-center justify-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 active:bg-blue-800 rounded-lg shadow-xs transition-colors shrink-0"
                  >
                    <Zap className="w-3.5 h-3.5" />
                    <span>Analyze Codebase Now</span>
                  </button>
                </div>
              </div>
            )}

            {/* 3. Participant Self-Reported Pitch (Collapsible) */}
            <div className="border border-[#E2E8F0] rounded-xl overflow-hidden bg-white shadow-2xs">
              <button
                type="button"
                onClick={() => setShowParticipantPitch((prev) => !prev)}
                className="w-full flex items-center justify-between p-3.5 text-left bg-white hover:bg-[#F8FAFC] transition-colors"
              >
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-[#64748B]" />
                  <span className="text-xs font-bold text-[#334155] uppercase tracking-wider">
                    Participant Self-Reported Pitch & Submission Notes
                  </span>
                  <span className="text-[10px] font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
                    Form Submission
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-xs font-semibold text-[#2563EB]">
                  <span>{showParticipantPitch ? 'Hide Pitch' : 'Show Pitch'}</span>
                  {showParticipantPitch ? (
                    <ChevronUp className="w-3.5 h-3.5" />
                  ) : (
                    <ChevronDown className="w-3.5 h-3.5" />
                  )}
                </div>
              </button>

              {showParticipantPitch && (
                <div className="p-4 pt-3 border-t border-[#E2E8F0] bg-[#F8FAFC]/50 text-xs text-[#334155] leading-relaxed whitespace-pre-line">
                  {reviewData.description ? (
                    reviewData.description
                  ) : (
                    <span className="italic text-slate-400">
                      No project description was provided by the submitting team in their registration form.
                    </span>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Right Column: Submission & Event Details */}
          <div className="space-y-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-4 self-start">
            <h3 className="text-xs font-semibold text-[#64748B] uppercase tracking-wider">
              Submission Details
            </h3>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-[#64748B]">Team:</span>
                <span className="font-semibold text-[#111827]">{reviewData.team_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Event:</span>
                <span className="font-medium text-[#111827]">{reviewData.hackathon_title || 'Hackathon'}</span>
              </div>
              {reviewData.created_at && (
                <div className="flex justify-between">
                  <span className="text-[#64748B]">Submitted:</span>
                  <span className="text-[#111827]">{new Date(reviewData.created_at).toLocaleDateString()}</span>
                </div>
              )}
              <div className="pt-2 border-t border-[#E2E8F0] space-y-2">
                <a
                  href={reviewData.repository_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-[#2563EB] bg-[#EFF6FF] hover:bg-blue-100 rounded-md transition-colors border border-[#BFDBFE]"
                >
                  <Github className="w-3.5 h-3.5" />
                  <span>Open GitHub Repository</span>
                  <ExternalLink className="w-3 h-3 ml-0.5" />
                </a>

                {inspection && (
                  <button
                    type="button"
                    onClick={() => handleRunOllamaInspection(true)}
                    disabled={isInspecting}
                    className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-600 bg-white hover:bg-slate-100 disabled:opacity-50 rounded-md transition-colors border border-slate-200"
                  >
                    <RefreshCw className={`w-3 h-3 ${isInspecting ? 'animate-spin' : ''}`} />
                    <span>Re-analyze with Ollama</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ========================================================
          SECTION B: SUBMISSION INFORMATION
      ======================================================== */}
      <section className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-xs space-y-4">
        <div className="flex items-center justify-between border-b border-[#E2E8F0] pb-3">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#2563EB]" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-[#111827]">
              Section B: Repository & Git Information
            </h2>
          </div>
          <span className="text-xs text-[#64748B]">Branch: <strong className="text-[#111827]">{reviewData.target_branch}</strong></span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          {/* Repo Name */}
          <div className="p-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg">
            <span className="text-[#64748B] block font-medium">Repository</span>
            <span className="font-bold text-[#111827] block truncate mt-1">
              {reviewData.repository_owner ? `${reviewData.repository_owner}/${reviewData.repository_name}` : reviewData.repository_url}
            </span>
          </div>

          {/* Branch */}
          <div className="p-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg">
            <span className="text-[#64748B] block font-medium">Target Branch</span>
            <div className="flex items-center gap-1.5 mt-1 font-semibold text-[#111827]">
              <GitBranch className="w-3.5 h-3.5 text-[#2563EB]" />
              <span>{reviewData.target_branch}</span>
            </div>
          </div>

          {/* Commit SHA */}
          <div className="p-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg">
            <span className="text-[#64748B] block font-medium">Verified Commit</span>
            <div className="flex items-center gap-2 mt-1">
              <code className="bg-white px-2 py-0.5 rounded border border-[#E2E8F0] font-mono text-[11px] text-[#111827]">
                {reviewData.verified_commit_sha ? reviewData.verified_commit_sha.slice(0, 10) : 'Head SHA'}
              </code>
              {reviewData.verified_commit_sha && (
                <button
                  type="button"
                  onClick={() => handleCopySha(reviewData.verified_commit_sha || '')}
                  title="Copy full commit SHA"
                  className="p-1 text-[#64748B] hover:text-[#111827] rounded hover:bg-slate-200 transition-colors"
                >
                  {copiedSha ? (
                    <Check className="w-3.5 h-3.5 text-emerald-600" />
                  ) : (
                    <Copy className="w-3.5 h-3.5" />
                  )}
                </button>
              )}
            </div>
          </div>

          {/* Connection Status */}
          <div className="p-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg">
            <span className="text-[#64748B] block font-medium">Repository Connection</span>
            <span
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold mt-1 ${
                reviewData.connection_status === 'verified'
                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                  : 'bg-amber-50 text-amber-700 border border-amber-200'
              }`}
            >
              <CheckCircle2 className="w-3 h-3" />
              <span className="capitalize">{reviewData.connection_status}</span>
            </span>
          </div>
        </div>
      </section>

      {/* ========================================================
          SECTION C: OLLAMA AI REPOSITORY INSPECTOR
      ======================================================== */}
      <section className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-xs space-y-6">
        {/* Header Bar */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 border-b border-[#E2E8F0] pb-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-blue-50 border border-blue-200 flex items-center justify-center">
                <Cpu className="w-4 h-4 text-[#2563EB]" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-[#111827]">
                    Section C: Ollama AI Repository Inspector
                  </h2>
                  <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE]">
                    {inspection ? `Ollama: ${inspection.model_name}` : 'Dual Ollama (Primary: 10.3.2.157 + Local Fallback)'}
                  </span>
                  {inspection && (
                    <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" />
                      <span>{inspection.cached ? 'Cached' : 'Live Analyzed'}</span>
                    </span>
                  )}
                </div>
                <p className="text-xs text-[#64748B]">
                  One-click deep inspection of codebase architecture, novelty, complete tech stack, complexity, and judge evaluation factors.
                </p>
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2.5 shrink-0 self-start lg:self-auto">
            {inspection && !isSubmitted && (
              <button
                type="button"
                onClick={handleApplyInspectionToRubric}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-[#1E40AF] bg-[#DBEAFE] hover:bg-[#BFDBFE] transition-colors border border-[#93C5FD]"
                title="Automatically populate rubric scores & feedback notes using Ollama findings"
              >
                <Sparkles className="w-3.5 h-3.5 text-[#2563EB]" />
                <span>Apply to Rubric</span>
              </button>
            )}

            <button
              type="button"
              onClick={() => handleRunOllamaInspection(Boolean(inspection))}
              disabled={isInspecting}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-bold transition-all shadow-xs ${
                isInspecting
                  ? 'bg-slate-100 text-slate-400 border border-slate-300 cursor-not-allowed'
                  : inspection
                  ? 'bg-white text-[#111827] border border-[#CBD5E1] hover:bg-slate-50'
                  : 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white hover:from-blue-700 hover:to-indigo-700 shadow-blue-500/20'
              }`}
            >
              {isInspecting ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-[#2563EB]" />
                  <span>Inspecting Codebase...</span>
                </>
              ) : inspection ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 text-[#2563EB]" />
                  <span>Re-Inspect Codebase</span>
                </>
              ) : (
                <>
                  <Zap className="w-3.5 h-3.5 text-amber-300 fill-amber-300" />
                  <span>Inspect Complete Repository with Ollama</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Inspection Progress Tracker */}
        {isInspecting && (
          <div className="p-5 rounded-xl bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-[#1E3A8A] flex items-center gap-2">
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-[#2563EB]" />
                <span>Ollama Neural Analysis in Progress...</span>
              </span>
              <span className="text-[11px] font-semibold text-[#2563EB] bg-white px-2.5 py-0.5 rounded-full border border-blue-200">
                Primary Engine: Remote Ollama (10.3.2.157)
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-4 gap-2 text-[11px]">
              <div className={`p-2.5 rounded-lg border ${inspectProgressStep >= 1 ? 'bg-white border-blue-300 text-blue-900 font-semibold' : 'bg-white/50 border-slate-200 text-slate-400'}`}>
                <span>1. Fetching Repo Tree & Files</span>
              </div>
              <div className={`p-2.5 rounded-lg border ${inspectProgressStep >= 2 ? 'bg-white border-blue-300 text-blue-900 font-semibold' : 'bg-white/50 border-slate-200 text-slate-400'}`}>
                <span>2. Extracting Manifests</span>
              </div>
              <div className={`p-2.5 rounded-lg border ${inspectProgressStep >= 3 ? 'bg-white border-blue-300 text-blue-900 font-semibold' : 'bg-white/50 border-slate-200 text-slate-400'}`}>
                <span>3. Ollama Neural Analysis</span>
              </div>
              <div className={`p-2.5 rounded-lg border ${inspectProgressStep >= 4 ? 'bg-white border-blue-300 text-blue-900 font-semibold' : 'bg-white/50 border-slate-200 text-slate-400'}`}>
                <span>4. Synthesizing Factors</span>
              </div>
            </div>

            <p className="text-[11px] text-[#475569]">
              Inspecting complete repository, extracting architecture patterns, evaluating innovation, and calculating judge scores... (Deep code analysis takes ~30–60s on Primary AI).
            </p>
          </div>
        )}

        {/* Error Banner */}
        {inspectionError && (
          <div className="p-4 rounded-xl bg-red-50 border border-red-200 flex items-start gap-3 text-xs text-red-900">
            <ShieldAlert className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <span className="font-bold">Inspection Error</span>
              <p>{inspectionError}</p>
            </div>
          </div>
        )}

        {/* Not yet inspected state */}
        {!inspection && !isInspecting && (
          <div className="p-8 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] text-center space-y-4">
            <div className="w-12 h-12 rounded-full bg-blue-100/70 border border-blue-200 flex items-center justify-center mx-auto text-[#2563EB]">
              <Zap className="w-6 h-6 fill-[#2563EB]" />
            </div>
            <div className="space-y-1 max-w-lg mx-auto">
              <h3 className="text-sm font-bold text-[#111827]">
                Ready to Inspect Repository with Ollama
              </h3>
              <p className="text-xs text-[#64748B] leading-relaxed">
                Click the button above to run an autonomous repository inspection. Ollama will inspect the repository structure, analyze the tech stack, evaluate innovation and technical complexity, and generate tailored judge interview questions.
              </p>
            </div>
            <div>
              <button
                type="button"
                onClick={() => handleRunOllamaInspection(false)}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-xs font-bold text-white bg-[#2563EB] hover:bg-blue-700 transition-colors shadow-xs"
              >
                <Zap className="w-3.5 h-3.5 fill-white" />
                <span>Inspect Repository Now</span>
              </button>
            </div>
          </div>
        )}

        {/* Inspected Results Showcase */}
        {inspection && (
          <div className="space-y-6">
            {/* 4 Score Metric Cards */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5">
              {/* Innovation */}
              <div className="p-4 rounded-xl bg-gradient-to-br from-amber-50 to-orange-50 border border-amber-200 space-y-1">
                <span className="text-[11px] font-semibold text-amber-800 uppercase tracking-wider block">
                  Innovation Score
                </span>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-2xl font-black text-amber-900">
                    {inspection.innovation.score.toFixed(1)}
                  </span>
                  <span className="text-xs font-semibold text-amber-700">/ 10</span>
                </div>
                <span className="text-[11px] text-amber-800 block truncate">
                  {inspection.innovation.novel_elements[0] || 'Novel architecture'}
                </span>
              </div>

              {/* Technical Complexity */}
              <div className="p-4 rounded-xl bg-gradient-to-br from-indigo-50 to-blue-50 border border-indigo-200 space-y-1">
                <span className="text-[11px] font-semibold text-indigo-800 uppercase tracking-wider block">
                  Complexity Level
                </span>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-black text-indigo-900">
                    {inspection.complexity.level}
                  </span>
                  <span className="text-xs font-semibold text-indigo-700">
                    ({inspection.complexity.score.toFixed(1)}/10)
                  </span>
                </div>
                <span className="text-[11px] text-indigo-800 block truncate">
                  {inspection.complexity.architecture_depth?.slice(0, 35) || 'Multi-tier architecture'}
                </span>
              </div>

              {/* Code Quality */}
              <div className="p-4 rounded-xl bg-gradient-to-br from-emerald-50 to-teal-50 border border-emerald-200 space-y-1">
                <span className="text-[11px] font-semibold text-emerald-800 uppercase tracking-wider block">
                  Code Quality
                </span>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-2xl font-black text-emerald-900">
                    {inspection.judge_factors.code_quality_score.toFixed(1)}
                  </span>
                  <span className="text-xs font-semibold text-emerald-700">/ 10</span>
                </div>
                <span className="text-[11px] text-emerald-800 block truncate">
                  {inspection.judge_factors.code_quality_summary?.slice(0, 35) || 'Clean, modular typing'}
                </span>
              </div>

              {/* Execution Status */}
              <div className="p-4 rounded-xl bg-gradient-to-br from-slate-50 to-slate-100 border border-slate-200 space-y-1">
                <span className="text-[11px] font-semibold text-slate-600 uppercase tracking-wider block">
                  Completeness
                </span>
                <div className="flex items-baseline gap-1.5">
                  <span className="text-2xl font-black text-slate-900">
                    {inspection.judge_factors.completeness_score.toFixed(1)}
                  </span>
                  <span className="text-xs font-semibold text-slate-600">/ 10</span>
                </div>
                <span className="text-[11px] text-emerald-700 font-semibold block truncate">
                  {inspection.judge_factors.is_working_demo ? '✓ Working Demo' : '⚠️ Prototype'}
                </span>
              </div>
            </div>

            {/* Sub-Tabs Navigation */}
            <div className="border-b border-[#E2E8F0] flex items-center gap-1 overflow-x-auto text-xs pb-px">
              {[
                { id: 'overview', label: '🏗️ What is Building?', count: null },
                { id: 'innovation', label: '💡 Innovation & Novelty', count: `${inspection.innovation.score}/10` },
                { id: 'tech_stack', label: '🛠️ Complete Tech Stack', count: `${inspection.tech_stack.languages.length + inspection.tech_stack.frameworks.length + inspection.tech_stack.databases.length}` },
                { id: 'complexity', label: '⚡ Complexity Depth', count: inspection.complexity.level },
                { id: 'judge_factors', label: '⚖️ Judge Evaluation Factors', count: '4 Criteria' },
                {
                  id: 'highlights',
                  label: '⚠️ Codebase Defects & Improvements',
                  count: `${
                    (inspection.codebase_defects?.length || inspection.potential_red_flags?.length || 0) +
                    (inspection.missing_implementations?.length || 0)
                  } Issues`,
                },
                { id: 'questions', label: '🎤 Suggested Pitch Q&A', count: `${inspection.suggested_judge_questions.length}` },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveInspectTab(tab.id as any)}
                  className={`px-3.5 py-2.5 font-bold transition-all border-b-2 whitespace-nowrap flex items-center gap-1.5 ${
                    activeInspectTab === tab.id
                      ? 'border-[#2563EB] text-[#2563EB] bg-blue-50/50'
                      : 'border-transparent text-[#64748B] hover:text-[#111827] hover:border-slate-300'
                  }`}
                >
                  <span>{tab.label}</span>
                  {tab.count && (
                    <span className="px-1.5 py-0.2 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600">
                      {tab.count}
                    </span>
                  )}
                </button>
              ))}
            </div>

            {/* Tab 1: What is Building */}
            {activeInspectTab === 'overview' && (
              <div className="p-5 rounded-xl bg-[#F8FAFC] border border-[#E2E8F0] space-y-4">
                {inspection.quick_summary && (
                  <div className="p-3.5 bg-blue-50/80 border border-blue-200 rounded-lg space-y-1">
                    <h5 className="text-[11px] font-bold text-blue-900 uppercase tracking-wider flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-blue-600" />
                      Executive Quick Summary
                    </h5>
                    <p className="text-sm font-medium text-blue-950 leading-relaxed">
                      {inspection.quick_summary}
                    </p>
                  </div>
                )}

                <div>
                  <h4 className="text-xs font-bold text-[#64748B] uppercase tracking-wider mb-1.5">
                    Exact Technical Overview (Codebase Verified)
                  </h4>
                  <p className="text-sm text-[#1E293B] leading-relaxed font-normal whitespace-pre-line">
                    {inspection.exact_overview || inspection.what_is_building}
                  </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-3 border-t border-[#E2E8F0] text-xs">
                  <div className="space-y-1">
                    <span className="font-semibold text-[#64748B]">Project Title:</span>
                    <p className="font-bold text-[#111827]">{inspection.project_name}</p>
                  </div>
                  <div className="space-y-1">
                    <span className="font-semibold text-[#64748B]">Analysis Engine:</span>
                    <p className="font-semibold text-[#2563EB]">
                      Ollama ({inspection.model_name}) &bull; {inspection.model_name.includes('10.3.2.157') || inspection.model_name.includes('Primary') ? 'Remote High-Speed Inference' : 'Local Fallback Inference'}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Tab 2: Innovation & Novelty */}
            {activeInspectTab === 'innovation' && (
              <div className="space-y-4">
                <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-amber-900 uppercase tracking-wider flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-amber-600" />
                      <span>Innovation Summary & Differentiation</span>
                    </span>
                    <span className="text-xs font-bold text-amber-900 bg-white px-2 py-0.5 rounded border border-amber-200">
                      Score: {inspection.innovation.score.toFixed(1)} / 10
                    </span>
                  </div>
                  <p className="text-xs text-amber-950 leading-relaxed">
                    {inspection.innovation.summary}
                  </p>
                </div>

                <div className="space-y-2">
                  <h4 className="text-xs font-bold text-[#111827] uppercase tracking-wider">
                    Novel Technical Elements & Creative Mechanisms:
                  </h4>
                  <div className="grid grid-cols-1 gap-2">
                    {inspection.innovation.novel_elements.map((elem, idx) => (
                      <div key={idx} className="p-3 rounded-lg bg-white border border-[#E2E8F0] flex items-start gap-2.5 text-xs text-[#334155]">
                        <span className="w-5 h-5 rounded-full bg-blue-50 text-[#2563EB] flex items-center justify-center shrink-0 font-bold text-[11px] mt-0.5">
                          {idx + 1}
                        </span>
                        <span className="font-medium leading-relaxed">{elem}</span>
                      </div>
                    ))}
                  </div>
                </div>

                {inspection.innovation.competitive_differentiation && (
                  <div className="p-4 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0] space-y-1 text-xs">
                    <span className="font-bold text-[#64748B] uppercase tracking-wider block">
                      Competitive Differentiation:
                    </span>
                    <p className="text-[#334155] leading-relaxed">
                      {inspection.innovation.competitive_differentiation}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Tab 3: Tech Stack */}
            {activeInspectTab === 'tech_stack' && (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
                {/* Languages */}
                <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2.5">
                  <span className="font-bold text-[#111827] uppercase tracking-wider block text-[11px] text-[#2563EB]">
                    Languages
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {inspection.tech_stack.languages.map((lang, idx) => (
                      <span key={idx} className="px-2.5 py-1 rounded-md text-[11px] font-semibold bg-blue-50 text-blue-800 border border-blue-200">
                        {lang}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Frameworks */}
                <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2.5">
                  <span className="font-bold text-[#111827] uppercase tracking-wider block text-[11px] text-purple-700">
                    Frameworks & Libraries
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {inspection.tech_stack.frameworks.map((fw, idx) => (
                      <span key={idx} className="px-2.5 py-1 rounded-md text-[11px] font-semibold bg-purple-50 text-purple-800 border border-purple-200">
                        {fw}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Databases */}
                <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2.5">
                  <span className="font-bold text-[#111827] uppercase tracking-wider block text-[11px] text-emerald-700">
                    Databases & Caching
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {inspection.tech_stack.databases.map((db, idx) => (
                      <span key={idx} className="px-2.5 py-1 rounded-md text-[11px] font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
                        {db}
                      </span>
                    ))}
                  </div>
                </div>

                {/* AI / ML Tools */}
                <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2.5">
                  <span className="font-bold text-[#111827] uppercase tracking-wider block text-[11px] text-amber-700">
                    AI & Machine Learning
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {inspection.tech_stack.ai_ml_tools.map((ai, idx) => (
                      <span key={idx} className="px-2.5 py-1 rounded-md text-[11px] font-semibold bg-amber-50 text-amber-800 border border-amber-200">
                        {ai}
                      </span>
                    ))}
                  </div>
                </div>

                {/* DevOps & Cloud */}
                <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2.5">
                  <span className="font-bold text-[#111827] uppercase tracking-wider block text-[11px] text-cyan-700">
                    DevOps & Infrastructure
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {inspection.tech_stack.devops_cloud.map((dev, idx) => (
                      <span key={idx} className="px-2.5 py-1 rounded-md text-[11px] font-semibold bg-cyan-50 text-cyan-800 border border-cyan-200">
                        {dev}
                      </span>
                    ))}
                  </div>
                </div>

                {/* APIs & Integrations */}
                <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2.5">
                  <span className="font-bold text-[#111827] uppercase tracking-wider block text-[11px] text-slate-700">
                    APIs & External Services
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {inspection.tech_stack.apis_integrations.map((apiItem, idx) => (
                      <span key={idx} className="px-2.5 py-1 rounded-md text-[11px] font-semibold bg-slate-100 text-slate-800 border border-slate-200">
                        {apiItem}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Tab 4: Complexity */}
            {activeInspectTab === 'complexity' && (
              <div className="space-y-4 text-xs">
                <div className="p-4 rounded-xl bg-indigo-50/70 border border-indigo-200 flex items-center justify-between">
                  <div>
                    <span className="text-[11px] font-bold text-indigo-900 uppercase tracking-wider block">
                      Overall Complexity Rating
                    </span>
                    <span className="text-lg font-black text-indigo-950 mt-0.5 block">
                      {inspection.complexity.level} ({inspection.complexity.score.toFixed(1)} / 10)
                    </span>
                  </div>
                  <span className="px-3 py-1 rounded-full text-xs font-bold bg-white text-indigo-700 border border-indigo-200">
                    Architectural Depth
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2">
                    <span className="font-bold text-[#111827] block text-[11px] uppercase tracking-wider">
                      Architecture Depth
                    </span>
                    <p className="text-[#334155] leading-relaxed">
                      {inspection.complexity.architecture_depth}
                    </p>
                  </div>

                  <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2">
                    <span className="font-bold text-[#111827] block text-[11px] uppercase tracking-wider">
                      Algorithmic Challenges
                    </span>
                    <p className="text-[#334155] leading-relaxed">
                      {inspection.complexity.algorithmic_challenges}
                    </p>
                  </div>

                  <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2">
                    <span className="font-bold text-[#111827] block text-[11px] uppercase tracking-wider">
                      Data Flow Complexity
                    </span>
                    <p className="text-[#334155] leading-relaxed">
                      {inspection.complexity.data_flow_complexity}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Tab 5: Judge Evaluation Factors */}
            {activeInspectTab === 'judge_factors' && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                {/* Code Quality */}
                <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2">
                  <div className="flex items-center justify-between border-b border-[#F1F5F9] pb-2">
                    <span className="font-bold text-[#111827] uppercase tracking-wider text-[11px]">
                      Code Quality & Modularity
                    </span>
                    <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-blue-50 text-[#2563EB]">
                      {inspection.judge_factors.code_quality_score.toFixed(1)} / 10
                    </span>
                  </div>
                  <p className="text-[#475569] leading-relaxed">
                    {inspection.judge_factors.code_quality_summary}
                  </p>
                </div>

                {/* Completeness */}
                <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2">
                  <div className="flex items-center justify-between border-b border-[#F1F5F9] pb-2">
                    <span className="font-bold text-[#111827] uppercase tracking-wider text-[11px]">
                      Execution & Completeness
                    </span>
                    <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-700">
                      {inspection.judge_factors.completeness_score.toFixed(1)} / 10
                    </span>
                  </div>
                  <p className="text-[#475569] leading-relaxed">
                    {inspection.judge_factors.completeness_summary}
                  </p>
                </div>

                {/* Potential Impact */}
                <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2">
                  <div className="flex items-center justify-between border-b border-[#F1F5F9] pb-2">
                    <span className="font-bold text-[#111827] uppercase tracking-wider text-[11px]">
                      Potential Impact & Utility
                    </span>
                    <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-purple-50 text-purple-700">
                      {inspection.judge_factors.potential_impact_score.toFixed(1)} / 10
                    </span>
                  </div>
                  <p className="text-[#475569] leading-relaxed">
                    {inspection.judge_factors.potential_impact_summary}
                  </p>
                </div>

                {/* Security */}
                <div className="p-4 rounded-xl bg-white border border-[#E2E8F0] space-y-2">
                  <div className="flex items-center justify-between border-b border-[#F1F5F9] pb-2">
                    <span className="font-bold text-[#111827] uppercase tracking-wider text-[11px]">
                      Security & Best Practices
                    </span>
                    <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-slate-100 text-slate-700">
                      Robustness
                    </span>
                  </div>
                  <p className="text-[#475569] leading-relaxed">
                    {inspection.judge_factors.security_summary}
                  </p>
                </div>
              </div>
            )}

            {/* Tab 6: Codebase Defects, Missing Implementations & Required Improvements (Block 6) */}
            {activeInspectTab === 'highlights' && (
              <div className="space-y-5 text-xs">
                {/* Block 6 Objective Audit Header Banner */}
                <div className="p-4 rounded-xl bg-gradient-to-r from-rose-50 via-amber-50 to-blue-50 border border-rose-200/80 space-y-2">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <div className="p-2 rounded-lg bg-rose-600 text-white shadow-xs">
                        <Bug className="w-4 h-4" />
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                          <span>Block 6: Codebase Defect & Improvement Audit</span>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-100 text-rose-700 border border-rose-300">
                            Negative Points Analysis
                          </span>
                        </h4>
                        <p className="text-[11px] text-slate-600">
                          Dedicated audit focused exclusively on finding defects, missing implementations, antipatterns, and required improvements from the repository.
                        </p>
                      </div>
                    </div>

                    {/* Summary Issue Badges */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="px-2.5 py-1 rounded-lg bg-rose-100 text-rose-800 font-bold text-[11px] border border-rose-200 flex items-center gap-1.5">
                        <Bug className="w-3 h-3 text-rose-600" />
                        <span>{(inspection.codebase_defects?.length || inspection.potential_red_flags?.length || 0)} Defects</span>
                      </span>
                      <span className="px-2.5 py-1 rounded-lg bg-amber-100 text-amber-800 font-bold text-[11px] border border-amber-200 flex items-center gap-1.5">
                        <AlertTriangle className="w-3 h-3 text-amber-600" />
                        <span>{(inspection.missing_implementations?.length || 0)} Missing</span>
                      </span>
                      <span className="px-2.5 py-1 rounded-lg bg-blue-100 text-blue-800 font-bold text-[11px] border border-blue-200 flex items-center gap-1.5">
                        <Wrench className="w-3 h-3 text-blue-600" />
                        <span>{(inspection.recommended_improvements?.length || 0)} Fixes</span>
                      </span>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* Column 1: Codebase Defects & Flaws */}
                  <div className="p-4 rounded-xl bg-rose-50/60 border border-rose-200 space-y-3">
                    <div className="flex items-center justify-between border-b border-rose-200/80 pb-2">
                      <span className="font-bold text-rose-900 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                        <Bug className="w-4 h-4 text-rose-600" />
                        <span>1. Code Defects & Bugs</span>
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-200/70 text-rose-800">
                        {(inspection.codebase_defects?.length || inspection.potential_red_flags?.length || 0)}
                      </span>
                    </div>
                    <p className="text-[11px] text-rose-800/80">
                      Bugs, flaws, antipatterns, and negative points detected in codebase files.
                    </p>
                    <div className="space-y-2">
                      {(inspection.codebase_defects && inspection.codebase_defects.length > 0
                        ? inspection.codebase_defects
                        : inspection.potential_red_flags
                      ).map((item, idx) => (
                        <div
                          key={idx}
                          className="p-3 rounded-lg bg-white border border-rose-200/90 shadow-2xs flex items-start gap-2.5 text-rose-950 font-medium"
                        >
                          <span className="w-5 h-5 rounded-full bg-rose-100 text-rose-700 flex items-center justify-center font-bold text-[10px] shrink-0 mt-0.5">
                            {idx + 1}
                          </span>
                          <span className="leading-relaxed">{item}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Column 2: Missing Implementations & Code Gaps */}
                  <div className="p-4 rounded-xl bg-amber-50/60 border border-amber-200 space-y-3">
                    <div className="flex items-center justify-between border-b border-amber-200/80 pb-2">
                      <span className="font-bold text-amber-900 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                        <AlertTriangle className="w-4 h-4 text-amber-600" />
                        <span>2. Missing Implementations</span>
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-200/70 text-amber-800">
                        {inspection.missing_implementations?.length || 0}
                      </span>
                    </div>
                    <p className="text-[11px] text-amber-800/80">
                      Unfinished features, stubbed functions, absent unit tests, or unhandled errors.
                    </p>
                    <div className="space-y-2">
                      {(inspection.missing_implementations && inspection.missing_implementations.length > 0 ? (
                        inspection.missing_implementations.map((item, idx) => (
                          <div
                            key={idx}
                            className="p-3 rounded-lg bg-white border border-amber-200/90 shadow-2xs flex items-start gap-2.5 text-amber-950 font-medium"
                          >
                            <span className="w-5 h-5 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center font-bold text-[10px] shrink-0 mt-0.5">
                              {idx + 1}
                            </span>
                            <span className="leading-relaxed">{item}</span>
                          </div>
                        ))
                      ) : (
                        <div className="p-3 rounded-lg bg-white border border-amber-200 text-amber-900">
                          No incomplete stubs or missing features detected.
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Column 3: Actionable Code Improvements */}
                  <div className="p-4 rounded-xl bg-blue-50/60 border border-blue-200 space-y-3">
                    <div className="flex items-center justify-between border-b border-blue-200/80 pb-2">
                      <span className="font-bold text-blue-900 uppercase tracking-wider text-[11px] flex items-center gap-1.5">
                        <Wrench className="w-4 h-4 text-blue-600" />
                        <span>3. Required Improvements</span>
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-200/70 text-blue-800">
                        {inspection.recommended_improvements?.length || 0}
                      </span>
                    </div>
                    <p className="text-[11px] text-blue-800/80">
                      Actionable technical recommendations to fix the identified defects.
                    </p>
                    <div className="space-y-2">
                      {(inspection.recommended_improvements && inspection.recommended_improvements.length > 0 ? (
                        inspection.recommended_improvements.map((item, idx) => (
                          <div
                            key={idx}
                            className="p-3 rounded-lg bg-white border border-blue-200/90 shadow-2xs flex items-start gap-2.5 text-blue-950 font-medium"
                          >
                            <span className="w-5 h-5 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center font-bold text-[10px] shrink-0 mt-0.5">
                              {idx + 1}
                            </span>
                            <span className="leading-relaxed">{item}</span>
                          </div>
                        ))
                      ) : (
                        <div className="p-3 rounded-lg bg-white border border-blue-200 text-blue-900">
                          Codebase adheres to baseline requirements.
                        </div>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Critical Judge Red Flag Verification */}
                {inspection.potential_red_flags && inspection.potential_red_flags.length > 0 && (
                  <div className="p-4 rounded-xl bg-slate-900 text-white space-y-3 border border-slate-800 shadow-sm">
                    <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                      <span className="font-bold uppercase tracking-wider text-[11px] text-rose-400 flex items-center gap-1.5">
                        <ShieldAlert className="w-4 h-4 text-rose-400" />
                        <span>Critical Risks & Negative Points for Judge Verification</span>
                      </span>
                      <span className="text-[10px] font-semibold text-slate-400">
                        Verify authenticity during live Q&A
                      </span>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 pt-1">
                      {inspection.potential_red_flags.map((flag, idx) => (
                        <div
                          key={idx}
                          className="p-3 rounded-lg bg-slate-800/90 border border-slate-700 flex items-start gap-2 text-slate-200 font-medium text-xs"
                        >
                          <AlertCircle className="w-3.5 h-3.5 text-rose-400 shrink-0 mt-0.5" />
                          <span>{flag}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Tab 7: Suggested Judge Pitch Questions */}
            {activeInspectTab === 'questions' && (
              <div className="space-y-3 text-xs">
                <div className="p-4 rounded-xl bg-blue-50 border border-blue-200 flex items-start gap-3">
                  <HelpCircle className="w-4 h-4 text-[#2563EB] shrink-0 mt-0.5" />
                  <p className="text-blue-900 leading-relaxed font-medium">
                    These questions are dynamically generated by Ollama based on the project's code architecture. Ask these during the live demo/presentation to evaluate how deeply the team understands their implementation.
                  </p>
                </div>

                <div className="space-y-2.5">
                  {inspection.suggested_judge_questions.map((question, idx) => (
                    <div
                      key={idx}
                      className="p-4 rounded-xl bg-white border border-[#E2E8F0] hover:border-blue-300 transition-colors flex items-start justify-between gap-3 group"
                    >
                      <div className="flex items-start gap-3">
                        <span className="w-6 h-6 rounded-full bg-blue-100 text-[#2563EB] flex items-center justify-center shrink-0 font-bold text-xs mt-0.5">
                          {idx + 1}
                        </span>
                        <p className="text-sm font-semibold text-[#111827] leading-relaxed">
                          {question}
                        </p>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleCopyQuestion(question, idx)}
                        className="px-2.5 py-1 text-xs font-semibold text-[#2563EB] bg-[#EFF6FF] hover:bg-blue-100 rounded-md transition-colors border border-[#BFDBFE] shrink-0 flex items-center gap-1"
                        title="Copy question text"
                      >
                        {copiedQuestionIndex === idx ? (
                          <>
                            <Check className="w-3 h-3 text-emerald-600" />
                            <span className="text-emerald-700">Copied</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3 h-3" />
                            <span>Copy</span>
                          </>
                        )}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ========================================================
          SECTION C.2: ADVISORY BATCH EVALUATION CITATIONS
      ======================================================== */}
      {reviewData.ai_evaluation && (
        <section className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-xs space-y-5">
          <div className="flex items-center justify-between border-b border-[#E2E8F0] pb-3">
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-[#2563EB]" />
              <h2 className="text-sm font-bold uppercase tracking-wider text-[#111827]">
                Rubric Grounded Code References & Explanations
              </h2>
            </div>
            {reviewData.ai_evaluation?.normalized_score !== undefined && (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-[#EFF6FF] border border-[#BFDBFE] text-xs font-bold text-[#2563EB]">
                Overall: {Number(reviewData.ai_evaluation.normalized_score).toFixed(1)} / 100
              </span>
            )}
          </div>

          {/* Overall AI Assessment */}
          {(reviewData.ai_evaluation.quick_summary || reviewData.ai_evaluation.summary_assessment) && (
            <div className="rounded-xl border border-blue-100 bg-blue-50/40 p-4 space-y-2">
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-blue-900">
                <Sparkles className="w-4 h-4 text-blue-600" />
                <span>Overall Project AI Assessment</span>
              </div>
              <DualExplanationView
                quickExplanation={reviewData.ai_evaluation.quick_summary}
                detailedExplanation={reviewData.ai_evaluation.detailed_summary}
                rawText={reviewData.ai_evaluation.summary_assessment}
              />
            </div>
          )}

          <div className="space-y-4">
            <h3 className="text-xs font-bold text-[#64748B] uppercase tracking-wider">
              Criterion-by-Criterion Evaluations
            </h3>
            {reviewData.ai_evaluation.criterion_scores?.map((cs) => (
              <div key={cs.id || cs.criterion_id} className="p-4 rounded-lg border border-[#E2E8F0] bg-white space-y-3">
                <div className="flex items-center justify-between border-b border-[#F1F5F9] pb-2">
                  <span className="font-bold text-xs text-[#111827]">{cs.title || 'Rubric Criterion'}</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-[#EFF6FF] text-[#2563EB]">
                    Suggested: {Number(cs.awarded_score).toFixed(1)} / 100
                  </span>
                </div>
                <DualExplanationView
                  quickExplanation={cs.quick_explanation}
                  detailedExplanation={cs.detailed_explanation}
                  rawText={cs.rationale}
                />
                {cs.evidence_references && cs.evidence_references.length > 0 && (
                  <div className="space-y-2 pt-2 border-t border-[#F1F5F9]">
                    {cs.evidence_references.map((ev, idx) => (
                      <div key={ev.id || idx} className="rounded-lg bg-[#0F172A] p-3 text-slate-200 font-mono text-[11px] space-y-1">
                        <div className="flex items-center justify-between text-slate-400 text-[10px]">
                          <span>{ev.file_path}</span>
                          {ev.is_verified_in_repo && <span className="text-emerald-400 font-semibold">✓ Verified</span>}
                        </div>
                        <pre className="overflow-x-auto whitespace-pre leading-relaxed text-slate-300">
                          <code>{ev.snippet}</code>
                        </pre>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ========================================================
          SECTION D: JUDGE SCORING FORM
      ======================================================== */}
      <section className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-xs space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#E2E8F0] pb-3">
          <div className="flex items-center gap-2">
            <Scale className="w-4 h-4 text-[#2563EB]" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-[#111827]">
              Section D: Rubric Scoring Form
            </h2>
          </div>

          {/* Live Total Score Pill */}
          <div className="flex items-center gap-3 bg-[#F8FAFC] px-4 py-2 rounded-lg border border-[#E2E8F0]">
            <span className="text-xs font-medium text-[#64748B]">
              Calculated Total:
            </span>
            <span className="text-lg font-bold text-[#111827]">
              {calculatedTotalScore.toFixed(1)}
              <span className="text-xs font-normal text-[#64748B]"> / 100</span>
            </span>
          </div>
        </div>

        {/* Rubric Criteria List */}
        <div className="space-y-6">
          {reviewData.rubric_criteria.map((crit, index) => {
            const min = Number(crit.min_score) || 0;
            const max = Number(crit.max_score) || 100;
            const weightPercent = Math.round(Number(crit.weight) * 100);
            const currentScore = criterionScores[crit.id]?.score ?? min;
            const currentNotes = criterionScores[crit.id]?.notes ?? '';

            return (
              <div
                key={crit.id}
                className="p-5 rounded-xl border border-[#E2E8F0] bg-[#F8FAFC] space-y-4"
              >
                {/* Header */}
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="w-5 h-5 rounded-full bg-[#2563EB] text-white flex items-center justify-center font-bold text-[10px]">
                        {index + 1}
                      </span>
                      <h3 className="text-sm font-bold text-[#111827]">
                        {crit.title}
                      </h3>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-[#EFF6FF] text-[#2563EB] border border-[#BFDBFE]">
                        Weight: {weightPercent}%
                      </span>
                    </div>
                    {crit.description && (
                      <p className="text-xs text-[#64748B] mt-1 pl-7">
                        {crit.description}
                      </p>
                    )}
                  </div>

                  {/* Numerical input */}
                  <div className="flex items-center gap-2 pl-7 sm:pl-0">
                    <span className="text-xs text-[#64748B] font-medium">Score:</span>
                    <input
                      type="number"
                      min={min}
                      max={max}
                      step={1}
                      disabled={isSubmitted}
                      value={currentScore}
                      onChange={(e) => {
                        const val = Math.min(
                          max,
                          Math.max(min, Number(e.target.value) || 0)
                        );
                        handleScoreChange(crit.id, val);
                      }}
                      className="w-20 px-3 py-1.5 text-center font-bold text-sm text-[#111827] bg-white border border-[#CBD5E1] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#2563EB] disabled:bg-slate-100 disabled:text-slate-600 transition-colors"
                    />
                    <span className="text-xs text-[#64748B]">/ {max}</span>
                  </div>
                </div>

                {/* Score Slider */}
                <div className="pl-7 pr-2">
                  <input
                    type="range"
                    min={min}
                    max={max}
                    step={1}
                    disabled={isSubmitted}
                    value={currentScore}
                    onChange={(e) =>
                      handleScoreChange(crit.id, Number(e.target.value))
                    }
                    className="w-full accent-[#2563EB] cursor-pointer disabled:cursor-not-allowed"
                  />
                  <div className="flex justify-between text-[10px] text-[#94A3B8] mt-1 font-mono">
                    <span>{min} (Minimum)</span>
                    <span>{Math.round((min + max) / 2)}</span>
                    <span>{max} (Outstanding)</span>
                  </div>
                </div>

                {/* Criterion Notes */}
                <div className="pl-7 space-y-1">
                  <label className="text-xs font-semibold text-[#64748B] block">
                    Criterion Notes (Optional)
                  </label>
                  <textarea
                    rows={2}
                    disabled={isSubmitted}
                    value={currentNotes}
                    onChange={(e) => handleNotesChange(crit.id, e.target.value)}
                    placeholder={`Notes on ${crit.title.toLowerCase()} implementation, architecture, or edge cases...`}
                    className="w-full px-3 py-2 text-xs text-[#111827] bg-white border border-[#CBD5E1] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#2563EB] disabled:bg-slate-100 disabled:text-slate-600 placeholder-[#94A3B8] transition-colors resize-y"
                  />
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ========================================================
          SECTION E: WRITTEN FEEDBACK
      ======================================================== */}
      <section className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-xs space-y-5">
        <div className="flex items-center gap-2 border-b border-[#E2E8F0] pb-3">
          <FileText className="w-4 h-4 text-[#2563EB]" />
          <h2 className="text-sm font-bold uppercase tracking-wider text-[#111827]">
            Section E: Written Feedback & Recommendation
          </h2>
        </div>

        <div className="space-y-4">
          {/* Decision recommendation */}
          <div className="space-y-1.5 max-w-xs">
            <label className="text-xs font-bold text-[#111827] block">
              Recommendation Decision:
            </label>
            <select
              disabled={isSubmitted}
              value={decision}
              onChange={(e) => setDecision(e.target.value)}
              className="w-full px-3 py-2 text-xs font-semibold text-[#111827] bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#2563EB] disabled:bg-slate-100 disabled:text-slate-600 transition-colors"
            >
              <option value="accepted">Accepted / Recommend for Award</option>
              <option value="adjusted">Adjusted / Qualified</option>
              <option value="rejected">Rejected / Needs Major Rework</option>
            </select>
          </div>

          {/* Overall feedback textarea */}
          <div className="space-y-1.5">
            <label className="text-xs font-bold text-[#111827] block">
              Overall Constructive Feedback{' '}
              <span className="text-red-500 font-normal">
                (Mandatory for final submission)
              </span>
            </label>
            <textarea
              rows={5}
              disabled={isSubmitted}
              value={overallFeedback}
              onChange={(e) => setOverallFeedback(e.target.value)}
              placeholder="Provide constructive feedback for the team. Detail key strengths, innovative aspects, architecture soundness, and recommendations for future iterations..."
              className="w-full px-4 py-3 text-xs text-[#111827] bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#2563EB] focus:bg-white disabled:bg-slate-100 disabled:text-slate-600 placeholder-[#94A3B8] transition-colors resize-y leading-relaxed"
            />
            <p className="text-[11px] text-[#64748B]">
              This feedback will be accessible to event organizers and may be shared with the team following the judging period.
            </p>
          </div>
        </div>
      </section>

      {/* ========================================================
          SECTION F: ACTIONS
      ======================================================== */}
      <section className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <span className="text-xs font-semibold text-[#64748B] block">
            Weighted Total Score:
          </span>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-[#111827]">
              {calculatedTotalScore.toFixed(1)}
            </span>
            <span className="text-xs text-[#64748B]">out of 100 points</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Link
            href="/judge/projects"
            className="px-4 py-2.5 text-xs font-semibold text-[#64748B] hover:text-[#111827] hover:bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg transition-colors"
          >
            Cancel / Back
          </Link>

          {isSubmitted && (
            <button
              type="button"
              onClick={() => {
                setRevertTargetStatus('draft');
                setRevertReason('');
                setIsRevertModalOpen(true);
              }}
              className="inline-flex items-center gap-2 px-4 py-2.5 text-xs font-semibold text-[#1E40AF] bg-[#EFF6FF] border border-[#BFDBFE] hover:bg-[#DBEAFE] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#2563EB] transition-colors shadow-xs"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reopen for Re-evaluation</span>
            </button>
          )}

          {!isSubmitted && (
            <>
              <button
                type="button"
                onClick={handleSaveDraft}
                disabled={isSavingDraft || isSubmitting}
                className="inline-flex items-center gap-2 px-4 py-2.5 text-xs font-semibold text-[#2563EB] bg-[#EFF6FF] border border-[#BFDBFE] hover:bg-blue-100 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#2563EB] disabled:opacity-50 transition-colors shadow-xs"
              >
                <Save className="w-3.5 h-3.5" />
                <span>{isSavingDraft ? 'Saving Draft...' : 'Save Draft'}</span>
              </button>

              <button
                type="button"
                onClick={() => setIsConfirmModalOpen(true)}
                disabled={isSavingDraft || isSubmitting}
                className="inline-flex items-center gap-2 px-5 py-2.5 text-xs font-semibold text-white bg-[#2563EB] hover:bg-blue-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[#2563EB] disabled:opacity-50 transition-colors shadow-xs"
              >
                <Send className="w-3.5 h-3.5" />
                <span>Submit Final Review</span>
              </button>
            </>
          )}
        </div>
      </section>

      {/* ========================================================
          CONFIRMATION MODAL FOR FINAL SUBMISSION
      ======================================================== */}
      {isConfirmModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <div className="bg-white border border-[#E2E8F0] rounded-xl max-w-md w-full p-6 shadow-xl space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-blue-50 border border-blue-200 flex items-center justify-center text-[#2563EB]">
                <Scale className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-[#111827]">
                  Confirm Final Review Submission
                </h3>
                <p className="text-xs text-[#64748B]">
                  Project: {reviewData.submission_title}
                </p>
              </div>
            </div>

            <div className="p-4 rounded-lg bg-[#F8FAFC] border border-[#E2E8F0] space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-[#64748B]">Awarded Score:</span>
                <span className="font-bold text-[#111827]">{calculatedTotalScore.toFixed(1)} / 100</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#64748B]">Recommendation:</span>
                <span className="font-semibold capitalize text-[#111827]">{decision}</span>
              </div>
              <div className="pt-2 border-t border-[#E2E8F0] text-[#D97706] font-medium leading-relaxed">
                Notice: Submitting this review publishes your scores to the event leaderboard. You can reopen it later for re-evaluation if further review is required.
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setIsConfirmModalOpen(false)}
                disabled={isSubmitting}
                className="px-4 py-2 text-xs font-semibold text-[#64748B] hover:text-[#111827] rounded-lg border border-[#E2E8F0] hover:bg-[#F8FAFC] transition-colors"
              >
                Go Back
              </button>
              <button
                type="button"
                onClick={handleSubmitFinal}
                disabled={isSubmitting}
                className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-[#2563EB] hover:bg-blue-700 rounded-lg transition-colors shadow-xs"
              >
                {isSubmitting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Submitting...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Confirm & Submit</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================
          CONFIRMATION MODAL FOR REVERTING / RE-EVALUATION
      ======================================================== */}
      {isRevertModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs">
          <div className="bg-white border border-[#E2E8F0] rounded-xl max-w-lg w-full p-6 shadow-xl space-y-5">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-full bg-blue-50 border border-blue-200 flex items-center justify-center text-[#2563EB]">
                <RotateCcw className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-[#111827]">
                  Revert Review / Re-evaluation
                </h3>
                <p className="text-xs text-[#64748B]">
                  Project: {reviewData.submission_title}
                </p>
              </div>
            </div>

            <div className="p-3.5 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-900 leading-relaxed">
              <strong>Notice:</strong> This review is currently marked as <strong>Completed</strong> and counted in leaderboard scores. Reverting will change its status and allow you to re-evaluate or start fresh.
            </div>

            {/* Target Selection */}
            <div className="space-y-3">
              <label className="text-xs font-bold text-[#111827] block">
                Choose Reversion Action:
              </label>

              <label
                className={`flex items-start gap-3 p-3.5 rounded-lg border cursor-pointer transition-all ${
                  revertTargetStatus === 'draft'
                    ? 'border-[#2563EB] bg-[#EFF6FF]'
                    : 'border-[#CBD5E1] bg-white hover:bg-[#F8FAFC]'
                }`}
              >
                <input
                  type="radio"
                  name="revertTarget"
                  value="draft"
                  checked={revertTargetStatus === 'draft'}
                  onChange={() => setRevertTargetStatus('draft')}
                  className="mt-0.5 accent-[#2563EB]"
                />
                <div className="text-xs space-y-1">
                  <span className="font-bold text-[#111827] block">
                    Reopen for Re-evaluation (Revert to Draft)
                  </span>
                  <p className="text-[#64748B] leading-relaxed">
                    Unlocks the evaluation form while preserving your entered criterion scores and comments. You can review the project, adjust scores, and submit a revised evaluation.
                  </p>
                </div>
              </label>

              <label
                className={`flex items-start gap-3 p-3.5 rounded-lg border cursor-pointer transition-all ${
                  revertTargetStatus === 'awaiting'
                    ? 'border-[#2563EB] bg-[#EFF6FF]'
                    : 'border-[#CBD5E1] bg-white hover:bg-[#F8FAFC]'
                }`}
              >
                <input
                  type="radio"
                  name="revertTarget"
                  value="awaiting"
                  checked={revertTargetStatus === 'awaiting'}
                  onChange={() => setRevertTargetStatus('awaiting')}
                  className="mt-0.5 accent-[#2563EB]"
                />
                <div className="text-xs space-y-1">
                  <span className="font-bold text-[#111827] block">
                    Reset to Awaiting Review (Complete Reset)
                  </span>
                  <p className="text-[#64748B] leading-relaxed">
                    Completely resets your evaluation for this submission. Clears entered scores and moves the project back to &quot;Awaiting Review&quot; in your judging queue.
                  </p>
                </div>
              </label>
            </div>

            {/* Reason input */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-[#111827] block">
                Reason / Rationale (Recorded in Audit Trail):
              </label>
              <textarea
                rows={2}
                value={revertReason}
                onChange={(e) => setRevertReason(e.target.value)}
                placeholder="Optional explanation for audit logging (e.g., reviewed team demo, revising score, etc.)..."
                className="w-full px-3 py-2 text-xs text-[#111827] bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg focus:outline-none focus:ring-2 focus:ring-[#2563EB] placeholder-[#94A3B8] transition-colors resize-y"
              />
            </div>

            <div className="flex items-center justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setIsRevertModalOpen(false)}
                disabled={isReverting}
                className="px-4 py-2 text-xs font-semibold text-[#64748B] hover:text-[#111827] rounded-lg border border-[#E2E8F0] hover:bg-[#F8FAFC] transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleRevertReview}
                disabled={isReverting}
                className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-[#2563EB] hover:bg-blue-700 rounded-lg transition-colors shadow-xs disabled:opacity-50"
              >
                {isReverting ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Reverting...</span>
                  </>
                ) : (
                  <>
                    <RotateCcw className="w-3.5 h-3.5" />
                    <span>
                      {revertTargetStatus === 'draft'
                        ? 'Confirm Reopen for Re-evaluation'
                        : 'Confirm Reset to Awaiting'}
                    </span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
