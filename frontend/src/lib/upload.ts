import { ApiError, getAccessToken } from "@/lib/api";
import { images } from "@/lib/resources";

const CHUNK_SIZE = 8 * 1024 * 1024; // 8 MB, matches the read block size the backend streams with

export interface UploadProgress {
  sentBytes: number;
  totalBytes: number;
}

/**
 * Drives the chunked upload protocol in apps/images/views.py: initiate ->
 * PUT each chunk (raw body, DRF's FileUploadParser needs a
 * Content-Disposition filename since the URL carries no filename kwarg)
 * -> finalize. The whole file is only ever held in memory one 8MB slice
 * at a time via File.slice(), matching the backend's own "never load a
 * multi-gigabyte image into memory" rule on the client side too.
 */
export async function uploadImage(
  file: File,
  meta: { name: string; version?: string; type: string; format?: string; storage: string },
  onProgress?: (progress: UploadProgress) => void,
) {
  const session = await images.initiateUpload({ ...meta, total_size_bytes: file.size });
  const sessionUuid = session.uuid;

  let offset = 0;
  let index = 0;
  while (offset < file.size) {
    const chunk = file.slice(offset, offset + CHUNK_SIZE);
    await putChunk(sessionUuid, index, chunk);
    offset += chunk.size;
    index += 1;
    onProgress?.({ sentBytes: offset, totalBytes: file.size });
  }

  return images.finalizeUpload(sessionUuid);
}

async function putChunk(sessionUuid: string, index: number, chunk: Blob): Promise<void> {
  const token = getAccessToken();
  const response = await fetch(`/api/v1/images/uploads/${sessionUuid}/chunk/?index=${index}`, {
    method: "PUT",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      "Content-Disposition": "attachment; filename=chunk",
      "Content-Type": "application/octet-stream",
    },
    body: chunk,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, body?.error?.code ?? "UPLOAD_FAILED", body?.error?.message ?? "Chunk upload failed", body?.error?.details ?? {});
  }
}
