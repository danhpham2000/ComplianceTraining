"use client";

import { useCallback, useEffect, useRef } from "react";
import { CirclePlay, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";

type WatchProgressPayload = {
  startSecond: number;
  endSecond: number;
  currentPositionSeconds: number;
  durationSeconds: number;
};

type CourseVideoPlayerProps = {
  url?: string | null;
  title: string;
  fallbackLabel?: string;
  onWatchProgress?: (payload: WatchProgressPayload) => void;
  onVideoComplete?: () => void;
};

export function CourseVideoPlayer({
  url,
  title,
  fallbackLabel = "Open lesson video",
  onWatchProgress,
  onVideoComplete,
}: CourseVideoPlayerProps) {
  const nativeVideoRef = useRef<HTMLVideoElement | null>(null);
  const trackingIntervalRef = useRef<number | null>(null);
  const lastObservedTimeRef = useRef<number | null>(null);
  const segmentStartRef = useRef<number | null>(null);
  const onWatchProgressRef = useRef(onWatchProgress);
  const onVideoCompleteRef = useRef(onVideoComplete);

  useEffect(() => {
    onWatchProgressRef.current = onWatchProgress;
  }, [onWatchProgress]);

  useEffect(() => {
    onVideoCompleteRef.current = onVideoComplete;
  }, [onVideoComplete]);

  const stopTracking = useCallback(() => {
    if (trackingIntervalRef.current !== null) {
      window.clearInterval(trackingIntervalRef.current);
      trackingIntervalRef.current = null;
    }
  }, []);

  const flushSegment = useCallback((forceCurrent?: number) => {
    const player = nativeVideoRef.current;
    const onProgress = onWatchProgressRef.current;
    if (!player || !onProgress) {
      return;
    }

    const current = forceCurrent ?? Math.floor(player.currentTime ?? 0);
    const start = segmentStartRef.current;
    const end = Math.max(lastObservedTimeRef.current ?? current, current);
    if (start === null || end <= start) {
      segmentStartRef.current = current;
      lastObservedTimeRef.current = current;
      return;
    }

    onProgress({
      startSecond: start,
      endSecond: end,
      currentPositionSeconds: current,
      durationSeconds: Math.floor(player.duration ?? 0),
    });
    segmentStartRef.current = current;
    lastObservedTimeRef.current = current;
  }, []);

  const sampleProgress = useCallback(() => {
    const player = nativeVideoRef.current;
    if (!player) {
      return;
    }

    const current = Math.floor(player.currentTime ?? 0);
    const previous = lastObservedTimeRef.current;

    if (previous === null) {
      lastObservedTimeRef.current = current;
      segmentStartRef.current = current;
      return;
    }

    const delta = current - previous;
    if (delta >= 0 && delta <= 3) {
      lastObservedTimeRef.current = current;
      if (segmentStartRef.current === null) {
        segmentStartRef.current = current;
      }
      if (current - segmentStartRef.current >= 10) {
        flushSegment(current);
      }
      return;
    }

    flushSegment(previous);
    segmentStartRef.current = current;
    lastObservedTimeRef.current = current;
  }, [flushSegment]);

  const beginTracking = useCallback(() => {
    stopTracking();
    trackingIntervalRef.current = window.setInterval(sampleProgress, 2000);
  }, [sampleProgress, stopTracking]);

  useEffect(() => {
    return () => {
      stopTracking();
      lastObservedTimeRef.current = null;
      segmentStartRef.current = null;
    };
  }, [stopTracking]);

  if (!url || !isVideoUrl(url)) {
    return (
      <VideoFallback
        title="Embedded preview unavailable"
        body="Attach a valid lesson source to keep the training inside the workspace."
      />
    );
  }

  return (
    <div className="course-player-shell">
      <div className="course-player-frame">
        <video
          ref={nativeVideoRef}
          className="h-full w-full bg-black object-contain"
          controls
          preload="metadata"
          playsInline
          onPlay={beginTracking}
          onPause={() => {
            stopTracking();
            flushSegment();
          }}
          onEnded={() => {
            stopTracking();
            const duration = Math.floor(nativeVideoRef.current?.duration ?? 0);
            flushSegment(duration || undefined);
            onVideoCompleteRef.current?.();
          }}
        >
          <source src={url} />
        </video>
      </div>

      <div className="course-player-footer">
        <div>
          <p className="course-player-title">{title}</p>
          <p className="course-player-caption">Embedded lesson view</p>
        </div>

        <Button
          asChild
          variant="outline"
          className="h-10 rounded-full border-border bg-white px-4 text-[#5b6f8c] shadow-none hover:bg-[#f7f9fc] hover:text-foreground"
        >
          <a href={url} target="_blank" rel="noreferrer">
            <ExternalLink className="size-4" />
            {fallbackLabel}
          </a>
        </Button>
      </div>
    </div>
  );
}

function VideoFallback({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex h-full min-h-[420px] items-center justify-center bg-[#f6f8fc] px-10 text-center">
      <div>
        <CirclePlay className="mx-auto size-12 text-[#f38820]" />
        <p className="mt-4 text-base font-medium text-foreground">{title}</p>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{body}</p>
      </div>
    </div>
  );
}

function isVideoUrl(url?: string | null) {
  if (!url) {
    return false;
  }
  try {
    const parsed = new URL(url, "http://localhost");
    return /\.(mp4|webm|ogg|mov)$/i.test(parsed.pathname);
  } catch {
    return false;
  }
}
