import { useEffect, useRef, useState, useCallback } from 'react';
import { AlgoPilotEvent } from '../types/events';

type WSStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

interface UseWebSocketOptions {
  enabled?: boolean;
  runId: string | null;
  onEvent?: (event: AlgoPilotEvent) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: () => void;
}

export function useWebSocket({
  runId,
  enabled = true,
  onEvent,
  onOpen,
  onClose,
  onError,
}: UseWebSocketOptions) {
  const [status, setStatus] = useState<WSStatus>('disconnected');
  const wsRef = useRef<WebSocket | null>(null);
  const onEventRef = useRef(onEvent);
  const onOpenRef = useRef(onOpen);
  const onCloseRef = useRef(onClose);
  const onErrorRef = useRef(onError);
  onEventRef.current = onEvent;
  onOpenRef.current = onOpen;
  onCloseRef.current = onClose;
  onErrorRef.current = onError;

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    setStatus('disconnected');
  }, []);

  useEffect(() => {
    if (!runId || !enabled) {
      disconnect();
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/live/${runId}`;
    setStatus('connecting');

    const ws = new WebSocket(url);
    wsRef.current = ws;
    let active = true;

    ws.onopen = () => {
      if (!active || wsRef.current !== ws) {
        return;
      }
      setStatus('connected');
      onOpenRef.current?.();
    };

    ws.onmessage = (msg) => {
      if (!active || wsRef.current !== ws) {
        return;
      }
      try {
        const raw = JSON.parse(msg.data);
        const event: AlgoPilotEvent = raw.event
          ? { ...raw.event, seq: raw.seq, ts: raw.timestamp }
          : raw;
        onEventRef.current?.(event);
      } catch {
        // ignore malformed messages
      }
    };

    ws.onerror = () => {
      if (!active || wsRef.current !== ws) {
        return;
      }
      setStatus('error');
      onErrorRef.current?.();
    };

    ws.onclose = () => {
      if (!active || wsRef.current !== ws) {
        return;
      }
      setStatus('disconnected');
      wsRef.current = null;
      onCloseRef.current?.();
    };

    return () => {
      active = false;
      ws.onopen = null;
      ws.onmessage = null;
      ws.onerror = null;
      ws.onclose = null;
      ws.close();
      if (wsRef.current === ws) {
        wsRef.current = null;
      }
    };
  }, [enabled, runId, disconnect]);

  return { status, disconnect };
}
