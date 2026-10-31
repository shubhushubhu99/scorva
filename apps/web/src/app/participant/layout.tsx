'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { ParticipantSidebar } from '@/components/participant/ParticipantSidebar';
import { ParticipantHeader } from '@/components/participant/ParticipantHeader';
import { UnskippableRegistrationModal } from '@/components/participant/UnskippableRegistrationModal';
import { api, ApiClientError } from '@/lib/api-client';
import { RegistrationStatusResponse, ParticipantTeamItem } from '@/types/api';
import { Loader2, Lock, AlertCircle, ArrowRight, ShieldAlert } from 'lucide-react';

export default function ParticipantLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [regStatus, setRegStatus] = useState<RegistrationStatusResponse | null>(null);
  const [isCheckingReg, setIsCheckingReg] = useState(true);
  const [teams, setTeams] = useState<ParticipantTeamItem[]>([]);
  const [isCheckingTeams, setIsCheckingTeams] = useState(true);

  // Team Access Code Gate State
  const [gateCode, setGateCode] = useState('');
  const [isVerifyingGate, setIsVerifyingGate] = useState(false);
  const [gateError, setGateError] = useState<string | null>(null);

  const refreshNotificationCount = useCallback(async () => {
    try {
      const data = await api.getParticipantNotifications();
      setUnreadCount(data.unread_count);
    } catch {
      // Non-blocking
    }
  }, []);

  const checkTeamsAndRegistration = useCallback(async () => {
    setIsCheckingReg(true);
    setIsCheckingTeams(true);
    try {
      const [statusData, teamsData] = await Promise.all([
        api.getParticipantRegistrationStatus(),
        api.getParticipantTeams(),
      ]);
      setRegStatus(statusData);
      setTeams(teamsData);
    } catch (err) {
      console.error('Failed to load participant status or teams', err);
    } finally {
      setIsCheckingReg(false);
      setIsCheckingTeams(false);
    }
  }, []);

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login?redirect=/participant');
    } else if (user) {
      refreshNotificationCount();
      checkTeamsAndRegistration();
    }
  }, [user, isLoading, router, refreshNotificationCount, checkTeamsAndRegistration]);

  const handleVerifyGateCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!gateCode.trim()) return;
    setGateError(null);
    setIsVerifyingGate(true);
    try {
      await api.verifyParticipantJoinCode(gateCode.trim());
      setGateCode('');
      await checkTeamsAndRegistration();
      refreshNotificationCount();
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setGateError(err.message);
      } else {
        setGateError('Invalid team code. Access to event dashboard denied. Please contact your hackathon organizer.');
      }
    } finally {
      setIsVerifyingGate(false);
    }
  };

  if (isLoading || !user || isCheckingReg || isCheckingTeams) {
    return (
      <div className="min-h-screen bg-[#F8FAFC] flex flex-col items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-8 h-8 text-[#2563EB] animate-spin" />
          <p className="text-xs font-medium text-[#64748B]">
            Loading Participant Workspace...
          </p>
        </div>
      </div>
    );
  }

  // Access Gate: If participant has not entered a valid code or joined a team
  if (teams.length === 0) {
    return (
      <div className="min-h-screen bg-[#0D1A2B] flex flex-col items-center justify-center p-4 relative overflow-hidden">
        {/* Subtle background glow */}
        <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-96 h-96 bg-[#2563EB]/10 rounded-full blur-3xl pointer-events-none" />

        <div className="bg-white border border-[#E2E8F0] rounded-2xl w-full max-w-md shadow-2xl p-6 sm:p-8 space-y-6 relative z-10 animate-in fade-in zoom-in-95 duration-200">
          <div className="text-center space-y-2">
            <div className="w-14 h-14 rounded-2xl bg-[#EFF6FF] border border-[#BFDBFE] flex items-center justify-center mx-auto text-[#2563EB] shadow-xs">
              <Lock className="w-7 h-7" />
            </div>
            <h2 className="text-xl font-bold text-[#111827]">
              Enter Event Team Code
            </h2>
            <p className="text-xs text-[#64748B] leading-relaxed">
              Access to this participant dashboard is restricted. Enter the team join code provided by your event organizer to unlock your hackathon workspace.
            </p>
          </div>

          {gateError && (
            <div className="p-3.5 bg-red-50 border border-red-200 rounded-xl flex items-start gap-2.5 text-xs text-red-600 animate-in fade-in duration-150">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <div className="space-y-0.5">
                <span className="font-semibold block">Access Denied</span>
                <span>{gateError}</span>
              </div>
            </div>
          )}

          <form onSubmit={handleVerifyGateCode} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-[#475569] mb-1.5">
                Team Access / Join Code <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                required
                placeholder="e.g. 4B7B5F8A9C12"
                value={gateCode}
                onChange={(e) => setGateCode(e.target.value.toUpperCase())}
                className="w-full px-4 py-2.5 text-sm font-mono uppercase bg-[#F8FAFC] border border-[#CBD5E1] rounded-xl text-[#111827] focus:outline-none focus:border-[#2563EB] tracking-widest text-center placeholder:tracking-normal placeholder:font-sans placeholder:text-xs"
              />
            </div>

            <button
              type="submit"
              disabled={isVerifyingGate || !gateCode.trim()}
              className="w-full py-2.5 px-4 bg-[#2563EB] hover:bg-[#1D4ED8] disabled:opacity-50 text-white rounded-xl text-xs font-semibold transition-colors flex items-center justify-center gap-2 shadow-sm"
            >
              {isVerifyingGate ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Verifying Code...</span>
                </>
              ) : (
                <>
                  <span>Verify Code & Unlock Dashboard</span>
                  <ArrowRight className="w-4 h-4" />
                </>
              )}
            </button>
          </form>

          <div className="pt-4 border-t border-[#E2E8F0] flex items-center justify-between text-xs text-[#64748B]">
            <span>Need help? Contact organizer</span>
            <button
              type="button"
              onClick={() => {
                api.logout().then(() => router.push('/login'));
              }}
              className="text-[#2563EB] hover:underline font-medium"
            >
              Sign Out
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-[#F8FAFC] text-[#111827] overflow-hidden relative">
      {/* Unskippable Mandatory Onboarding Intake Modal */}
      {regStatus && !regStatus.is_registered && (
        <UnskippableRegistrationModal
          statusData={regStatus}
          onSuccess={() => {
            checkTeamsAndRegistration();
            refreshNotificationCount();
          }}
        />
      )}

      {/* Desktop Sidebar */}
      <div className="hidden md:flex md:w-64 md:shrink-0 h-full">
        <ParticipantSidebar unreadNotificationsCount={unreadCount} />
      </div>

      {/* Mobile Sidebar Overlay Drawer */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-40 md:hidden flex">
          <div
            className="fixed inset-0 bg-black/50 backdrop-blur-xs transition-opacity"
            onClick={() => setMobileMenuOpen(false)}
            aria-hidden="true"
          />
          <div className="relative flex-1 flex flex-col max-w-xs w-full bg-white z-40">
            <ParticipantSidebar
              onCloseMobile={() => setMobileMenuOpen(false)}
              unreadNotificationsCount={unreadCount}
            />
          </div>
        </div>
      )}

      {/* Main Content Column */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <ParticipantHeader
          onOpenMobileMenu={() => setMobileMenuOpen(true)}
          unreadNotificationsCount={unreadCount}
        />
        <main className="flex-1 overflow-y-auto bg-[#F8FAFC]">
          <div className="max-w-7xl mx-auto px-4 sm:px-8 py-7 md:py-8">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
