/** Compress an image File to a JPEG data URL (max edge px, quality). */
export async function compressImageFile(
  file: File,
  maxEdge = 1280,
  quality = 0.72
): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxEdge / Math.max(bitmap.width, bitmap.height));
  const w = Math.max(1, Math.round(bitmap.width * scale));
  const h = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Could not process image.");
  ctx.drawImage(bitmap, 0, 0, w, h);
  bitmap.close();
  return canvas.toDataURL("image/jpeg", quality);
}

export async function filesToWorkPhotos(
  files: FileList | File[],
  existing: string[],
  max = 6
): Promise<string[]> {
  const next = [...existing];
  for (const file of Array.from(files)) {
    if (next.length >= max) break;
    if (!file.type.startsWith("image/")) continue;
    next.push(await compressImageFile(file, 1280, 0.7));
  }
  return next.slice(0, max);
}

/** Fit logo to a header-friendly JPEG data URL. */
export async function compressLogoFile(file: File): Promise<string> {
  return compressImageFile(file, 800, 0.82);
}
