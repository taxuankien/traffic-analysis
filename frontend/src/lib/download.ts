/**
 * Programmatic file download by clicking a temporary `<a>` tag pointing
 * directly at the server URL.
 *
 * The backend already sets `Content-Disposition: attachment; filename="..."`
 * so the browser natively uses the correct filename + extension.
 *
 * We do NOT use fetch + Blob + ObjectURL because some browsers ignore
 * the `download` attribute on blob URLs and save with the UUID instead.
 */
export function triggerDownload(url: string, _filename?: string): void {
  const a = document.createElement('a');
  a.href = url;
  // Setting `download` helps signal the browser to download (not navigate).
  // The server's Content-Disposition header provides the actual filename.
  if (_filename) {
    a.download = _filename;
  } else {
    a.download = '';
  }
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  // Cleanup
  requestAnimationFrame(() => {
    document.body.removeChild(a);
  });
}
