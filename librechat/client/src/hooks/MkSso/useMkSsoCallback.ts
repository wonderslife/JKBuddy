import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { request, apiBaseUrl } from 'librechat-data-provider';
import type { TLoginResponse } from 'librechat-data-provider';

export interface UseMkSsoCallbackOptions {
  enabled?: boolean;
}

export interface UseMkSsoCallbackResult {
  isLoading: boolean;
  error: string | null;
}

const MK_CODE_PARAM = 'mkCode';

async function mkSsoCallback(mkCode: string): Promise<TLoginResponse> {
  const url = `${apiBaseUrl()}/api/auth/mk-sso/callback`;
  const response = await request.post(url, { mkCode });
  return response as TLoginResponse;
}

function clearMkCodeFromUrl(): void {
  const url = new URL(window.location.href);
  url.searchParams.delete(MK_CODE_PARAM);
  window.history.replaceState({}, '', url.toString());
}

export default function useMkSsoCallback(
  options: UseMkSsoCallbackOptions = {},
): UseMkSsoCallbackResult {
  const { enabled = true } = options;
  const navigate = useNavigate();
  const isLoadingRef = useRef(false);
  const errorRef = useRef<string | null>(null);
  const hasProcessedRef = useRef(false);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const searchParams = new URLSearchParams(window.location.search);
    const mkCode = searchParams.get(MK_CODE_PARAM);

    if (!mkCode || hasProcessedRef.current) {
      return;
    }

    hasProcessedRef.current = true;
    isLoadingRef.current = true;

    mkSsoCallback(mkCode)
      .then((data) => {
        if (data.token) {
          request.dispatchTokenUpdatedEvent(data.token);
          clearMkCodeFromUrl();
          navigate('/c/new', { replace: true });
        } else {
          throw new Error('SSO登录失败：未返回token');
        }
      })
      .catch((error) => {
        errorRef.current = error instanceof Error ? error.message : 'SSO登录失败';
        navigate('/login?error=sso_failed', { replace: true });
      })
      .finally(() => {
        isLoadingRef.current = false;
      });
  }, [enabled, navigate]);

  return {
    isLoading: isLoadingRef.current,
    error: errorRef.current,
  };
}