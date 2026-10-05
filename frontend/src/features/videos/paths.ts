/** Detail page path for a video, keeping the current filter query string. */
export function videoPath(videoId: string, search = ''): string {
  return `/videos/${encodeURIComponent(videoId)}${search}`;
}
