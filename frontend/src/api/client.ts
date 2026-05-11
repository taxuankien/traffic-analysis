import { API_BASE } from '../lib/constants';

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string | Record<string, unknown>,
  ) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail));
    this.name = 'ApiError';
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: string | Record<string, unknown>;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      detail = res.statusText;
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  return handleResponse<T>(res);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handleResponse<T>(res);
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return handleResponse<T>(res);
}

export async function apiDelete(path: string): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { method: 'DELETE' });
  return handleResponse<void>(res);
}

export function uploadFile(
  path: string,
  formData: FormData,
  onProgress?: (pct: number) => void,
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}${path}`);
    xhr.timeout = 30 * 60 * 1000; // 30 min for large videos
    if (onProgress) {
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) onProgress((e.loaded / e.total) * 100);
      });
    }
    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try {
          const body = JSON.parse(xhr.responseText);
          reject(new ApiError(xhr.status, body.detail ?? body));
        } catch {
          reject(new ApiError(xhr.status, xhr.statusText || 'Upload thất bại'));
        }
      }
    });
    xhr.addEventListener('error', () =>
      reject(new Error('Lỗi mạng — không thể kết nối tới server. Kiểm tra backend đang chạy.')),
    );
    xhr.addEventListener('timeout', () =>
      reject(new Error('Upload quá thời gian chờ (timeout 30 phút).')),
    );
    xhr.addEventListener('abort', () =>
      reject(new Error('Upload đã bị huỷ.')),
    );
    xhr.send(formData);
  });
}
